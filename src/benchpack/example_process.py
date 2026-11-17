"""Bounded POSIX child transport used by the external-agent examples."""
from __future__ import annotations

import math
import os
import selectors
import signal
import subprocess
import sys
import threading
import time
from contextlib import contextmanager

import psutil

MAX_AGENT_OUTPUT_BYTES = 16 * 1024 * 1024
MAX_PROMPT_BYTES = 32 * 1024 * 1024
_RETIRE_GRACE_S = 0.1
_REAP_S = 0.5
_MAX_GROUP_SCAN = 4096
_GROUP_SCAN_S = 0.1


class AgentTimeout(ValueError):
    pass


@contextmanager
def exit_on_termination_signals():
    """Turn SIGTERM/SIGHUP into SystemExit so owned cleanup scopes still run."""
    handlers = {}
    if threading.current_thread() is threading.main_thread():
        def interrupted(number, frame):
            raise SystemExit(128 + number)
        for number in (signal.SIGTERM, signal.SIGHUP):
            # Respect signals the caller ignores (for example under nohup).
            if signal.getsignal(number) is not signal.SIG_IGN:
                handlers[number] = signal.signal(number, interrupted)
    try:
        yield
    finally:
        for number, handler in handlers.items():
            signal.signal(number, handler)


def _zombie_only_group(pid):
    """Conservatively confirm a complete group snapshot with its pinned leader."""
    deadline = time.monotonic() + _GROUP_SCAN_S
    snapshots = []
    inspected = 0
    try:
        # A member can fork and exit during enumeration. Require the same
        # complete zombie membership twice; new descendants make it uncertain.
        for _ in range(2):
            members = set()
            for member in psutil.process_iter():
                inspected += 1
                if inspected > _MAX_GROUP_SCAN or time.monotonic() >= deadline:
                    return False
                try:
                    if os.getpgid(member.pid) != pid:
                        continue
                    if member.status() != psutil.STATUS_ZOMBIE:
                        return False
                    members.add(member.pid)
                except (ProcessLookupError, psutil.NoSuchProcess):
                    continue
            snapshots.append(members)
    except (OSError, psutil.Error):
        return False
    return (time.monotonic() < deadline and pid in snapshots[0]
            and snapshots[0] == snapshots[1])


def _signal_group(pid, number):
    try:
        os.killpg(pid, number)
    except ProcessLookupError:
        pass
    except PermissionError:
        # Darwin can report EPERM for zombies, but a denied live group is not
        # proof of retirement. Failed/incomplete inspection stays unconfirmed.
        if not _zombie_only_group(pid):
            raise ValueError('agent process-group retirement unconfirmed') from None


def _retire(process):
    # Do not reap/poll the session leader until after the final group signal:
    # its unreaped pid reserves the identity even when descendants hold pipes.
    failure = None
    for stage, operation in (
        ('terminate', lambda: _signal_group(process.pid, signal.SIGTERM)),
        ('grace', lambda: time.sleep(_RETIRE_GRACE_S)),
        ('kill', lambda: _signal_group(process.pid, signal.SIGKILL)),
        ('reap', lambda: process.wait(timeout=_REAP_S)),
    ):
        try:
            operation()
        except BaseException as exc:
            if failure is None:
                failure = exc
            else:
                failure.add_note(f'agent {stage} failed; process-group retirement unconfirmed')
    if failure is not None:
        # CLI examples intentionally print only their primary error category.
        try:
            print('example cleanup warning: agent process-group retirement unconfirmed', file=sys.stderr)
        except BaseException:
            pass
        raise failure


def run_agent(command, *, cwd, timeout_s, prompt: bytes | None = None):
    """Deliver bounded stdin and capture bounded output; retire on every exit."""
    if os.name != 'posix' or not hasattr(os, 'WNOWAIT'):
        raise ValueError('example agent transport requires POSIX waitid/WNOWAIT')
    if not math.isfinite(timeout_s) or timeout_s <= 0:
        raise ValueError('agent timeout must be finite and positive')
    if prompt is not None and len(prompt) > MAX_PROMPT_BYTES:
        raise ValueError('agent prompt exceeds byte limit')
    deadline = time.monotonic() + timeout_s
    process = None
    retired = False
    primary = None
    handlers = {}
    pending_signal = None

    def interrupted(number, frame):
        # Never raise between Popen returning a handle and assigning ownership,
        # or while retirement is in progress. Settle at the next checkpoint.
        nonlocal pending_signal
        if pending_signal is None:
            pending_signal = number

    def check_cancelled():
        if pending_signal == signal.SIGINT:
            raise KeyboardInterrupt
        if pending_signal is not None:
            raise SystemExit(128 + pending_signal)

    output = {'stdout': bytearray(), 'stderr': bytearray()}
    total = 0
    sent = 0
    try:
        if threading.current_thread() is threading.main_thread():
            for number in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
                if signal.getsignal(number) is not signal.SIG_IGN:
                    handlers[number] = signal.signal(number, interrupted)
        check_cancelled()
        process = subprocess.Popen(
            command, cwd=cwd, stdin=subprocess.PIPE if prompt is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True,
        )
        check_cancelled()
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
                check_cancelled()
                if not retired and time.monotonic() >= deadline:
                    raise AgentTimeout("agent deadline exceeded")
                if not retired and os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT):
                    # _retire attempts all stages, including reaping, on failure.
                    # Never signal the group again after that identity is released.
                    retired = True
                    _retire(process)
                    check_cancelled()
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
        check_cancelled()
    except BaseException as exc:
        primary = exc
    finally:
        try:
            if process is not None and not retired:
                _retire(process)
        except BaseException as exc:
            if primary is None:
                primary = exc
            else:
                note = 'agent retirement failed; process-group retirement unconfirmed'
                primary.add_note(note)
        finally:
            streams = (process.stdin, process.stdout, process.stderr) if process is not None else ()
            for stream in streams:
                if stream is not None:
                    try:
                        stream.close()
                    except BaseException as exc:
                        if primary is None:
                            primary = exc
                        else:
                            primary.add_note('agent stream closure failed')
            for number, handler in handlers.items():
                try:
                    signal.signal(number, handler)
                except BaseException as exc:
                    if primary is None:
                        primary = exc
                    else:
                        primary.add_note('agent signal restoration failed')
    if primary is not None:
        raise primary
    check_cancelled()
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
