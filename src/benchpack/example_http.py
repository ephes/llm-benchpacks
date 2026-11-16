"""One bounded, non-redirecting HTTP exchange for external-agent examples."""
from contextlib import contextmanager
import http.client
import math
import socket
import threading
import time
from urllib.parse import urlsplit

MAX_RESPONSE_BYTES = 16 * 1024 * 1024


@contextmanager
def open_response(request, timeout):
    """Use public connection/socket APIs; never follow a Location header."""
    parts = urlsplit(request.full_url)
    cls = http.client.HTTPSConnection if parts.scheme == 'https' else http.client.HTTPConnection
    connection = cls(parts.hostname, parts.port, timeout=timeout)
    timer = None
    deadline = time.monotonic() + timeout
    try:
        connection.connect()
        owned_socket = connection.sock
        def expire():
            try:
                owned_socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        timer = threading.Timer(max(0, deadline - time.monotonic()), expire)
        timer.daemon = True
        timer.start()
        path = parts.path or '/'
        if parts.query:
            path += '?' + parts.query
        connection.request(request.get_method(), path, body=request.data, headers=dict(request.header_items()))
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
        with open_response(request, timeout) as response:
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
