"""Report-wide admission and exceptional subprocess lifecycle regressions."""
import os
import select
import signal
import subprocess
import sys
import time

import pytest

from benchpack import report, tasks
from tests.test_report import _write_run


@pytest.mark.parametrize('budget', ['RUNS', 'BYTES', 'RECORDS'])
def test_report_total_budget_limits_loading(tmp_path, monkeypatch, budget):
    paths = [tmp_path / str(index) for index in range(3)]
    for path in paths:
        _write_run(path)
    limit = {'RUNS': 2, 'BYTES': 2 * (paths[0] / 'run.jsonl').stat().st_size, 'RECORDS': 2}[budget]
    monkeypatch.setattr(report, f'MAX_REPORT_{budget}', limit, raising=False)
    with pytest.raises(report.ReportError):
        report.load_report_runs(paths)
    runs = report.load_report_runs(paths[:2])
    assert len(runs) == 2
    assert '# benchpack report' in report.render_report(runs)


def test_report_deduplicates_canonical_run_identity(tmp_path, monkeypatch):
    run = tmp_path / 'run'
    _write_run(run)
    alias = tmp_path / 'alias'
    alias.symlink_to(run, target_is_directory=True)
    calls = []
    load = report.load_result_run

    def track(path, **kwargs):
        calls.append(path)
        return load(path, **kwargs)

    monkeypatch.setattr(report, 'load_result_run', track)
    runs = report.load_report_runs([run, alias, run / '..' / 'run'])
    assert len(runs) == len(calls) == 1


@pytest.mark.parametrize('exception', [KeyboardInterrupt, OSError])
def test_external_exception_cleans_parent_and_descendant(tmp_path, monkeypatch, exception):
    marker = tmp_path / 'child.pid'
    process_holder = []
    pipe_readers = []
    popen = subprocess.Popen
    primary = exception('synthetic interruption')
    code = '''import os, signal, subprocess, sys, time
child = subprocess.Popen([sys.executable, '-c', 'import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)'])
open(sys.argv[1], 'w').write(str(child.pid))
time.sleep(60)
'''

    def interrupted(*args, **kwargs):
        process = popen(*args, **kwargs)
        process_holder.append(process)
        pipe_readers.append(os.dup(process.stdout.fileno()))
        os.set_blocking(pipe_readers[-1], False)
        communicate = process.communicate
        calls = [0]
        def fail(**kw):
            calls[0] += 1
            if calls[0] == 1:
                deadline = time.monotonic() + 5
                while not marker.exists() and time.monotonic() < deadline:
                    time.sleep(0.01)
                assert marker.exists()
                raise primary
            return communicate(**kw)
        process.communicate = fail
        return process

    monkeypatch.setattr(tasks.subprocess, 'Popen', interrupted)
    try:
        started = time.monotonic()
        with pytest.raises(exception) as raised:
            tasks._run_external_process_command([sys.executable, '-c', code, str(marker)], tmp_path,
                                                timeout_s=10, case_id='synthetic')
        assert raised.value is primary
        assert time.monotonic() - started < 5
        process = process_holder[0]
        assert process.poll() is not None
        assert process.stdout.closed and process.stderr.closed
        # Both descendants inherit stdout. EOF on a duplicate read descriptor
        # proves no owned process still holds a writer, without host ps access.
        # SIGKILL delivery is synchronous but the descendant's exit is not, so
        # allow a short bounded wait for the last writer to disappear.
        readable, _, _ = select.select([pipe_readers[0]], [], [], 2)
        assert readable, 'a descendant still holds the harness pipe'
        assert os.read(pipe_readers[0], 1) == b''
    finally:
        for fd in pipe_readers:
            os.close(fd)
        # The regression itself must never leak processes on the unfixed tree.
        for process in process_holder:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                # macOS answers EPERM for a group that only holds exiting members.
                pass
            process.wait(timeout=2)
            for stream in (process.stdout, process.stderr):
                stream.close()


@pytest.mark.parametrize('budget', ['BYTES', 'RECORDS'])
def test_report_passes_remaining_allowance_into_reader(tmp_path, monkeypatch, budget):
    paths = [tmp_path / 'a', tmp_path / 'b']
    for path in paths:
        _write_run(path, rows=[{'case': 'one'}, {'case': 'two'}])
    size = (paths[0] / 'run.jsonl').stat().st_size
    limit = size + size // 2 if budget == 'BYTES' else 3
    monkeypatch.setattr(report, f'MAX_REPORT_{budget}', limit)
    calls = []
    load = report.load_result_run
    def track(path, **kwargs):
        calls.append(kwargs)
        return load(path, **kwargs)
    monkeypatch.setattr(report, 'load_result_run', track)
    with pytest.raises(report.ReportError):
        report.load_report_runs(paths)
    assert len(calls) == 2
    key = 'byte_limit' if budget == 'BYTES' else 'record_limit'
    consumed = size if budget == 'BYTES' else 2
    assert calls[1][key] == limit - consumed


def test_report_deduplicates_hardlinked_runs(tmp_path):
    a = tmp_path / 'a'
    b = tmp_path / 'b'
    _write_run(a)
    b.mkdir()
    os.link(a / 'run.jsonl', b / 'run.jsonl')
    assert len(report.load_report_runs([a, b])) == 1


def test_cleanup_uses_owned_group_after_leader_exit(monkeypatch):
    signals = []
    class ExitedLeader:
        pid = 12345
        def wait(self, *, timeout):
            assert timeout == tasks._EXTERNAL_PROCESS_TIMEOUT_GRACE_S
            return 0
    def send(pgid, number, case, **kwargs):
        signals.append((pgid, number, kwargs.get('exiting_ok')))
    monkeypatch.setattr(tasks, '_signal_external_process_group', send)
    monkeypatch.setattr(tasks, 'sleep', lambda _: None)
    tasks._reap_external_process_group(ExitedLeader(), 'synthetic')
    # The unreaped leader may be the group's only (zombie) member: both group
    # signals must tolerate macOS EPERM.
    assert signals == [(12345, signal.SIGTERM, True), (12345, signal.SIGKILL, True)]


def test_reap_completes_when_the_group_only_holds_a_zombie_leader(monkeypatch):
    waited = []
    class ExitedLeader:
        pid = 12345
        def wait(self, *, timeout):
            waited.append(timeout)
            return 0
    def eperm(pgid, number):
        raise PermissionError(1, 'Operation not permitted')
    monkeypatch.setattr(tasks.os, 'killpg', eperm)
    monkeypatch.setattr(tasks, 'sleep', lambda _: None)
    tasks._reap_external_process_group(ExitedLeader(), 'synthetic')
    assert waited == [tasks._EXTERNAL_PROCESS_TIMEOUT_GRACE_S]


def test_cleanup_errors_do_not_replace_interrupt_and_close_both_streams(tmp_path, monkeypatch):
    primary = KeyboardInterrupt('original')
    closed = []
    class Stream:
        def __init__(self, name):
            self.name = name
        def close(self):
            closed.append(self.name)
            if self.name == 'stdout':
                raise OSError('stream close failed')
    class Process:
        pid = 12345
        stdout = Stream('stdout')
        stderr = Stream('stderr')
        def communicate(self, **kwargs):
            raise primary
        def wait(self, **kwargs):
            return 0
    def signal_group(pgid, number, case_id, **kwargs):
        if number == signal.SIGTERM:
            raise OSError('terminate failed')
    monkeypatch.setattr(tasks.subprocess, 'Popen', lambda *a, **kw: Process())
    monkeypatch.setattr(tasks, '_signal_external_process_group', signal_group)
    with pytest.raises(KeyboardInterrupt) as raised:
        tasks._run_external_process_command(['synthetic'], tmp_path, timeout_s=1, case_id='synthetic')
    assert raised.value is primary
    assert closed == ['stdout', 'stderr']
    assert len(primary.__notes__) == 2


def test_timeout_cleanup_failure_is_not_a_successful_timeout(tmp_path, monkeypatch):
    import io
    class Process:
        pid = 12345
        stdout = io.StringIO()
        stderr = io.StringIO()
        calls = 0
        def communicate(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise subprocess.TimeoutExpired('synthetic', 1)
            return '', ''
        def wait(self, **kwargs):
            return 0
    def signal_group(pgid, number, case_id, **kwargs):
        if number == signal.SIGKILL:
            raise tasks.TaskError('cannot kill synthetic group')
    monkeypatch.setattr(tasks.subprocess, 'Popen', lambda *a, **kw: Process())
    monkeypatch.setattr(tasks, '_signal_external_process_group', signal_group)
    monkeypatch.setattr(tasks, 'sleep', lambda _: None)
    with pytest.raises(tasks.TaskError, match='cannot kill'):
        tasks._run_external_process_command(['synthetic'], tmp_path, timeout_s=1, case_id='synthetic')
