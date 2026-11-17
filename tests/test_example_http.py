"""Synthetic transport lifetime regressions; no model endpoints or credentials."""
import http.client
import socket
import threading
import time
from urllib.request import Request

import pytest

from benchpack import example_http


def test_stalled_resolution_has_fixed_admission_and_recovers(monkeypatch):
    release = threading.Event()
    lock = threading.Lock()
    calls = []
    failures = []

    def resolve(*args, **kwargs):
        with lock:
            calls.append(threading.current_thread())
        release.wait(3)
        raise socket.gaierror('synthetic private resolver detail')

    monkeypatch.setattr(socket, 'getaddrinfo', resolve)

    def call():
        try:
            example_http.response_bytes(Request('http://synthetic.invalid/'), .05)
        except ValueError as exc:
            failures.append(str(exc))

    callers = [threading.Thread(target=call) for _ in range(16)]
    try:
        for caller in callers:
            caller.start()
        for caller in callers:
            caller.join(.1)
        assert all(not caller.is_alive() for caller in callers)
        assert len(failures) == 16
        assert len(calls) == 4
        # Retry while abandoned libc work is still running: no extra jobs/queue.
        for _ in range(8):
            call()
        assert len(calls) == 4
        assert not any('private' in failure for failure in failures)
    finally:
        release.set()
        for caller in callers:
            caller.join(4)
        for worker in calls:
            worker.join(4)
    call()
    assert len(calls) == 5  # admission was released by the resolver itself


def test_late_resolution_never_sends_request(monkeypatch):
    sent = []
    original = socket.getaddrinfo

    def resolve(*args, **kwargs):
        time.sleep(.3)
        return original('127.0.0.1', listener.getsockname()[1], type=socket.SOCK_STREAM)

    monkeypatch.setattr(socket, 'getaddrinfo', resolve)
    monkeypatch.setattr(http.client.HTTPConnection, 'request', lambda *a, **k: sent.append(True))
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        listener.listen()
        started = time.monotonic()
        with pytest.raises(ValueError):
            example_http.response_bytes(Request('http://synthetic.invalid/', data=b'synthetic'), .05)
        elapsed = time.monotonic() - started
        time.sleep(.35)  # abandoned resolution must not continue into HTTP
    assert elapsed < .2
    assert sent == []


def test_address_attempts_share_remaining_deadline(monkeypatch):
    now = [0.0]
    budgets = []

    class Socket:
        def settimeout(self, timeout):
            self.timeout = timeout

        def connect(self, address):
            budgets.append(self.timeout)
            now[0] += .06
            raise OSError('synthetic connect failure')

        def close(self):
            pass

    monkeypatch.setattr(example_http.time, 'monotonic', lambda: now[0])
    monkeypatch.setattr(socket, 'socket', lambda *a: Socket())
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *a, **k: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('127.0.0.1', port))
        for port in (1, 2, 3)
    ])
    with pytest.raises(ValueError):
        example_http.response_bytes(Request('http://synthetic.invalid/'), .1)
    assert budgets == pytest.approx([.1, .04])


def test_tls_handshake_uses_budget_left_after_resolution(monkeypatch):
    original = socket.getaddrinfo
    release = threading.Event()

    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        listener.listen()
        listener.settimeout(2)

        def server():
            with listener.accept()[0] as peer:
                release.wait(2)  # TCP succeeds, TLS peer stays silent

        thread = threading.Thread(target=server)
        thread.start()

        def resolve(*args, **kwargs):
            time.sleep(.2)
            return original('127.0.0.1', listener.getsockname()[1], type=socket.SOCK_STREAM)

        monkeypatch.setattr(socket, 'getaddrinfo', resolve)
        try:
            started = time.monotonic()
            with pytest.raises(ValueError):
                example_http.response_bytes(Request('https://synthetic.invalid/'), .3)
            assert time.monotonic() - started < .43
        finally:
            release.set()
            thread.join(3)


@pytest.fixture
def retirement_transport(monkeypatch):
    calls = []
    faults = set()
    join_budgets = []

    def stage(name):
        calls.append(name)
        if 'interrupt:' + name in faults:
            raise KeyboardInterrupt()
        if name in faults:
            raise RuntimeError('synthetic private cleanup detail')

    class Socket:
        def settimeout(self, value):
            pass

        def shutdown(self, how):
            stage('shutdown')

        def close(self):
            stage('socket-close')

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.close()

        def close(self):
            stage('response-close')

    class Connection:
        def __init__(self, *args, **kwargs):
            self.sock = None

        def request(self, *args, **kwargs):
            pass

        def getresponse(self):
            return Response()

        def close(self):
            stage('connection-close')

    class Timer:
        def __init__(self, *args):
            pass

        def start(self):
            stage('start')

        def cancel(self):
            stage('cancel')

        def join(self, timeout=None):
            join_budgets.append(timeout)
            stage('join')

        def is_alive(self):
            return 'timer-alive' in faults

    monkeypatch.setattr(http.client, 'HTTPConnection', Connection)
    monkeypatch.setattr(example_http, '_connect', lambda conn, *a: setattr(conn, 'sock', Socket()))
    monkeypatch.setattr(example_http.threading, 'Timer', Timer)
    return calls, faults, join_budgets


@pytest.mark.parametrize('fault', ['cancel', 'join', 'shutdown', 'response-close', 'connection-close', 'socket-close', 'timer-alive', 'all'])
@pytest.mark.parametrize('outcome', ['success', 'parse', 'timeout', 'interrupt'])
def test_retirement_stages_are_independent_and_preserve_primary(retirement_transport, capsys, fault, outcome):
    calls, faults, budgets = retirement_transport
    faults.update(['cancel', 'join', 'shutdown', 'response-close', 'connection-close', 'socket-close'] if fault == 'all' else [fault])
    primary = {
        'success': None,
        'parse': ValueError('synthetic parse failure'),
        'timeout': TimeoutError('synthetic timeout'),
        'interrupt': KeyboardInterrupt(),
    }[outcome]
    with pytest.raises(BaseException) as caught:
        with example_http.open_response(Request('http://synthetic.invalid/'), 1):
            if primary is not None:
                raise primary
    assert {'cancel', 'join', 'shutdown', 'response-close', 'connection-close', 'socket-close'} <= set(calls)
    assert all(budget is not None and 0 < budget <= .1 for budget in budgets)
    if primary is not None:
        assert caught.value is primary
    else:
        assert isinstance(caught.value, ValueError)
        assert str(caught.value) == 'HTTP cleanup failed'
    assert caught.value.__notes__
    diagnostic = str(caught.value) + repr(caught.value.__notes__) + capsys.readouterr().err
    assert 'private cleanup detail' not in diagnostic
    assert 'retirement unconfirmed' in diagnostic


def test_success_retires_socket_with_bounded_timer_join(retirement_transport):
    calls, faults, budgets = retirement_transport
    with example_http.open_response(Request('http://synthetic.invalid/'), 1):
        pass
    assert 'socket-close' in calls
    assert budgets and 0 < budgets[0] <= .1


def test_timer_start_fault_still_retires_socket(retirement_transport):
    calls, faults, budgets = retirement_transport
    faults.add('start')
    with pytest.raises(RuntimeError, match='synthetic private cleanup detail'):
        with example_http.open_response(Request('http://synthetic.invalid/'), 1):
            pytest.fail('timer start failed before request')
    assert 'socket-close' in calls


@pytest.mark.parametrize('stage', ['cancel', 'join', 'shutdown', 'response-close', 'connection-close', 'socket-close'])
@pytest.mark.parametrize('has_primary', [False, True])
def test_cleanup_interrupt_still_attempts_all_owners(retirement_transport, stage, has_primary):
    calls, faults, budgets = retirement_transport
    faults.add('interrupt:' + stage)
    primary = ValueError('synthetic parse failure') if has_primary else None
    with pytest.raises(BaseException) as caught:
        with example_http.open_response(Request('http://synthetic.invalid/'), 1):
            if primary is not None:
                raise primary
    if has_primary:
        assert caught.value is primary
    else:
        assert isinstance(caught.value, KeyboardInterrupt)
    assert {'cancel', 'join', 'shutdown', 'response-close', 'connection-close', 'socket-close'} <= set(calls)


def test_live_timer_cannot_extend_retirement_indefinitely(retirement_transport, monkeypatch):
    calls, faults, budgets = retirement_transport
    release = threading.Event()
    entered = threading.Event()
    timers = []

    def blocked():
        entered.set()
        release.wait(3)

    # Use a real thread that remains live despite cancellation.
    from threading import Thread
    class BlockingTimer(Thread):
        def __init__(self, *args):
            super().__init__(target=blocked, daemon=True)
            timers.append(self)

        def cancel(self):
            pass

    monkeypatch.setattr(example_http.threading, 'Timer', BlockingTimer)
    try:
        started = time.monotonic()
        with pytest.raises(ValueError, match='HTTP cleanup failed'):
            with example_http.open_response(Request('http://synthetic.invalid/'), 1):
                assert entered.wait(1)
        assert time.monotonic() - started < .4
        assert 'socket-close' in calls
    finally:
        release.set()
        for timer in timers:
            timer.join(3)


def test_response_close_fault_cannot_leave_live_socket_traffic(monkeypatch):
    local, peer = socket.socketpair()
    retained_stream = local.makefile('rb')

    class Response:
        def close(self):
            raise RuntimeError('synthetic private close failure')

    class Connection:
        def __init__(self, *args, **kwargs):
            self.sock = None

        def request(self, *args, **kwargs):
            pass

        def getresponse(self):
            self.sock = None  # HTTPConnection detaches will-close responses
            return Response()

        def close(self):
            raise RuntimeError('synthetic private connection failure')

    monkeypatch.setattr(http.client, 'HTTPConnection', Connection)
    monkeypatch.setattr(example_http, '_connect', lambda conn, *a: setattr(conn, 'sock', local))
    try:
        with pytest.raises(ValueError, match='HTTP cleanup failed'):
            with example_http.open_response(Request('http://synthetic.invalid/'), 1):
                pass
        peer.settimeout(.2)
        assert peer.recv(1) == b''
    finally:
        retained_stream.close()
        local.close()
        peer.close()


def test_resolver_start_interruption_does_not_release_running_admission(monkeypatch):
    slots = threading.BoundedSemaphore(1)
    entered = threading.Event()
    release = threading.Event()
    workers = []
    real_thread = threading.Thread

    def resolve(*args, **kwargs):
        entered.set()
        release.wait(3)
        return []

    class InterruptedStart(real_thread):
        def start(self):
            super().start()
            workers.append(self)
            assert entered.wait(1)
            raise KeyboardInterrupt()

    monkeypatch.setattr(example_http, '_resolver_slots', slots)
    monkeypatch.setattr(socket, 'getaddrinfo', resolve)
    monkeypatch.setattr(example_http.threading, 'Thread', InterruptedStart)
    try:
        with pytest.raises(KeyboardInterrupt):
            example_http._resolve('synthetic.invalid', 80, time.monotonic() + 1)
        assert not slots.acquire(blocking=False)
    finally:
        release.set()
        for worker in workers:
            worker.join(3)
    assert slots.acquire(blocking=False)


def test_interrupted_resolver_start_cancels_late_worker(monkeypatch):
    slots = threading.BoundedSemaphore(1)
    jobs = []
    calls = []

    class InterruptedStart:
        def __init__(self, *, target, **kwargs):
            jobs.append(target)

        def start(self):
            raise KeyboardInterrupt()

    monkeypatch.setattr(example_http, '_resolver_slots', slots)
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *a, **k: calls.append(True))
    monkeypatch.setattr(example_http.threading, 'Thread', InterruptedStart)
    with pytest.raises(KeyboardInterrupt):
        example_http._resolve('synthetic.invalid', 80, time.monotonic() + 1)
    jobs[0]()  # a thread started before interruption may enter only afterward
    assert calls == []
    assert slots.acquire(blocking=False)


def test_partial_connect_failure_keeps_private_cleanup_notes(retirement_transport, monkeypatch, capsys):
    calls, faults, budgets = retirement_transport
    faults.add('connection-close')
    original = example_http._connect
    primary = TimeoutError('synthetic private connect detail')

    def connect(connection, *args):
        original(connection, *args)
        raise primary

    monkeypatch.setattr(example_http, '_connect', connect)
    with pytest.raises(ValueError, match='HTTP transport failed') as caught:
        example_http.response_bytes(Request('http://synthetic.invalid/'), 1)
    assert str(caught.value) == 'HTTP transport failed'
    assert caught.value.__cause__ is primary
    assert 'socket-close' in calls
    assert caught.value.__notes__ == primary.__notes__
    assert 'private' not in repr(caught.value.__notes__) + capsys.readouterr().err


@pytest.mark.parametrize(('url', 'port', 'host'), [
    ('http://synthetic.invalid:0/', 0, 'synthetic.invalid:0'),
    ('https://synthetic.invalid:443/', 443, 'synthetic.invalid'),
    ('https://synthetic.invalid:80/', 80, 'synthetic.invalid:80'),
    ('https://synthetic.invalid/', 443, 'synthetic.invalid'),
])
def test_scheme_and_explicit_port_keep_standard_host_header(monkeypatch, url, port, host):
    local, peer = socket.socketpair()
    observed = []

    def connect(connection, *args):
        assert connection.port == port
        connection.sock = local  # isolate routing/HTTP serialization from TLS

    def server():
        peer.settimeout(2)
        observed.append(peer.recv(65536))
        peer.sendall(b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}')

    monkeypatch.setattr(example_http, '_connect', connect)
    thread = threading.Thread(target=server)
    thread.start()
    try:
        assert example_http.response_bytes(Request(url), 1) == b'{}'
        assert b'Host: ' + host.encode() + b'\r\n' in observed[0]
    finally:
        thread.join(3)
        local.close()
        peer.close()
