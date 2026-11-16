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
    redirects = ",stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL" if redirect else ""
    candidate = (
        "import subprocess,sys,time; "
        "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']"
        + redirects + "); open('pid','w').write(str(p.pid))"
        + ("; time.sleep(30)" if timeout else "")
    )
    code = f"""import importlib.util, pathlib, sys
spec=importlib.util.spec_from_file_location('s', {str(SCORER.resolve())!r})
s=importlib.util.module_from_spec(spec); spec.loader.exec_module(s)
s._run_command([sys.executable, '-c', {candidate!r}], cwd=pathlib.Path('.'), timeout_s=0.3)
"""
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
                if psutil.Process(pid).status() == psutil.STATUS_ZOMBIE:
                    break
            except (ProcessLookupError, psutil.NoSuchProcess):
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


def test_member_exiting_during_sample_is_skipped(scorer, monkeypatch):
    from types import SimpleNamespace
    def gone():
        raise psutil.NoSuchProcess(2)
    def zombie():
        raise psutil.ZombieProcess(3)
    members = [SimpleNamespace(pid=1, status=lambda: 'running',
                               memory_info=lambda: SimpleNamespace(rss=5*1024*1024)),
               SimpleNamespace(pid=2, status=gone, memory_info=gone),
               SimpleNamespace(pid=3, status=zombie, memory_info=zombie)]
    monkeypatch.setattr(scorer.psutil, 'process_iter', lambda: iter(members))
    monkeypatch.setattr(scorer.os, 'getpgid', lambda pid: 1)
    assert scorer._rss_mb(1) == 5


def test_denied_member_accounting_fails_the_sample(scorer, monkeypatch):
    from types import SimpleNamespace
    def denied():
        raise psutil.AccessDenied(1)
    members = [SimpleNamespace(pid=1, status=denied, memory_info=denied)]
    monkeypatch.setattr(scorer.psutil, 'process_iter', lambda: iter(members))
    monkeypatch.setattr(scorer.os, 'getpgid', lambda pid: 1)
    assert scorer._rss_mb(1) is None


def test_leader_exit_inside_sample_keeps_memory_complete(scorer, tmp_path, monkeypatch):
    calls = []
    def sample(pid):
        calls.append(pid)
        if len(calls) == 1:
            return 7.0
        # Model the leader exiting inside the sampling window: it is an
        # unreaped zombie, so no group member is observable.
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                if psutil.Process(pid).status() == psutil.STATUS_ZOMBIE:
                    break
            except psutil.Error:
                break
            time.sleep(0.01)
        return None
    monkeypatch.setattr(scorer, '_rss_mb', sample)
    result = scorer._run_command([sys.executable, '-c', 'import time; time.sleep(.3)'],
                                 cwd=tmp_path, timeout_s=10)
    assert result['ok']
    assert len(calls) == 2
    assert result['memory_complete'] is True
    assert result['peak_rss_mb'] == 7.0


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
    # A valid sentinel would be accepted if the loader followed the symlink.
    sentinel.write_text({
        '_load_clusters': 'offer_id,cluster_id\nprivate,sentinel\n',
        '_load_pair_scores': 'pair_id,score\nprivate,1\n',
        '_load_program_metrics': '{"private":"sentinel"}',
    }[loader])
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


def run_synthetic_main(scorer, tmp_path, monkeypatch, clusters, pairs):
    import json
    workspace = tmp_path / 'workspace'
    workspace.mkdir(exist_ok=True)
    (workspace / 'clusters.csv').write_text(clusters)
    (workspace / 'pair_scores.csv').write_text(pairs)
    patch = tmp_path / 'patch'
    patch.write_text('synthetic change')
    trusted = {
        'test_offers.csv': [{'offer_id': 'a'}, {'offer_id': 'b'}],
        'eval_pairs.csv': [{'pair_id': 'p', 'offer_id_left': 'a', 'offer_id_right': 'b'}],
        'hidden_test_clusters.csv': [{'offer_id': 'a', 'cluster_id': 'c'},
                                     {'offer_id': 'b', 'cluster_id': 'c'}],
        'hidden_eval_pair_labels.csv': [{'pair_id': 'p', 'label': '1'}]}
    monkeypatch.setattr(scorer, '_read_csv', lambda p: trusted[p.name])
    monkeypatch.setattr(scorer, '_run_program', lambda *args: {
        'ok': True, 'duration_s': .5, 'peak_rss_mb': 12,
        'memory_scope': 'owned_process_group_sampled_rss',
        'memory_complete': True, 'memory_samples': 2})
    output = tmp_path / 'verify.json'
    monkeypatch.setattr(sys, 'argv', ['score', '--workspace', str(workspace),
        '--case', 'synthetic-python', '--pack-id', 'synthetic', '--pack-version', '0.1',
        '--source-fixture-id', 'synthetic', '--patch', str(patch), '--output', str(output)])
    code = scorer.main()
    return code, json.loads(output.read_text())


@pytest.mark.parametrize('clusters,pairs', [
    ('offer_id,cluster_id\n', 'pair_id,score\np,1\n'),
    ('offer_id,cluster_id\na,c\na,c\nb,c\n', 'pair_id,score\np,1\n'),
    ('offer_id,cluster_id\na,c\nb,c\n', 'pair_id,score\n'),
    ('offer_id,cluster_id\na,c\nb,c\n', 'pair_id,score\np,1\np,0\n')])
def test_invalid_predictions_never_receive_quality(scorer, tmp_path, monkeypatch, clusters, pairs):
    def forbidden(**kwargs):
        pytest.fail('quality calculation reached with invalid evidence')
    monkeypatch.setattr(scorer, '_bcubed_metrics', forbidden)
    code, payload = run_synthetic_main(scorer, tmp_path, monkeypatch, clusters, pairs)
    assert code == 1
    assert not payload['passed']
    assert payload['prediction_errors']
    assert payload.get('metrics') is None
    assert payload['combined_score']['value'] is None
    assert payload['system_metrics']['program_duration_s'] == .5
    assert payload.get('pr_curve') is None


def test_complete_wrong_predictions_still_receive_quality(scorer, tmp_path, monkeypatch):
    _, payload = run_synthetic_main(scorer, tmp_path, monkeypatch,
        'offer_id,cluster_id\na,c1\nb,c2\n', 'pair_id,score\np,0\n')
    assert payload['prediction_errors'] == []
    assert payload['metrics']['pairwise_cluster']['f1'] == 0
    assert isinstance(payload['combined_score']['value'], float)


def test_missing_cluster_endpoints_are_not_equal(scorer):
    metrics = scorer._eval_cluster_operating_point(eval_pairs=[{
        'pair_id': 'p', 'offer_id_left': 'a', 'offer_id_right': 'b'}],
        pair_labels={'p': 0}, predicted_clusters={})
    assert metrics['fp'] == 0


@pytest.mark.parametrize('failure', ['curve-write', 'json-write', 'curve-replace', 'json-replace', 'serialize'])
def test_result_publication_preserves_previous_generation(scorer, tmp_path, monkeypatch, failure):
    import json
    output = tmp_path / 'verify.json'
    old_curve = tmp_path / 'old.csv'
    old_curve.write_bytes(b'old exact curve\n')
    old_payload = {'passed': True, 'pr_curve': {'path': str(old_curve)}}
    output.write_text(json.dumps(old_payload))
    previous = output.read_bytes()
    payload = {'passed': True, 'pr_curve': {'points': 0}}
    if failure == 'serialize':
        payload['bad'] = float('nan')
    if failure == 'curve-write':
        monkeypatch.setattr(scorer, '_write_pr_curve', lambda *args: (_ for _ in ()).throw(OSError('curve')))
    real_write = Path.write_text
    def write(self, *args, **kwargs):
        if failure == 'json-write' and self != output:
            raise OSError('json')
        return real_write(self, *args, **kwargs)
    monkeypatch.setattr(Path, 'write_text', write)
    replace = scorer.os.replace
    def fail_replace(src, dst):
        if (failure == 'json-replace' and Path(dst) == output or
            failure == 'curve-replace' and str(dst).endswith('.pr-curve.csv')):
            raise OSError('replace')
        return replace(src, dst)
    monkeypatch.setattr(scorer.os, 'replace', fail_replace)
    with pytest.raises((OSError, ValueError)):
        scorer._publish_result(output, payload, [])
    assert output.read_bytes() == previous
    assert old_curve.read_bytes() == b'old exact curve\n'


def test_generation_reference_survives_outer_normalization(scorer, tmp_path):
    import json
    from benchpack.verifiers import _write_authoritative_json
    output = tmp_path / 'verify.json'
    scorer._publish_result(output, {'passed': True, 'pr_curve': {'points': 0}}, [])
    payload = json.loads(output.read_text())
    curve = Path(payload['pr_curve']['path'])
    assert curve.exists()
    before = curve.read_bytes()
    _write_authoritative_json(output, exit_code=0, passed=True)
    assert json.loads(output.read_text())['pr_curve']['path'] == str(curve)
    assert curve.read_bytes() == before


def test_all_missed_short_lived_samples_are_unavailable(scorer, tmp_path, monkeypatch):
    real_spawn = scorer.subprocess.Popen
    def completed(*args, **kwargs):
        process = real_spawn(*args, **kwargs)
        process.wait(timeout=3)
        return process
    monkeypatch.setattr(scorer.subprocess, 'Popen', completed)
    result = scorer._run_command([sys.executable, '-c', 'pass'], cwd=tmp_path, timeout_s=3)
    assert result['ok']
    assert result['memory_samples'] == 0
    assert result['memory_complete'] is False
    assert result['peak_rss_mb'] is None


def test_changed_opened_prediction_generation_is_refused(scorer, tmp_path, monkeypatch):
    path = tmp_path / 'clusters.csv'
    path.write_text('offer_id,cluster_id\na,c\n')
    read = scorer.os.read
    mutated = False
    def change(fd, count):
        nonlocal mutated
        result = read(fd, count)
        if not mutated:
            mutated = True
            with path.open('ab') as handle:
                handle.write(b'b,c\n')
        return result
    monkeypatch.setattr(scorer.os, 'read', change)
    value, errors = scorer._load_clusters(path)
    assert not value
    assert errors


def test_shared_evidence_row_budget(scorer, tmp_path, monkeypatch):
    monkeypatch.setattr(scorer, 'EVIDENCE_TOTAL_ROWS', 1)
    clusters, scores = tmp_path / 'clusters.csv', tmp_path / 'pair_scores.csv'
    clusters.write_text('offer_id,cluster_id\na,c\n')
    scores.write_text('pair_id,score\np,1\n')
    budget = scorer._EvidenceBudget()
    assert scorer._load_clusters(clusters, budget) == ({'a': 'c'}, [])
    assert scorer._load_pair_scores(scores, budget)[1]
