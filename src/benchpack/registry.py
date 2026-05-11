"""Local SQLite result registry import helpers."""

from __future__ import annotations

import hashlib
import html as html_lib
import json
import math
import re
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from typing import Any, Iterable

from .compare import CompareError, ResultRun, load_result_run
from .external_agent_model_calls import (
    MODEL_CALL_LOG_PATTERN,
    ModelCallLogError,
    summarize_model_call_logs,
)
from .report import ReportError, render_report
from .run_metadata import RunMetadataError, load_optional_run_metadata


REGISTRY_SCHEMA_VERSION = 2
BUNDLE_SCHEMA_VERSION = 1
BUNDLE_MANIFEST_FILENAME = "benchpack-bundle.json"
STATIC_SITE_INDEX_FILENAME = "index.html"
STATIC_SITE_REPORT_FILENAME = "report.md"
STATIC_SITE_SNAPSHOT_FILENAME = "snapshot.json"
BUNDLE_PROVENANCE_LABELS = frozenset(
    {"self-reported", "operator-curated", "independently-reproduced"}
)
_SECRET_PATTERNS = (
    re.compile(r"(?i)\bauthorization\s*:\s*bearer\s+\S+"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{12,}"),
    re.compile(r"(?i)[?&](?:api[_-]?key|access[_-]?token|token|secret|password)="),
    re.compile(r"://[^/\s:@]+:[^/\s@]+@"),
    re.compile(
        r"(?i)\"(?:api[_-]?key|token|secret|password|authorization)\"\s*:\s*\"[^\"]{8,}\""
    ),
)
_RUN_COLUMN_DEFINITIONS = (
    ("id", "INTEGER PRIMARY KEY"),
    ("result_dir", "TEXT NOT NULL UNIQUE"),
    ("label", "TEXT NOT NULL"),
    ("imported_at", "TEXT NOT NULL"),
    ("row_count", "INTEGER NOT NULL"),
    ("run_jsonl_sha256", "TEXT NOT NULL"),
    ("pack_ids_json", "TEXT NOT NULL"),
    ("pack_versions_json", "TEXT NOT NULL"),
    ("adapters_json", "TEXT NOT NULL"),
    ("models_json", "TEXT NOT NULL"),
    ("endpoints_json", "TEXT NOT NULL"),
    ("hardware_json", "TEXT"),
    ("run_metadata_json", "TEXT"),
    ("host_hostname", "TEXT"),
    ("host_platform", "TEXT"),
    ("host_label", "TEXT"),
    ("host_repo_commit", "TEXT"),
    ("comparison_mode", "TEXT"),
    ("comparison_boundary", "TEXT"),
    ("runtime_name", "TEXT"),
    ("runtime_version", "TEXT"),
    ("runtime_endpoint", "TEXT"),
    ("runtime_options_json", "TEXT"),
    ("model_metadata_id", "TEXT"),
    ("model_quantization", "TEXT"),
    ("model_artifact_repo", "TEXT"),
    ("model_artifact_file", "TEXT"),
    ("model_revision", "TEXT"),
    ("model_sha256", "TEXT"),
    ("operating_power", "TEXT"),
    ("operating_thermal", "TEXT"),
    ("operating_background_load", "TEXT"),
)


class RegistryError(ValueError):
    """Raised when a result directory cannot be imported into the registry."""


@dataclass(frozen=True)
class RegistryImportSummary:
    """Summary for one imported result directory."""

    result_dir: Path
    run_id: int
    rows_imported: int


@dataclass(frozen=True)
class RegistryDuplicateRun:
    """One registry run that shares a run.jsonl digest with another run."""

    run_id: int
    label: str
    result_dir: Path
    row_count: int
    imported_at: str


@dataclass(frozen=True)
class RegistryDuplicateGroup:
    """A group of imported runs with identical run.jsonl contents."""

    run_jsonl_sha256: str
    runs: list[RegistryDuplicateRun]


@dataclass(frozen=True)
class RegistryBundleSummary:
    """Summary for a created or validated public result bundle."""

    bundle_dir: Path
    runs: int
    files: int
    omitted_artifacts: int
    provenance: str


@dataclass(frozen=True)
class _ValidatedBundle:
    """Validated bundle manifest plus loaded compact run directories.

    Each run path points at the bundled compact run directory; each run label
    is preserved from the bundle manifest's original source run label.
    """

    bundle_dir: Path
    provenance: str
    runs: list[ResultRun]
    files: int
    omitted_artifacts: int


@dataclass(frozen=True)
class RegistryStaticSiteSummary:
    """Summary for a generated static registry snapshot."""

    out_dir: Path
    runs: int
    files: int


@dataclass(frozen=True)
class _SiteComparisonMetric:
    """One registry-site comparison row derived from indexed result rows."""

    run_id: int
    run_label: str
    pack_id: str
    pack_version: str
    case_id: str
    host_label: str | None
    host_hostname: str | None
    host_platform: str | None
    runtime_name: str | None
    model_metadata_id: str | None
    model: str | None
    model_quantization: str | None
    rows: int
    ok_count: int
    scoring_passed_count: int
    scoring_rows: int
    wall_s_median: float | None
    ttft_s_median: float | None
    decode_tps_median: float | None
    total_tps_median: float | None
    prompt_tokens_median: float | None
    cached_prompt_tokens_median: float | None
    output_tokens_median: float | None


def load_registry_report_runs(
    db_path: Path | str,
    *,
    run_ids: list[int] | None = None,
    labels: list[str] | None = None,
) -> list[ResultRun]:
    """Load report runs from the local SQLite registry."""

    if str(db_path) == "":
        raise RegistryError("registry database path must not be empty")
    _validate_registry_selection("registry report", run_ids=run_ids, labels=labels)

    db = Path(db_path)
    if not db.is_file():
        raise RegistryError(f"registry database not found: {db}")

    try:
        with sqlite3.connect(db) as conn:
            conn.execute("PRAGMA query_only = ON")
            conn.row_factory = sqlite3.Row
            _assert_report_schema(conn, db)
            run_rows = _select_report_run_rows(
                conn,
                run_ids=run_ids,
                labels=labels,
                command="registry report",
            )
            runs = [_registry_result_run(conn, row) for row in run_rows]
    except sqlite3.Error as exc:
        raise RegistryError(f"could not read registry database {db}: {exc}") from exc

    if not runs:
        raise RegistryError("registry report selection matched no runs")
    return runs


def find_registry_duplicate_runs(db_path: Path | str) -> list[RegistryDuplicateGroup]:
    """Find imported registry runs with identical run.jsonl artifact hashes."""

    if str(db_path) == "":
        raise RegistryError("registry database path must not be empty")
    db = Path(db_path)
    if not db.is_file():
        raise RegistryError(f"registry database not found: {db}")

    try:
        with sqlite3.connect(db) as conn:
            conn.execute("PRAGMA query_only = ON")
            conn.row_factory = sqlite3.Row
            _assert_report_schema(conn, db)
            duplicate_hashes = conn.execute(
                """
                SELECT run_jsonl_sha256
                FROM runs
                GROUP BY run_jsonl_sha256
                HAVING COUNT(*) > 1
                ORDER BY MIN(id)
                """
            ).fetchall()
            groups: list[RegistryDuplicateGroup] = []
            for hash_row in duplicate_hashes:
                rows = conn.execute(
                    """
                    SELECT id, label, result_dir, row_count, imported_at
                    FROM runs
                    WHERE run_jsonl_sha256 = ?
                    ORDER BY id
                    """,
                    (hash_row["run_jsonl_sha256"],),
                ).fetchall()
                groups.append(
                    RegistryDuplicateGroup(
                        run_jsonl_sha256=hash_row["run_jsonl_sha256"],
                        runs=[
                            RegistryDuplicateRun(
                                run_id=int(row["id"]),
                                label=str(row["label"]),
                                result_dir=Path(row["result_dir"]),
                                row_count=int(row["row_count"]),
                                imported_at=str(row["imported_at"]),
                            )
                            for row in rows
                        ],
                    )
                )
    except sqlite3.Error as exc:
        raise RegistryError(f"could not read registry database {db}: {exc}") from exc
    return groups


def query_registry_results(
    db_path: Path | str,
    *,
    run_ids: list[int] | None = None,
    labels: list[str] | None = None,
    pack_id: str | None = None,
    case_id: str | None = None,
    adapter: str | None = None,
    model: str | None = None,
    host_label: str | None = None,
    runtime_name: str | None = None,
    model_quantization: str | None = None,
    ok: bool | None = None,
    scoring_passed: bool | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Query normalized result rows from a local registry database."""

    if str(db_path) == "":
        raise RegistryError("registry database path must not be empty")
    _validate_registry_selection("registry query", run_ids=run_ids, labels=labels)
    _validate_registry_query_filters(
        pack_id=pack_id,
        case_id=case_id,
        adapter=adapter,
        model=model,
        host_label=host_label,
        runtime_name=runtime_name,
        model_quantization=model_quantization,
        limit=limit,
    )
    db = Path(db_path)
    if not db.is_file():
        raise RegistryError(f"registry database not found: {db}")

    try:
        with sqlite3.connect(db) as conn:
            conn.execute("PRAGMA query_only = ON")
            conn.row_factory = sqlite3.Row
            _assert_report_schema(conn, db)
            selected_rows = _select_report_run_rows(
                conn,
                run_ids=run_ids,
                labels=labels,
                command="registry query",
            )
            if not selected_rows:
                raise RegistryError("registry query selection matched no runs")
            rows = _select_registry_query_rows(
                conn,
                [int(row["id"]) for row in selected_rows],
                pack_id=pack_id,
                case_id=case_id,
                adapter=adapter,
                model=model,
                host_label=host_label,
                runtime_name=runtime_name,
                model_quantization=model_quantization,
                ok=ok,
                scoring_passed=scoring_passed,
                limit=limit,
            )
    except sqlite3.Error as exc:
        raise RegistryError(f"could not read registry database {db}: {exc}") from exc
    return [_registry_query_row_dict(row) for row in rows]


def export_registry_static_site(
    db_path: Path | str,
    out_dir: Path | str,
    *,
    run_ids: list[int] | None = None,
    labels: list[str] | None = None,
    force: bool = False,
) -> RegistryStaticSiteSummary:
    """Export a read-only static HTML snapshot from the local registry."""

    if str(out_dir) == "":
        raise RegistryError("registry site output path must not be empty")
    site_root = Path(out_dir)
    if site_root.exists():
        if not force:
            raise RegistryError(
                f"registry site output already exists: {site_root}; "
                "pass --force to replace it"
            )

    try:
        runs, run_rows, case_rows, metric_rows = _load_registry_site_snapshot(
            db_path,
            run_ids=run_ids,
            labels=labels,
        )
        report_markdown = render_report(runs)
        generated_at = datetime.now(UTC).isoformat(timespec="seconds")
        index_html = _render_static_site_html(
            db_path=Path(db_path),
            run_rows=run_rows,
            case_rows=case_rows,
            metric_rows=metric_rows,
            report_markdown=report_markdown,
            generated_at=generated_at,
        )
        snapshot_json = _render_static_site_snapshot_json(
            db_path=Path(db_path),
            run_rows=run_rows,
            case_rows=case_rows,
            metric_rows=metric_rows,
            generated_at=generated_at,
        )
    except ReportError as exc:
        raise RegistryError(str(exc)) from exc

    if site_root.exists():
        if site_root.is_dir():
            shutil.rmtree(site_root)
        else:
            site_root.unlink()
    site_root.mkdir(parents=True, exist_ok=True)
    output_files = {
        STATIC_SITE_REPORT_FILENAME: report_markdown,
        STATIC_SITE_INDEX_FILENAME: index_html,
        STATIC_SITE_SNAPSHOT_FILENAME: snapshot_json,
    }
    for filename, contents in output_files.items():
        (site_root / filename).write_text(contents, encoding="utf-8")
    return RegistryStaticSiteSummary(
        out_dir=site_root,
        runs=len(runs),
        files=len(output_files),
    )


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
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("BEGIN")
            _ensure_schema(conn)
            summaries = [_import_run(conn, run) for run in loaded_runs]
    except sqlite3.Error as exc:
        raise RegistryError(f"could not update registry database {db}: {exc}") from exc
    return summaries


def import_result_bundles(
    bundle_dirs: list[Path | str],
    db_path: Path | str,
) -> list[RegistryImportSummary]:
    """Validate compact public bundles and import their runs into the registry."""

    if not bundle_dirs:
        raise RegistryError("benchpack registry bundle import requires bundle directories")

    # Validate every bundle before opening the database so multi-bundle imports
    # fail without partial writes when a later bundle is malformed.
    bundles = [_load_and_validate_result_bundle(path) for path in bundle_dirs]
    loaded_runs = [run for bundle in bundles for run in bundle.runs]
    if str(db_path) == "":
        raise RegistryError("registry database path must not be empty")
    db = Path(db_path)
    if db.parent != Path("."):
        db.parent.mkdir(parents=True, exist_ok=True)

    try:
        with sqlite3.connect(db) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("BEGIN")
            _ensure_schema(conn)
            summaries = [_import_run(conn, run) for run in loaded_runs]
    except sqlite3.Error as exc:
        raise RegistryError(f"could not update registry database {db}: {exc}") from exc
    return summaries


def create_result_bundle(
    result_dirs: list[Path | str],
    bundle_dir: Path | str,
    *,
    provenance: str = "self-reported",
    force: bool = False,
) -> RegistryBundleSummary:
    """Create a compact shareable bundle from existing result directories."""

    if provenance not in BUNDLE_PROVENANCE_LABELS:
        raise RegistryError(
            "bundle provenance must be one of: "
            + ", ".join(sorted(BUNDLE_PROVENANCE_LABELS))
        )
    if not result_dirs:
        raise RegistryError("benchpack registry bundle create requires result directories")
    runs = [_load_and_validate_result_dir(path) for path in result_dirs]

    bundle_root = Path(bundle_dir)
    if str(bundle_root) == "":
        raise RegistryError("bundle output path must not be empty")
    _assert_bundle_output_disjoint_from_sources(bundle_root, runs)
    if bundle_root.exists():
        if not force:
            raise RegistryError(
                f"bundle output already exists: {bundle_root}; pass --force to replace it"
            )
        if bundle_root.is_dir():
            shutil.rmtree(bundle_root)
        else:
            bundle_root.unlink()
    bundle_root.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, Any] = {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "provenance": provenance,
        "runs": [],
    }
    files_copied = 0
    omitted_count = 0

    try:
        for index, run in enumerate(runs, start=1):
            run_dir_name = f"run-{index:03d}-{_slug(run.label)}"
            run_bundle_dir = bundle_root / "runs" / run_dir_name
            run_bundle_dir.mkdir(parents=True)
            run_manifest, run_files, run_omitted = _copy_run_into_bundle(
                run=run,
                bundle_root=bundle_root,
                run_bundle_dir=run_bundle_dir,
                run_bundle_path=Path("runs") / run_dir_name,
            )
            manifest["runs"].append(run_manifest)
            files_copied += run_files
            omitted_count += run_omitted
        _write_bundle_manifest(bundle_root, manifest)
    except Exception:
        if bundle_root.exists():
            shutil.rmtree(bundle_root)
        raise

    return RegistryBundleSummary(
        bundle_dir=bundle_root,
        runs=len(runs),
        files=files_copied + 1,
        omitted_artifacts=omitted_count,
        provenance=provenance,
    )


def validate_result_bundle(bundle_dir: Path | str) -> RegistryBundleSummary:
    """Validate a compact public result bundle without network access."""

    bundle = _load_and_validate_result_bundle(bundle_dir)
    return RegistryBundleSummary(
        bundle_dir=bundle.bundle_dir,
        runs=len(bundle.runs),
        files=bundle.files,
        omitted_artifacts=bundle.omitted_artifacts,
        provenance=bundle.provenance,
    )


def _load_and_validate_result_bundle(bundle_dir: Path | str) -> _ValidatedBundle:
    """Validate a compact public result bundle and load its compact runs."""

    bundle_root = Path(bundle_dir)
    manifest_path = bundle_root / BUNDLE_MANIFEST_FILENAME
    try:
        manifest_text = manifest_path.read_text(encoding="utf-8")
        _assert_no_public_secret(manifest_text, BUNDLE_MANIFEST_FILENAME)
        manifest = json.loads(manifest_text)
    except json.JSONDecodeError as exc:
        raise RegistryError(f"could not parse {manifest_path}: {exc.msg}") from exc
    except OSError as exc:
        raise RegistryError(f"could not read {manifest_path}: {exc.strerror}") from exc
    if not isinstance(manifest, dict):
        raise RegistryError(f"expected JSON object in {manifest_path}")
    if manifest.get("schema_version") != BUNDLE_SCHEMA_VERSION:
        raise RegistryError(
            f"bundle schema_version must be {BUNDLE_SCHEMA_VERSION}: {manifest_path}"
        )
    provenance = manifest.get("provenance")
    if not isinstance(provenance, str) or provenance not in BUNDLE_PROVENANCE_LABELS:
        raise RegistryError(
            "bundle provenance must be one of: "
            + ", ".join(sorted(BUNDLE_PROVENANCE_LABELS))
        )
    runs = manifest.get("runs")
    if not isinstance(runs, list) or not runs:
        raise RegistryError(f"bundle manifest requires a non-empty runs list: {manifest_path}")

    expected_files = {BUNDLE_MANIFEST_FILENAME}
    file_count = 1
    omitted_count = 0
    loaded_runs: list[ResultRun] = []
    for run_index, run_manifest in enumerate(runs, start=1):
        if not isinstance(run_manifest, dict):
            raise RegistryError(f"bundle run entry {run_index} must be an object")
        label = _manifest_string(run_manifest, "label", f"run {run_index}")
        bundle_path = _manifest_string(run_manifest, "bundle_path", f"run {run_index}")
        run_dir = _resolve_bundle_relative(bundle_root, bundle_path)
        run = _load_and_validate_result_dir(run_dir)
        loaded_runs.append(
            ResultRun(
                path=run.path,
                label=label,
                records=run.records,
                hardware=run.hardware,
                run_metadata=run.run_metadata,
                artifact_root=run.artifact_root,
            )
        )
        files = run_manifest.get("files")
        if not isinstance(files, list) or not files:
            raise RegistryError(f"bundle run {run_index} requires non-empty files")
        for file_entry in files:
            if not isinstance(file_entry, dict):
                raise RegistryError(f"bundle run {run_index} file entries must be objects")
            rel_path = _manifest_string(file_entry, "path", f"run {run_index} file")
            role = _manifest_string(file_entry, "role", f"run {run_index} file")
            _validate_bundle_file_role(rel_path, role)
            file_path = _resolve_bundle_relative(bundle_root, rel_path)
            expected_files.add(rel_path)
            _assert_file_digest(file_path, file_entry, rel_path)
            _assert_file_has_no_public_secret(file_path, rel_path)
            file_count += 1
        omitted = run_manifest.get("omitted_artifacts", [])
        if not isinstance(omitted, list):
            raise RegistryError(f"bundle run {run_index} omitted_artifacts must be a list")
        omitted_count += len(omitted)

    actual_files = {
        path.relative_to(bundle_root).as_posix()
        for path in bundle_root.rglob("*")
        if path.is_file()
    }
    extra_files = sorted(actual_files - expected_files)
    if extra_files:
        raise RegistryError(f"bundle contains unlisted file: {extra_files[0]}")

    return _ValidatedBundle(
        bundle_dir=bundle_root,
        runs=loaded_runs,
        files=file_count,
        omitted_artifacts=omitted_count,
        provenance=provenance,
    )


def _assert_report_schema(conn: sqlite3.Connection, db: Path) -> None:
    version = conn.execute("PRAGMA user_version").fetchone()
    if version is None or int(version[0]) < REGISTRY_SCHEMA_VERSION:
        raise RegistryError(
            f"registry report requires schema version {REGISTRY_SCHEMA_VERSION}: {db}"
        )
    meta = conn.execute(
        "SELECT value FROM registry_meta WHERE key = 'schema_version'"
    ).fetchone()
    if meta is None or meta["value"] != str(REGISTRY_SCHEMA_VERSION):
        raise RegistryError(
            f"registry report requires schema version {REGISTRY_SCHEMA_VERSION}: {db}"
        )


def _select_report_run_rows(
    conn: sqlite3.Connection,
    *,
    run_ids: list[int] | None,
    labels: list[str] | None,
    command: str,
) -> list[sqlite3.Row]:
    if run_ids:
        placeholders = ",".join("?" for _ in run_ids)
        rows = conn.execute(
            f"""
            SELECT id, result_dir, label, hardware_json, run_metadata_json
            FROM runs
            WHERE id IN ({placeholders})
            ORDER BY id
            """,
            tuple(run_ids),
        ).fetchall()
        found_ids = {int(row["id"]) for row in rows}
        missing = [run_id for run_id in run_ids if run_id not in found_ids]
        if missing:
            raise RegistryError(f"{command} run_id not found: {missing[0]}")
        return rows

    if labels:
        placeholders = ",".join("?" for _ in labels)
        rows = conn.execute(
            f"""
            SELECT id, result_dir, label, hardware_json, run_metadata_json
            FROM runs
            WHERE label IN ({placeholders})
            ORDER BY id
            """,
            tuple(labels),
        ).fetchall()
        found_labels = {str(row["label"]) for row in rows}
        missing = [label for label in labels if label not in found_labels]
        if missing:
            raise RegistryError(f"{command} label not found: {missing[0]}")
        return rows

    return conn.execute(
        """
        SELECT id, result_dir, label, hardware_json, run_metadata_json
        FROM runs
        ORDER BY id
        """
    ).fetchall()


def _registry_result_run(conn: sqlite3.Connection, row: sqlite3.Row) -> ResultRun:
    raw_rows = conn.execute(
        """
        SELECT raw_json
        FROM result_rows
        WHERE run_id = ?
        ORDER BY row_index
        """,
        (row["id"],),
    ).fetchall()
    records: list[dict[str, Any]] = []
    for index, raw_row in enumerate(raw_rows, start=1):
        try:
            record = json.loads(raw_row["raw_json"])
        except json.JSONDecodeError as exc:
            raise RegistryError(
                f"could not parse indexed raw_json for run_id {row['id']} row {index}"
            ) from exc
        if not isinstance(record, dict):
            raise RegistryError(
                f"indexed raw_json for run_id {row['id']} row {index} is not an object"
            )
        records.append(record)
    if not records:
        raise RegistryError(f"registry run_id {row['id']} has no indexed rows")
    return ResultRun(
        path=Path(row["result_dir"]),
        label=row["label"],
        records=records,
        hardware=_json_object_or_none(row["hardware_json"], "hardware_json", row["id"]),
        run_metadata=_json_object_or_none(
            row["run_metadata_json"],
            "run_metadata_json",
            row["id"],
        ),
        artifact_root=None,
    )


def _validate_registry_selection(
    command: str,
    *,
    run_ids: list[int] | None,
    labels: list[str] | None,
) -> None:
    if run_ids is not None and labels is not None:
        raise RegistryError(f"{command} accepts either --run-id or --label, not both")
    if run_ids is not None:
        if not run_ids:
            raise RegistryError(f"{command} --run-id requires at least one value")
        for run_id in run_ids:
            if isinstance(run_id, bool) or not isinstance(run_id, int) or run_id < 1:
                raise RegistryError(
                    f"{command} --run-id values must be integers >= 1"
                )
    if labels is not None:
        if not labels:
            raise RegistryError(f"{command} --label requires at least one value")
        for label in labels:
            if not isinstance(label, str) or label == "":
                raise RegistryError(f"{command} --label values must be non-empty")


def _validate_registry_query_filters(
    *,
    pack_id: str | None,
    case_id: str | None,
    adapter: str | None,
    model: str | None,
    host_label: str | None,
    runtime_name: str | None,
    model_quantization: str | None,
    limit: int | None,
) -> None:
    for name, value in (
        ("--pack", pack_id),
        ("--case", case_id),
        ("--adapter", adapter),
        ("--model", model),
        ("--host-label", host_label),
        ("--runtime", runtime_name),
        ("--quantization", model_quantization),
    ):
        if value is not None and value == "":
            raise RegistryError(f"registry query {name} value must be non-empty")
    if limit is not None:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise RegistryError("registry query --limit must be an integer >= 1")


def _load_registry_site_snapshot(
    db_path: Path | str,
    *,
    run_ids: list[int] | None,
    labels: list[str] | None,
) -> tuple[
    list[ResultRun],
    list[sqlite3.Row],
    list[sqlite3.Row],
    list[_SiteComparisonMetric],
]:
    if str(db_path) == "":
        raise RegistryError("registry database path must not be empty")
    _validate_registry_selection("registry site", run_ids=run_ids, labels=labels)
    db = Path(db_path)
    if not db.is_file():
        raise RegistryError(f"registry database not found: {db}")

    try:
        with sqlite3.connect(db) as conn:
            conn.execute("PRAGMA query_only = ON")
            conn.row_factory = sqlite3.Row
            _assert_report_schema(conn, db)
            selected_rows = _select_report_run_rows(
                conn,
                run_ids=run_ids,
                labels=labels,
                command="registry site",
            )
            if not selected_rows:
                raise RegistryError("registry site selection matched no runs")
            runs = [_registry_result_run(conn, row) for row in selected_rows]
            selected_ids = [int(row["id"]) for row in selected_rows]
            return (
                runs,
                _select_site_run_rows(conn, selected_ids),
                _select_site_case_rows(conn, selected_ids),
                _select_site_metric_rows(conn, selected_ids),
            )
    except sqlite3.Error as exc:
        raise RegistryError(f"could not read registry database {db}: {exc}") from exc


def _select_site_run_rows(
    conn: sqlite3.Connection,
    run_ids: list[int],
) -> list[sqlite3.Row]:
    placeholders = ",".join("?" for _ in run_ids)
    return conn.execute(
        f"""
        SELECT id, label, row_count, imported_at, run_jsonl_sha256,
               pack_ids_json, pack_versions_json, adapters_json, models_json,
               endpoints_json, host_hostname, host_platform, host_label,
               host_repo_commit, comparison_mode, comparison_boundary,
               runtime_name, runtime_version, runtime_endpoint,
               model_metadata_id, model_quantization, model_artifact_repo,
               model_artifact_file, model_revision, model_sha256,
               operating_power, operating_thermal, operating_background_load
        FROM runs
        WHERE id IN ({placeholders})
        ORDER BY id
        """,
        tuple(run_ids),
    ).fetchall()


def _select_site_case_rows(
    conn: sqlite3.Connection,
    run_ids: list[int],
) -> list[sqlite3.Row]:
    placeholders = ",".join("?" for _ in run_ids)
    return conn.execute(
        f"""
        SELECT r.id AS run_id, r.label AS run_label, s.pack_id,
               s.pack_version, s.case_id, s.row_count, s.ok_count,
               s.prompt_token_rows, s.prompt_token_median,
               s.cached_prompt_token_rows, s.cached_prompt_token_median,
               s.prefill_tps_rows, s.prefill_tps_median,
               r.host_label, r.host_hostname, r.host_platform,
               r.runtime_name, r.models_json, r.model_metadata_id,
               r.model_quantization
        FROM result_case_stats AS s
        JOIN runs AS r ON r.id = s.run_id
        WHERE s.run_id IN ({placeholders})
        ORDER BY s.run_id, s.pack_id, s.pack_version, s.case_id
        """,
        tuple(run_ids),
    ).fetchall()


def _select_site_metric_rows(
    conn: sqlite3.Connection,
    run_ids: list[int],
) -> list[_SiteComparisonMetric]:
    placeholders = ",".join("?" for _ in run_ids)
    rows = conn.execute(
        f"""
        SELECT r.id AS run_id, r.label AS run_label, r.host_label,
               r.host_hostname, r.host_platform, r.runtime_name,
               r.model_metadata_id, r.model_quantization, rr.model,
               rr.pack_id, rr.pack_version, rr.case_id, rr.ok,
               rr.scoring_passed, rr.wall_s, rr.ttft_s,
               rr.decode_tps, rr.total_tps, rr.prompt_tokens,
               rr.cached_prompt_tokens, rr.output_tokens
        FROM result_rows AS rr
        JOIN runs AS r ON r.id = rr.run_id
        WHERE rr.run_id IN ({placeholders})
        ORDER BY rr.run_id, rr.pack_id, rr.pack_version, rr.case_id, rr.row_index
        """,
        tuple(run_ids),
    ).fetchall()

    grouped: dict[tuple[object, ...], list[sqlite3.Row]] = {}
    for row in rows:
        key = (
            row["run_id"],
            row["pack_id"],
            row["pack_version"],
            row["case_id"],
        )
        grouped.setdefault(key, []).append(row)

    metrics: list[_SiteComparisonMetric] = []
    for group_rows in grouped.values():
        first = group_rows[0]
        scoring_values = [
            int(row["scoring_passed"])
            for row in group_rows
            if row["scoring_passed"] is not None
        ]
        metrics.append(
            _SiteComparisonMetric(
                run_id=int(first["run_id"]),
                run_label=str(first["run_label"]),
                pack_id=str(first["pack_id"]),
                pack_version=str(first["pack_version"]),
                case_id=str(first["case_id"]),
                host_label=_optional_text(first["host_label"]),
                host_hostname=_optional_text(first["host_hostname"]),
                host_platform=_optional_text(first["host_platform"]),
                runtime_name=_optional_text(first["runtime_name"]),
                model_metadata_id=_optional_text(first["model_metadata_id"]),
                model=_optional_text(first["model"]),
                model_quantization=_optional_text(first["model_quantization"]),
                rows=len(group_rows),
                ok_count=sum(1 for row in group_rows if int(row["ok"]) == 1),
                scoring_passed_count=sum(scoring_values),
                scoring_rows=len(scoring_values),
                wall_s_median=_site_median(row["wall_s"] for row in group_rows),
                ttft_s_median=_site_median(row["ttft_s"] for row in group_rows),
                decode_tps_median=_site_median(row["decode_tps"] for row in group_rows),
                total_tps_median=_site_median(row["total_tps"] for row in group_rows),
                prompt_tokens_median=_site_median(
                    row["prompt_tokens"] for row in group_rows
                ),
                cached_prompt_tokens_median=_site_median(
                    row["cached_prompt_tokens"] for row in group_rows
                ),
                output_tokens_median=_site_median(
                    row["output_tokens"] for row in group_rows
                ),
            )
        )
    return metrics


def _select_registry_query_rows(
    conn: sqlite3.Connection,
    run_ids: list[int],
    *,
    pack_id: str | None,
    case_id: str | None,
    adapter: str | None,
    model: str | None,
    host_label: str | None,
    runtime_name: str | None,
    model_quantization: str | None,
    ok: bool | None,
    scoring_passed: bool | None,
    limit: int | None,
) -> list[sqlite3.Row]:
    placeholders = ",".join("?" for _ in run_ids)
    conditions = [f"rr.run_id IN ({placeholders})"]
    params: list[object] = list(run_ids)
    for column, value in (
        ("rr.pack_id", pack_id),
        ("rr.case_id", case_id),
        ("rr.adapter", adapter),
        ("rr.model", model),
        ("r.host_label", host_label),
        ("r.runtime_name", runtime_name),
        ("r.model_quantization", model_quantization),
    ):
        if value is None:
            continue
        conditions.append(f"{column} = ?")
        params.append(value)
    if ok is not None:
        conditions.append("rr.ok = ?")
        params.append(1 if ok else 0)
    if scoring_passed is not None:
        conditions.append("rr.scoring_passed = ?")
        params.append(1 if scoring_passed else 0)

    limit_sql = ""
    if limit is not None:
        limit_sql = " LIMIT ?"
        params.append(limit)

    return conn.execute(
        f"""
        SELECT r.id AS run_id, r.label, r.result_dir, r.imported_at,
               r.host_label, r.host_platform, r.host_repo_commit,
               r.comparison_mode, r.comparison_boundary,
               r.runtime_name, r.runtime_version, r.runtime_endpoint,
               r.model_metadata_id, r.model_quantization,
               r.model_artifact_repo, r.model_artifact_file,
               r.model_revision, r.model_sha256,
               rr.row_index, rr.pack_id, rr.pack_version, rr.case_id,
               rr.repetition, rr.adapter, rr.model, rr.endpoint, rr.ok,
               rr.wall_s, rr.ttft_s, rr.prefill_tps, rr.decode_tps,
               rr.total_tps, rr.prompt_tokens, rr.output_tokens,
               rr.cached_prompt_tokens, rr.scoring_mode, rr.scoring_passed,
               rr.repo_task_status, rr.verify_exit_code
        FROM result_rows AS rr
        JOIN runs AS r ON r.id = rr.run_id
        WHERE {" AND ".join(conditions)}
        ORDER BY rr.run_id, rr.row_index
        {limit_sql}
        """,
        tuple(params),
    ).fetchall()


def _registry_query_row_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "run_id": int(row["run_id"]),
        "label": row["label"],
        "result_dir": row["result_dir"],
        "imported_at": row["imported_at"],
        "row_index": int(row["row_index"]),
        "pack": {
            "id": row["pack_id"],
            "version": row["pack_version"],
        },
        "case": row["case_id"],
        "repetition": row["repetition"],
        "adapter": row["adapter"],
        "model": row["model"],
        "endpoint": row["endpoint"],
        "ok": bool(row["ok"]),
        "timing": {
            "wall_s": row["wall_s"],
            "ttft_s": row["ttft_s"],
            "prefill_tps": row["prefill_tps"],
            "decode_tps": row["decode_tps"],
            "total_tps": row["total_tps"],
        },
        "tokens": {
            "prompt": row["prompt_tokens"],
            "output": row["output_tokens"],
            "cached_prompt": row["cached_prompt_tokens"],
        },
        "scoring": {
            "mode": row["scoring_mode"],
            "passed": _nullable_bool(row["scoring_passed"]),
        },
        "repo_task": {
            "status": row["repo_task_status"],
            "verify_exit_code": row["verify_exit_code"],
        },
        "host": {
            "label": row["host_label"],
            "platform": row["host_platform"],
            "repo_commit": row["host_repo_commit"],
        },
        "comparison": {
            "mode": row["comparison_mode"],
            "boundary": row["comparison_boundary"],
        },
        "runtime": {
            "name": row["runtime_name"],
            "version": row["runtime_version"],
            "endpoint": row["runtime_endpoint"],
        },
        "model_metadata": {
            "id": row["model_metadata_id"],
            "quantization": row["model_quantization"],
            "artifact_repo": row["model_artifact_repo"],
            "artifact_file": row["model_artifact_file"],
            "revision": row["model_revision"],
            "sha256": row["model_sha256"],
        },
    }


def _render_static_site_html(
    *,
    db_path: Path,
    run_rows: list[sqlite3.Row],
    case_rows: list[sqlite3.Row],
    metric_rows: list[_SiteComparisonMetric],
    report_markdown: str,
    generated_at: str,
) -> str:
    lines = [
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>benchpack registry snapshot</title>",
        "<style>",
        "body{margin:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#202124;background:#f8faf9;line-height:1.45}",
        "header{background:#12343b;color:#fff;padding:24px 32px}",
        "main{padding:24px 32px;max-width:1440px}",
        "h1{font-size:28px;margin:0 0 8px}h2{font-size:20px;margin:28px 0 12px}",
        "p{margin:0 0 12px}.meta{color:#d7e4e5}",
        "code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.92em}",
        ".filters{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin:0 0 12px}",
        ".filters label{display:grid;gap:4px;font-size:12px;font-weight:600;color:#334244}",
        ".filters input,.filters select{font:inherit;font-size:13px;padding:7px 8px;border:1px solid #b8c9ca;background:#fff;color:#202124}",
        ".filter-count{color:#526466;font-size:13px}",
        ".is-hidden{display:none}",
        ".table-wrap{overflow-x:auto;border:1px solid #cbd8d9;background:#fff}",
        "table{border-collapse:collapse;width:100%;font-size:13px}",
        "th,td{border-bottom:1px solid #e1e8e8;padding:8px 10px;text-align:left;vertical-align:top;white-space:nowrap}",
        "th{background:#edf4f2;color:#273536;font-weight:600;position:sticky;top:0}",
        "tr:nth-child(even) td{background:#fbfdfc}",
        "pre{background:#101820;color:#f5f7f7;overflow:auto;padding:16px;border-radius:6px;font-size:12px;line-height:1.5}",
        "a{color:#0b6670}",
        "</style>",
        "</head>",
        "<body>",
        "<header>",
        "<h1>benchpack registry snapshot</h1>",
        (
            '<p class="meta">Generated {generated} from <code>{db}</code>. '
            "Static, read-only export over indexed compact rows.</p>"
        ).format(
            generated=_html(generated_at),
            db=_html(db_path.name or str(db_path)),
        ),
        (
            '<p class="meta">Machine-readable snapshot: '
            f'<a href="{STATIC_SITE_SNAPSHOT_FILENAME}">'
            f"{STATIC_SITE_SNAPSHOT_FILENAME}</a>.</p>"
        ),
        "</header>",
        "<main>",
        "<section>",
        "<h2>Browse Filters</h2>",
        '<div class="filters" data-registry-filters>',
        '<label>Search<input id="filter-search" type="search" '
        'placeholder="run, pack, model, host"></label>',
        '<label>Table<select id="filter-table">'
        '<option value="">All tables</option>'
        '<option value="runs">Runs</option>'
        '<option value="comparison">Comparison Matrix</option>'
        '<option value="cases">Case Metrics</option>'
        "</select></label>",
        _site_filter_select(
            "filter-pack",
            "Pack",
            _site_pack_filter_options(run_rows, case_rows, metric_rows),
        ),
        _site_filter_select(
            "filter-case",
            "Case",
            _site_case_filter_options(case_rows, metric_rows),
        ),
        _site_filter_select(
            "filter-host",
            "Host",
            _site_host_filter_options(run_rows, case_rows, metric_rows),
        ),
        _site_filter_select(
            "filter-runtime",
            "Runtime",
            _site_runtime_filter_options(run_rows, case_rows, metric_rows),
        ),
        _site_filter_select(
            "filter-model",
            "Model",
            _site_model_filter_options(run_rows, case_rows, metric_rows),
        ),
        _site_filter_select(
            "filter-quantization",
            "Quantization",
            _site_quantization_filter_options(run_rows, case_rows, metric_rows),
        ),
        "</div>",
        '<p id="filter-count" class="filter-count"></p>',
        "</section>",
        '<section data-registry-section="runs">',
        "<h2>Runs</h2>",
        '<div class="table-wrap">',
        "<table>",
        "<thead><tr>"
        "<th>id</th><th>label</th><th>imported</th><th>rows</th>"
        "<th>packs</th><th>adapters</th><th>models</th><th>endpoints</th>"
        "<th>runtime</th><th>model metadata</th><th>quantization</th>"
        "<th>model artifact</th><th>model revision</th><th>model sha256</th>"
        "<th>host</th><th>comparison</th><th>repo commit</th><th>operating</th>"
        "<th>run.jsonl sha256</th>"
        "</tr></thead>",
        "<tbody>",
    ]
    for row in run_rows:
        packs = _json_list_values(row["pack_ids_json"])
        models = _json_list_values(row["models_json"])
        search_values = [
            row["id"],
            row["label"],
            row["imported_at"],
            row["row_count"],
            *packs,
            *_json_list_values(row["adapters_json"]),
            *models,
            *_json_list_values(row["endpoints_json"]),
            _site_runtime_cell(row),
            row["model_metadata_id"],
            row["model_quantization"],
            _site_model_artifact_cell(row),
            row["model_revision"],
            row["model_sha256"],
            _site_host_cell(row),
            _site_comparison_cell(row),
            row["host_repo_commit"],
            _site_operating_cell(row),
            row["run_jsonl_sha256"],
        ]
        lines.append(
            "<tr class=\"registry-row\""
            f" data-table=\"runs\""
            f" data-pack=\"{_site_filter_values_attr(packs)}\""
            f" data-case=\"\""
            " data-host=\""
            f"{_site_filter_values_attr([row['host_label'], row['host_hostname'], row['host_platform']])}\""
            f" data-runtime=\"{_site_filter_values_attr([row['runtime_name']])}\""
            f" data-model=\"{_site_filter_values_attr([row['model_metadata_id'], *models])}\""
            f" data-quantization=\"{_site_filter_values_attr([row['model_quantization']])}\""
            f" data-search=\"{_site_search_attr(search_values)}\">"
            f"<td>{_html(row['id'])}</td>"
            f"<td>{_html(row['label'])}</td>"
            f"<td>{_html(row['imported_at'] or '—')}</td>"
            f"<td>{_html(row['row_count'])}</td>"
            f"<td>{_html(_json_list_cell(row['pack_ids_json'], row['pack_versions_json']))}</td>"
            f"<td>{_html(_json_list_cell(row['adapters_json']))}</td>"
            f"<td>{_html(_json_list_cell(row['models_json']))}</td>"
            f"<td>{_html(_json_list_cell(row['endpoints_json']))}</td>"
            f"<td>{_html(_site_runtime_cell(row))}</td>"
            f"<td>{_html(row['model_metadata_id'] or '—')}</td>"
            f"<td>{_html(row['model_quantization'] or '—')}</td>"
            f"<td>{_html(_site_model_artifact_cell(row))}</td>"
            f"<td>{_html(row['model_revision'] or '—')}</td>"
            f"<td>{_html(row['model_sha256'] or '—')}</td>"
            f"<td>{_html(_site_host_cell(row))}</td>"
            f"<td>{_html(_site_comparison_cell(row))}</td>"
            f"<td>{_html(row['host_repo_commit'] or '—')}</td>"
            f"<td>{_html(_site_operating_cell(row))}</td>"
            f"<td>{_html(row['run_jsonl_sha256'] or '—')}</td>"
            "</tr>"
        )
    lines.extend(
        [
            "</tbody>",
            "</table>",
            "</div>",
            "</section>",
            '<section data-registry-section="comparison">',
            "<h2>Comparison Matrix</h2>",
            '<div class="table-wrap">',
            "<table>",
            "<thead><tr>"
            "<th>run</th><th>pack</th><th>case</th><th>host</th>"
            "<th>runtime</th><th>model</th><th>quantization</th>"
            "<th>rows</th><th>ok</th><th>scoring passed</th>"
            "<th>wall med s</th><th>TTFT med s</th>"
            "<th>decode TPS med</th><th>total TPS med</th>"
            "<th>prompt tok med</th><th>cached tok med</th><th>output tok med</th>"
            "</tr></thead>",
            "<tbody>",
        ]
    )
    for row in metric_rows:
        search_values = [
            row.run_label,
            row.pack_id,
            row.pack_version,
            row.case_id,
            row.host_label,
            row.host_hostname,
            row.host_platform,
            row.runtime_name,
            row.model_metadata_id,
            row.model,
            row.model_quantization,
            row.rows,
            row.ok_count,
            _site_count_cell(row.scoring_passed_count, row.scoring_rows),
        ]
        lines.append(
            "<tr class=\"registry-row\""
            f" data-table=\"comparison\""
            f" data-pack=\"{_site_filter_values_attr([row.pack_id])}\""
            f" data-case=\"{_site_filter_values_attr([row.case_id])}\""
            f" data-host=\"{_site_filter_values_attr([row.host_label, row.host_hostname, row.host_platform])}\""
            f" data-runtime=\"{_site_filter_values_attr([row.runtime_name])}\""
            f" data-model=\"{_site_filter_values_attr([row.model_metadata_id, row.model])}\""
            f" data-quantization=\"{_site_filter_values_attr([row.model_quantization])}\""
            f" data-search=\"{_site_search_attr(search_values)}\">"
            f"<td>{_html(row.run_label)}</td>"
            f"<td>{_html(row.pack_id + ' ' + row.pack_version)}</td>"
            f"<td>{_html(row.case_id)}</td>"
            f"<td>{_html(_site_parts_cell(row.host_label, row.host_platform))}</td>"
            f"<td>{_html(row.runtime_name or '—')}</td>"
            f"<td>{_html(row.model_metadata_id or '—')}</td>"
            f"<td>{_html(row.model_quantization or '—')}</td>"
            f"<td>{_html(row.rows)}</td>"
            f"<td>{_html(row.ok_count)}</td>"
            f"<td>{_html(_site_count_cell(row.scoring_passed_count, row.scoring_rows))}</td>"
            f"<td>{_html(_site_float(row.wall_s_median))}</td>"
            f"<td>{_html(_site_float(row.ttft_s_median))}</td>"
            f"<td>{_html(_site_float(row.decode_tps_median))}</td>"
            f"<td>{_html(_site_float(row.total_tps_median))}</td>"
            f"<td>{_html(_site_float(row.prompt_tokens_median))}</td>"
            f"<td>{_html(_site_float(row.cached_prompt_tokens_median))}</td>"
            f"<td>{_html(_site_float(row.output_tokens_median))}</td>"
            "</tr>"
        )
    lines.extend(
        [
            "</tbody>",
            "</table>",
            "</div>",
            "</section>",
            '<section data-registry-section="cases">',
            "<h2>Case Metrics</h2>",
            '<div class="table-wrap">',
            "<table>",
            "<thead><tr>"
            "<th>run</th><th>pack</th><th>case</th><th>rows</th><th>ok</th>"
            "<th>prompt rows</th><th>prompt median</th>"
            "<th>cached rows</th><th>cached median</th>"
            "<th>prefill rows</th><th>prefill median</th>"
            "</tr></thead>",
            "<tbody>",
        ]
    )
    for row in case_rows:
        search_values = [
            row["run_label"],
            row["pack_id"],
            row["pack_version"],
            row["case_id"],
            row["host_label"],
            row["host_hostname"],
            row["host_platform"],
            row["runtime_name"],
            row["model_metadata_id"],
            *_json_list_values(row["models_json"]),
            row["model_quantization"],
        ]
        models = _json_list_values(row["models_json"])
        lines.append(
            "<tr class=\"registry-row\""
            f" data-table=\"cases\""
            f" data-pack=\"{_site_filter_values_attr([row['pack_id']])}\""
            f" data-case=\"{_site_filter_values_attr([row['case_id']])}\""
            f" data-host=\"{_site_filter_values_attr([row['host_label'], row['host_hostname'], row['host_platform']])}\""
            f" data-runtime=\"{_site_filter_values_attr([row['runtime_name']])}\""
            f" data-model=\"{_site_filter_values_attr([row['model_metadata_id'], *models])}\""
            f" data-quantization=\"{_site_filter_values_attr([row['model_quantization']])}\""
            f" data-search=\"{_site_search_attr(search_values)}\">"
            f"<td>{_html(row['run_label'])}</td>"
            f"<td>{_html(row['pack_id'] + ' ' + row['pack_version'])}</td>"
            f"<td>{_html(row['case_id'])}</td>"
            f"<td>{_html(row['row_count'])}</td>"
            f"<td>{_html(row['ok_count'])}</td>"
            f"<td>{_html(row['prompt_token_rows'])}</td>"
            f"<td>{_html(_site_float(row['prompt_token_median']))}</td>"
            f"<td>{_html(row['cached_prompt_token_rows'])}</td>"
            f"<td>{_html(_site_float(row['cached_prompt_token_median']))}</td>"
            f"<td>{_html(row['prefill_tps_rows'])}</td>"
            f"<td>{_html(_site_float(row['prefill_tps_median']))}</td>"
            "</tr>"
        )
    lines.extend(
        [
            "</tbody>",
            "</table>",
            "</div>",
            "</section>",
            "<section>",
            "<h2>Markdown Report</h2>",
            (
                f'<p><a href="{STATIC_SITE_REPORT_FILENAME}">'
                f"Open {STATIC_SITE_REPORT_FILENAME}</a></p>"
            ),
            f"<pre>{_html(report_markdown)}</pre>",
            "</section>",
            "<script>",
            "const registryRows=Array.from(document.querySelectorAll('.registry-row'));",
            "const registrySections=Array.from(document.querySelectorAll('[data-registry-section]'));",
            "const filterIds=['pack','case','host','runtime','model','quantization'];",
            "const filters={search:document.getElementById('filter-search'),table:document.getElementById('filter-table')};",
            "for(const id of filterIds){filters[id]=document.getElementById('filter-'+id);}",
            "const countEl=document.getElementById('filter-count');",
            "function rowMatches(row){",
            "  if(filters.table.value&&row.dataset.table!==filters.table.value){return false;}",
            "  const query=filters.search.value.trim().toLowerCase();",
            "  if(query&&!(row.dataset.search||'').includes(query)){return false;}",
            "  for(const id of filterIds){",
            "    const value=filters[id].value;",
            "    if(!value){continue;}",
            "    const values=JSON.parse(row.dataset[id]||'[]');",
            "    if(!values.includes(value)){return false;}",
            "  }",
            "  return true;",
            "}",
            "function applyFilters(){",
            "  let shown=0;",
            "  for(const row of registryRows){",
            "    const visible=rowMatches(row);",
            "    row.classList.toggle('is-hidden',!visible);",
            "    if(visible){shown+=1;}",
            "  }",
            "  for(const section of registrySections){",
            "    const table=section.dataset.registrySection;",
            "    const visibleRows=section.querySelectorAll('.registry-row:not(.is-hidden)').length;",
            "    const hidden=(filters.table.value&&filters.table.value!==table)||visibleRows===0;",
            "    section.classList.toggle('is-hidden',hidden);",
            "  }",
            "  countEl.textContent=shown+' visible row'+(shown===1?'':'s')+' across generated tables.';",
            "}",
            "filters.search.addEventListener('input',applyFilters);",
            "filters.table.addEventListener('change',applyFilters);",
            "for(const id of filterIds){filters[id].addEventListener('change',applyFilters);}",
            "applyFilters();",
            "</script>",
            "</main>",
            "</body>",
            "</html>",
            "",
        ]
    )
    return "\n".join(lines)


def _render_static_site_snapshot_json(
    *,
    db_path: Path,
    run_rows: list[sqlite3.Row],
    case_rows: list[sqlite3.Row],
    metric_rows: list[_SiteComparisonMetric],
    generated_at: str,
) -> str:
    snapshot = {
        "schema_version": 1,
        "registry_schema_version": REGISTRY_SCHEMA_VERSION,
        "generated_at": generated_at,
        "source_database": db_path.name or str(db_path),
        "runs": [_site_run_row_dict(row) for row in run_rows],
        "comparison_matrix": [_site_metric_row_dict(row) for row in metric_rows],
        "case_metrics": [_site_case_row_dict(row) for row in case_rows],
        "report_path": STATIC_SITE_REPORT_FILENAME,
    }
    return json.dumps(snapshot, indent=2, sort_keys=True) + "\n"


def _site_run_row_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "label": row["label"],
        "imported_at": row["imported_at"],
        "row_count": int(row["row_count"]),
        "run_jsonl_sha256": row["run_jsonl_sha256"],
        "packs": _site_pack_list(row["pack_ids_json"], row["pack_versions_json"]),
        "pack_versions": _json_list_values(row["pack_versions_json"]),
        "adapters": _json_list_values(row["adapters_json"]),
        "models": _json_list_values(row["models_json"]),
        "endpoints": _json_list_values(row["endpoints_json"]),
        "host": {
            "label": row["host_label"],
            "hostname": row["host_hostname"],
            "platform": row["host_platform"],
            "repo_commit": row["host_repo_commit"],
        },
        "comparison": {
            "mode": row["comparison_mode"],
            "boundary": row["comparison_boundary"],
        },
        "runtime": {
            "name": row["runtime_name"],
            "version": row["runtime_version"],
            "endpoint": row["runtime_endpoint"],
        },
        "model_metadata": {
            "id": row["model_metadata_id"],
            "quantization": row["model_quantization"],
            "artifact_repo": row["model_artifact_repo"],
            "artifact_file": row["model_artifact_file"],
            "revision": row["model_revision"],
            "sha256": row["model_sha256"],
        },
        "operating_conditions": {
            "power": row["operating_power"],
            "thermal": row["operating_thermal"],
            "background_load": row["operating_background_load"],
        },
    }


def _site_pack_list(
    pack_ids_json: str | None,
    pack_versions_json: str | None,
) -> list[dict[str, str | None]]:
    pack_ids = _json_list_values(pack_ids_json)
    versions = _json_list_values(pack_versions_json)
    if len(pack_ids) != 1 or len(versions) != 1:
        return [{"id": pack_id, "version": None} for pack_id in pack_ids]
    return [{"id": pack_ids[0], "version": versions[0]}]


def _site_metric_row_dict(row: _SiteComparisonMetric) -> dict[str, Any]:
    return {
        "run_id": row.run_id,
        "run": row.run_label,
        "pack": {"id": row.pack_id, "version": row.pack_version},
        "case": row.case_id,
        "host": {
            "label": row.host_label,
            "hostname": row.host_hostname,
            "platform": row.host_platform,
        },
        "runtime": {"name": row.runtime_name},
        "model": row.model,
        "model_metadata": {
            "id": row.model_metadata_id,
            "quantization": row.model_quantization,
        },
        "rows": row.rows,
        "ok_count": row.ok_count,
        "scoring": {
            "passed_count": row.scoring_passed_count,
            "rows": row.scoring_rows,
        },
        "medians": {
            "wall_s": row.wall_s_median,
            "ttft_s": row.ttft_s_median,
            "decode_tps": row.decode_tps_median,
            "total_tps": row.total_tps_median,
            "prompt_tokens": row.prompt_tokens_median,
            "cached_prompt_tokens": row.cached_prompt_tokens_median,
            "output_tokens": row.output_tokens_median,
        },
    }


def _site_case_row_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "run_id": int(row["run_id"]),
        "run": row["run_label"],
        "pack": {"id": row["pack_id"], "version": row["pack_version"]},
        "case": row["case_id"],
        "rows": int(row["row_count"]),
        "ok_count": int(row["ok_count"]),
        "prompt_tokens": {
            "rows": int(row["prompt_token_rows"]),
            "median": row["prompt_token_median"],
        },
        "cached_prompt_tokens": {
            "rows": int(row["cached_prompt_token_rows"]),
            "median": row["cached_prompt_token_median"],
        },
        "prefill_tps": {
            "rows": int(row["prefill_tps_rows"]),
            "median": row["prefill_tps_median"],
        },
        "host": {
            "label": row["host_label"],
            "hostname": row["host_hostname"],
            "platform": row["host_platform"],
        },
        "runtime": {"name": row["runtime_name"]},
        "models": _json_list_values(row["models_json"]),
        "model_metadata": {
            "id": row["model_metadata_id"],
            "quantization": row["model_quantization"],
        },
    }


def _html(value: object) -> str:
    return html_lib.escape(str(value), quote=True)


def _site_filter_select(
    element_id: str,
    label: str,
    options: list[tuple[str, str]],
) -> str:
    rendered = [
        f'<label>{_html(label)}<select id="{_html(element_id)}">',
        '<option value="">All</option>',
    ]
    for key, display in options:
        rendered.append(f'<option value="{_html(key)}">{_html(display)}</option>')
    rendered.append("</select></label>")
    return "".join(rendered)


def _site_pack_filter_options(
    run_rows: list[sqlite3.Row],
    case_rows: list[sqlite3.Row],
    metric_rows: list[_SiteComparisonMetric],
) -> list[tuple[str, str]]:
    values: list[object] = []
    for row in run_rows:
        values.extend(_json_list_values(row["pack_ids_json"]))
    values.extend(row["pack_id"] for row in case_rows)
    values.extend(row.pack_id for row in metric_rows)
    return _site_filter_options(values)


def _site_case_filter_options(
    case_rows: list[sqlite3.Row],
    metric_rows: list[_SiteComparisonMetric],
) -> list[tuple[str, str]]:
    return _site_filter_options(
        [row["case_id"] for row in case_rows] + [row.case_id for row in metric_rows]
    )


def _site_host_filter_options(
    run_rows: list[sqlite3.Row],
    case_rows: list[sqlite3.Row],
    metric_rows: list[_SiteComparisonMetric],
) -> list[tuple[str, str]]:
    values: list[object] = []
    for row in run_rows:
        values.extend([row["host_label"], row["host_hostname"], row["host_platform"]])
    for row in case_rows:
        values.extend([row["host_label"], row["host_hostname"], row["host_platform"]])
    for row in metric_rows:
        values.extend([row.host_label, row.host_hostname, row.host_platform])
    return _site_filter_options(values)


def _site_runtime_filter_options(
    run_rows: list[sqlite3.Row],
    case_rows: list[sqlite3.Row],
    metric_rows: list[_SiteComparisonMetric],
) -> list[tuple[str, str]]:
    return _site_filter_options(
        [row["runtime_name"] for row in run_rows]
        + [row["runtime_name"] for row in case_rows]
        + [row.runtime_name for row in metric_rows]
    )


def _site_model_filter_options(
    run_rows: list[sqlite3.Row],
    case_rows: list[sqlite3.Row],
    metric_rows: list[_SiteComparisonMetric],
) -> list[tuple[str, str]]:
    values: list[object] = []
    for row in run_rows:
        values.extend([row["model_metadata_id"], *_json_list_values(row["models_json"])])
    for row in case_rows:
        values.extend([row["model_metadata_id"], *_json_list_values(row["models_json"])])
    for row in metric_rows:
        values.extend([row.model_metadata_id, row.model])
    return _site_filter_options(values)


def _site_quantization_filter_options(
    run_rows: list[sqlite3.Row],
    case_rows: list[sqlite3.Row],
    metric_rows: list[_SiteComparisonMetric],
) -> list[tuple[str, str]]:
    return _site_filter_options(
        [row["model_quantization"] for row in run_rows]
        + [row["model_quantization"] for row in case_rows]
        + [row.model_quantization for row in metric_rows]
    )


def _site_filter_options(values: Iterable[object]) -> list[tuple[str, str]]:
    by_key: dict[str, str] = {}
    for value in values:
        key = _site_filter_key(value)
        if key is None:
            continue
        by_key.setdefault(key, str(value))
    return sorted(by_key.items(), key=lambda item: item[1].lower())


def _site_filter_values_attr(values: Iterable[object]) -> str:
    keys: list[str] = []
    for value in values:
        key = _site_filter_key(value)
        if key is not None:
            keys.append(key)
    return _html(json.dumps(list(dict.fromkeys(keys)), separators=(",", ":")))


def _site_search_attr(values: Iterable[object]) -> str:
    rendered = [
        str(value).lower()
        for value in values
        if value not in (None, "", [], "—")
    ]
    return _html(" ".join(rendered))


def _site_filter_key(value: object) -> str | None:
    if value in (None, "", [], "—"):
        return None
    return str(value).strip().lower()


def _json_list_cell(raw_json: str | None, paired_json: str | None = None) -> str:
    values = _json_list_values(raw_json)
    if paired_json is None:
        return ", ".join(values) if values else "—"
    paired = _json_list_values(paired_json)
    if not values:
        return "—"
    if len(values) == 1 and len(paired) == 1:
        return f"{values[0]} {paired[0]}"
    if paired:
        return ", ".join(values) + " (versions: " + ", ".join(paired) + ")"
    return ", ".join(values)


def _json_list_values(raw_json: str | None) -> list[str]:
    if raw_json is None:
        return []
    try:
        value = json.loads(raw_json)
    except json.JSONDecodeError:
        return []
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item not in (None, "", [])]


def _site_runtime_cell(row: sqlite3.Row) -> str:
    parts = [
        row["runtime_name"],
        row["runtime_version"],
        row["runtime_endpoint"],
    ]
    rendered = [str(part) for part in parts if part not in (None, "", [])]
    return "; ".join(rendered) if rendered else "—"


def _site_model_artifact_cell(row: sqlite3.Row) -> str:
    parts = [row["model_artifact_repo"], row["model_artifact_file"]]
    rendered = [str(part) for part in parts if part not in (None, "", [])]
    return "; ".join(rendered) if rendered else "—"


def _site_host_cell(row: sqlite3.Row) -> str:
    parts = [
        row["host_label"],
        row["host_hostname"],
        row["host_platform"],
    ]
    rendered = [str(part) for part in parts if part not in (None, "", [])]
    return "; ".join(rendered) if rendered else "—"


def _site_comparison_cell(row: sqlite3.Row) -> str:
    parts = [row["comparison_mode"], row["comparison_boundary"]]
    rendered = [str(part) for part in parts if part not in (None, "", [])]
    return "; ".join(rendered) if rendered else "—"


def _site_operating_cell(row: sqlite3.Row) -> str:
    parts = [
        row["operating_power"],
        row["operating_thermal"],
        row["operating_background_load"],
    ]
    rendered = [str(part) for part in parts if part not in (None, "", [])]
    return "; ".join(rendered) if rendered else "—"


def _site_parts_cell(*parts: object) -> str:
    rendered = [str(part) for part in parts if part not in (None, "", [])]
    return "; ".join(rendered) if rendered else "—"


def _site_count_cell(passed: int, total: int) -> str:
    if total == 0:
        return "—"
    return f"{passed}/{total}"


def _site_median(values: Iterable[object]) -> float | None:
    numeric = [
        float(value)
        for value in values
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    ]
    if not numeric:
        return None
    return float(median(numeric))


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _site_float(value: object) -> str:
    if value is None:
        return "—"
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return "—"
    return f"{float(value):.2f}"


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


def _copy_run_into_bundle(
    *,
    run: ResultRun,
    bundle_root: Path,
    run_bundle_dir: Path,
    run_bundle_path: Path,
) -> tuple[dict[str, Any], int, int]:
    included: list[dict[str, Any]] = []
    omitted: list[dict[str, Any]] = []
    files_copied = 0

    for relative_path, role in _included_artifacts(run):
        source = _safe_existing_file(run.path, relative_path)
        if source is None:
            omitted.append(_omitted_artifact(run.path, relative_path, "missing-or-unsafe"))
            continue
        _assert_file_has_no_public_secret(source, relative_path)
        destination = run_bundle_dir / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        included.append(
            _file_manifest_entry(
                bundle_root,
                run_bundle_path / relative_path,
                role,
            )
        )
        files_copied += 1

    for relative_path, reason in _omitted_artifacts(run):
        omitted.append(_omitted_artifact(run.path, relative_path, reason))

    run_manifest = {
        "label": run.label,
        "source_result_name": run.path.name,
        "bundle_path": run_bundle_path.as_posix(),
        "row_count": len(run.records),
        "run_jsonl_sha256": _sha256(run.path / "run.jsonl"),
        "files": included,
        "omitted_artifacts": omitted,
    }
    return run_manifest, files_copied, len(omitted)


def _assert_bundle_output_disjoint_from_sources(
    bundle_root: Path,
    runs: list[ResultRun],
) -> None:
    bundle_resolved = bundle_root.resolve(strict=False)
    for run in runs:
        source = run.path.resolve()
        try:
            bundle_resolved.relative_to(source)
        except ValueError:
            pass
        else:
            raise RegistryError(
                "bundle output must be disjoint from source result directories: "
                f"{bundle_root}"
            )
        try:
            source.relative_to(bundle_resolved)
        except ValueError:
            pass
        else:
            raise RegistryError(
                "bundle output must be disjoint from source result directories: "
                f"{bundle_root}"
            )


def _included_artifacts(run: ResultRun) -> list[tuple[str, str]]:
    artifacts: list[tuple[str, str]] = [("run.jsonl", "run-jsonl")]
    for filename, role in (("hardware.json", "hardware"), ("run-metadata.json", "run-metadata")):
        if (run.path / filename).is_file():
            artifacts.append((filename, role))
    for record in run.records:
        patch = record.get("patch")
        if isinstance(patch, dict) and isinstance(patch.get("path"), str):
            artifacts.append((patch["path"], "patch"))
    try:
        model_call_summaries = summarize_model_call_logs(run.path)
    except ModelCallLogError as exc:
        raise RegistryError(str(exc)) from exc
    for summary in model_call_summaries:
        if summary.invalid == 0:
            artifacts.append((summary.relative_path, "model-call-log"))
    return _dedupe_artifacts(artifacts)


def _omitted_artifacts(run: ResultRun) -> list[tuple[str, str]]:
    omitted: list[tuple[str, str]] = []
    for record in run.records:
        raw = record.get("raw")
        if isinstance(raw, dict):
            for key in ("request_path", "response_path"):
                if isinstance(raw.get(key), str):
                    omitted.append((raw[key], "raw-payload-omitted"))
        workspace = record.get("workspace")
        if isinstance(workspace, dict) and isinstance(workspace.get("path"), str):
            omitted.append((workspace["path"], "workspace-omitted"))
        task = record.get("task")
        if isinstance(task, dict):
            for key in ("stdout_path", "stderr_path"):
                if isinstance(task.get(key), str):
                    omitted.append((task[key], "task-log-omitted"))
        verify = record.get("verify")
        if isinstance(verify, dict):
            for value in verify.values():
                if isinstance(value, str):
                    omitted.append((value, "verify-artifact-omitted"))
    try:
        summaries = summarize_model_call_logs(run.path)
    except ModelCallLogError as exc:
        raise RegistryError(str(exc)) from exc
    invalid_paths = {
        summary.relative_path for summary in summaries if summary.invalid != 0
    }
    safe_paths = {summary.relative_path for summary in summaries}
    for path in sorted(run.path.glob(MODEL_CALL_LOG_PATTERN)):
        try:
            relative_path = path.relative_to(run.path).as_posix()
        except ValueError:
            continue
        if relative_path in invalid_paths or relative_path not in safe_paths:
            omitted.append((relative_path, "unsafe-model-call-log-omitted"))
    return _dedupe_artifacts(omitted)


def _dedupe_artifacts(artifacts: list[tuple[str, str]]) -> list[tuple[str, str]]:
    seen: set[tuple[str, str]] = set()
    deduped: list[tuple[str, str]] = []
    for path, role in artifacts:
        key = (path, role)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(key)
    return deduped


def _omitted_artifact(root: Path, relative_path: str, reason: str) -> dict[str, Any]:
    entry: dict[str, Any] = {"path": relative_path, "reason": reason}
    source = _safe_existing_file(root, relative_path)
    if source is not None:
        entry["sha256"] = _sha256(source)
        entry["bytes"] = source.stat().st_size
    return entry


def _file_manifest_entry(bundle_root: Path, relative_path: Path, role: str) -> dict[str, Any]:
    bundle_relative = relative_path.as_posix()
    path = bundle_root / bundle_relative
    return {
        "path": bundle_relative,
        "role": role,
        "sha256": _sha256(path),
        "bytes": path.stat().st_size,
    }


def _write_bundle_manifest(bundle_root: Path, manifest: dict[str, Any]) -> None:
    manifest_path = bundle_root / BUNDLE_MANIFEST_FILENAME
    manifest_text = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    _assert_no_public_secret(manifest_text, BUNDLE_MANIFEST_FILENAME)
    manifest_path.write_text(manifest_text, encoding="utf-8")


def _safe_existing_file(root: Path, relative_path: str) -> Path | None:
    if relative_path == "" or Path(relative_path).is_absolute():
        return None
    root_resolved = root.resolve()
    candidate = (root_resolved / relative_path).resolve(strict=False)
    try:
        candidate.relative_to(root_resolved)
    except ValueError:
        return None
    if not candidate.is_file():
        return None
    return candidate


def _resolve_bundle_relative(bundle_root: Path, relative_path: str) -> Path:
    candidate = Path(relative_path)
    if (
        relative_path == ""
        or candidate.is_absolute()
        or any(part in ("", ".", "..") for part in candidate.parts)
    ):
        raise RegistryError(f"bundle path must be relative and non-empty: {relative_path!r}")
    root = bundle_root.resolve()
    path = (root / relative_path).resolve(strict=False)
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise RegistryError(f"bundle path escapes bundle root: {relative_path}") from exc
    return path


def _manifest_string(record: dict[str, Any], field: str, source: str) -> str:
    value = record.get(field)
    if not isinstance(value, str) or value == "":
        raise RegistryError(f"bundle {source} field {field!r} must be a non-empty string")
    return value


def _assert_file_digest(path: Path, entry: dict[str, Any], relative_path: str) -> None:
    if not path.is_file():
        raise RegistryError(f"bundle file missing: {relative_path}")
    expected_sha = entry.get("sha256")
    expected_bytes = entry.get("bytes")
    if not isinstance(expected_sha, str) or len(expected_sha) != 64:
        raise RegistryError(f"bundle file {relative_path} has invalid sha256 metadata")
    if not isinstance(expected_bytes, int) or isinstance(expected_bytes, bool):
        raise RegistryError(f"bundle file {relative_path} has invalid byte metadata")
    if _sha256(path) != expected_sha:
        raise RegistryError(f"bundle file hash mismatch: {relative_path}")
    if path.stat().st_size != expected_bytes:
        raise RegistryError(f"bundle file size mismatch: {relative_path}")


def _validate_bundle_file_role(relative_path: str, role: str) -> None:
    path = Path(relative_path)
    parts = path.parts
    if len(parts) < 3 or parts[0] != "runs":
        raise RegistryError(f"bundle file path has unexpected shape: {relative_path}")
    run_relative = parts[2:]
    if role == "run-jsonl" and run_relative != ("run.jsonl",):
        raise RegistryError(f"run-jsonl bundle file has unexpected path: {relative_path}")
    if role == "hardware" and run_relative != ("hardware.json",):
        raise RegistryError(f"hardware bundle file has unexpected path: {relative_path}")
    if role == "run-metadata" and run_relative != ("run-metadata.json",):
        raise RegistryError(f"run-metadata bundle file has unexpected path: {relative_path}")
    if role == "patch" and (
        len(run_relative) < 3
        or run_relative[0] != "patch"
        or Path(run_relative[-1]).suffix != ".diff"
    ):
        raise RegistryError(f"patch bundle file has unexpected path: {relative_path}")
    if role == "model-call-log" and (
        len(run_relative) != 3
        or run_relative[0] != "task"
        or not run_relative[-1].endswith(".model-calls.jsonl")
    ):
        raise RegistryError(f"model-call-log bundle file has unexpected name: {relative_path}")
    if role not in {"run-jsonl", "hardware", "run-metadata", "patch", "model-call-log"}:
        raise RegistryError(f"unknown bundle file role: {role}")


def _assert_no_public_secret(text: str, source: str) -> None:
    for pattern in _SECRET_PATTERNS:
        if pattern.search(text):
            raise RegistryError(f"possible secret detected in bundle file {source}")


def _assert_file_has_no_public_secret(path: Path, source: str) -> None:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise RegistryError(f"could not decode bundle file {source}") from exc
    except OSError as exc:
        raise RegistryError(f"could not read bundle file {source}: {exc.strerror}") from exc
    _assert_no_public_secret(text, source)


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip("-._").lower()
    return slug or "run"


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS registry_meta (
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL
        )
        """
    )
    conn.execute(_create_runs_table_sql())
    conn.execute(
        """
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
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS result_case_stats (
          id INTEGER PRIMARY KEY,
          run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
          pack_id TEXT NOT NULL,
          pack_version TEXT NOT NULL,
          case_id TEXT NOT NULL,
          row_count INTEGER NOT NULL,
          ok_count INTEGER NOT NULL,
          prompt_token_rows INTEGER NOT NULL,
          prompt_token_median REAL,
          cached_prompt_token_rows INTEGER NOT NULL,
          cached_prompt_token_median REAL,
          prefill_tps_rows INTEGER NOT NULL,
          prefill_tps_median REAL,
          UNIQUE(run_id, pack_id, pack_version, case_id)
        )
        """
    )
    _ensure_run_columns(conn)
    conn.execute(
        "INSERT OR REPLACE INTO registry_meta(key, value) VALUES (?, ?)",
        ("schema_version", str(REGISTRY_SCHEMA_VERSION)),
    )
    conn.execute(f"PRAGMA user_version = {REGISTRY_SCHEMA_VERSION}")


def _create_runs_table_sql() -> str:
    columns = ",\n          ".join(
        f"{name} {declaration}"
        for name, declaration in _RUN_COLUMN_DEFINITIONS
    )
    return f"CREATE TABLE IF NOT EXISTS runs (\n          {columns}\n        )"


def _ensure_run_columns(conn: sqlite3.Connection) -> None:
    existing = {
        row[1]
        for row in conn.execute("PRAGMA table_info(runs)").fetchall()
    }
    for column, declaration in _RUN_COLUMN_DEFINITIONS:
        if column not in existing:
            conn.execute(f"ALTER TABLE runs ADD COLUMN {column} {declaration}")


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
          host_platform, host_label, host_repo_commit, comparison_mode,
          comparison_boundary, runtime_name, runtime_version, runtime_endpoint,
          runtime_options_json, model_metadata_id, model_quantization,
          model_artifact_repo, model_artifact_file, model_revision, model_sha256,
          operating_power, operating_thermal, operating_background_load
        )
        VALUES (
          :result_dir, :label, :imported_at, :row_count, :run_jsonl_sha256,
          :pack_ids_json, :pack_versions_json, :adapters_json, :models_json,
          :endpoints_json, :hardware_json, :run_metadata_json, :host_hostname,
          :host_platform, :host_label, :host_repo_commit, :comparison_mode,
          :comparison_boundary, :runtime_name, :runtime_version, :runtime_endpoint,
          :runtime_options_json, :model_metadata_id, :model_quantization,
          :model_artifact_repo, :model_artifact_file, :model_revision, :model_sha256,
          :operating_power, :operating_thermal, :operating_background_load
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
          host_label = excluded.host_label,
          host_repo_commit = excluded.host_repo_commit,
          comparison_mode = excluded.comparison_mode,
          comparison_boundary = excluded.comparison_boundary,
          runtime_name = excluded.runtime_name,
          runtime_version = excluded.runtime_version,
          runtime_endpoint = excluded.runtime_endpoint,
          runtime_options_json = excluded.runtime_options_json,
          model_metadata_id = excluded.model_metadata_id,
          model_quantization = excluded.model_quantization,
          model_artifact_repo = excluded.model_artifact_repo,
          model_artifact_file = excluded.model_artifact_file,
          model_revision = excluded.model_revision,
          model_sha256 = excluded.model_sha256,
          operating_power = excluded.operating_power,
          operating_thermal = excluded.operating_thermal,
          operating_background_load = excluded.operating_background_load
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
    conn.execute("DELETE FROM result_case_stats WHERE run_id = ?", (run_id,))
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
    conn.executemany(
        """
        INSERT INTO result_case_stats(
          run_id, pack_id, pack_version, case_id, row_count, ok_count,
          prompt_token_rows, prompt_token_median, cached_prompt_token_rows,
          cached_prompt_token_median, prefill_tps_rows, prefill_tps_median
        )
        VALUES (
          :run_id, :pack_id, :pack_version, :case_id, :row_count, :ok_count,
          :prompt_token_rows, :prompt_token_median, :cached_prompt_token_rows,
          :cached_prompt_token_median, :prefill_tps_rows, :prefill_tps_median
        )
        """,
        _case_stat_values(run_id, run.records),
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
    host = run_metadata.get("host") if isinstance(run_metadata, dict) else None
    repo = run_metadata.get("repo") if isinstance(run_metadata, dict) else None
    operating = (
        run_metadata.get("operating_conditions")
        if isinstance(run_metadata, dict)
        else None
    )
    runtime_options = runtime.get("options") if isinstance(runtime, dict) else None
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
        "host_label": _string_or_none(host, "label"),
        "host_repo_commit": _string_or_none(host, "repo_commit")
        or _string_or_none(repo, "commit"),
        "comparison_mode": _string_or_none(run_metadata, "comparison_mode"),
        "comparison_boundary": _string_or_none(run_metadata, "comparison_boundary"),
        "runtime_name": _string_or_none(runtime, "name"),
        "runtime_version": _string_or_none(runtime, "version"),
        "runtime_endpoint": _string_or_none(runtime, "endpoint"),
        "runtime_options_json": (
            _json_dumps(runtime_options) if isinstance(runtime_options, dict) else None
        ),
        "model_metadata_id": _string_or_none(model_metadata, "id"),
        "model_quantization": _string_or_none(model_metadata, "quantization"),
        "model_artifact_repo": _string_or_none(model_metadata, "artifact_repo"),
        "model_artifact_file": _string_or_none(model_metadata, "artifact_file"),
        "model_revision": _string_or_none(model_metadata, "revision"),
        "model_sha256": _string_or_none(model_metadata, "sha256"),
        "operating_power": _string_or_none(operating, "power"),
        "operating_thermal": _string_or_none(operating, "thermal"),
        "operating_background_load": _string_or_none(
            operating,
            "background_load",
        ),
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


def _case_stat_values(
    run_id: int,
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for record in records:
        pack = record["pack"]
        key = (pack["id"], pack["version"], record["case"])
        grouped.setdefault(key, []).append(record)

    rows: list[dict[str, Any]] = []
    for (pack_id, pack_version, case_id), case_records in sorted(grouped.items()):
        prompt_values = _record_metric_values(case_records, ("tokens", "prompt"))
        cached_prompt_values = _record_metric_values(
            case_records,
            ("tokens", "cached_prompt"),
        )
        prefill_values = _record_metric_values(case_records, ("timing", "prefill_tps"))
        rows.append(
            {
                "run_id": run_id,
                "pack_id": pack_id,
                "pack_version": pack_version,
                "case_id": case_id,
                "row_count": len(case_records),
                "ok_count": sum(1 for record in case_records if record["ok"] is True),
                "prompt_token_rows": len(prompt_values),
                "prompt_token_median": _median_or_none(prompt_values),
                "cached_prompt_token_rows": len(cached_prompt_values),
                "cached_prompt_token_median": _median_or_none(cached_prompt_values),
                "prefill_tps_rows": len(prefill_values),
                "prefill_tps_median": _median_or_none(prefill_values),
            }
        )
    return rows


def _record_metric_values(
    records: list[dict[str, Any]],
    path: tuple[str, str],
) -> list[float]:
    values: list[float] = []
    section, key = path
    for record in records:
        nested = record.get(section)
        if not isinstance(nested, dict):
            continue
        value = _optional_number(nested.get(key))
        if value is not None:
            values.append(value)
    return values


def _median_or_none(values: list[float]) -> float | None:
    if not values:
        return None
    return float(median(values))


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


def _json_object_or_none(
    raw_json: str | None,
    field: str,
    run_id: int,
) -> dict[str, Any] | None:
    if raw_json is None:
        return None
    try:
        value = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise RegistryError(
            f"could not parse indexed {field} for run_id {run_id}"
        ) from exc
    if not isinstance(value, dict):
        raise RegistryError(f"indexed {field} for run_id {run_id} is not an object")
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


def _nullable_bool(value: Any) -> bool | None:
    if value is None:
        return None
    return bool(value)


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
