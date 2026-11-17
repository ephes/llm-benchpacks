"""Deterministic process ownership faults; no delegate or OS group signals."""
import io
import signal
import sys

import pytest

from benchpack import example_process as transport


class Child:
    pid = 12345
    returncode = 0

    def __init__(self):
        self.stdin = io.BytesIO()
        self.stdout = io.BytesIO()
        self.stderr = io.BytesIO()
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
