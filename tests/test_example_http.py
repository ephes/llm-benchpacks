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
