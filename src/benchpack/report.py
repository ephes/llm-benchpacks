"""Read-only Markdown reports over existing result directories."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .compare import (
    MISSING,
    ResultRun,
    cache_warnings,
    disambiguate_runs,
    format_float,
    format_tokens,
    load_result_run,
    pack_warning_lines,
    pack_versions,
    prefill_parity_statuses,
    summarize_runs,
)
from .run_metadata import RunMetadataError, load_optional_run_metadata


class ReportError(ValueError):
    """Raised when report inputs cannot be loaded."""


def load_report_runs(result_dirs: list[Path | str]) -> list[ResultRun]:
    """Load report inputs from result directories."""

    if not result_dirs:
        raise ReportError("benchpack report requires at least one result directory")
    try:
        return [load_result_run(path) for path in result_dirs]
    except ValueError as exc:
        raise ReportError(str(exc)) from exc


def render_report(runs: list[ResultRun]) -> str:
    """Render a pasteable Markdown report for loaded result runs."""

    runs = disambiguate_runs(runs)
    summaries = summarize_runs(runs)
    statuses = prefill_parity_statuses(summaries)
    warning_lines = pack_warning_lines(runs) + cache_warnings(summaries)

    lines: list[str] = ["# benchpack report", ""]
    lines.extend(_render_inputs(runs))
    lines.append("")
    lines.extend(_render_run_metadata(runs))
    lines.append("")
    lines.extend(_render_runtime_metadata(runs))
    lines.append("")
    lines.extend(_render_case_outcomes(runs))
    lines.append("")
    lines.extend(_render_compare_medians(summaries, statuses, warning_lines))
    lines.append("")
    return "\n".join(lines)


def _render_inputs(runs: list[ResultRun]) -> list[str]:
    lines = ["Inputs:"]
    for run in runs:
        row_word = "row" if len(run.records) == 1 else "rows"
        lines.append(f"- `{run.label}`: `{run.path}` ({len(run.records)} {row_word})")
    return lines


def _render_run_metadata(runs: list[ResultRun]) -> list[str]:
    lines = [
        "## Run Metadata",
        "",
        "| run | pack | adapter | model | endpoint | hardware |",
        "|-----|------|---------|-------|----------|----------|",
    ]
    for run in runs:
        lines.append(
            "| {run} | {pack} | {adapter} | {model} | {endpoint} | {hardware} |".format(
                run=run.label,
                pack=_markdown_cell(_pack_cell(run)),
                adapter=_markdown_cell(_unique_record_values(run.records, ("adapter",))),
                model=_markdown_cell(_unique_record_values(run.records, ("model",))),
                endpoint=_markdown_cell(
                    _unique_record_values(run.records, ("endpoint",))
                ),
                hardware=_markdown_cell(_hardware_cell(run.path)),
            )
        )
    return lines


def _render_runtime_metadata(runs: list[ResultRun]) -> list[str]:
    lines = [
        "## User-Supplied Runtime Metadata",
        "",
        "| run | runtime | model metadata | operating conditions | notes |",
        "|-----|---------|----------------|----------------------|-------|",
    ]
    for run in runs:
        metadata = _runtime_metadata(run.path)
        if metadata is None:
            lines.append(
                "| {run} | run-metadata.json missing | {missing} | {missing} | "
                "{missing} |".format(run=run.label, missing=MISSING)
            )
            continue
        lines.append(
            "| {run} | {runtime} | {model} | {conditions} | {notes} |".format(
                run=run.label,
                runtime=_markdown_cell(_metadata_section_cell(metadata, "runtime")),
                model=_markdown_cell(_metadata_section_cell(metadata, "model")),
                conditions=_markdown_cell(
                    _metadata_section_cell(metadata, "operating_conditions")
                ),
                notes=_markdown_cell(_metadata_notes_cell(metadata)),
            )
        )
    return lines


def _render_case_outcomes(runs: list[ResultRun]) -> list[str]:
    lines = [
        "## Case Outcomes",
        "",
        "| run | case | rows | ok | scoring pass | scoring fail | unscored |",
        "|-----|------|------|----|--------------|--------------|----------|",
    ]
    for run in runs:
        for case in _case_order(run.records):
            rows = [record for record in run.records if record.get("case") == case]
            scoring = _scoring_counts(rows)
            lines.append(
                "| {run} | {case} | {rows} | {ok} | {passed} | {failed} | "
                "{unscored} |".format(
                    run=run.label,
                    case=case,
                    rows=len(rows),
                    ok=sum(1 for row in rows if row.get("ok") is True),
                    passed=scoring["passed"],
                    failed=scoring["failed"],
                    unscored=scoring["unscored"],
                )
            )
    return lines


def _render_compare_medians(
    summaries,
    statuses: dict[str, str],
    warning_lines: list[str],
) -> list[str]:
    lines = [
        "## Compare Medians",
        "",
        "Medians use the same metric filtering, cache coverage, warning, and "
        "prefill-parity rules as `benchpack compare`.",
        "",
    ]
    for warning in warning_lines:
        lines.append(warning)
    if warning_lines:
        lines.append("")
    lines.extend(
        [
            "| run | case | rows | ok | wall_s med | ttft_s med | "
            "prefill_tps med | decode_tps med | total_tps med | "
            "output_tokens med | prompt_tokens med | cached_prompt med | "
            "cache rows | prefill parity |",
            "|-----|------|------|----|------------|------------|-----------------|"
            "----------------|---------------|-------------------|-------------------|"
            "-------------------|------------|----------------|",
        ]
    )
    for summary in summaries:
        prefill_parity = statuses[summary.case]
        prefill_tps = (
            format_float(summary.prefill_tps, digits=2)
            if prefill_parity == "comparable"
            else MISSING
        )
        lines.append(
            "| {run} | {case} | {rows} | {ok} | {wall} | {ttft} | {prefill} | "
            "{decode} | {total} | {output} | {prompt} | {cached} | "
            "{cache_rows} | {prefill_parity} |".format(
                run=summary.run_label,
                case=summary.case,
                rows=summary.rows,
                ok=summary.ok,
                wall=format_float(summary.wall_s, digits=3),
                ttft=format_float(summary.ttft_s, digits=3),
                prefill=prefill_tps,
                decode=format_float(summary.decode_tps, digits=2),
                total=format_float(summary.total_tps, digits=2),
                output=format_tokens(summary.output_tokens),
                prompt=format_tokens(summary.prompt_tokens),
                cached=format_tokens(summary.cached_prompt_tokens),
                cache_rows=f"{summary.cache_rows}/{summary.rows}",
                prefill_parity=prefill_parity,
            )
        )
    return lines


def _runtime_metadata(result_dir: Path) -> dict[str, Any] | None:
    try:
        return load_optional_run_metadata(result_dir)
    except RunMetadataError as exc:
        raise ReportError(str(exc)) from exc


def _metadata_section_cell(metadata: dict[str, Any], section: str) -> str:
    value = metadata.get(section)
    if not isinstance(value, dict):
        return MISSING
    return _compact_mapping(value)


def _metadata_notes_cell(metadata: dict[str, Any]) -> str:
    notes = metadata.get("notes")
    if not isinstance(notes, str) or not notes:
        return MISSING
    return notes


def _pack_cell(run: ResultRun) -> str:
    versions = pack_versions([run])
    if len(versions) == 1:
        pack_id, version = next(iter(versions))
        return f"{pack_id} {version}"
    return "mixed: " + ", ".join(
        f"{pack_id} {version}" for pack_id, version in sorted(versions)
    )


def _hardware_cell(result_dir: Path) -> str:
    path = result_dir / "hardware.json"
    if not path.is_file():
        return "hardware.json missing"
    try:
        hardware = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ReportError(f"could not parse {path}: {exc.msg}") from exc
    if not isinstance(hardware, dict):
        raise ReportError(f"expected JSON object in {path}")

    parts: list[str] = []
    for key in (
        "hostname",
        "chip",
        "hardware_model",
        "hardware_model_name",
        "hardware_model_identifier",
        "ram_mb",
        "os",
    ):
        value = hardware.get(key)
        if value not in (None, "", []):
            parts.append(f"{key}={_compact_value(value)}")
    gpus = hardware.get("gpus")
    if isinstance(gpus, list) and gpus:
        parts.append("gpus=" + _compact_value(gpus))
    return "; ".join(parts) if parts else "hardware.json present"


def _unique_record_values(records: list[dict[str, Any]], path: tuple[str, ...]) -> str:
    values: list[str] = []
    seen: set[str] = set()
    for record in records:
        value: Any = record
        for key in path:
            if not isinstance(value, dict) or key not in value:
                value = None
                break
            value = value[key]
        rendered = _compact_value(value) if value not in (None, "", []) else MISSING
        if rendered not in seen:
            seen.add(rendered)
            values.append(rendered)
    if not values:
        return MISSING
    if len(values) == 1:
        return values[0]
    return "mixed: " + ", ".join(values)


def _compact_value(value: Any) -> str:
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict):
                model = item.get("model")
                parts.append(str(model) if model is not None else json.dumps(item))
            else:
                parts.append(str(item))
        return ", ".join(parts)
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True)
    return str(value)


def _compact_mapping(values: dict[str, Any]) -> str:
    if not values:
        return MISSING
    parts = [
        f"{key}={_compact_value(value)}"
        for key, value in sorted(values.items())
        if value not in (None, "", [])
    ]
    return "; ".join(parts) if parts else MISSING


def _case_order(records: list[dict[str, Any]]) -> list[str]:
    cases: list[str] = []
    seen: set[str] = set()
    for record in records:
        case = record.get("case")
        if isinstance(case, str) and case not in seen:
            seen.add(case)
            cases.append(case)
    return cases


def _scoring_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"passed": 0, "failed": 0, "unscored": 0}
    for row in rows:
        scoring = row.get("scoring")
        if not isinstance(scoring, dict) or not isinstance(scoring.get("passed"), bool):
            counts["unscored"] += 1
        elif scoring["passed"]:
            counts["passed"] += 1
        else:
            counts["failed"] += 1
    return counts


def _markdown_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
