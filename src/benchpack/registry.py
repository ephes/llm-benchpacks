"""Local SQLite result registry import helpers."""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .compare import CompareError, ResultRun, load_result_run
from .run_metadata import RunMetadataError, load_optional_run_metadata


REGISTRY_SCHEMA_VERSION = 1


class RegistryError(ValueError):
    """Raised when a result directory cannot be imported into the registry."""


@dataclass(frozen=True)
class RegistryImportSummary:
    """Summary for one imported result directory."""

    result_dir: Path
    run_id: int
    rows_imported: int


def import_result_dirs(
    result_dirs: list[Path | str],
    db_path: Path | str,
) -> list[RegistryImportSummary]:
    """Import existing result directories into a local SQLite registry."""

    if not result_dirs:
        raise RegistryError("benchpack registry import requires result directories")

    # Validate every input before opening the database so multi-dir imports fail
    # without partial registry writes when a later input is malformed.
    loaded_runs = [_load_and_validate_result_dir(path) for path in result_dirs]
    if str(db_path) == "":
        raise RegistryError("registry database path must not be empty")
    db = Path(db_path)
    if db.parent != Path("."):
        db.parent.mkdir(parents=True, exist_ok=True)

    try:
        with sqlite3.connect(db) as conn:
            _ensure_schema(conn)
            summaries = [_import_run(conn, run) for run in loaded_runs]
    except sqlite3.Error as exc:
        raise RegistryError(f"could not update registry database {db}: {exc}") from exc
    return summaries


def _load_and_validate_result_dir(path: Path | str) -> ResultRun:
    try:
        run = load_result_run(path)
    except CompareError as exc:
        raise RegistryError(str(exc)) from exc
    for row_index, record in enumerate(run.records, start=1):
        _validate_record(record, run.path / "run.jsonl", row_index)
    try:
        _load_optional_json_object(run.path, "hardware.json")
        load_optional_run_metadata(run.path)
    except (RegistryError, RunMetadataError) as exc:
        raise RegistryError(str(exc)) from exc
    return run


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        PRAGMA foreign_keys = ON;

        CREATE TABLE IF NOT EXISTS registry_meta (
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS runs (
          id INTEGER PRIMARY KEY,
          result_dir TEXT NOT NULL UNIQUE,
          label TEXT NOT NULL,
          imported_at TEXT NOT NULL,
          row_count INTEGER NOT NULL,
          run_jsonl_sha256 TEXT NOT NULL,
          pack_ids_json TEXT NOT NULL,
          pack_versions_json TEXT NOT NULL,
          adapters_json TEXT NOT NULL,
          models_json TEXT NOT NULL,
          endpoints_json TEXT NOT NULL,
          hardware_json TEXT,
          run_metadata_json TEXT,
          host_hostname TEXT,
          host_platform TEXT,
          runtime_name TEXT,
          runtime_version TEXT,
          model_metadata_id TEXT,
          model_quantization TEXT
        );

        CREATE TABLE IF NOT EXISTS result_rows (
          id INTEGER PRIMARY KEY,
          run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
          row_index INTEGER NOT NULL,
          pack_id TEXT NOT NULL,
          pack_version TEXT NOT NULL,
          case_id TEXT NOT NULL,
          repetition INTEGER,
          adapter TEXT NOT NULL,
          model TEXT NOT NULL,
          endpoint TEXT NOT NULL,
          ok INTEGER NOT NULL,
          wall_s REAL,
          ttft_s REAL,
          prefill_tps REAL,
          decode_tps REAL,
          total_tps REAL,
          prompt_tokens INTEGER,
          output_tokens INTEGER,
          cached_prompt_tokens INTEGER,
          scoring_mode TEXT,
          scoring_passed INTEGER,
          repo_task_status TEXT,
          verify_exit_code INTEGER,
          raw_json TEXT NOT NULL,
          UNIQUE(run_id, row_index)
        );
        """
    )
    conn.execute(
        "INSERT OR REPLACE INTO registry_meta(key, value) VALUES (?, ?)",
        ("schema_version", str(REGISTRY_SCHEMA_VERSION)),
    )
    conn.execute(f"PRAGMA user_version = {REGISTRY_SCHEMA_VERSION}")


def _import_run(
    conn: sqlite3.Connection,
    run: ResultRun,
) -> RegistryImportSummary:
    result_dir = str(run.path.resolve())
    hardware = _load_optional_json_object(run.path, "hardware.json")
    try:
        run_metadata = load_optional_run_metadata(run.path)
    except RunMetadataError as exc:
        raise RegistryError(str(exc)) from exc
    inserted = _run_row_values(run, result_dir, hardware, run_metadata)
    conn.execute(
        """
        INSERT INTO runs(
          result_dir, label, imported_at, row_count, run_jsonl_sha256,
          pack_ids_json, pack_versions_json, adapters_json, models_json,
          endpoints_json, hardware_json, run_metadata_json, host_hostname,
          host_platform, runtime_name, runtime_version, model_metadata_id,
          model_quantization
        )
        VALUES (
          :result_dir, :label, :imported_at, :row_count, :run_jsonl_sha256,
          :pack_ids_json, :pack_versions_json, :adapters_json, :models_json,
          :endpoints_json, :hardware_json, :run_metadata_json, :host_hostname,
          :host_platform, :runtime_name, :runtime_version, :model_metadata_id,
          :model_quantization
        )
        ON CONFLICT(result_dir) DO UPDATE SET
          label = excluded.label,
          imported_at = excluded.imported_at,
          row_count = excluded.row_count,
          run_jsonl_sha256 = excluded.run_jsonl_sha256,
          pack_ids_json = excluded.pack_ids_json,
          pack_versions_json = excluded.pack_versions_json,
          adapters_json = excluded.adapters_json,
          models_json = excluded.models_json,
          endpoints_json = excluded.endpoints_json,
          hardware_json = excluded.hardware_json,
          run_metadata_json = excluded.run_metadata_json,
          host_hostname = excluded.host_hostname,
          host_platform = excluded.host_platform,
          runtime_name = excluded.runtime_name,
          runtime_version = excluded.runtime_version,
          model_metadata_id = excluded.model_metadata_id,
          model_quantization = excluded.model_quantization
        """,
        inserted,
    )
    row = conn.execute(
        "SELECT id FROM runs WHERE result_dir = ?",
        (result_dir,),
    ).fetchone()
    if row is None:
        raise RegistryError(f"could not read imported run id for {run.path}")
    run_id = int(row[0])
    conn.execute("DELETE FROM result_rows WHERE run_id = ?", (run_id,))
    conn.executemany(
        """
        INSERT INTO result_rows(
          run_id, row_index, pack_id, pack_version, case_id, repetition,
          adapter, model, endpoint, ok, wall_s, ttft_s, prefill_tps,
          decode_tps, total_tps, prompt_tokens, output_tokens,
          cached_prompt_tokens, scoring_mode, scoring_passed,
          repo_task_status, verify_exit_code, raw_json
        )
        VALUES (
          :run_id, :row_index, :pack_id, :pack_version, :case_id, :repetition,
          :adapter, :model, :endpoint, :ok, :wall_s, :ttft_s, :prefill_tps,
          :decode_tps, :total_tps, :prompt_tokens, :output_tokens,
          :cached_prompt_tokens, :scoring_mode, :scoring_passed,
          :repo_task_status, :verify_exit_code, :raw_json
        )
        """,
        [
            _result_row_values(run_id, index, record)
            for index, record in enumerate(run.records, start=1)
        ],
    )
    return RegistryImportSummary(
        result_dir=run.path,
        run_id=run_id,
        rows_imported=len(run.records),
    )


def _run_row_values(
    run: ResultRun,
    result_dir: str,
    hardware: dict[str, Any] | None,
    run_metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    runtime = run_metadata.get("runtime") if isinstance(run_metadata, dict) else None
    model_metadata = run_metadata.get("model") if isinstance(run_metadata, dict) else None
    return {
        "result_dir": result_dir,
        "label": run.label,
        "imported_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "row_count": len(run.records),
        "run_jsonl_sha256": _sha256(run.path / "run.jsonl"),
        "pack_ids_json": _json_dumps(_unique_pack_values(run.records, "id")),
        "pack_versions_json": _json_dumps(_unique_pack_values(run.records, "version")),
        "adapters_json": _json_dumps(_unique_record_values(run.records, "adapter")),
        "models_json": _json_dumps(_unique_record_values(run.records, "model")),
        "endpoints_json": _json_dumps(_unique_record_values(run.records, "endpoint")),
        "hardware_json": _json_dumps(hardware) if hardware is not None else None,
        "run_metadata_json": (
            _json_dumps(run_metadata) if run_metadata is not None else None
        ),
        "host_hostname": _string_or_none(hardware, "hostname"),
        "host_platform": _string_or_none(hardware, "platform"),
        "runtime_name": _string_or_none(runtime, "name"),
        "runtime_version": _string_or_none(runtime, "version"),
        "model_metadata_id": _string_or_none(model_metadata, "id"),
        "model_quantization": _string_or_none(model_metadata, "quantization"),
    }


def _result_row_values(
    run_id: int,
    row_index: int,
    record: dict[str, Any],
) -> dict[str, Any]:
    pack = record["pack"]
    timing = record["timing"]
    tokens = record["tokens"]
    scoring = record.get("scoring")
    repo_task = record.get("repo_task")
    scoring_passed = None
    if isinstance(scoring, dict):
        if scoring.get("passed") is True:
            scoring_passed = 1
        elif scoring.get("passed") is False:
            scoring_passed = 0
    return {
        "run_id": run_id,
        "row_index": row_index,
        "pack_id": pack["id"],
        "pack_version": pack["version"],
        "case_id": record["case"],
        "repetition": _optional_positive_int(record.get("repetition")),
        "adapter": record["adapter"],
        "model": record["model"],
        "endpoint": record["endpoint"],
        "ok": 1 if record["ok"] else 0,
        "wall_s": _optional_number(timing.get("wall_s")),
        "ttft_s": _optional_number(timing.get("ttft_s")),
        "prefill_tps": _optional_number(timing.get("prefill_tps")),
        "decode_tps": _optional_number(timing.get("decode_tps")),
        "total_tps": _optional_number(timing.get("total_tps")),
        "prompt_tokens": _optional_int(tokens.get("prompt")),
        "output_tokens": _optional_int(tokens.get("output")),
        "cached_prompt_tokens": _optional_int(tokens.get("cached_prompt")),
        "scoring_mode": scoring.get("mode") if isinstance(scoring, dict) else None,
        "scoring_passed": scoring_passed,
        "repo_task_status": (
            repo_task.get("status") if isinstance(repo_task, dict) else None
        ),
        "verify_exit_code": (
            _optional_int(repo_task.get("verify_exit_code"))
            if isinstance(repo_task, dict)
            else None
        ),
        "raw_json": _json_dumps(record),
    }


def _validate_record(record: dict[str, Any], jsonl_path: Path, row_index: int) -> None:
    source = f"{jsonl_path}:{row_index}"
    pack = _required_dict(record, "pack", source)
    _required_string(pack, "id", source)
    _required_string(pack, "version", source)
    _required_string(record, "case", source)
    _required_string(record, "adapter", source)
    _required_string(record, "endpoint", source)
    _required_string(record, "model", source)
    if not isinstance(record.get("ok"), bool):
        raise RegistryError(f"field 'ok' must be boolean in {source}")
    timing = _required_dict(record, "timing", source)
    tokens = _required_dict(record, "tokens", source)
    _validate_optional_metric(timing, "wall_s", source)
    _validate_optional_metric(timing, "ttft_s", source)
    _validate_optional_metric(timing, "prefill_tps", source)
    _validate_optional_metric(timing, "decode_tps", source)
    _validate_optional_metric(timing, "total_tps", source)
    _validate_optional_int(tokens, "prompt", source)
    _validate_optional_int(tokens, "output", source)
    _validate_optional_int(tokens, "cached_prompt", source)
    repetition = record.get("repetition")
    if repetition is not None and _optional_positive_int(repetition) is None:
        raise RegistryError(f"field 'repetition' must be integer >= 1 in {source}")
    scoring = record.get("scoring")
    if scoring is not None:
        if not isinstance(scoring, dict):
            raise RegistryError(f"field 'scoring' must be object or null in {source}")
        _required_string(scoring, "mode", source)
        if not isinstance(scoring.get("passed"), bool):
            raise RegistryError(f"field 'scoring.passed' must be boolean in {source}")
    repo_task = record.get("repo_task")
    if repo_task is not None:
        if not isinstance(repo_task, dict):
            raise RegistryError(f"field 'repo_task' must be object in {source}")
        _required_string(repo_task, "status", source)
        verify_exit_code = repo_task.get("verify_exit_code")
        if verify_exit_code is not None and _optional_int(verify_exit_code) is None:
            raise RegistryError(
                f"field 'repo_task.verify_exit_code' must be integer or null in {source}"
            )


def _load_optional_json_object(result_dir: Path, filename: str) -> dict[str, Any] | None:
    path = result_dir / filename
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RegistryError(f"could not parse {path}: {exc.msg}") from exc
    except OSError as exc:
        raise RegistryError(f"could not read {path}: {exc.strerror}") from exc
    if not isinstance(value, dict):
        raise RegistryError(f"expected JSON object in {path}")
    return value


def _required_dict(record: dict[str, Any], field: str, source: str) -> dict[str, Any]:
    value = record.get(field)
    if not isinstance(value, dict):
        raise RegistryError(f"field {field!r} must be object in {source}")
    return value


def _required_string(record: dict[str, Any], field: str, source: str) -> str:
    value = record.get(field)
    if not isinstance(value, str) or value == "":
        raise RegistryError(f"field {field!r} must be a non-empty string in {source}")
    return value


def _validate_optional_metric(record: dict[str, Any], field: str, source: str) -> None:
    value = record.get(field)
    if value is None:
        return
    if _optional_number(value) is None:
        raise RegistryError(f"field {field!r} must be a finite number or null in {source}")


def _validate_optional_int(record: dict[str, Any], field: str, source: str) -> None:
    value = record.get(field)
    if value is None:
        return
    if _optional_int(value) is None:
        raise RegistryError(f"field {field!r} must be an integer or null in {source}")


def _optional_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(float(value)):
        return None
    return float(value)


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _optional_positive_int(value: Any) -> int | None:
    integer = _optional_int(value)
    if integer is None or integer < 1:
        return None
    return integer


def _unique_pack_values(records: list[dict[str, Any]], field: str) -> list[str]:
    return sorted({record["pack"][field] for record in records})


def _unique_record_values(records: list[dict[str, Any]], field: str) -> list[str]:
    return sorted({record[field] for record in records})


def _string_or_none(value: Any, key: str) -> str | None:
    if not isinstance(value, dict):
        return None
    item = value.get(key)
    return item if isinstance(item, str) and item else None


def _json_dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
