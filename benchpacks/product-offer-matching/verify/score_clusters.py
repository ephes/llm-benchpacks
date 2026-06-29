from __future__ import annotations

import argparse
import csv
import json
import math
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


BCUBED_F1_MIN = 0.70
PAIRWISE_CLUSTER_F1_MIN = 0.20
PROGRAM_TIMEOUT_S = 60.0


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _rss_mb(pid: int) -> float | None:
    try:
        completed = subprocess.run(
            ["ps", "-o", "rss=", "-p", str(pid)],
            check=False,
            capture_output=True,
            text=True,
            timeout=1.0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    text = completed.stdout.strip()
    if not text:
        return None
    try:
        return int(text.splitlines()[-1].strip()) / 1024.0
    except ValueError:
        return None


def _run_command(
    command: list[str],
    *,
    cwd: Path,
    timeout_s: float,
) -> dict[str, Any]:
    started = time.monotonic()
    try:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except OSError as exc:
        return {
            "ok": False,
            "phase": "spawn",
            "command": command,
            "error": str(exc),
            "duration_s": time.monotonic() - started,
        }

    peak_rss_mb = 0.0
    timed_out = False
    while process.poll() is None:
        rss = _rss_mb(process.pid)
        if rss is not None:
            peak_rss_mb = max(peak_rss_mb, rss)
        if time.monotonic() - started > timeout_s:
            timed_out = True
            process.kill()
            break
        time.sleep(0.02)

    stdout, stderr = process.communicate()
    duration_s = time.monotonic() - started
    if timed_out:
        return {
            "ok": False,
            "phase": "run",
            "command": command,
            "timed_out": True,
            "timeout_s": timeout_s,
            "stdout": stdout,
            "stderr": stderr,
            "duration_s": duration_s,
            "peak_rss_mb": round(peak_rss_mb, 3),
        }
    return {
        "ok": process.returncode == 0,
        "phase": "run",
        "command": command,
        "exit_code": process.returncode,
        "stdout": stdout,
        "stderr": stderr,
        "duration_s": duration_s,
        "peak_rss_mb": round(peak_rss_mb, 3),
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


def _load_clusters(path: Path) -> tuple[dict[str, str], list[str]]:
    errors: list[str] = []
    if not path.is_file():
        return {}, ["clusters.csv was not created"]
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != ["offer_id", "cluster_id"]:
            errors.append("clusters.csv header must be exactly offer_id,cluster_id")
        clusters: dict[str, str] = {}
        for index, row in enumerate(reader, start=2):
            offer_id = (row.get("offer_id") or "").strip()
            cluster_id = (row.get("cluster_id") or "").strip()
            if not offer_id:
                errors.append(f"row {index} has blank offer_id")
                continue
            if offer_id in clusters:
                errors.append(f"duplicate prediction for offer_id {offer_id}")
                continue
            if not cluster_id:
                errors.append(f"row {index} has blank cluster_id")
                continue
            clusters[offer_id] = cluster_id
    return clusters, errors


def _load_pair_scores(path: Path) -> tuple[dict[str, float], list[str]]:
    errors: list[str] = []
    if not path.is_file():
        return {}, ["pair_scores.csv was not created"]
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != ["pair_id", "score"]:
            errors.append("pair_scores.csv header must be exactly pair_id,score")
        scores: dict[str, float] = {}
        for index, row in enumerate(reader, start=2):
            pair_id = (row.get("pair_id") or "").strip()
            raw_score = (row.get("score") or "").strip()
            if not pair_id:
                errors.append(f"scores row {index} has blank pair_id")
                continue
            if pair_id in scores:
                errors.append(f"duplicate score for pair_id {pair_id}")
                continue
            try:
                score = float(raw_score)
            except ValueError:
                errors.append(f"scores row {index} has invalid score {raw_score!r}")
                continue
            if not math.isfinite(score):
                errors.append(f"scores row {index} has non-finite score {raw_score!r}")
                continue
            scores[pair_id] = score
    return scores, errors


def _load_program_metrics(path: Path) -> tuple[dict[str, Any] | None, list[str]]:
    if not path.is_file():
        return None, []
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, [f"metrics.json could not be parsed: {exc}"]
    if not isinstance(loaded, dict):
        return None, ["metrics.json must contain an object"]
    allowed: dict[str, Any] = {}
    for key, value in loaded.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            allowed[str(key)] = value
    return allowed, []


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
            predicted_clusters.get(row["offer_id_left"])
            == predicted_clusters.get(row["offer_id_right"])
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

    thresholds = sorted({scores[pair_id] for pair_id in scored_ids}, reverse=True)
    curve: list[dict[str, Any]] = []
    for threshold in thresholds:
        predictions = {
            pair_id: 1 if scores[pair_id] >= threshold else 0
            for pair_id in scored_ids
        }
        curve.append(
            {
                "threshold": threshold,
                **_binary_metrics(
                    expected_ids=scored_ids,
                    labels=labels,
                    predictions=predictions,
                ),
            }
        )

    total_pos = sum(labels[pair_id] for pair_id in scored_ids)
    tp = 0
    seen = 0
    precision_sum = 0.0
    for pair_id in sorted(scored_ids, key=lambda item: scores[item], reverse=True):
        seen += 1
        if labels[pair_id] == 1:
            tp += 1
            precision_sum += tp / seen
    average_precision = precision_sum / total_pos if total_pos else 0.0
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
    peak_rss_mb = float(system_metrics.get("peak_rss_mb") or 0.0)
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

    try:
        test_rows = _read_csv(test_path)
        eval_pairs = _read_csv(eval_pairs_path)
        expected_offer_ids = [row["offer_id"] for row in test_rows]
        expected_pair_ids = [row["pair_id"] for row in eval_pairs]
        true_clusters = {
            row["offer_id"]: row["cluster_id"] for row in _read_csv(hidden_clusters_path)
        }
        pair_labels = {
            row["pair_id"]: int(row["label"]) for row in _read_csv(hidden_pairs_path)
        }
        run_result = _run_program(workspace, args.case, output_path.parent)
        payload["program"] = {
            key: value
            for key, value in run_result.items()
            if key not in {"stdout", "stderr"}
        }
        if not run_result.get("ok"):
            payload["error"] = "program failed"
            payload["program_stdout"] = run_result.get("stdout", "")[-2000:]
            payload["program_stderr"] = run_result.get("stderr", "")[-2000:]
            payload["passed"] = False
        else:
            predicted_clusters, cluster_errors = _load_clusters(workspace / "clusters.csv")
            pair_scores, score_errors = _load_pair_scores(workspace / "pair_scores.csv")
            program_metrics, metric_errors = _load_program_metrics(
                workspace / "metrics.json"
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
            pr_curve_path = output_path.with_suffix(".pr-curve.csv")
            _write_pr_curve(pr_curve_path, curve)
            errors += curve_errors
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
            }
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
                "path": str(pr_curve_path),
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

    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
