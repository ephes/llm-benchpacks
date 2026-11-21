"""Read-only comparison helpers for existing ``run.jsonl`` artifacts."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, BinaryIO

from .safe_files import open_contained_regular, open_result_directory, require_stable_file


MISSING = "—"
MAX_RESULT_LINE_BYTES = 1024 * 1024
MAX_RESULT_RUN_BYTES = 64 * 1024 * 1024
MAX_RESULT_SIDECAR_BYTES = MAX_RESULT_RUN_BYTES
MAX_RESULT_RECORDS = 100_000
MAX_RESULT_RUN_REFERENCES = 1_000
MAX_CASE_SUMMARIES = 100_000


class CompareError(ValueError):
    """Raised when comparison inputs cannot be loaded or summarized."""


@dataclass(frozen=True)
class ResultRun:
    """A loaded result directory."""

    path: Path
    label: str
    records: list[dict[str, Any]]
    hardware: dict[str, Any] | None = None
    run_metadata: dict[str, Any] | None = None
    artifact_root: Path | None = None
    source_bytes: int = 0
    # SHA-256 of exactly the run.jsonl bytes admitted through the opened
    # descriptor; None for runs rebuilt from the registry index.
    source_sha256: str | None = None
    # Device and inode of the directory used to open the on-disk rows.
    directory_identity: tuple[int, int] | None = None


@dataclass(frozen=True)
class CaseSummary:
    """Median summary for one case within one input run."""

    run_label: str
    case: str
    rows: int
    ok: int
    wall_s: float | None
    ttft_s: float | None
    prefill_tps: float | None
    decode_tps: float | None
    total_tps: float | None
    output_tokens: float | None
    prompt_tokens: float | None
    prompt_rows: int
    cached_prompt_tokens: float | None
    cache_rows: int
    # Records group by (pack id, case id): equal case ids from different packs
    # are distinct cases. ``case_label`` is the rendered identity.
    pack_id: str | None = None
    case_label: str | None = None
    prompt_homogeneous: bool = False
    cache_homogeneous: bool = False

    @property
    def case_key(self) -> tuple[str | None, str]:
        return (self.pack_id, self.case)

    @property
    def display_case(self) -> str:
        return self.case_label if self.case_label is not None else self.case


def load_result_run(
    result_dir: Path | str, *,
    byte_limit: int = MAX_RESULT_RUN_BYTES,
    record_limit: int = MAX_RESULT_RECORDS,
) -> ResultRun:
    """Load ``run.jsonl`` from a result directory."""

    path = Path(result_dir)
    with _open_result_input(path) as (fh, directory_identity):
        return _read_result_run(
            path, fh, byte_limit=byte_limit, record_limit=record_limit,
            directory_identity=directory_identity,
        )


@contextmanager
def _open_result_input(path: Path) -> Iterator[tuple[BinaryIO, tuple[int, int]]]:
    if not path.is_dir():
        raise CompareError(f"result input must be a directory: {path}")

    jsonl_path = path / "run.jsonl"
    try:
        with open_result_directory(path) as directory:
            info = os.fstat(directory)
            fd = open_contained_regular(directory, "run.jsonl")
            if fd is None:
                raise CompareError(f"missing run.jsonl or refused non-regular file: {jsonl_path}")
            try:
                stream = os.fdopen(fd, "rb")
            except BaseException:
                os.close(fd)
                raise
            with stream:
                yield stream, (info.st_dev, info.st_ino)
    except OSError as exc:
        raise CompareError(f"could not read {jsonl_path}") from exc


def _read_result_run(
    path: Path, fh: BinaryIO, *, byte_limit: int, record_limit: int,
    directory_identity: tuple[int, int] | None = None,
    initial: os.stat_result | None = None,
) -> ResultRun:
    """Parse one already opened input with the remaining actual-byte allowance."""
    jsonl_path = path / "run.jsonl"
    byte_limit = min(byte_limit, MAX_RESULT_RUN_BYTES)
    record_limit = min(record_limit, MAX_RESULT_RECORDS)
    records: list[dict[str, Any]] = []
    total = 0
    line_number = 0
    digest = hashlib.sha256()
    if initial is None:
        initial = os.fstat(fh.fileno())
    try:
        while True:
            line = fh.readline(min(
                MAX_RESULT_LINE_BYTES + 1,
                byte_limit - total + 1,
            ))
            if not line:
                break
            line_number += 1
            source = f"{jsonl_path}:{line_number}"
            total += len(line)
            digest.update(line)
            if total > byte_limit:
                raise CompareError(f"run byte limit exceeded in {source}")
            if len(line) > MAX_RESULT_LINE_BYTES:
                raise CompareError(f"record byte limit exceeded in {source}")
            stripped = line.decode("utf-8").strip()
            if not stripped:
                continue
            if len(records) >= record_limit:
                raise CompareError(f"record count limit exceeded in {source}")
            try:
                record = json.loads(stripped, object_pairs_hook=unique_json_object)
            except (ValueError, RecursionError) as exc:
                raise CompareError(f"could not parse {source}: invalid JSON") from exc
            if not isinstance(record, dict):
                raise CompareError(f"expected JSON object in {source}")
            records.append(record)
        require_stable_file(fh.fileno(), initial)
        if total != initial.st_size:
            raise CompareError(
                f"incomplete read of {jsonl_path}: expected {initial.st_size} bytes, read {total}"
            )
    except UnicodeError as exc:
        raise CompareError(f"could not decode {jsonl_path}:{line_number}: invalid UTF-8") from exc
    except OSError as exc:
        raise CompareError(f"could not read {jsonl_path}:{line_number}") from exc

    if not records:
        raise CompareError(f"run.jsonl has no records: {jsonl_path}")

    return ResultRun(
        path=path, label=path.name, records=records, artifact_root=path,
        source_bytes=total, source_sha256=digest.hexdigest(),
        directory_identity=directory_identity,
    )


def load_result_runs(
    result_dirs: list[Path | str], *, run_limit: int = 100,
    byte_limit: int = MAX_RESULT_RUN_BYTES, record_limit: int = MAX_RESULT_RECORDS,
    reference_limit: int = MAX_RESULT_RUN_REFERENCES,
) -> list[ResultRun]:
    """Admit a bounded collection, deduplicating the descriptors actually read."""
    if len(result_dirs) > reference_limit:
        raise CompareError(f"total run reference limit exceeded ({reference_limit})")
    runs: list[ResultRun] = []
    seen: dict[tuple[int, int], tuple[int, int, int]] = {}
    total_bytes = total_records = 0
    for raw_path in result_dirs:
        path = Path(raw_path)
        with _open_result_input(path) as (fh, directory_identity):
            info = os.fstat(fh.fileno())
            identity = (info.st_dev, info.st_ino)
            generation = (info.st_size, info.st_mtime_ns, info.st_ctime_ns)
            if identity in seen:
                if seen[identity] != generation:
                    raise CompareError(f"run.jsonl changed between input references: {path / 'run.jsonl'}")
                continue
            if (len(runs) >= run_limit or total_bytes >= byte_limit
                    or total_records >= record_limit):
                raise CompareError("total run/byte/record limit exceeded")
            run = _read_result_run(
                path, fh, byte_limit=byte_limit - total_bytes,
                record_limit=record_limit - total_records,
                directory_identity=directory_identity, initial=info,
            )
            seen[identity] = generation
            total_bytes += run.source_bytes
            total_records += len(run.records)
            runs.append(run)
    return runs


def unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Reject ambiguous JSON members recursively while retaining extensions."""
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON member")
        result[key] = value
    return result


def record_pack_id(record: dict[str, Any]) -> str | None:
    """Return an admitted pack id, or ``None`` for unlabeled legacy rows."""

    if "pack" not in record:
        return None
    pack = record["pack"]
    if not isinstance(pack, dict):
        raise CompareError("invalid pack identity: pack must be an object")
    if "id" not in pack:
        return None
    pack_id = pack["id"]
    if not isinstance(pack_id, str) or not pack_id.strip():
        raise CompareError("invalid pack identity: pack.id must be a nonblank string")
    return pack_id


def group_case_records(
    run: ResultRun,
) -> dict[tuple[str | None, str], list[dict[str, Any]]]:
    """Group records by (pack id, case id) in first-seen order, in one pass."""

    groups: dict[tuple[str | None, str], list[dict[str, Any]]] = {}
    for record_number, record in enumerate(run.records, start=1):
        case = record.get("case")
        if not isinstance(case, str) or not case.strip():
            raise CompareError(f"{run.path}: record {record_number}: case must be a nonblank string")
        groups.setdefault((record_pack_id(record), case), []).append(record)
    return groups


def case_labels(keys: list[tuple[str | None, str]]) -> dict[tuple[str | None, str], str]:
    """Render case identities; qualify with the pack id when packs are mixed."""

    if len({pack_id for pack_id, _ in keys}) <= 1:
        return {key: key[1] for key in keys}
    return {
        key: f"{key[0] if key[0] is not None else MISSING}/{key[1]}" for key in keys
    }


def validate_run_identity(run: ResultRun) -> None:
    """Refuse mixed runtime identities, invalid pack ids and mixed pack versions."""
    for field in ("adapter", "model"):
        identities = set()
        for record in run.records:
            value = record.get(field)
            if value is not None and not isinstance(value, str):
                raise CompareError(f"mixed or invalid runtime identity: {field}; split result runs")
            identities.add(value)
        if len(identities) > 1:
            raise CompareError(f"mixed runtime identity: {field}; split result runs")
    versions: dict[str | None, set[str | None]] = {}
    for record in run.records:
        pack_id = record_pack_id(record)
        pack = record.get("pack")
        version = pack.get("version") if isinstance(pack, dict) else None
        if version is not None and not isinstance(version, str):
            raise CompareError("mixed or invalid pack version identity; split result runs")
        versions.setdefault(pack_id, set()).add(version)
    if any(len(values) > 1 for values in versions.values()):
        raise CompareError("mixed pack version identity; split result runs")


def summarize_runs(runs: list[ResultRun]) -> list[CaseSummary]:
    """Summarize each run/case pair using medians over numeric samples."""

    for run in runs:
        validate_run_identity(run)
    grouped = [group_case_records(run) for run in runs]
    case_order: list[tuple[str | None, str]] = []
    seen_cases: set[tuple[str | None, str]] = set()
    for groups in grouped:
        for key in groups:
            if key not in seen_cases:
                seen_cases.add(key)
                case_order.append(key)
    summary_count = len(runs) * len(case_order)
    if summary_count > MAX_CASE_SUMMARIES:
        raise CompareError(
            f"comparison summary row limit exceeded ({summary_count} rows, "
            f"limit {MAX_CASE_SUMMARIES}). Split the inputs into smaller groups."
        )
    labels = case_labels(case_order)

    summaries: list[CaseSummary] = []
    for key in case_order:
        pack_id, case = key
        for run, groups in zip(runs, grouped, strict=True):
            rows = groups.get(key, [])
            if not rows:
                summaries.append(
                    CaseSummary(
                        run_label=run.label,
                        case=case,
                        rows=0,
                        ok=0,
                        wall_s=None,
                        ttft_s=None,
                        prefill_tps=None,
                        decode_tps=None,
                        total_tps=None,
                        output_tokens=None,
                        prompt_tokens=None,
                        prompt_rows=0,
                        cached_prompt_tokens=None,
                        cache_rows=0,
                        pack_id=pack_id,
                        case_label=labels[key],
                    )
                )
                continue

            successful = [row for row in rows if row.get("ok") is True]
            prompt_values = _numeric_metric_values(successful, ("tokens", "prompt"))
            cached_prompt_values = _numeric_metric_values(
                successful, ("tokens", "cached_prompt")
            )
            summaries.append(
                CaseSummary(
                    run_label=run.label,
                    case=case,
                    rows=len(rows),
                    ok=len(successful),
                    wall_s=_median_metric(successful, ("timing", "wall_s")),
                    ttft_s=_median_metric(successful, ("timing", "ttft_s")),
                    prefill_tps=_median_metric(successful, ("timing", "prefill_tps")),
                    decode_tps=_median_metric(successful, ("timing", "decode_tps")),
                    total_tps=_median_metric(successful, ("timing", "total_tps")),
                    output_tokens=_median_metric(successful, ("tokens", "output")),
                    prompt_tokens=finite_median(prompt_values),
                    prompt_rows=len(prompt_values),
                    cached_prompt_tokens=finite_median(cached_prompt_values),
                    cache_rows=len(cached_prompt_values),
                    prompt_homogeneous=len(set(prompt_values)) == 1,
                    cache_homogeneous=len(set(cached_prompt_values)) == 1,
                    pack_id=pack_id,
                    case_label=labels[key],
                )
            )
    return summaries


_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f-\x9f\u2028\u2029]+")
_MARKDOWN_SPECIAL_RE = re.compile(r"([\\|`\[\]])")


def markdown_cell(value: object) -> str:
    """Render untrusted text as one inert Markdown table cell.

    Control/line-separator characters collapse to spaces, HTML-significant
    characters become entities, and Markdown table/inline syntax is escaped so a
    label cannot split cells, start code spans, links or raw HTML.
    """

    text = _CONTROL_RE.sub(" ", str(value))
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return _MARKDOWN_SPECIAL_RE.sub(r"\\\1", text)


def markdown_code(value: object) -> str:
    """Render untrusted text as a single-line Markdown code span."""

    text = _CONTROL_RE.sub(" ", str(value))
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    fence = "`" * (longest + 1)
    pad = " " if text.startswith("`") or text.endswith("`") or not text.strip() else ""
    # A pipe would still split a table cell; these spans are used outside tables.
    return f"{fence}{pad}{text}{pad}{fence}"


def markdown_text(value: object) -> str:
    """Render one line of literal Markdown prose, including at paragraph start."""
    text = re.sub(r"([*~])", r"\\\1", markdown_cell(value).strip())
    # Underscores inside words are already literal, including in model labels.
    text = re.sub(
        r"(?<!\w)_+|(?<!_)_+(?!\w)", lambda match: match[0].replace("_", r"\_"), text,
    )
    return re.sub(r"^([0-9]{1,9})?([#=+:\-]|[.)](?= |$))", r"\1\\\2", text)


def disambiguate_runs(runs: list[ResultRun]) -> list[ResultRun]:
    """Return runs with stable labels when input basenames collide."""

    return _disambiguate_labels(runs)


def pack_versions(runs: list[ResultRun]) -> set[tuple[str, str]]:
    """Return distinct pack id/version pairs present in loaded records."""

    return _pack_versions(runs)


def pack_warning_lines(runs: list[ResultRun]) -> list[str]:
    """Return compare warning lines for pack id/version mismatches."""

    version_set = pack_versions(runs)
    if len(version_set) <= 1:
        return []
    rendered = ", ".join(
        f"{markdown_cell(pack_id)} {markdown_cell(version)}"
        for pack_id, version in sorted(version_set)
    )
    return [
        "WARNING: compared records use different pack ids or versions: "
        f"{rendered}"
    ]


def cache_warnings(summaries: list[CaseSummary]) -> list[str]:
    """Return compare warning lines for prompt/cache metadata issues."""

    return _cache_warnings(summaries)


def prefill_parity_statuses(
    summaries: list[CaseSummary],
) -> dict[tuple[str | None, str], str]:
    """Return prefill parity statuses keyed by ``CaseSummary.case_key``."""

    return _prefill_parity_statuses(summaries)


def format_float(value: float | None, digits: int) -> str:
    """Format a nullable floating-point metric for compare-style tables."""

    return _format_float(value, digits)


def format_tokens(value: float | None) -> str:
    """Format a nullable token metric for compare-style tables."""

    return _format_tokens(value)


def render_comparison(runs: list[ResultRun]) -> str:
    """Render a compact Markdown table comparing loaded result runs."""

    runs = disambiguate_runs(runs)
    summaries = summarize_runs(runs)
    pack_version_set = pack_versions(runs)
    lines: list[str] = ["# benchpack compare", "", "Inputs:"]
    for run in runs:
        row_word = "row" if len(run.records) == 1 else "rows"
        lines.append(
            f"- {markdown_code(run.label)}: {markdown_code(run.path)} "
            f"({len(run.records)} {row_word})"
        )
    lines.append("")

    if len(pack_version_set) == 1:
        pack_id, version = next(iter(pack_version_set))
        lines.append(f"Pack: {markdown_code(pack_id)} version {markdown_code(version)}")
    else:
        lines.extend(pack_warning_lines(runs))
    lines.append("")
    lines.append(
        "Note: medians use only successful (`ok: true`) rows and ignore null metric values."
    )
    lines.append("")
    lines.append(
        "`prefill_tps med` is shown "
        "only when the case-level `prefill parity` status is `comparable`; "
        "otherwise it renders as `—`. New rows may include `tokens.prompt` and "
        "`tokens.cached_prompt`, but old rows may lack one or both fields; do "
        "not draw prefill-speed conclusions without prompt/cache parity "
        "evidence. The `prefill parity` column reports deterministic "
        "prompt/cache status for each case."
    )
    lines.append("")

    prefill_statuses = prefill_parity_statuses(summaries)
    warning_lines = metric_warnings(runs) + cache_warnings(summaries)
    for warning in warning_lines:
        lines.append(warning)
    if warning_lines:
        lines.append("")

    lines.append(
        "| run | case | rows | ok | wall_s med | ttft_s med | "
        "prefill_tps med | decode_tps med | total_tps med | "
        "output_tokens med | prompt_tokens med | cached_prompt med | "
        "cache rows | prefill parity | failed |"
    )
    lines.append(
        "|-----|------|------|----|------------|------------|-----------------|"
        "----------------|---------------|-------------------|-------------------|"
        "-------------------|------------|----------------|--------|"
    )
    for summary in summaries:
        prefill_parity = prefill_statuses[summary.case_key]
        # Summary keeps the median; display is gated by case-level parity.
        prefill_tps = (
            _format_float(summary.prefill_tps, digits=2)
            if prefill_parity == "comparable"
            else MISSING
        )
        lines.append(
            "| {run} | {case} | {rows} | {ok} | {wall} | {ttft} | {prefill} | "
            "{decode} | {total} | {output} | {prompt} | {cached} | {cache_rows} | "
            "{prefill_parity} | {failed} |".format(
                run=markdown_cell(summary.run_label),
                case=markdown_cell(summary.display_case),
                rows=summary.rows,
                ok=summary.ok,
                wall=_format_float(summary.wall_s, digits=3),
                ttft=_format_float(summary.ttft_s, digits=3),
                prefill=prefill_tps,
                decode=_format_float(summary.decode_tps, digits=2),
                total=_format_float(summary.total_tps, digits=2),
                output=_format_tokens(summary.output_tokens),
                prompt=_format_tokens(summary.prompt_tokens),
                cached=_format_tokens(summary.cached_prompt_tokens),
                cache_rows=f"{summary.cache_rows}/{summary.ok}",
                prefill_parity=prefill_parity,
                failed=summary.rows - summary.ok,
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
    reserved = set(candidates)
    suffixes: Counter[str] = Counter()
    labeled: list[ResultRun] = []
    for run, candidate in zip(runs, candidates, strict=True):
        label = candidate
        if candidate_counts[candidate] > 1:
            while label in reserved:
                suffixes[candidate] += 1
                label = f"{candidate}#{suffixes[candidate]}"
            reserved.add(label)
        labeled.append(replace(run, label=label))
    return labeled


def _pack_versions(runs: list[ResultRun]) -> set[tuple[str, str]]:
    versions: set[tuple[str, str]] = set()
    for run in runs:
        for record in run.records:
            pack_id = record_pack_id(record)
            pack = record.get("pack")
            version = pack.get("version") if isinstance(pack, dict) else None
            versions.add((str(pack_id), str(version)))
    return versions


def _cache_warnings(summaries: list[CaseSummary]) -> list[str]:
    warnings: list[str] = []
    by_case: dict[tuple[str | None, str], list[CaseSummary]] = {}
    for summary in summaries:
        by_case.setdefault(summary.case_key, []).append(summary)

    for case_summaries in by_case.values():
        case = markdown_code(case_summaries[0].display_case)
        has_all_case_rows = all(summary.ok > 0 for summary in case_summaries)
        prompt_medians = {
            summary.prompt_tokens
            for summary in case_summaries
            if summary.prompt_tokens is not None
        }
        has_complete_prompt_medians = (
            has_all_case_rows
            and all(summary.prompt_rows == summary.ok for summary in case_summaries)
        )
        if has_complete_prompt_medians and len(prompt_medians) > 1:
            warnings.append(
                "WARNING: prompt-token medians differ for case "
                f"{case}; cache parity is not comparable across different prompts."
            )

        if any(
            summary.ok > 0 and summary.cache_rows < summary.ok
            for summary in case_summaries
        ):
            warnings.append(
                "WARNING: cache metadata incomplete for case "
                f"{case}; some rows lack valid `tokens.cached_prompt`."
            )
            continue

        if not has_all_case_rows:
            continue

        medians = {
            summary.cached_prompt_tokens
            for summary in case_summaries
            if summary.cached_prompt_tokens is not None
        }
        if len(medians) > 1:
            warnings.append(
                "WARNING: cached prompt-token medians differ for case "
                f"{case}; do not compare prefill speed."
            )
    for key, status in _prefill_parity_statuses(summaries).items():
        if status in {"prompt-mixed", "cache-mixed"}:
            case = by_case[key][0].display_case
            warnings.append(
                f"WARNING: mixed prompt/cache samples for case {markdown_code(case)}; "
                "do not compare prefill speed."
            )
    return warnings


def _prefill_parity_statuses(
    summaries: list[CaseSummary],
) -> dict[tuple[str | None, str], str]:
    statuses: dict[tuple[str | None, str], str] = {}
    by_case: dict[tuple[str | None, str], list[CaseSummary]] = {}
    for summary in summaries:
        by_case.setdefault(summary.case_key, []).append(summary)

    for case, case_summaries in by_case.items():
        if any(summary.rows == 0 for summary in case_summaries):
            statuses[case] = "missing-case"
            continue

        if any(summary.ok == 0 for summary in case_summaries):
            statuses[case] = "no-success"
            continue

        if any(summary.prompt_rows < summary.ok for summary in case_summaries):
            statuses[case] = "prompt-missing"
            continue

        if any(not summary.prompt_homogeneous for summary in case_summaries):
            statuses[case] = "prompt-mixed"
            continue

        prompt_medians = {summary.prompt_tokens for summary in case_summaries}
        if len(prompt_medians) > 1:
            statuses[case] = "prompt-diff"
            continue

        if any(summary.cache_rows < summary.ok for summary in case_summaries):
            statuses[case] = "cache-missing"
            continue

        if any(not summary.cache_homogeneous for summary in case_summaries):
            statuses[case] = "cache-mixed"
            continue

        cached_medians = {summary.cached_prompt_tokens for summary in case_summaries}
        if len(cached_medians) > 1:
            statuses[case] = "cache-diff"
            continue

        statuses[case] = "comparable"

    return statuses


def _median_metric(rows: list[dict[str, Any]], path: tuple[str, str]) -> float | None:
    return finite_median(_numeric_metric_values(rows, path))


def _numeric_metric_values(
    rows: list[dict[str, Any]], path: tuple[str, str]
) -> list[float]:
    values: list[float] = []
    section_name, field_name = path
    for row in rows:
        section = row.get(section_name)
        if not isinstance(section, dict):
            continue
        numeric_value = _section_metric_value(section, section_name, field_name)
        if numeric_value is not None:
            values.append(numeric_value)
    return values


def _section_metric_value(
    values: dict[str, Any], section: str, field: str,
) -> float | None:
    value = _metric_value(values.get(field), section)
    if value is not None and (section, field) == ("tokens", "cached_prompt"):
        prompt = _metric_value(values.get("prompt"), section)
        if prompt is not None and value > prompt:
            return None
    return value


def _metric_value(value: Any, section: str) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except OverflowError:
        return None
    if not math.isfinite(number) or number < 0:
        return None
    if section == "tokens" and (not number.is_integer() or int(number) != value):
        return None
    return number


def metric_warnings(runs: list[ResultRun]) -> list[str]:
    """One bounded warning for invalid supplied metrics, without raw values."""
    invalid = 0
    for run in runs:
        for row in run.records:
            for section, fields in (
                ("timing", ("wall_s", "ttft_s", "prefill_tps", "decode_tps", "total_tps")),
                ("tokens", ("prompt", "output", "cached_prompt")),
            ):
                values = row.get(section)
                if not isinstance(values, dict):
                    if values is not None:
                        invalid += 1
                    continue
                for field in fields:
                    value = values.get(field)
                    if value is not None and _section_metric_value(values, section, field) is None:
                        invalid += 1
    if not invalid:
        return []
    return [
        f"WARNING: {invalid} invalid metric samples ignored; timing/rates require "
        "finite nonnegative values and tokens require exact nonnegative counts. "
        "Metric sections must be objects when supplied and non-null. "
        "Cached prompt counts cannot exceed prompt counts."
    ]


def finite_median(values: list[float]) -> float | None:
    """Return an overflow-safe median of already admitted finite samples."""
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    result = ordered[middle]
    if len(ordered) % 2 == 0:
        lower = ordered[middle - 1]
        # Same-sign subtraction cannot overflow; opposite signs can be halved
        # independently. Keep identical subnormal samples unchanged, too.
        result = (lower + (result - lower) / 2
                  if (lower >= 0) == (result >= 0)
                  else lower / 2 + result / 2)
    return result if math.isfinite(result) else None


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
