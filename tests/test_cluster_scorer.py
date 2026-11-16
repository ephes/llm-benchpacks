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


@pytest.mark.parametrize('loader,name', [('_load_clusters', 'clusters.csv'),
    ('_load_pair_scores', 'pair_scores.csv'), ('_load_program_metrics', 'metrics.json')])
@pytest.mark.parametrize('kind', ['symlink', 'fifo', 'oversized', 'invalid-utf8'])
def test_prediction_file_open_admission(scorer, tmp_path, loader, name, kind, monkeypatch):
    path = tmp_path / name
    sentinel = tmp_path / 'sentinel'
    sentinel.write_text('private sentinel')
    if kind == 'symlink':
        path.symlink_to(sentinel)
    elif kind == 'fifo':
        os.mkfifo(path)
    elif kind == 'oversized':
        path.write_bytes(b'x' * (17 * 1024 * 1024))
    else:
        path.write_bytes(b'\xff')
    # Old FIFO readers would block; raise at their path.open to demonstrate the
    # unsafe reopen without ever entering a blocking read in the regression run.
    old_open = Path.open
    def guard(self, *args, **kwargs):
        if kind == 'fifo' and self == path:
            raise AssertionError('blocking path.open on FIFO')
        return old_open(self, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', guard)
    value, errors = getattr(scorer, loader)(path)
    assert errors
    assert not value
    assert 'private sentinel' not in str(errors)


@pytest.mark.parametrize('raw', ['{"n":NaN}', '{"n":Infinity}', '{"n":1e999}',
    '{"n":1,"n":2}', '{"a":{"n":1,"n":2}}', '{"s":"\\ud800"}',
    '[' * 1500 + '0' + ']' * 1500])
def test_strict_candidate_metrics(scorer, tmp_path, raw):
    path = tmp_path / 'metrics.json'
    path.write_text(raw)
    value, errors = scorer._load_program_metrics(path)
    assert value is None
    assert errors


def test_admission_exact_byte_row_and_aggregate_limits(scorer, tmp_path, monkeypatch):
    path = tmp_path / 'clusters.csv'
    raw = b'offer_id,cluster_id\na,c\n'
    path.write_bytes(raw)
    monkeypatch.setattr(scorer, 'PREDICTION_FILE_BYTES', len(raw), raising=False)
    monkeypatch.setattr(scorer, 'PREDICTION_ROWS', 1, raising=False)
    assert scorer._load_clusters(path) == ({'a': 'c'}, [])
    path.write_bytes(raw + b'b,c\n')
    assert scorer._load_clusters(path)[1]
    monkeypatch.setattr(scorer, 'EVIDENCE_TOTAL_BYTES', len(raw), raising=False)
    budget = scorer._EvidenceBudget()
    path.write_bytes(raw)
    assert not scorer._load_clusters(path, budget)[1]
    assert scorer._load_clusters(path, budget)[1]


def test_metrics_scalar_extensions_round_trip(scorer, tmp_path):
    import json
    path = tmp_path / 'metrics.json'
    path.write_text('{"custom":1.5,"yes":true,"label":"μ","empty":null,"nested":{}}')
    value, errors = scorer._load_program_metrics(path)
    assert not errors
    assert json.loads(json.dumps(value, allow_nan=False)) == {
        'custom': 1.5, 'yes': True, 'label': 'μ', 'empty': None}


def test_curve_matches_independent_threshold_oracle(scorer):
    import random
    rng = random.Random(10)
    for n in range(1, 30):
        ids = [str(i) for i in range(n)]
        labels = {i: rng.randrange(2) for i in ids}
        scores = {i: rng.randrange(5) / 4 for i in ids}
        curve, summary, errors = scorer._precision_recall_curve(
            expected_ids=ids, labels=labels, scores=scores)
        assert not errors
        previous_tp = 0
        ap = 0
        positives = sum(labels.values())
        for row, threshold in zip(curve, sorted(set(scores.values()), reverse=True)):
            tp = sum(labels[i] == 1 and scores[i] >= threshold for i in ids)
            fp = sum(labels[i] == 0 and scores[i] >= threshold for i in ids)
            fn = positives - tp
            tn = n - tp - fp - fn
            precision = tp / (tp+fp)
            recall = tp / positives if positives else 0
            f1 = 2*precision*recall/(precision+recall) if precision+recall else 0
            assert row == dict(threshold=threshold, tp=tp, fp=fp, tn=tn, fn=fn,
                precision=round(precision, 6), recall=round(recall, 6),
                f1=round(f1, 6), accuracy=round((tp+tn)/n, 6),
                positive_prevalence=round(positives/n, 6))
            ap += (tp-previous_tp) * precision / positives if positives else 0
            previous_tp = tp
        assert summary['average_precision'] == round(ap, 6)


def test_curve_classification_work_is_linear_after_sort(scorer):
    class Counted(dict):
        reads = 0
        def __getitem__(self, key):
            self.reads += 1
            return super().__getitem__(key)
        def values(self):
            self.reads += len(self)
            return super().values()
    ids = [str(i) for i in range(1000)]
    labels = Counted({i: int(i) % 2 for i in ids})
    scores = Counted({i: float(i) for i in ids})
    scorer._precision_recall_curve(expected_ids=ids, labels=labels, scores=scores)
    assert labels.reads < 10 * len(ids)
    assert scores.reads < 10 * len(ids)


def test_average_precision_is_invariant_within_ties(scorer):
    import itertools
    labels = {'p': 1, 'n': 0, 'p2': 1}
    scores = {'p': 1., 'n': 1., 'p2': 0.}
    for ids in itertools.permutations(labels):
        _, summary, _ = scorer._precision_recall_curve(
            expected_ids=list(ids), labels=labels, scores=scores)
        assert summary['average_precision'] == round((.5 + 2/3) / 2, 6)
    _, summary, _ = scorer._precision_recall_curve(
        expected_ids=['p', 'n'], labels={'p': 1, 'n': 0}, scores={'p': 1., 'n': 1.})
    assert summary['average_precision'] == .5
