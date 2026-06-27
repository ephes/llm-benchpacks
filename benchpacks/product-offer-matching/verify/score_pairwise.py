from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


F1_MIN = 0.70
PROGRAM_TIMEOUT_S = 20.0


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _run_program(workspace: Path, case_id: str, output_root: Path) -> dict[str, Any]:
    predictions_path = workspace / "predictions.csv"
    try:
        predictions_path.unlink()
    except FileNotFoundError:
        pass

    if case_id.endswith("-python"):
        command = [
            sys.executable,
            "matcher.py",
            "--train",
            "data/train.csv",
            "--predict",
            "data/test_pairs.csv",
            "--output",
            "predictions.csv",
        ]
    elif case_id.endswith("-rust"):
        binary = output_root / "matcher-rust"
        compile_command = ["rustc", "matcher.rs", "-O", "-o", str(binary)]
        compile_started = time.monotonic()
        compile_completed = subprocess.run(
            compile_command,
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=PROGRAM_TIMEOUT_S,
            check=False,
        )
        compile_duration_s = time.monotonic() - compile_started
        if compile_completed.returncode != 0:
            return {
                "ok": False,
                "phase": "compile",
                "command": compile_command,
                "exit_code": compile_completed.returncode,
                "stdout": compile_completed.stdout,
                "stderr": compile_completed.stderr,
                "duration_s": compile_duration_s,
            }
        command = [
            str(binary),
            "--train",
            "data/train.csv",
            "--predict",
            "data/test_pairs.csv",
            "--output",
            "predictions.csv",
        ]
    else:
        return {"ok": False, "phase": "select", "error": f"unknown case {case_id}"}

    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=PROGRAM_TIMEOUT_S,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "phase": "run",
            "timed_out": True,
            "timeout_s": PROGRAM_TIMEOUT_S,
            "stdout": _stream_text(exc.stdout),
            "stderr": _stream_text(exc.stderr),
        }
    duration_s = time.monotonic() - started
    return {
        "ok": completed.returncode == 0,
        "phase": "run",
        "command": command,
        "exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "duration_s": duration_s,
        "predictions_path": str(predictions_path),
    }


def _stream_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _load_predictions(path: Path) -> tuple[dict[str, int], list[str]]:
    errors: list[str] = []
    if not path.is_file():
        return {}, ["predictions.csv was not created"]
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != ["pair_id", "label"]:
            errors.append("predictions.csv header must be exactly pair_id,label")
        predictions: dict[str, int] = {}
        for index, row in enumerate(reader, start=2):
            pair_id = (row.get("pair_id") or "").strip()
            label = (row.get("label") or "").strip()
            if not pair_id:
                errors.append(f"row {index} has blank pair_id")
                continue
            if pair_id in predictions:
                errors.append(f"duplicate prediction for pair_id {pair_id}")
                continue
            if label not in {"0", "1"}:
                errors.append(f"row {index} has invalid label {label!r}")
                continue
            predictions[pair_id] = int(label)
    return predictions, errors


def _score(
    *,
    expected_ids: list[str],
    labels: dict[str, int],
    predictions: dict[str, int],
) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    expected_set = set(expected_ids)
    predicted_set = set(predictions)
    missing = sorted(expected_set - predicted_set)
    extra = sorted(predicted_set - expected_set)
    if missing:
        errors.append(f"missing predictions for {len(missing)} pair ids")
    if extra:
        errors.append(f"predictions contain {len(extra)} unknown pair ids")

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
    metrics = {
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
    return metrics, errors


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
    labels_path = Path(__file__).with_name("hidden_labels.csv")
    test_path = workspace / "data" / "test_pairs.csv"
    patch_path = Path(args.patch)

    payload: dict[str, Any] = {
        "schema_version": 1,
        "case_id": args.case,
        "pack_id": args.pack_id,
        "pack_version": args.pack_version,
        "source_fixture_id": args.source_fixture_id,
        "thresholds": {"f1_min": F1_MIN},
        "patch_exists": patch_path.is_file(),
        "patch_bytes": patch_path.stat().st_size if patch_path.is_file() else 0,
        "checks": [],
    }

    try:
        test_rows = _read_csv(test_path)
        expected_ids = [row["pair_id"] for row in test_rows]
        labels = {row["pair_id"]: int(row["label"]) for row in _read_csv(labels_path)}
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
            predictions, prediction_errors = _load_predictions(
                workspace / "predictions.csv"
            )
            metrics, score_errors = _score(
                expected_ids=expected_ids,
                labels=labels,
                predictions=predictions,
            )
            errors = prediction_errors + score_errors
            payload["metrics"] = metrics
            payload["prediction_errors"] = errors
            payload["passed"] = (
                not errors
                and metrics["f1"] >= F1_MIN
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
