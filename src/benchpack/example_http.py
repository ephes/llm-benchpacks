"""One bounded, non-redirecting HTTP exchange for external-agent examples."""
from contextlib import contextmanager
import http.client
import math
import socket
import ssl
import threading
import time
from urllib.parse import urlsplit

MAX_RESPONSE_BYTES = 16 * 1024 * 1024
MAX_RESOLVERS = 4
_resolver_slots = threading.BoundedSemaphore(MAX_RESOLVERS)


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
    result = []
    errors = []

    def run():
        try:
            result.extend(socket.getaddrinfo(host, port, type=socket.SOCK_STREAM))
        except BaseException as exc:
            errors.append(exc)
        finally:
            _resolver_slots.release()
            done.set()

    # No executor queue or exit-time join of uninterruptible system resolution.
    worker = threading.Thread(target=run, name='example-http-resolver', daemon=True)
    try:
        worker.start()
    except BaseException:
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
            connection.close()
    else:
        raise last_error
    if parts.scheme == 'https':
        context = ssl.create_default_context()
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
    port = parts.port or (443 if parts.scheme == 'https' else 80)
    connection = http.client.HTTPConnection(parts.hostname, port, timeout=timeout)
    # We provide an already-connected socket. Never reconnect/send after expiry.
    connection.auto_open = 0
    timer = None
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
        timer = threading.Timer(_remaining(deadline), expire)
        timer.daemon = True
        timer.start()
        path = parts.path or '/'
        if parts.query:
            path += '?' + parts.query
        owned_socket.settimeout(_remaining(deadline))
        connection.request(request.get_method(), path, body=request.data, headers=dict(request.header_items()))
        owned_socket.settimeout(_remaining(deadline))
        with connection.getresponse() as response:
            yield response
    finally:
        if timer is not None:
            timer.cancel()
            timer.join()
        connection.close()


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
        raise ValueError('HTTP transport failed') from exc
