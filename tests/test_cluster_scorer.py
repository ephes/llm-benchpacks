"""Synthetic regressions for the pack-local candidate evidence boundary."""
import importlib.util
import os
import signal
import subprocess
import sys
import time
from fractions import Fraction
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


@pytest.mark.parametrize('signum', [signal.SIGTERM, signal.SIGHUP])
def test_group_signal_to_scorer_retires_candidate_session(tmp_path, signum):
    # The outer verifier signals the scorer's group; the candidate has its own
    # session and is only retired if the scorer unwinds through its cleanup.
    workspace = tmp_path / 'workspace'
    (workspace / 'data').mkdir(parents=True)
    (workspace / 'data' / 'eval_pairs.csv').write_text('pair_id,offer_id_left,offer_id_right\np,a,b\n')
    (workspace / 'data' / 'test_offers.csv').write_text('offer_id\na\nb\n')
    (tmp_path / 'hidden_test_clusters.csv').write_text('offer_id,cluster_id\na,c\nb,c\n')
    (tmp_path / 'hidden_eval_pair_labels.csv').write_text('pair_id,label\np,1\n')
    pid_file = tmp_path / 'pid'
    candidate = (f"import os,time; open({str(pid_file)!r},'w').write(str(os.getpid())); "
                 "time.sleep(30)")
    code = f"""import importlib.util, sys
spec=importlib.util.spec_from_file_location('s', {str(SCORER.resolve())!r})
s=importlib.util.module_from_spec(spec); spec.loader.exec_module(s)
s.__file__ = {str(tmp_path / 'score_clusters.py')!r}
s._run_program = lambda w, c, o: s._run_command([sys.executable, '-c', {candidate!r}], cwd=w, timeout_s=30)
sys.argv = ['score', '--workspace', {str(workspace)!r}, '--case', 'c', '--pack-id', 'p',
            '--pack-version', '1', '--source-fixture-id', 'f', '--patch', 'missing.patch',
            '--output', {str(tmp_path / 'out' / 'result.json')!r}]
s.main()
"""
    pid = None
    proc = subprocess.Popen([sys.executable, '-c', code], cwd=tmp_path, start_new_session=True)
    try:
        deadline = time.monotonic() + 10
        while not (pid_file.exists() and pid_file.read_text()):
            if time.monotonic() >= deadline or proc.poll() is not None:
                pytest.fail('candidate did not start')
            time.sleep(.01)
        pid = int(pid_file.read_text())
        os.killpg(proc.pid, signum)
        proc.wait(timeout=5)
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            try:
                if psutil.Process(pid).status() == psutil.STATUS_ZOMBIE:
                    break
            except psutil.NoSuchProcess:
                break
            time.sleep(.01)
        else:
            pytest.fail('candidate session survived the scorer signal')
    finally:
        for target in (pid, proc.pid):
            if target:
                try:
                    os.kill(target, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        proc.wait()


@pytest.mark.parametrize('window', ['after_spawn', 'before_retire'])
def test_signal_in_cleanup_windows_still_retires_candidate(scorer, tmp_path, monkeypatch, window):
    leaders = []
    real_spawn = scorer.subprocess.Popen
    real_retire = scorer._retire
    def spawn(*args, **kwargs):
        process = real_spawn(*args, **kwargs)
        leaders.append(process)
        if window == 'after_spawn':
            scorer._terminate(signal.SIGTERM, None)
        return process
    def retire(process):
        if window == 'before_retire':
            scorer._terminate(signal.SIGTERM, None)
        real_retire(process)
    monkeypatch.setattr(scorer.subprocess, 'Popen', spawn)
    monkeypatch.setattr(scorer, '_retire', retire)
    try:
        with pytest.raises(SystemExit) as stopped:
            scorer._run_command([sys.executable, '-c', 'import time; time.sleep(30)'],
                                cwd=tmp_path, timeout_s=0.2 if window == 'before_retire' else 30)
        assert stopped.value.code == 128 + signal.SIGTERM
        assert leaders[0].poll() is not None
    finally:
        for leader in leaders:
            if leader.poll() is None:
                leader.kill()
                leader.wait()


def test_signal_outside_owned_run_exits_immediately(scorer):
    with pytest.raises(SystemExit) as stopped:
        scorer._terminate(signal.SIGHUP, None)
    assert stopped.value.code == 128 + signal.SIGHUP


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

            def exact(num, den):
                return float(round(Fraction(num, den), 6)) if den else 0.0

            assert row == dict(threshold=threshold, tp=tp, fp=fp, tn=tn, fn=fn,
                precision=exact(tp, tp+fp), recall=exact(tp, positives),
                f1=exact(2*tp, tp+fp+positives), accuracy=exact(tp+tn, n),
                positive_prevalence=exact(positives, n))
            ap += (tp-previous_tp) * precision / positives if positives else 0
            previous_tp = tp
        assert summary['average_precision'] == round(ap, 6)


@pytest.mark.parametrize('counts,best_threshold', [
    ([(5000, 5001), (1, 3), (4999, 20000)], 2),  # 10002/20005 > 10000/20001
    ([(1, 1), (1, 3)], 3),  # Both thresholds have exact F1 of 1/2.
    ([(53, 3), (53, 203), (94, 400)], 3),  # Exact F1 53/128 at both rows.
])
def test_curve_selects_exact_best_threshold(scorer, counts, best_threshold):
    labels = {}
    scores = {}
    for offset, (positives, negatives) in enumerate(counts):
        for match in [1] * positives + [0] * negatives:
            pair_id = str(len(labels))
            labels[pair_id] = match
            scores[pair_id] = float(3 - offset)

    curve, summary, errors = scorer._precision_recall_curve(
        expected_ids=list(labels), labels=labels, scores=scores,
    )
    assert not errors
    assert curve[0]['f1'] == curve[1]['f1']
    assert summary['best_hidden']['threshold'] == best_threshold
    assert summary['best_hidden']['f1'] == curve[0]['f1']


def test_curve_rounds_exact_ratio_midpoints_half_even(scorer):
    # 8004/12800 = 0.6253125 exactly; the float is slightly above it.
    labels = {}
    scores = {}
    for score, (positives, negatives) in [(1.0, (4002, 3798)), (0.0, (998, 0))]:
        for match in [1] * positives + [0] * negatives:
            pair_id = str(len(labels))
            labels[pair_id] = match
            scores[pair_id] = score
    curve, _summary, errors = scorer._precision_recall_curve(
        expected_ids=list(labels), labels=labels, scores=scores,
    )
    assert not errors
    assert curve[0]['f1'] == 0.625312
    metrics = scorer._binary_metrics(
        expected_ids=list(labels), labels=labels,
        predictions={pair_id: int(score == 1.0) for pair_id, score in scores.items()},
    )
    assert metrics['f1'] == 0.625312


def test_best_threshold_keeps_full_precision(scorer, tmp_path):
    import csv
    cutoff = 0.9999999999999
    labels = {'a': 1, 'b': 1, 'c': 0}
    scores = {'a': 1.0, 'b': cutoff, 'c': 0.5}
    curve, summary, errors = scorer._precision_recall_curve(
        expected_ids=list(labels), labels=labels, scores=scores,
    )
    assert not errors
    assert summary['best_hidden']['threshold'] == cutoff
    path = tmp_path / 'curve.csv'
    scorer._write_pr_curve(path, curve)
    with path.open(newline='') as handle:
        rows = list(csv.DictReader(handle))
    assert [float(row['threshold']) for row in rows] == [1.0, cutoff, 0.5]


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


def synthetic_fixtures():
    return {
        'test_offers.csv': [{'offer_id': 'a'}, {'offer_id': 'b'}],
        'eval_pairs.csv': [{'pair_id': 'p', 'offer_id_left': 'a', 'offer_id_right': 'b'}],
        'hidden_test_clusters.csv': [{'offer_id': 'a', 'cluster_id': 'c'},
                                     {'offer_id': 'b', 'cluster_id': 'c'}],
        'hidden_eval_pair_labels.csv': [{'pair_id': 'p', 'label': '1'}]}


def run_synthetic_main(scorer, tmp_path, monkeypatch, clusters, pairs, *, fixtures=None):
    import json
    workspace = tmp_path / 'workspace'
    workspace.mkdir(exist_ok=True)
    (workspace / 'clusters.csv').write_text(clusters)
    (workspace / 'pair_scores.csv').write_text(pairs)
    patch = tmp_path / 'patch'
    patch.write_text('synthetic change')
    fixtures = synthetic_fixtures() if fixtures is None else fixtures
    monkeypatch.setattr(scorer, '_read_csv', lambda p: fixtures[p.name])
    output = tmp_path / 'verify.json'
    monkeypatch.setattr(sys, 'argv', ['score', '--workspace', str(workspace),
        '--case', 'synthetic-python', '--pack-id', 'synthetic', '--pack-version', '0.1',
        '--source-fixture-id', 'synthetic', '--patch', str(patch), '--output', str(output)])
    code = scorer.main()
    return code, json.loads(output.read_text())


@pytest.fixture
def successful_program(scorer, monkeypatch):
    monkeypatch.setattr(scorer, '_run_program', lambda *args: {
        'ok': True, 'duration_s': .5, 'peak_rss_mb': 12,
        'memory_scope': 'owned_process_group_sampled_rss',
        'memory_complete': True, 'memory_samples': 2})


@pytest.mark.parametrize('filename,problem,diagnostic', [
    ('test_offers.csv', 'duplicate', 'duplicate offer_id'),
    ('eval_pairs.csv', 'duplicate', 'duplicate pair_id'),
    ('hidden_test_clusters.csv', 'duplicate', 'duplicate offer_id'),
    ('hidden_eval_pair_labels.csv', 'duplicate', 'duplicate pair_id'),
    ('hidden_test_clusters.csv', 'missing', 'missing 1 expected ids'),
    ('hidden_eval_pair_labels.csv', 'extra', 'contains 1 unknown ids'),
    ('eval_pairs.csv', 'dangling', 'unknown offer_id_right'),
])
def test_invalid_fixture_identities_stop_before_candidate(
    scorer, tmp_path, monkeypatch, filename, problem, diagnostic,
):
    fixtures = synthetic_fixtures()
    rows = fixtures[filename]
    if problem == 'duplicate':
        rows.append(rows[0].copy())
    elif problem == 'missing':
        rows.pop()
    elif problem == 'extra':
        rows.append({'pair_id': 'extra', 'label': '0'})
    elif problem == 'dangling':
        rows[0]['offer_id_right'] = 'unknown'

    def forbidden(*args):
        pytest.fail('candidate ran with invalid fixture identities')

    monkeypatch.setattr(scorer, '_run_program', forbidden)
    code, payload = run_synthetic_main(scorer, tmp_path, monkeypatch, '', '', fixtures=fixtures)
    assert code == 1
    assert payload['passed'] is False
    assert payload['error'] == 'invalid scoring fixtures'
    assert filename in payload['fixture_errors'][0]
    assert diagnostic in payload['fixture_errors'][0]
    assert 'program' not in payload


@pytest.mark.parametrize('clusters,pairs', [
    ('offer_id,cluster_id\n', 'pair_id,score\np,1\n'),
    ('offer_id,cluster_id\na,c\na,c\nb,c\n', 'pair_id,score\np,1\n'),
    ('offer_id,cluster_id\na,c\nb,c\n', 'pair_id,score\n'),
    ('offer_id,cluster_id\na,c\nb,c\n', 'pair_id,score\np,1\np,0\n')])
def test_invalid_predictions_never_receive_quality(scorer, tmp_path, monkeypatch, successful_program, clusters, pairs):
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


def test_complete_wrong_predictions_still_receive_quality(scorer, tmp_path, monkeypatch, successful_program):
    _, payload = run_synthetic_main(scorer, tmp_path, monkeypatch,
        'offer_id,cluster_id\na,c1\nb,c2\n', 'pair_id,score\np,0\n')
    assert payload['prediction_errors'] == []
    assert payload['metrics']['pairwise_cluster']['f1'] == 0
    assert isinstance(payload['combined_score']['value'], float)


def run_synthetic_partition(scorer, tmp_path, monkeypatch, truth, predicted):
    fixtures = synthetic_fixtures()
    partitions = list(enumerate(zip(truth, predicted, strict=True)))
    fixtures['test_offers.csv'] = [{'offer_id': str(i)} for i, _ in partitions]
    fixtures['hidden_test_clusters.csv'] = [
        {'offer_id': str(i), 'cluster_id': gold} for i, (gold, _) in partitions
    ]
    fixtures['eval_pairs.csv'][0].update(offer_id_left='0', offer_id_right='1')
    cluster_csv = 'offer_id,cluster_id\n' + ''.join(
        f'{i},{cluster}\n' for i, (_, cluster) in partitions
    )
    return run_synthetic_main(
        scorer, tmp_path, monkeypatch, cluster_csv, 'pair_id,score\np,1\n', fixtures=fixtures,
    )


@pytest.mark.parametrize('fp_offset', [-1, 0, 1])
def test_pairwise_minimum_uses_exact_f1(scorer, tmp_path, monkeypatch, successful_program, fp_offset):
    truth = ['correct'] * 500 + [f'single-{i}' for i in range(3500)]
    predicted = ['correct'] * 500
    # The three false merges contribute 997,999 pairs. Each extra merge adds one.
    for size in (1413, 29, 6):
        predicted.extend([f'merged-{size}'] * size)
    predicted.extend(truth[len(predicted):])
    for i in range(fp_offset + 1):
        predicted[-2 - 2 * i] = predicted[-1 - 2 * i]

    code, payload = run_synthetic_partition(scorer, tmp_path, monkeypatch, truth, predicted)
    pairwise = payload['metrics']['pairwise_cluster']
    assert (pairwise['tp_pairs'], pairwise['fp_pairs'], pairwise['fn_pairs']) == (
        124750, 998000 + fp_offset, 0,
    )
    assert pairwise['f1'] == payload['thresholds']['pairwise_cluster_f1_min'] == 0.20
    assert payload['metrics']['bcubed']['f1'] > 0.70
    assert payload['passed'] is (fp_offset <= 0)
    assert code == int(fp_offset > 0)


@pytest.mark.parametrize('size_offset', [-1, 0, 1])
def test_bcubed_minimum_uses_exact_f1(scorer, tmp_path, monkeypatch, successful_program, size_offset):
    # At offset zero, precision is (2027 + 2 + 1) / 3770 = 7/13 and
    # recall is 1. Moving a singleton between the two merged groups changes
    # exact F1 while both variants still round to 0.70.
    truth = ['correct'] * 2027 + ['mixed'] * 30 + [f'single-{i}' for i in range(1713)]
    predicted = ['correct'] * 2027 + ['mixed'] * (870 + size_offset) + ['merged'] * (873 - size_offset)

    code, payload = run_synthetic_partition(scorer, tmp_path, monkeypatch, truth, predicted)
    assert payload['metrics']['bcubed']['f1'] == payload['thresholds']['bcubed_f1_min'] == 0.70
    assert payload['metrics']['pairwise_cluster']['f1'] > 0.20
    assert payload['passed'] is (size_offset <= 0)
    assert code == int(size_offset > 0)


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


def test_result_publication_retains_curve_after_json_rename(scorer, tmp_path, monkeypatch):
    import json

    output = tmp_path / 'verify.json'
    replace = scorer.os.replace

    def interrupt_after_replace(src, dst):
        replace(src, dst)
        if Path(dst) == output:
            raise SystemExit(143)

    monkeypatch.setattr(scorer.os, 'replace', interrupt_after_replace)
    with pytest.raises(SystemExit) as interrupted:
        scorer._publish_result(output, {'passed': True, 'pr_curve': {'points': 0}}, [])
    assert interrupted.value.code == 143

    published = json.loads(output.read_text())
    assert published['passed'] is True
    assert Path(published['pr_curve']['path']).read_text().splitlines() == [
        'threshold,precision,recall,f1,accuracy,tp,fp,tn,fn,positive_prevalence',
    ]


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
