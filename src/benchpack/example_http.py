"""One bounded, non-redirecting HTTP exchange for external-agent examples."""
from contextlib import contextmanager
import errno
import http.client
import math
import socket
import ssl
import sys
import threading
import time
from urllib.parse import urlsplit

MAX_RESPONSE_BYTES = 16 * 1024 * 1024
MAX_RESOLVERS = 4
_resolver_slots = threading.BoundedSemaphore(MAX_RESOLVERS)
_TIMER_JOIN_S = .1


def _retire(operations, primary):
    """Attempt every owner independently; expose only fixed private categories."""
    notes = []
    interrupt = None
    for category, operation in operations:
        try:
            operation()
        except BaseException as exc:
            notes.append(f'HTTP {category} failed; retirement unconfirmed')
            if interrupt is None and not isinstance(exc, Exception):
                interrupt = exc
    if not notes:
        return False
    failure = primary if primary is not None else interrupt
    if failure is None:
        failure = ValueError('HTTP cleanup failed')
    for note in notes:
        failure.add_note(note)
    # The examples print only the primary message, so notes alone are insufficient.
    try:
        print('example cleanup warning: HTTP retirement unconfirmed', file=sys.stderr)
    except BaseException:
        pass
    if primary is None:
        raise failure from None
    return True


def _join_timer(timer, expiry_errors):
    timer.join(timeout=_TIMER_JOIN_S)
    if timer.is_alive() or expiry_errors:
        raise ValueError('HTTP timer retirement unconfirmed')


def _shutdown_socket(sock):
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError as exc:
        # Both are ordinary after HTTPResponse has already closed its socket.
        if exc.errno not in (errno.EBADF, errno.ENOTCONN):
            raise


def _remaining(deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ValueError('HTTP response deadline exceeded')
    return remaining


def _resolve(host, port, deadline):
    """Only libc resolution may outlive a caller; it retains its admission."""
    _remaining(deadline)
    if not _resolver_slots.acquire(blocking=False):
        raise ValueError('HTTP resolver capacity exceeded')
    done = threading.Event()
    ownership = threading.Lock()
    running = False
    cancelled = False
    result = []
    errors = []

    def run():
        nonlocal running
        with ownership:
            if cancelled:
                return
            running = True
        try:
            result.extend(socket.getaddrinfo(host, port, type=socket.SOCK_STREAM))
        except BaseException as exc:
            errors.append(exc)
        finally:
            _resolver_slots.release()
            done.set()

    # No executor queue or exit-time join of uninterruptible system resolution.
    try:
        worker = threading.Thread(target=run, name='example-http-resolver', daemon=True)
        worker.start()
    except BaseException:
        # start() can be interrupted after spawning but before returning. A late
        # worker must either own admission or observe cancellation before libc.
        with ownership:
            if not running:
                cancelled = True
                _resolver_slots.release()
        raise
    if not done.wait(_remaining(deadline)):
        raise ValueError('HTTP response deadline exceeded')
    _remaining(deadline)
    if errors:
        raise errors[0]
    return result


def _connect(connection, parts, deadline):
    addresses = _resolve(parts.hostname, connection.port, deadline)
    last_error = OSError('HTTP address resolution failed')
    for family, kind, protocol, _, address in addresses:
        _remaining(deadline)
        try:
            connection.sock = socket.socket(family, kind, protocol)
            connection.sock.settimeout(_remaining(deadline))
            connection.sock.connect(address)
            break
        except OSError as exc:
            last_error = exc
            failed_socket = connection.sock
            operations = [('connection close', connection.close)]
            if failed_socket is not None:
                operations.append(('socket close', failed_socket.close))
            if _retire(operations, exc):
                raise
    else:
        raise last_error
    if parts.scheme == 'https':
        context = ssl.create_default_context()
        context.set_alpn_protocols(['http/1.1'])
        connection.sock.settimeout(_remaining(deadline))
        connection.sock = context.wrap_socket(
            connection.sock, server_hostname=parts.hostname, do_handshake_on_connect=False,
        )
        connection.sock.settimeout(_remaining(deadline))
        connection.sock.do_handshake()
    connection.sock.settimeout(_remaining(deadline))


@contextmanager
def open_response(request, timeout, *, deadline=None):
    """Use public connection/socket APIs; never follow a Location header."""
    parts = urlsplit(request.full_url)
    cls = http.client.HTTPSConnection if parts.scheme == 'https' else http.client.HTTPConnection
    connection = cls(parts.hostname, parts.port, timeout=timeout)
    # We provide an already-connected socket. Never reconnect/send after expiry.
    connection.auto_open = 0
    timer = None
    response = None
    owned_socket = None
    primary = None
    expiry_errors = []
    if deadline is None:
        deadline = time.monotonic() + timeout
    try:
        _connect(connection, parts, deadline)
        owned_socket = connection.sock
        def expire():
            try:
                owned_socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            except BaseException:
                expiry_errors.append(True)
        timer = threading.Timer(_remaining(deadline), expire)
        timer.daemon = True
        timer.start()
        path = parts.path or '/'
        if parts.query:
            path += '?' + parts.query
        owned_socket.settimeout(_remaining(deadline))
        connection.request(request.get_method(), path, body=request.data, headers=dict(request.header_items()))
        owned_socket.settimeout(_remaining(deadline))
        response = connection.getresponse()
        yield response
    except BaseException as exc:
        primary = exc
        raise
    finally:
        # getresponse() may detach a will-close socket from HTTPConnection.
        # Keep that socket independently, even if response/connection close fails.
        sockets = {id(sock): sock for sock in (owned_socket, connection.sock) if sock is not None}
        operations = []
        if timer is not None:
            operations.extend([
                ('timer cancellation', timer.cancel),
                ('timer join', lambda: _join_timer(timer, expiry_errors)),
            ])
        # Socket file objects can retain the descriptor after socket.close().
        # Shut down traffic independently of a failing response stream close.
        operations.extend(('socket shutdown', lambda sock=sock: _shutdown_socket(sock)) for sock in sockets.values())
        if response is not None:
            operations.append(('response close', response.close))
        operations.append(('connection close', connection.close))
        operations.extend(('socket close', sock.close) for sock in sockets.values())
        _retire(operations, primary)


def response_bytes(request, timeout):
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('HTTP timeout must be finite and positive')
    deadline = time.monotonic() + timeout
    try:
        with open_response(request, timeout, deadline=deadline) as response:
            status = getattr(response, 'status', 200)
            if status != 200:
                # Error bodies have no control authority and are never retained.
                raise ValueError(f'HTTP request failed with status {status}')
            chunks = []
            total = 0
            while True:
                if time.monotonic() >= deadline:
                    raise ValueError('HTTP response deadline exceeded')
                chunk = response.read1(min(65536, MAX_RESPONSE_BYTES + 1 - total))
                if time.monotonic() >= deadline:
                    raise ValueError('HTTP response deadline exceeded')
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_RESPONSE_BYTES:
                    raise ValueError('HTTP response exceeds byte limit')
                chunks.append(chunk)
            return b''.join(chunks)
    except (OSError, http.client.HTTPException) as exc:
        failure = ValueError('HTTP transport failed')
        for note in getattr(exc, '__notes__', ()):
            failure.add_note(note)
        raise failure from exc
