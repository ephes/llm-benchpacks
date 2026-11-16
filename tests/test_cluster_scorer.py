"""Synthetic regressions for the pack-local candidate evidence boundary."""
import importlib.util
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import psutil
import pytest

SCORER = Path('benchpacks/product-offer-matching/verify/score_clusters.py')


@pytest.fixture
def scorer():
    spec = importlib.util.spec_from_file_location('cluster_scorer', SCORER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_drains_both_pipes_with_bounded_tail(scorer, tmp_path):
    result = scorer._run_command([sys.executable, '-c',
        "import os; os.write(1,b'x'*300000); os.write(2,b'y'*300000); "
        "open('clusters.csv','w').write('offer_id,cluster_id\\na,c\\n')"],
        cwd=tmp_path, timeout_s=3)
    assert result['ok']
    assert (tmp_path / 'clusters.csv').exists()
    assert 0 < len(result['stdout']) <= 65536
    assert 0 < len(result['stderr']) <= 65536


@pytest.mark.parametrize('timeout', [False, True])
@pytest.mark.parametrize('redirect', [False, True])
def test_retires_descendants_on_leader_exit(scorer, tmp_path, timeout, redirect):
    # Run the scorer in a watchdog process: the old implementation blocks on EOF.
    code = f'''import importlib.util, pathlib, sys
spec=importlib.util.spec_from_file_location('s', {str(SCORER.resolve())!r})
s=importlib.util.module_from_spec(spec); spec.loader.exec_module(s)
s._run_command([sys.executable, '-c', {("import subprocess,sys,time; p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']" + (",stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL" if redirect else "") + "); open('pid','w').write(str(p.pid)); time.sleep(30)" if timeout else "import subprocess,sys; p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']" + (",stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL" if redirect else "") + "); open('pid','w').write(str(p.pid))")!r}], cwd=pathlib.Path('.'), timeout_s=0.3)
'''
    pid = None
    try:
        proc = subprocess.Popen([sys.executable, '-c', code], cwd=tmp_path,
                                start_new_session=True)
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
            pytest.fail('scorer blocked on inherited pipe')
        pid = int((tmp_path / 'pid').read_text())
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
            time.sleep(.01)
        else:
            pytest.fail('owned child still alive')
    finally:
        if (tmp_path / 'pid').exists():
            pid = int((tmp_path / 'pid').read_text())
        if pid:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def test_memory_includes_owned_worker(scorer, tmp_path):
    try:
        psutil.pids()
    except (OSError, psutil.Error) as exc:
        pytest.skip(f'process accounting blocked: {exc}')
    result = scorer._run_command([sys.executable, '-c',
        "import subprocess,sys; p=subprocess.Popen([sys.executable,'-c',"
        "'import time; data=bytearray(80*1024*1024); time.sleep(0.7)']); p.wait()"],
        cwd=tmp_path, timeout_s=3)
    assert result['ok']
    assert result['peak_rss_mb'] > 75
    assert result['memory_scope'] == 'owned_process_group_sampled_rss'
    assert result['memory_complete'] is True


def test_missing_memory_evidence_cannot_score(scorer, tmp_path, monkeypatch):
    monkeypatch.setattr(scorer, '_rss_mb', lambda pid: None)
    result = scorer._run_command([sys.executable, '-c', 'import time; time.sleep(.1)'],
                                 cwd=tmp_path, timeout_s=3)
    assert result['peak_rss_mb'] is None
    combined = scorer._combined_score(bcubed={'f1': 1}, pairwise={'f1': 1},
        pr_curve={'average_precision': 1}, system_metrics=result)
    assert combined['value'] is None


def test_owned_group_accounting_uses_public_api(scorer, monkeypatch):
    from types import SimpleNamespace
    members = [SimpleNamespace(pid=1, status=lambda: 'running',
                               memory_info=lambda: SimpleNamespace(rss=3*1024*1024)),
               SimpleNamespace(pid=2, status=lambda: 'running',
                               memory_info=lambda: SimpleNamespace(rss=80*1024*1024)),
               SimpleNamespace(pid=3, status=lambda: 'running',
                               memory_info=lambda: SimpleNamespace(rss=900*1024*1024))]
    monkeypatch.setattr(scorer.psutil, 'process_iter', lambda: iter(members))
    monkeypatch.setattr(scorer.os, 'getpgid', lambda pid: 1 if pid < 3 else 3)
    assert scorer._rss_mb(1) == 83


def test_interrupt_reaps_leader_and_preserves_error(scorer, tmp_path, monkeypatch):
    real_spawn = scorer.subprocess.Popen
    leaders = []
    def spawn(*args, **kwargs):
        process = real_spawn(*args, **kwargs)
        leaders.append(process)
        return process
    monkeypatch.setattr(scorer.subprocess, 'Popen', spawn)
    def interrupt(pid):
        raise KeyboardInterrupt('primary')
    monkeypatch.setattr(scorer, '_rss_mb', interrupt)
    with pytest.raises(KeyboardInterrupt, match='primary'):
        scorer._run_command([sys.executable, '-c', 'import time; time.sleep(30)'],
                            cwd=tmp_path, timeout_s=3)
    assert leaders[0].poll() is not None
