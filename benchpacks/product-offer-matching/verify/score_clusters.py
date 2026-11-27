from __future__ import annotations

import argparse
import csv
import json
import io
import math
import os
import selectors
import signal
import stat
import subprocess
import sys
import time
import tempfile
import uuid
from collections import Counter, defaultdict
from pathlib import Path
from itertools import groupby
from typing import Any

import psutil


BCUBED_F1_MIN = 0.70
PAIRWISE_CLUSTER_F1_MIN = 0.20
PROGRAM_TIMEOUT_S = 60.0


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


OUTPUT_TAIL_BYTES = 65536
# Drain up to 1 MiB per stream between RSS samples, so a full process scan does
# not throttle verbose candidates while deadline checks still run regularly.
DRAIN_READS_PER_SAMPLE = 16
CLEANUP_GRACE_S = 0.5


_stop_signal: int | None = None
_owned_runs = 0


def _terminate(signum: int, _frame: object) -> None:
    # The candidate runs in its own session, so a group signal to the scorer
    # does not reach it. During an owned run only record the request: the run
    # loop stops and retires the candidate before _run_command exits.
    global _stop_signal
    _stop_signal = signum
    if not _owned_runs:
        raise SystemExit(128 + signum)


def _rss_mb(pgid: int) -> float | None:
    """Sample the sum of resident bytes in the owned POSIX process group."""
    total = 0
    observed = False
    try:
        for process in psutil.process_iter():
            try:
                if os.getpgid(process.pid) != pgid:
                    continue
            except ProcessLookupError:
                continue
            # A member exiting mid-sample is a normal exit, not missing accounting
            # (ZombieProcess is a NoSuchProcess); AccessDenied still fails the sample.
            try:
                if process.status() == psutil.STATUS_ZOMBIE:
                    continue
                total += process.memory_info().rss
                observed = True
            except psutil.NoSuchProcess:
                continue
    except (OSError, psutil.Error):
        return None
    return total / (1024 * 1024) if observed else None


def _retire(process: subprocess.Popen) -> None:
    # Kill the group even after the leader exits: descendants may own pipes or
    # have redirected them. Never wait for descendant EOF during cleanup.
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except PermissionError:
        if process.poll() is None:
            raise
    process.wait(timeout=CLEANUP_GRACE_S)


def _run_command(
    command: list[str],
    *,
    cwd: Path,
    timeout_s: float,
) -> dict[str, Any]:
    global _owned_runs
    _owned_runs += 1
    try:
        result = _run_owned(command, cwd=cwd, timeout_s=timeout_s)
    finally:
        _owned_runs -= 1
    if _stop_signal is not None:
        raise SystemExit(128 + _stop_signal)
    return result


def _run_owned(
    command: list[str],
    *,
    cwd: Path,
    timeout_s: float,
) -> dict[str, Any]:
    started = time.monotonic()
    if _stop_signal is not None:
        return {"ok": False, "phase": "spawn", "command": command,
                "error": "scorer stopping", "duration_s": 0.0}
    try:
        process = subprocess.Popen(
            command, cwd=cwd, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            start_new_session=True, bufsize=0,
        )
    except OSError as exc:
        return {"ok": False, "phase": "spawn", "command": command,
                "error": str(exc), "duration_s": time.monotonic() - started}

    tails = [bytearray(), bytearray()]
    peak = None
    samples = 0
    memory_complete = True
    timed_out = False
    cleanup_error = None
    selector = None
    try:
        selector = selectors.DefaultSelector()
        for index, stream in enumerate((process.stdout, process.stderr)):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, index)
        deadline = started + timeout_s
        while process.poll() is None:
            if _stop_signal is not None:
                break
            if time.monotonic() >= deadline:
                timed_out = True
                break
            rss = _rss_mb(process.pid)
            if rss is None:
                # The leader exiting inside the sampling window ends the run; only
                # an unobservable group that is still running is missing evidence.
                if process.poll() is not None:
                    break
                memory_complete = False
            else:
                samples += 1
                peak = max(peak or 0.0, rss)
            for key, _ in selector.select(max(0, min(0.02, deadline - time.monotonic()))):
                for _ in range(DRAIN_READS_PER_SAMPLE):
                    try:
                        chunk = os.read(key.fd, OUTPUT_TAIL_BYTES)
                    except BlockingIOError:
                        break
                    if not chunk:
                        selector.unregister(key.fileobj)
                        break
                    tails[key.data].extend(chunk)
                    del tails[key.data][:-OUTPUT_TAIL_BYTES]
    finally:
        # Cleanup must preserve KeyboardInterrupt/read errors and has a fixed
        # wait budget; success still retires any remaining group members.
        try:
            _retire(process)
        except (OSError, subprocess.TimeoutExpired) as exc:
            cleanup_error = type(exc).__name__
        if selector is not None:
            # Read at most one retained tail after retirement; an escaped pipe
            # holder cannot force an unbounded EOF wait here.
            for key in list(selector.get_map().values()):
                try:
                    chunk = os.read(key.fd, OUTPUT_TAIL_BYTES)
                    tails[key.data].extend(chunk)
                    del tails[key.data][:-OUTPUT_TAIL_BYTES]
                except OSError:
                    pass
            selector.close()
        process.stdout.close()
        process.stderr.close()

    complete = memory_complete and samples > 0 and peak is not None and peak > 0
    return {
        "ok": process.returncode == 0 and not timed_out and cleanup_error is None,
        "phase": "run", "command": command, "exit_code": process.returncode,
        "timed_out": timed_out, "timeout_s": timeout_s,
        "stdout": tails[0].decode("utf-8", errors="replace"),
        "stderr": tails[1].decode("utf-8", errors="replace"),
        "duration_s": time.monotonic() - started,
        "peak_rss_mb": round(peak, 3) if complete else None,
        "memory_scope": "owned_process_group_sampled_rss",
        "memory_complete": complete, "memory_samples": samples,
        "cleanup_error": cleanup_error,
    }


def _run_program(workspace: Path, case_id: str, output_root: Path) -> dict[str, Any]:
    for relative in [
        "clusters.csv",
        "pair_scores.csv",
        "metrics.json",
    ]:
        try:
            (workspace / relative).unlink()
        except FileNotFoundError:
            pass

    if case_id.endswith("-python"):
        command = [
            sys.executable,
            "clusterer.py",
            "--train",
            "data/train_offers.csv",
            "--predict",
            "data/test_offers.csv",
            "--output",
            "clusters.csv",
            "--pair-input",
            "data/eval_pairs.csv",
            "--pair-scores",
            "pair_scores.csv",
        ]
    elif case_id.endswith("-rust"):
        binary = output_root / "clusterer-rust"
        compile_command = ["rustc", "clusterer.rs", "-O", "-o", str(binary)]
        compile_result = _run_command(
            compile_command,
            cwd=workspace,
            timeout_s=PROGRAM_TIMEOUT_S,
        )
        if not compile_result.get("ok"):
            return {**compile_result, "ok": False, "phase": "compile"}
        command = [
            str(binary),
            "--train",
            "data/train_offers.csv",
            "--predict",
            "data/test_offers.csv",
            "--output",
            "clusters.csv",
            "--pair-input",
            "data/eval_pairs.csv",
            "--pair-scores",
            "pair_scores.csv",
        ]
    else:
        return {"ok": False, "phase": "select", "error": f"unknown case {case_id}"}

    result = _run_command(command, cwd=workspace, timeout_s=PROGRAM_TIMEOUT_S)
    result["clusters_path"] = str(workspace / "clusters.csv")
    result["pair_scores_path"] = str(workspace / "pair_scores.csv")
    result["metrics_path"] = str(workspace / "metrics.json")
    return result


PREDICTION_FILE_BYTES = 16 * 1024 * 1024
METRICS_FILE_BYTES = 64 * 1024
EVIDENCE_TOTAL_BYTES = 32 * 1024 * 1024
PREDICTION_ROWS = 100_000
EVIDENCE_TOTAL_ROWS = 200_000
MAX_ERRORS = 20


class _EvidenceBudget:
    def __init__(self):
        self.bytes = 0
        self.rows = 0


def _read_evidence(path: Path, budget: _EvidenceBudget, limit: int) -> str:
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("expected regular file")
        available = min(limit, EVIDENCE_TOTAL_BYTES - budget.bytes)
        if before.st_size > available:
            raise ValueError("evidence byte budget exceeded")
        data = bytearray()
        while len(data) <= available:
            chunk = os.read(fd, min(65536, available + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
        budget.bytes += len(data)
        after = os.fstat(fd)
        identity = lambda st: (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)
        if len(data) > available or len(data) != before.st_size or identity(before) != identity(after):
            raise ValueError("evidence changed or exceeded budget")
        return data.decode("utf-8")
    finally:
        os.close(fd)


def _prediction_csv(path: Path, fields: list[str], budget: _EvidenceBudget):
    reader = csv.DictReader(io.StringIO(_read_evidence(path, budget, PREDICTION_FILE_BYTES), newline=""))
    if reader.fieldnames != fields:
        raise ValueError("unexpected CSV header")
    for index, row in enumerate(reader, start=1):
        budget.rows += 1
        if index > PREDICTION_ROWS or budget.rows > EVIDENCE_TOTAL_ROWS:
            raise ValueError("evidence row budget exceeded")
        if None in row or any(value is None for value in row.values()):
            raise ValueError("unexpected CSV row width")
        yield row


def _load_clusters(path: Path, budget: _EvidenceBudget | None = None) -> tuple[dict[str, str], list[str]]:
    clusters = {}
    errors = []
    try:
        for index, row in enumerate(_prediction_csv(path, ["offer_id", "cluster_id"], budget or _EvidenceBudget()), 2):
            offer_id, cluster_id = row["offer_id"].strip(), row["cluster_id"].strip()
            if not offer_id or not cluster_id:
                errors.append(f"clusters row {index} has blank id")
            elif offer_id in clusters:
                errors.append(f"clusters row {index} duplicates offer_id")
            else:
                clusters[offer_id] = cluster_id
            if len(errors) >= MAX_ERRORS:
                break
    except (OSError, ValueError, csv.Error) as exc:
        return {}, [f"clusters.csv evidence refused ({type(exc).__name__})"]
    return clusters, errors


def _load_pair_scores(path: Path, budget: _EvidenceBudget | None = None) -> tuple[dict[str, float], list[str]]:
    scores = {}
    errors = []
    try:
        for index, row in enumerate(_prediction_csv(path, ["pair_id", "score"], budget or _EvidenceBudget()), 2):
            pair_id = row["pair_id"].strip()
            try:
                score = float(row["score"])
                valid = math.isfinite(score)
            except ValueError:
                valid = False
            if not pair_id or not valid:
                errors.append(f"scores row {index} has invalid id/score")
            elif pair_id in scores:
                errors.append(f"scores row {index} duplicates pair_id")
            else:
                scores[pair_id] = score
            if len(errors) >= MAX_ERRORS:
                break
    except (OSError, ValueError, csv.Error) as exc:
        return {}, [f"pair_scores.csv evidence refused ({type(exc).__name__})"]
    return scores, errors


def _unique_members(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate metrics member")
        result[key] = value
    return result


def _finite_float(text):
    value = float(text)
    if not math.isfinite(value):
        raise ValueError("nonfinite metrics number")
    return value


def _invalid_constant(text):
    raise ValueError("nonfinite metrics constant")


def _load_program_metrics(path: Path, budget: _EvidenceBudget | None = None) -> tuple[dict[str, Any] | None, list[str]]:
    try:
        raw = _read_evidence(path, budget or _EvidenceBudget(), METRICS_FILE_BYTES)
        loaded = json.loads(raw, object_pairs_hook=_unique_members,
                            parse_float=_finite_float, parse_constant=_invalid_constant)
        if not isinstance(loaded, dict) or len(loaded) > 128:
            raise ValueError("expected bounded metrics object")
        allowed = {}
        for key, value in loaded.items():
            if len(key.encode("utf-8")) > 128:
                raise ValueError("metrics key too long")
            if isinstance(value, str) and len(value.encode("utf-8")) > 4096:
                raise ValueError("metrics string too long")
            if isinstance(value, (str, int, float, bool)) or value is None:
                allowed[key] = value
        json.dumps(allowed, allow_nan=False)
        return allowed, []
    except FileNotFoundError:
        return None, []
    except (OSError, ValueError, RecursionError, OverflowError, MemoryError) as exc:
        return None, [f"metrics.json evidence refused ({type(exc).__name__})"]


def _validate_expected_ids(
    *,
    expected_ids: list[str],
    actual_ids: set[str],
    output_name: str,
) -> list[str]:
    expected_set = set(expected_ids)
    missing = sorted(expected_set - actual_ids)
    extra = sorted(actual_ids - expected_set)
    errors: list[str] = []
    if missing:
        errors.append(f"{output_name} missing {len(missing)} expected ids")
    if extra:
        errors.append(f"{output_name} contains {len(extra)} unknown ids")
    return errors


def _fixture_rows_by_id(path: Path, column: str) -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    for line, row in enumerate(_read_csv(path), start=2):
        row_id = row.get(column)
        if not row_id or not row_id.strip():
            raise ValueError(f"{path.name} row {line} missing {column}")
        if row_id in rows:
            raise ValueError(f"{path.name} row {line} has duplicate {column}")
        rows[row_id] = row
    return rows


def _load_scoring_fixtures(
    test_path: Path, eval_pairs_path: Path, hidden_clusters_path: Path, hidden_pairs_path: Path,
) -> tuple[list[str], list[dict[str, str]], dict[str, str], dict[str, int]]:
    offer_ids = list(_fixture_rows_by_id(test_path, "offer_id"))
    eval_pairs = _fixture_rows_by_id(eval_pairs_path, "pair_id")
    hidden_clusters = _fixture_rows_by_id(hidden_clusters_path, "offer_id")
    hidden_pairs = _fixture_rows_by_id(hidden_pairs_path, "pair_id")
    errors = _validate_expected_ids(
        expected_ids=offer_ids, actual_ids=set(hidden_clusters), output_name=hidden_clusters_path.name,
    ) + _validate_expected_ids(
        expected_ids=list(eval_pairs), actual_ids=set(hidden_pairs), output_name=hidden_pairs_path.name,
    )
    if errors:
        raise ValueError("; ".join(errors))
    for line, row in enumerate(eval_pairs.values(), start=2):
        for endpoint in ("offer_id_left", "offer_id_right"):
            if row.get(endpoint) not in hidden_clusters:
                raise ValueError(f"{eval_pairs_path.name} row {line} has unknown {endpoint}")
    return (
        offer_ids,
        list(eval_pairs.values()),
        {offer_id: row["cluster_id"] for offer_id, row in hidden_clusters.items()},
        {pair_id: int(row["label"]) for pair_id, row in hidden_pairs.items()},
    )


def _comb2(value: int) -> int:
    return value * (value - 1) // 2


def _bcubed_metrics(
    *,
    expected_ids: list[str],
    true_clusters: dict[str, str],
    predicted_clusters: dict[str, str],
) -> dict[str, Any]:
    true_by_id: dict[str, set[str]] = defaultdict(set)
    pred_by_id: dict[str, set[str]] = defaultdict(set)
    intersections: Counter[tuple[str, str]] = Counter()
    for offer_id in expected_ids:
        true_id = true_clusters[offer_id]
        pred_id = predicted_clusters.get(offer_id, f"__missing__{offer_id}")
        true_by_id[true_id].add(offer_id)
        pred_by_id[pred_id].add(offer_id)
        intersections[(true_id, pred_id)] += 1

    precision_sum = 0.0
    recall_sum = 0.0
    for offer_id in expected_ids:
        true_id = true_clusters[offer_id]
        pred_id = predicted_clusters.get(offer_id, f"__missing__{offer_id}")
        overlap = intersections[(true_id, pred_id)]
        precision_sum += overlap / len(pred_by_id[pred_id])
        recall_sum += overlap / len(true_by_id[true_id])
    precision = precision_sum / len(expected_ids) if expected_ids else 0.0
    recall = recall_sum / len(expected_ids) if expected_ids else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f1": round(f1, 6),
    }


def _cluster_pairwise_metrics(
    *,
    expected_ids: list[str],
    true_clusters: dict[str, str],
    predicted_clusters: dict[str, str],
) -> dict[str, Any]:
    true_counts: Counter[str] = Counter()
    pred_counts: Counter[str] = Counter()
    intersections: Counter[tuple[str, str]] = Counter()
    for offer_id in expected_ids:
        true_id = true_clusters[offer_id]
        pred_id = predicted_clusters.get(offer_id, f"__missing__{offer_id}")
        true_counts[true_id] += 1
        pred_counts[pred_id] += 1
        intersections[(true_id, pred_id)] += 1
    true_pairs = sum(_comb2(value) for value in true_counts.values())
    predicted_pairs = sum(_comb2(value) for value in pred_counts.values())
    tp = sum(_comb2(value) for value in intersections.values())
    fp = predicted_pairs - tp
    fn = true_pairs - tp
    precision = tp / predicted_pairs if predicted_pairs else 0.0
    recall = tp / true_pairs if true_pairs else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f1": round(f1, 6),
        "tp_pairs": tp,
        "fp_pairs": fp,
        "fn_pairs": fn,
        "true_pairs": true_pairs,
        "predicted_pairs": predicted_pairs,
    }


def _eval_cluster_operating_point(
    *,
    eval_pairs: list[dict[str, str]],
    pair_labels: dict[str, int],
    predicted_clusters: dict[str, str],
) -> dict[str, Any]:
    predictions = {
        row["pair_id"]: int(
            row["offer_id_left"] in predicted_clusters
            and row["offer_id_right"] in predicted_clusters
            and predicted_clusters[row["offer_id_left"]]
            == predicted_clusters[row["offer_id_right"]]
        )
        for row in eval_pairs
    }
    return _binary_metrics(
        expected_ids=[row["pair_id"] for row in eval_pairs],
        labels=pair_labels,
        predictions=predictions,
    )


def _binary_metrics(
    *,
    expected_ids: list[str],
    labels: dict[str, int],
    predictions: dict[str, int],
) -> dict[str, Any]:
    tp = fp = tn = fn = 0
    for pair_id in expected_ids:
        actual = labels[pair_id]
        predicted = predictions.get(pair_id, 0)
        if predicted == 1 and actual == 1:
            tp += 1
        elif predicted == 1 and actual == 0:
            fp += 1
        elif predicted == 0 and actual == 0:
            tn += 1
        elif predicted == 0 and actual == 1:
            fn += 1
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    accuracy = (tp + tn) / len(expected_ids) if expected_ids else 0.0
    return {
        "f1": round(f1, 6),
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "accuracy": round(accuracy, 6),
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "positive_prevalence": round(sum(labels.values()) / len(labels), 6),
    }


def _precision_recall_curve(
    *,
    expected_ids: list[str],
    labels: dict[str, int],
    scores: dict[str, float],
) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    errors = _validate_expected_ids(
        expected_ids=expected_ids,
        actual_ids=set(scores),
        output_name="pair_scores.csv",
    )
    scored_ids = [pair_id for pair_id in expected_ids if pair_id in scores]
    if not scored_ids:
        return [], {"average_precision": 0.0, "points": 0}, errors

    ordered = sorted(scored_ids, key=scores.__getitem__, reverse=True)
    total_pos = sum(labels[pair_id] for pair_id in scored_ids)
    total_neg = len(scored_ids) - total_pos
    tp = fp = 0
    average_precision = 0.0
    curve: list[dict[str, Any]] = []
    for threshold, group in groupby(ordered, key=scores.__getitem__):
        previous_tp = tp
        for pair_id in group:
            if labels[pair_id] == 1:
                tp += 1
            else:
                fp += 1
        fn = total_pos - tp
        tn = total_neg - fp
        precision = tp / (tp + fp)
        recall = tp / total_pos if total_pos else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        curve.append({
            "threshold": threshold, "precision": round(precision, 6),
            "recall": round(recall, 6), "f1": round(f1, 6),
            "accuracy": round((tp + tn) / len(scored_ids), 6),
            "tp": tp, "fp": fp, "tn": tn, "fn": fn,
            "positive_prevalence": round(total_pos / len(scored_ids), 6),
        })
        # Noninterpolated AP: each entire tie group contributes its recall
        # increment times precision at the end of that threshold group.
        if total_pos:
            average_precision += (tp - previous_tp) / total_pos * precision
    best_f1 = max((row["f1"] for row in curve), default=0.0)
    best_rows = [row for row in curve if row["f1"] == best_f1]
    best_row = best_rows[0] if best_rows else {}
    summary = {
        "average_precision": round(average_precision, 6),
        "points": len(curve),
        "best_hidden": {
            key: (round(value, 6) if isinstance(value, float) else value)
            for key, value in best_row.items()
        },
    }
    return curve, summary, errors


def _write_pr_curve(path: Path, curve: list[dict[str, Any]]) -> None:
    fieldnames = [
        "threshold",
        "precision",
        "recall",
        "f1",
        "accuracy",
        "tp",
        "fp",
        "tn",
        "fn",
        "positive_prevalence",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in curve:
            writer.writerow(
                {
                    key: (
                        f"{row[key]:.12g}"
                        if isinstance(row.get(key), float)
                        else row.get(key)
                    )
                    for key in fieldnames
                }
            )


def _publish_result(output_path: Path, payload: dict[str, Any], curve) -> None:
    """Publish one immutable curve generation, then its atomic JSON reference.

    Prior curves remain valid for readers holding an older result. Concurrent
    publishers use unique curve names; the final JSON replacement is the commit.
    """
    generation = output_path.with_name(f"{output_path.stem}.{uuid.uuid4().hex}.pr-curve.csv")
    if curve is not None:
        payload["pr_curve"]["path"] = str(generation)
    # Finish strict serialization before touching any published artifact.
    serialized = json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"
    with tempfile.TemporaryDirectory(prefix=".cluster-result-", dir=output_path.parent) as directory:
        stage = Path(directory)
        if curve is not None:
            _write_pr_curve(stage / "curve.csv", curve)
        (stage / "result.json").write_text(serialized, encoding="utf-8")
        if curve is not None:
            os.replace(stage / "curve.csv", generation)
        try:
            os.replace(stage / "result.json", output_path)
        except BaseException:
            if curve is not None:
                try:
                    generation.unlink()
                except OSError:
                    pass  # An unreferenced complete curve is safe to retain.
            raise


def _combined_score(
    *,
    bcubed: dict[str, Any],
    pairwise: dict[str, Any],
    pr_curve: dict[str, Any],
    system_metrics: dict[str, Any],
) -> dict[str, Any]:
    bcubed_f1 = float(bcubed.get("f1") or 0.0)
    pairwise_f1 = float(pairwise.get("f1") or 0.0)
    average_precision = float(pr_curve.get("average_precision") or 0.0)
    offers_per_second = float(system_metrics.get("offers_per_second") or 0.0)
    if not system_metrics.get("memory_complete") or system_metrics.get("peak_rss_mb") is None:
        return {"value": None, "unavailable_reason": "incomplete owned-process memory evidence"}
    peak_rss_mb = float(system_metrics["peak_rss_mb"])
    throughput_norm = min(1.0, max(0.0, offers_per_second / 10_000.0))
    memory_norm = min(1.0, 1024.0 / peak_rss_mb) if peak_rss_mb > 0 else 0.0
    value = 100.0 * (
        0.35 * bcubed_f1
        + 0.25 * pairwise_f1
        + 0.25 * average_precision
        + 0.10 * throughput_norm
        + 0.05 * memory_norm
    )
    return {
        "value": round(value, 6),
        "formula": (
            "100 * (0.35*bcubed_f1 + 0.25*pairwise_cluster_f1 + "
            "0.25*average_precision + 0.10*min(offers_per_second/10000,1) + "
            "0.05*min(1024/peak_rss_mb,1))"
        ),
        "components": {
            "bcubed_f1": round(bcubed_f1, 6),
            "pairwise_cluster_f1": round(pairwise_f1, 6),
            "average_precision": round(average_precision, 6),
            "throughput_norm": round(throughput_norm, 6),
            "memory_norm": round(memory_norm, 6),
        },
    }


def main() -> int:
    for signum in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(signum, _terminate)
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--case", required=True)
    parser.add_argument("--pack-id", required=True)
    parser.add_argument("--pack-version", required=True)
    parser.add_argument("--source-fixture-id", required=True)
    parser.add_argument("--patch", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    workspace = Path(args.workspace)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    test_path = workspace / "data" / "test_offers.csv"
    eval_pairs_path = workspace / "data" / "eval_pairs.csv"
    hidden_clusters_path = Path(__file__).with_name("hidden_test_clusters.csv")
    hidden_pairs_path = Path(__file__).with_name("hidden_eval_pair_labels.csv")
    patch_path = Path(args.patch)

    payload: dict[str, Any] = {
        "schema_version": 1,
        "case_id": args.case,
        "pack_id": args.pack_id,
        "pack_version": args.pack_version,
        "source_fixture_id": args.source_fixture_id,
        "thresholds": {
            "bcubed_f1_min": BCUBED_F1_MIN,
            "pairwise_cluster_f1_min": PAIRWISE_CLUSTER_F1_MIN,
        },
        "patch_exists": patch_path.is_file(),
        "patch_bytes": patch_path.stat().st_size if patch_path.is_file() else 0,
        "checks": [],
    }

    curve = None
    try:
        try:
            expected_offer_ids, eval_pairs, true_clusters, pair_labels = _load_scoring_fixtures(
                test_path, eval_pairs_path, hidden_clusters_path, hidden_pairs_path,
            )
        except (OSError, ValueError, KeyError, TypeError, csv.Error) as exc:
            payload["fixture_errors"] = [str(exc)]
            raise ValueError("invalid scoring fixtures") from exc
        expected_pair_ids = [row["pair_id"] for row in eval_pairs]
        run_result = _run_program(workspace, args.case, output_path.parent)
        payload["program"] = {
            key: value
            for key, value in run_result.items()
            if key not in {"stdout", "stderr"}
        }
        system_metrics = {
            "test_offers": len(expected_offer_ids),
            "eval_pairs": len(expected_pair_ids),
            "program_duration_s": round(
                float(run_result.get("duration_s", 0.0)), 6
            ),
            "offers_per_second": round(
                len(expected_offer_ids) / float(run_result.get("duration_s", 1.0)),
                6,
            )
            if float(run_result.get("duration_s", 0.0)) > 0
            else None,
            "eval_pairs_per_second": round(
                len(expected_pair_ids) / float(run_result.get("duration_s", 1.0)),
                6,
            )
            if float(run_result.get("duration_s", 0.0)) > 0
            else None,
            "peak_rss_mb": run_result.get("peak_rss_mb"),
            "memory_scope": run_result.get("memory_scope"),
            "memory_complete": run_result.get("memory_complete", False),
            "memory_samples": run_result.get("memory_samples", 0),
        }
        payload["system_metrics"] = system_metrics
        if not run_result.get("ok"):
            payload["error"] = "program failed"
            payload["program_stdout"] = run_result.get("stdout", "")[-2000:]
            payload["program_stderr"] = run_result.get("stderr", "")[-2000:]
            payload["passed"] = False
        else:
            budget = _EvidenceBudget()
            predicted_clusters, cluster_errors = _load_clusters(workspace / "clusters.csv", budget)
            pair_scores, score_errors = _load_pair_scores(workspace / "pair_scores.csv", budget)
            program_metrics, metric_errors = _load_program_metrics(
                workspace / "metrics.json", budget
            )
            errors = (
                cluster_errors
                + score_errors
                + metric_errors
                + _validate_expected_ids(
                    expected_ids=expected_offer_ids,
                    actual_ids=set(predicted_clusters),
                    output_name="clusters.csv",
                )
            )
            errors += _validate_expected_ids(
                expected_ids=expected_pair_ids, actual_ids=set(pair_scores),
                output_name="pair_scores.csv",
            )
            payload["prediction_errors"] = errors
            if errors:
                payload["metrics"] = None
                payload["pr_curve"] = None
                payload["combined_score"] = {"value": None, "unavailable_reason": "invalid prediction evidence"}
                raise ValueError("invalid prediction evidence")
            bcubed = _bcubed_metrics(
                expected_ids=expected_offer_ids,
                true_clusters=true_clusters,
                predicted_clusters=predicted_clusters,
            )
            pairwise = _cluster_pairwise_metrics(
                expected_ids=expected_offer_ids,
                true_clusters=true_clusters,
                predicted_clusters=predicted_clusters,
            )
            eval_operating_point = _eval_cluster_operating_point(
                eval_pairs=eval_pairs,
                pair_labels=pair_labels,
                predicted_clusters=predicted_clusters,
            )
            curve, curve_summary, curve_errors = _precision_recall_curve(
                expected_ids=expected_pair_ids,
                labels=pair_labels,
                scores=pair_scores,
            )
            errors += curve_errors
            payload["metrics"] = {
                "bcubed": bcubed,
                "pairwise_cluster": pairwise,
                "eval_pair_operating_point_from_clusters": eval_operating_point,
            }
            payload["system_metrics"] = system_metrics
            if program_metrics is not None:
                payload["program_metrics"] = program_metrics
            payload["pr_curve"] = {
                **curve_summary,
                "score_file": "pair_scores.csv",
            }
            payload["combined_score"] = _combined_score(
                bcubed=bcubed,
                pairwise=pairwise,
                pr_curve=payload["pr_curve"],
                system_metrics=system_metrics,
            )
            payload["prediction_errors"] = errors
            payload["passed"] = (
                not errors
                and bcubed["f1"] >= BCUBED_F1_MIN
                and pairwise["f1"] >= PAIRWISE_CLUSTER_F1_MIN
                and payload["patch_exists"]
                and payload["patch_bytes"] > 0
            )
    except Exception as exc:
        payload["error"] = str(exc)
        payload["passed"] = False

    _publish_result(output_path, payload, curve)
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
