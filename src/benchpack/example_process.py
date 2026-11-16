"""Bounded POSIX child transport used by the external-agent examples."""
from __future__ import annotations

import math
import os
import selectors
import signal
import subprocess
import threading
import time

MAX_AGENT_OUTPUT_BYTES = 16 * 1024 * 1024
MAX_PROMPT_BYTES = 32 * 1024 * 1024
_RETIRE_GRACE_S = 0.1
_REAP_S = 0.5


class AgentTimeout(ValueError):
    pass


def _signal_group(pid, number):
    try:
        os.killpg(pid, number)
    except (ProcessLookupError, PermissionError):
        # Darwin can report EPERM for a group containing only an exiting zombie.
        pass


def _retire(process):
    # Do not reap/poll the session leader until after the final group signal:
    # its unreaped pid reserves the identity even when descendants hold pipes.
    try:
        _signal_group(process.pid, signal.SIGTERM)
        time.sleep(_RETIRE_GRACE_S)
    finally:
        try:
            _signal_group(process.pid, signal.SIGKILL)
        finally:
            process.wait(timeout=_REAP_S)


def run_agent(command, *, cwd, timeout_s, prompt: bytes | None = None):
    """Deliver bounded stdin and capture bounded output; retire on every exit."""
    if os.name != 'posix' or not hasattr(os, 'WNOWAIT'):
        raise ValueError('example agent transport requires POSIX waitid/WNOWAIT')
    if not math.isfinite(timeout_s) or timeout_s <= 0:
        raise ValueError('agent timeout must be finite and positive')
    if prompt is not None and len(prompt) > MAX_PROMPT_BYTES:
        raise ValueError('agent prompt exceeds byte limit')
    deadline = time.monotonic() + timeout_s
    process = subprocess.Popen(
        command, cwd=cwd, stdin=subprocess.PIPE if prompt is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True,
    )
    retired = False
    primary = None
    handlers = {}
    output = {'stdout': bytearray(), 'stderr': bytearray()}
    total = 0
    sent = 0
    try:
        if threading.current_thread() is threading.main_thread():
            def interrupted(number, frame):
                raise SystemExit(128 + number)
            for number in (signal.SIGTERM, signal.SIGHUP):
                handlers[number] = signal.signal(number, interrupted)
        with selectors.DefaultSelector() as selector:
            for name in output:
                stream = getattr(process, name)
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ, name)
            if prompt is not None:
                os.set_blocking(process.stdin.fileno(), False)
                if prompt:
                    selector.register(process.stdin, selectors.EVENT_WRITE, 'stdin')
                else:
                    process.stdin.close()
            while True:
                if not retired and time.monotonic() >= deadline:
                    raise AgentTimeout("agent deadline exceeded")
                if not retired and os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT):
                    _retire(process)
                    retired = True
                    if prompt is not None and sent != len(prompt):
                        raise ValueError('agent exited before complete prompt delivery')
                    # Pipes may contain already written bytes. Drain only those
                    # bytes, with a finite grace even for escaped pipe owners.
                    deadline = time.monotonic() + _REAP_S
                if retired and not selector.get_map():
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise AgentTimeout('agent deadline exceeded')
                for key, _ in selector.select(min(.05, remaining)):
                    stream = key.fileobj
                    if key.data == 'stdin':
                        try:
                            count = os.write(stream.fileno(), prompt[sent:sent + 65536])
                        except BlockingIOError:
                            continue
                        except BrokenPipeError as exc:
                            raise ValueError('agent closed prompt input early') from exc
                        if count <= 0:
                            raise ValueError('agent prompt write made no progress')
                        sent += count
                        if sent == len(prompt):
                            selector.unregister(stream)
                            stream.close()
                    else:
                        try:
                            chunk = os.read(stream.fileno(), min(65536, MAX_AGENT_OUTPUT_BYTES + 1 - total))
                        except BlockingIOError:
                            continue
                        if not chunk:
                            selector.unregister(stream)
                            continue
                        total += len(chunk)
                        if total > MAX_AGENT_OUTPUT_BYTES:
                            raise ValueError('agent output exceeds byte limit')
                        output[key.data].extend(chunk)
        try:
            stdout = output['stdout'].decode('utf-8')
            stderr = output['stderr'].decode('utf-8')
        except UnicodeError as exc:
            raise ValueError('agent output must be UTF-8') from exc
        return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
    except BaseException as exc:
        primary = exc
        raise
    finally:
        try:
            if not retired:
                _retire(process)
        except BaseException:
            if primary is None:
                raise
            primary.add_note('agent retirement failed')
        finally:
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None:
                    try:
                        stream.close()
                    except OSError:
                        if primary is not None:
                            primary.add_note('agent stream closure failed')
            for number, handler in handlers.items():
                signal.signal(number, handler)
