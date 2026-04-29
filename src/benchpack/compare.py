"""Read-only comparison helpers for existing ``run.jsonl`` artifacts."""

from __future__ import annotations

import json
import math
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Any


MISSING = "—"


class CompareError(ValueError):
    """Raised when comparison inputs cannot be loaded or summarized."""


@dataclass(frozen=True)
class ResultRun:
    """A loaded result directory."""

    path: Path
    label: str
    records: list[dict[str, Any]]


@dataclass(frozen=True)
class CaseSummary:
    """Median summary for one case within one input run."""

    run_label: str
    case: str
    rows: int
    ok: int
    wall_s: float | None
    ttft_s: float | None
    decode_tps: float | None
    total_tps: float | None
    output_tokens: float | None
    cached_prompt_tokens: float | None
    cache_rows: int


def load_result_run(result_dir: Path | str) -> ResultRun:
    """Load ``run.jsonl`` from a result directory."""

    path = Path(result_dir)
    if not path.is_dir():
        raise CompareError(f"result input must be a directory: {path}")

    jsonl_path = path / "run.jsonl"
    if not jsonl_path.is_file():
        raise CompareError(f"missing run.jsonl in result directory: {path}")

    records: list[dict[str, Any]] = []
    with jsonl_path.open(encoding="utf-8") as fh:
        for line_number, line in enumerate(fh, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                record = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise CompareError(
                    f"could not parse {jsonl_path}:{line_number}: {exc.msg}"
                ) from exc
            if not isinstance(record, dict):
                raise CompareError(
                    f"expected JSON object in {jsonl_path}:{line_number}"
                )
            records.append(record)

    if not records:
        raise CompareError(f"run.jsonl has no records: {jsonl_path}")

    return ResultRun(path=path, label=path.name, records=records)


def summarize_runs(runs: list[ResultRun]) -> list[CaseSummary]:
    """Summarize each run/case pair using medians over numeric samples."""

    case_order: list[str] = []
    seen_cases: set[str] = set()
    for run in runs:
        for record in run.records:
            case = record.get("case")
            if isinstance(case, str) and case not in seen_cases:
                seen_cases.add(case)
                case_order.append(case)

    summaries: list[CaseSummary] = []
    for case in case_order:
        for run in runs:
            rows = [record for record in run.records if record.get("case") == case]
            if not rows:
                summaries.append(
                    CaseSummary(
                        run_label=run.label,
                        case=case,
                        rows=0,
                        ok=0,
                        wall_s=None,
                        ttft_s=None,
                        decode_tps=None,
                        total_tps=None,
                        output_tokens=None,
                        cached_prompt_tokens=None,
                        cache_rows=0,
                    )
                )
                continue

            cached_prompt_values = _numeric_metric_values(
                rows, ("tokens", "cached_prompt")
            )
            summaries.append(
                CaseSummary(
                    run_label=run.label,
                    case=case,
                    rows=len(rows),
                    ok=sum(1 for row in rows if row.get("ok") is True),
                    wall_s=_median_metric(rows, ("timing", "wall_s")),
                    ttft_s=_median_metric(rows, ("timing", "ttft_s")),
                    decode_tps=_median_metric(rows, ("timing", "decode_tps")),
                    total_tps=_median_metric(rows, ("timing", "total_tps")),
                    output_tokens=_median_metric(rows, ("tokens", "output")),
                    cached_prompt_tokens=_median_values(cached_prompt_values),
                    cache_rows=len(cached_prompt_values),
                )
            )
    return summaries


def render_comparison(runs: list[ResultRun]) -> str:
    """Render a compact Markdown table comparing loaded result runs."""

    runs = _disambiguate_labels(runs)
    pack_versions = _pack_versions(runs)
    lines: list[str] = ["# benchpack compare", "", "Inputs:"]
    for run in runs:
        row_word = "row" if len(run.records) == 1 else "rows"
        lines.append(f"- `{run.label}`: `{run.path}` ({len(run.records)} {row_word})")
    lines.append("")

    if len(pack_versions) == 1:
        pack_id, version = next(iter(pack_versions))
        lines.append(f"Pack: `{pack_id}` version `{version}`")
    else:
        rendered = ", ".join(
            f"{pack_id} {version}" for pack_id, version in sorted(pack_versions)
        )
        lines.append(
            "WARNING: compared records use different pack ids or versions: "
            f"{rendered}"
        )
    lines.append("")
    lines.append(
        "Note: medians ignore null metric values. `prefill_tps` is intentionally "
        "omitted because prefill comparisons require prompt-cache parity. New "
        "rows may include `tokens.cached_prompt`, but old rows may lack it; do "
        "not draw prefill-speed conclusions without cache evidence."
    )
    lines.append("")

    summaries = summarize_runs(runs)
    cache_warnings = _cache_warnings(summaries)
    for warning in cache_warnings:
        lines.append(warning)
    if cache_warnings:
        lines.append("")

    lines.append(
        "| run | case | rows | ok | wall_s med | ttft_s med | "
        "decode_tps med | total_tps med | output_tokens med | "
        "cached_prompt med | cache rows |"
    )
    lines.append(
        "|-----|------|------|----|------------|------------|----------------|"
        "---------------|-------------------|-------------------|------------|"
    )
    for summary in summaries:
        lines.append(
            "| {run} | {case} | {rows} | {ok} | {wall} | {ttft} | {decode} | "
            "{total} | {output} | {cached} | {cache_rows} |".format(
                run=summary.run_label,
                case=summary.case,
                rows=summary.rows,
                ok=summary.ok,
                wall=_format_float(summary.wall_s, digits=3),
                ttft=_format_float(summary.ttft_s, digits=3),
                decode=_format_float(summary.decode_tps, digits=2),
                total=_format_float(summary.total_tps, digits=2),
                output=_format_tokens(summary.output_tokens),
                cached=_format_tokens(summary.cached_prompt_tokens),
                cache_rows=f"{summary.cache_rows}/{summary.rows}",
            )
        )
    lines.append("")
    return "\n".join(lines)


def _disambiguate_labels(runs: list[ResultRun]) -> list[ResultRun]:
    basename_counts = Counter(run.path.name for run in runs)
    candidates: list[str] = []
    for run in runs:
        if basename_counts[run.path.name] == 1:
            candidates.append(run.path.name)
            continue
        parent = run.path.parent.name
        candidates.append(f"{parent}/{run.path.name}" if parent else run.path.name)

    candidate_counts = Counter(candidates)
    seen: Counter[str] = Counter()
    labeled: list[ResultRun] = []
    for run, candidate in zip(runs, candidates, strict=True):
        seen[candidate] += 1
        label = (
            f"{candidate}#{seen[candidate]}"
            if candidate_counts[candidate] > 1
            else candidate
        )
        labeled.append(ResultRun(path=run.path, label=label, records=run.records))
    return labeled


def _pack_versions(runs: list[ResultRun]) -> set[tuple[str, str]]:
    versions: set[tuple[str, str]] = set()
    for run in runs:
        for record in run.records:
            pack = record.get("pack")
            if isinstance(pack, dict):
                pack_id = pack.get("id")
                version = pack.get("version")
            else:
                pack_id = None
                version = None
            versions.add((str(pack_id), str(version)))
    return versions


def _cache_warnings(summaries: list[CaseSummary]) -> list[str]:
    warnings: list[str] = []
    by_case: dict[str, list[CaseSummary]] = {}
    for summary in summaries:
        by_case.setdefault(summary.case, []).append(summary)

    for case, case_summaries in by_case.items():
        if any(
            summary.rows > 0 and summary.cache_rows < summary.rows
            for summary in case_summaries
        ):
            warnings.append(
                "WARNING: cache metadata incomplete for case "
                f"`{case}`; some rows lack numeric `tokens.cached_prompt`."
            )
            continue

        if not all(summary.rows > 0 for summary in case_summaries):
            continue

        medians = {
            summary.cached_prompt_tokens
            for summary in case_summaries
            if summary.cached_prompt_tokens is not None
        }
        if len(medians) > 1:
            warnings.append(
                "WARNING: cached prompt-token medians differ for case "
                f"`{case}`; do not compare prefill speed."
            )
    return warnings


def _median_metric(rows: list[dict[str, Any]], path: tuple[str, str]) -> float | None:
    return _median_values(_numeric_metric_values(rows, path))


def _numeric_metric_values(
    rows: list[dict[str, Any]], path: tuple[str, str]
) -> list[float]:
    values: list[float] = []
    section_name, field_name = path
    for row in rows:
        section = row.get(section_name)
        if not isinstance(section, dict):
            continue
        value = section.get(field_name)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            continue
        values.append(float(value))
    return values


def _median_values(values: list[float]) -> float | None:
    if not values:
        return None
    return float(median(values))


def _format_float(value: float | None, digits: int) -> str:
    if value is None:
        return MISSING
    return f"{value:.{digits}f}"


def _format_tokens(value: float | None) -> str:
    if value is None:
        return MISSING
    if value.is_integer():
        return str(int(value))
    return f"{value:.1f}"
