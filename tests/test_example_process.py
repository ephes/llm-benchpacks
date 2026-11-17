"""Deterministic process ownership faults; no delegate or OS group signals."""
import io
import signal
import sys

import pytest
import psutil

from benchpack import example_process as transport

SIGNAL_GROUP = transport._signal_group


class Pipe(io.BytesIO):
    def fileno(self):
        return 100


class Child:
    pid = 12345
    returncode = 0

    def __init__(self):
        self.stdin = Pipe()
        self.stdout = Pipe()
        self.stderr = Pipe()
        self.waits = []

    def wait(self, *, timeout):
        self.waits.append(timeout)
        return self.returncode


@pytest.fixture
def owned(monkeypatch):
    child = Child()
    signals = []
    previous = {number: signal.SIG_DFL for number in
                (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)}
    handlers = previous.copy()

    def install(number, handler):
        old = handlers[number]
        handlers[number] = handler
        return old

    monkeypatch.setattr(transport.signal, 'getsignal', handlers.__getitem__)
    monkeypatch.setattr(transport.signal, 'signal', install)
    monkeypatch.setattr(transport.subprocess, 'Popen', lambda *a, **kw: child)
    monkeypatch.setattr(transport, '_signal_group', lambda pid, number: signals.append(number))
    monkeypatch.setattr(transport.time, 'sleep', lambda seconds: None)
    return child, signals, handlers, previous


def assert_retired(owned):
    child, signals, handlers, previous = owned
    assert signals == [signal.SIGTERM, signal.SIGKILL]
    assert child.waits == [transport._REAP_S]
    assert all(stream.closed for stream in (child.stdin, child.stdout, child.stderr))
    assert handlers == previous


def test_interrupt_immediately_after_handle_acquisition(owned, tmp_path):
    child = owned[0]

    def interrupt(frame, event, arg):
        if (frame.f_code is transport.run_agent.__code__ and event == 'line'
                and frame.f_locals.get('process') is child):
            sys.settrace(None)
            raise KeyboardInterrupt
        return interrupt

    previous_trace = sys.gettrace()
    try:
        sys.settrace(interrupt)
        with pytest.raises(KeyboardInterrupt):
            transport.run_agent(['synthetic'], cwd=tmp_path, timeout_s=1)
    finally:
        sys.settrace(previous_trace)
    assert_retired(owned)


@pytest.mark.parametrize('number', [signal.SIGINT, signal.SIGTERM, signal.SIGHUP])
def test_signal_during_acquisition_is_settled_after_return(owned, monkeypatch, tmp_path, number):
    child, _, handlers, _ = owned

    def acquire(*args, **kwargs):
        handler = handlers[number]
        assert callable(handler), 'cancellation must be installed before launch'
        handler(number, None)
        return child

    monkeypatch.setattr(transport.subprocess, 'Popen', acquire)
    expected = KeyboardInterrupt if number == signal.SIGINT else SystemExit
    with pytest.raises(expected):
        transport.run_agent(['synthetic'], cwd=tmp_path, timeout_s=1)
    assert_retired(owned)


def test_observed_cancellation_prevents_launch(owned, monkeypatch, tmp_path):
    _, signals, handlers, previous = owned
    install = transport.signal.signal

    def cancelled(number, handler):
        old = install(number, handler)
        if number == signal.SIGHUP and callable(handler):
            handler(signal.SIGTERM, None)
        return old

    monkeypatch.setattr(transport.signal, 'signal', cancelled)
    monkeypatch.setattr(transport.subprocess, 'Popen', lambda *a, **kw: pytest.fail('launched after cancellation'))
    with pytest.raises(SystemExit) as caught:
        transport.run_agent(['synthetic'], cwd=tmp_path, timeout_s=1)
    assert caught.value.code == 128 + signal.SIGTERM
    assert not signals
    assert handlers == previous


def test_partial_handler_install_failure_restores_without_launch(owned, monkeypatch, tmp_path):
    _, signals, handlers, previous = owned
    install = transport.signal.signal

    def fail(number, handler):
        if number == signal.SIGHUP and callable(handler):
            raise OSError('synthetic install failure')
        return install(number, handler)

    monkeypatch.setattr(transport.signal, 'signal', fail)
    monkeypatch.setattr(transport.subprocess, 'Popen', lambda *a, **kw: pytest.fail('launched before handlers'))
    with pytest.raises(OSError, match='install failure'):
        transport.run_agent(['synthetic'], cwd=tmp_path, timeout_s=1)
    assert not signals
    assert handlers == previous


def test_launch_failure_restores_caller_dispositions(owned, monkeypatch, tmp_path):
    _, signals, handlers, previous = owned
    previous[signal.SIGHUP] = handlers[signal.SIGHUP] = signal.SIG_IGN
    previous[signal.SIGTERM] = handlers[signal.SIGTERM] = lambda *args: None

    def fail(*args, **kwargs):
        assert handlers[signal.SIGHUP] is signal.SIG_IGN
        raise OSError('synthetic launch failure')

    monkeypatch.setattr(transport.subprocess, 'Popen', fail)
    with pytest.raises(OSError, match='launch failure'):
        transport.run_agent(['synthetic'], cwd=tmp_path, timeout_s=1)
    assert not signals
    assert handlers == previous


def test_signals_during_retirement_do_not_interrupt_reaping(owned, monkeypatch, tmp_path):
    child, signals, handlers, _ = owned

    def acquire(*args, **kwargs):
        handlers[signal.SIGTERM](signal.SIGTERM, None)
        return child

    def signalling(pid, number):
        signals.append(number)
        handlers[signal.SIGINT](signal.SIGINT, None)

    monkeypatch.setattr(transport.subprocess, 'Popen', acquire)
    monkeypatch.setattr(transport, '_signal_group', signalling)
    with pytest.raises(SystemExit) as caught:
        transport.run_agent(['synthetic'], cwd=tmp_path, timeout_s=1)
    assert caught.value.code == 143
    assert_retired(owned)


class Member:
    def __init__(self, pid, status):
        self.pid = pid
        self.state = status

    def status(self):
        return self.state


@pytest.fixture
def denied(owned, monkeypatch):
    child, signals, _, _ = owned
    # The leader has exited. A redirected descendant is alive in the same group,
    # so pipe EOF or leader reaping cannot establish group retirement.
    members = [Member(child.pid, psutil.STATUS_ZOMBIE),
               Member(child.pid + 1, psutil.STATUS_SLEEPING)]

    def refuse(pid, number):
        assert not child.waits, 'group identity released before final signalling'
        signals.append(number)
        raise PermissionError('SYNTHETIC_PRIVATE_SIGNAL_DETAIL')

    monkeypatch.setattr(transport, '_signal_group', SIGNAL_GROUP)
    monkeypatch.setattr(transport.os, 'killpg', refuse)
    monkeypatch.setattr(transport.os, 'getpgid', lambda pid: child.pid)
    monkeypatch.setattr(psutil, 'process_iter', lambda: iter(members))
    return members


class EmptySelector:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def register(self, *args):
        pass

    def get_map(self):
        return {}


def test_denied_group_retirement_cannot_return_success(owned, denied, monkeypatch, tmp_path):
    monkeypatch.setattr(transport.selectors, 'DefaultSelector', EmptySelector)
    monkeypatch.setattr(transport.os, 'set_blocking', lambda *args: None)
    monkeypatch.setattr(transport.os, 'waitid', lambda *args: object())
    with pytest.raises(ValueError, match='process-group retirement unconfirmed') as caught:
        transport.run_agent(['synthetic'], cwd=tmp_path, timeout_s=1)
    assert 'SYNTHETIC_PRIVATE' not in str(caught.value)
    assert_retired(owned)


def test_denied_retirement_preserves_primary_and_warns(owned, denied, monkeypatch, tmp_path, capsys):
    primary = transport.AgentTimeout('synthetic deadline exceeded')

    def fail():
        raise primary

    monkeypatch.setattr(transport.selectors, 'DefaultSelector', fail)
    with pytest.raises(transport.AgentTimeout) as caught:
        transport.run_agent(['synthetic'], cwd=tmp_path, timeout_s=1)
    assert caught.value is primary
    notes = ' '.join(primary.__notes__)
    diagnostic = capsys.readouterr().err
    assert 'process-group retirement unconfirmed' in notes
    assert 'process-group retirement unconfirmed' in diagnostic
    assert 'SYNTHETIC_PRIVATE' not in notes + diagnostic
    assert_retired(owned)


def test_denied_zombie_only_group_is_confirmed(owned, denied):
    denied[1].state = psutil.STATUS_ZOMBIE
    transport._retire(owned[0])
    assert owned[0].waits == [transport._REAP_S]
    assert owned[1] == [signal.SIGTERM, signal.SIGKILL]


def darwin_getpgid(members, leader):
    # Darwin reports ESRCH from getpgid for zombies, including the pinned leader.
    def getpgid(pid):
        member = next(m for m in members if m.pid == pid)
        if member.state == psutil.STATUS_ZOMBIE:
            raise ProcessLookupError
        return leader
    return getpgid


def test_darwin_zombie_only_group_is_confirmed(owned, denied, monkeypatch):
    denied[1].state = psutil.STATUS_ZOMBIE
    monkeypatch.setattr(transport.os, 'getpgid', darwin_getpgid(denied, owned[0].pid))
    transport._retire(owned[0])
    assert owned[0].waits == [transport._REAP_S]
    assert owned[1] == [signal.SIGTERM, signal.SIGKILL]


def test_darwin_live_member_with_zombie_leader_stays_unconfirmed(owned, denied, monkeypatch):
    monkeypatch.setattr(transport.os, 'getpgid', darwin_getpgid(denied, owned[0].pid))
    with pytest.raises(ValueError, match='process-group retirement unconfirmed'):
        transport._retire(owned[0])
    assert owned[0].waits == [transport._REAP_S]


def test_changing_zombie_membership_stays_unconfirmed(owned, denied, monkeypatch):
    denied[1].state = psutil.STATUS_ZOMBIE
    scans = 0

    def changing():
        nonlocal scans
        scans += 1
        return iter(denied if scans % 2 else denied[:1])

    monkeypatch.setattr(psutil, 'process_iter', changing)
    with pytest.raises(ValueError, match='process-group retirement unconfirmed'):
        transport._retire(owned[0])
    assert owned[0].waits == [transport._REAP_S]


def test_vanished_group_is_confirmed(owned, monkeypatch):
    def vanished(pid, number):
        owned[1].append(number)
        raise ProcessLookupError

    monkeypatch.setattr(transport, '_signal_group', SIGNAL_GROUP)
    monkeypatch.setattr(transport.os, 'killpg', vanished)
    transport._retire(owned[0])
    assert owned[0].waits == [transport._REAP_S]
    assert owned[1] == [signal.SIGTERM, signal.SIGKILL]


@pytest.mark.parametrize('fault', ['missing-leader', 'empty', 'unreadable', 'scan-limit', 'deadline'])
def test_incomplete_group_observation_stays_unconfirmed(owned, denied, monkeypatch, fault):
    child = owned[0]
    denied[1].state = psutil.STATUS_ZOMBIE
    if fault == 'missing-leader':
        denied.pop(0)
    elif fault == 'empty':
        denied.clear()
    elif fault == 'unreadable':
        def unreadable(pid):
            raise PermissionError('SYNTHETIC_PRIVATE_PROCESS_DETAIL')
        monkeypatch.setattr(transport.os, 'getpgid', unreadable)
    elif fault == 'scan-limit':
        denied.extend(Member(child.pid + n, psutil.STATUS_ZOMBIE) for n in range(2, 5000))
    else:
        tick = iter(range(100))
        monkeypatch.setattr(transport.time, 'monotonic', lambda: next(tick))
    with pytest.raises(ValueError, match='process-group retirement unconfirmed'):
        transport._retire(child)
    assert child.waits == [transport._REAP_S]
    assert owned[1] == [signal.SIGTERM, signal.SIGKILL]


def test_retirement_attempts_every_stage_and_keeps_first_failure(owned, monkeypatch):
    child = owned[0]
    events = []
    primary = KeyboardInterrupt()

    def fail_signal(pid, number):
        events.append(number)
        raise primary if number == signal.SIGTERM else OSError('private kill failure')

    def fail_grace(seconds):
        events.append('grace')
        raise OSError('private grace failure')

    def fail_wait(*, timeout):
        events.append('wait')
        raise OSError('private reap failure')

    monkeypatch.setattr(transport, '_signal_group', fail_signal)
    monkeypatch.setattr(transport.time, 'sleep', fail_grace)
    monkeypatch.setattr(child, 'wait', fail_wait)
    with pytest.raises(KeyboardInterrupt) as caught:
        transport._retire(child)
    assert caught.value is primary
    assert events == [signal.SIGTERM, 'grace', signal.SIGKILL, 'wait']
    assert 'private' not in ' '.join(primary.__notes__)


def test_stream_close_fault_cannot_skip_remaining_cleanup(owned, denied, monkeypatch, tmp_path, capsys):
    child = owned[0]
    primary = transport.AgentTimeout('synthetic timeout')

    def fail_selector():
        raise primary

    def fail_close():
        raise KeyboardInterrupt

    monkeypatch.setattr(transport.selectors, 'DefaultSelector', fail_selector)
    monkeypatch.setattr(child.stdin, 'close', fail_close)
    with pytest.raises(BaseException) as caught:
        transport.run_agent(['synthetic'], cwd=tmp_path, timeout_s=1)
    assert caught.value is primary
    assert child.stdout.closed and child.stderr.closed
    assert owned[2] == owned[3]
    assert child.waits == [transport._REAP_S]
    assert 'unconfirmed' in capsys.readouterr().err
