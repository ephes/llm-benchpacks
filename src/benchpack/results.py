"""Reporter: assemble adapter + collector + reporter contributions.

Per ``docs/architecture.md`` "Result Record Envelope" the reporter is
responsible for ``pack``/``case``/``timing.total_tps``/``scoring`` and writes
the combined record to ``run.jsonl``.  Verifiers run *before* the JSONL line
is appended so that the ``scoring`` field is present in the same record.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .adapters import AdapterResult
from .external_agent_model_calls import ModelCallLogError, summarize_model_call_logs
from .packs import Case, Pack
from .repo_task_outcomes import (
    count_repo_task_outcomes,
    format_patch_bytes,
    format_repetition,
    format_verify_exit_code,
    summarize_repo_task_outcomes,
)
from .run_metadata import write_run_metadata
from .scoring import evaluate


def _relativize(path: str, base: Path) -> str:
    candidate = Path(path)
    try:
        return str(candidate.resolve().relative_to(base.resolve()))
    except (OSError, ValueError):
        return str(candidate)


def _total_tps(tokens_out: int | None, wall_s: float | None) -> float | None:
    if not tokens_out or not wall_s:
        return None
    return round(tokens_out / wall_s, 4)


class RunReporter:
    """Coordinates raw paths, scoring, ``run.jsonl``, ``hardware.json`` and ``summary.md``."""

    def __init__(self, output_dir: Path, pack: Pack) -> None:
        self.output_dir = Path(output_dir)
        self.pack = pack
        self.raw_dir = self.output_dir / "raw"
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.records: list[dict[str, Any]] = []
        self._jsonl_path = self.output_dir / "run.jsonl"

    def case_paths(self, case: Case) -> tuple[Path, Path]:
        return (
            self.raw_dir / f"{case.id}.request.json",
            self.raw_dir / f"{case.id}.response.json",
        )

    def measured_paths(
        self,
        case: Case,
        repetition: int,
        total_repetitions: int,
    ) -> tuple[Path, Path]:
        if isinstance(repetition, bool) or not isinstance(repetition, int):
            raise ValueError("repetition must be an integer >= 1")
        if repetition < 1:
            raise ValueError("repetition must be an integer >= 1")
        if isinstance(total_repetitions, bool) or not isinstance(total_repetitions, int):
            raise ValueError("total_repetitions must be an integer >= 1")
        if total_repetitions < 1:
            raise ValueError("total_repetitions must be an integer >= 1")
        if repetition > total_repetitions:
            raise ValueError("repetition must be <= total_repetitions")
        if total_repetitions == 1:
            return self.case_paths(case)
        prefix = f"{case.id}.rep-{repetition:03d}"
        return (
            self.raw_dir / f"{prefix}.request.json",
            self.raw_dir / f"{prefix}.response.json",
        )

    def warmup_paths(self, case: Case, warmup_index: int) -> tuple[Path, Path]:
        if isinstance(warmup_index, bool) or not isinstance(warmup_index, int):
            raise ValueError("warmup_index must be an integer >= 1")
        if warmup_index < 1:
            raise ValueError("warmup_index must be an integer >= 1")
        prefix = f"{case.id}.warmup-{warmup_index:03d}"
        return (
            self.raw_dir / f"{prefix}.request.json",
            self.raw_dir / f"{prefix}.response.json",
        )

    def record(
        self,
        case: Case,
        adapter_result: AdapterResult,
        sample: dict[str, Any],
        repetition: int | None = None,
        *,
        workspace: dict[str, Any] | None = None,
        patch: dict[str, Any] | None = None,
        task: dict[str, Any] | None = None,
        verify: dict[str, Any] | None = None,
        repo_task: dict[str, Any] | None = None,
        scoring_override: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        scoring_cfg = case.scoring or self.pack.scoring
        scoring_result = (
            dict(scoring_override)
            if scoring_override is not None
            else evaluate(scoring_cfg, adapter_result.output_text)
        )

        timing = adapter_result.timing.to_dict()
        timing["total_tps"] = _total_tps(
            adapter_result.tokens.output, adapter_result.timing.wall_s
        )

        record: dict[str, Any] = {
            "pack": {"id": self.pack.id, "version": self.pack.version},
            "case": case.id,
            "adapter": adapter_result.adapter,
            "endpoint": adapter_result.endpoint,
            "model": adapter_result.model,
            "ok": adapter_result.ok,
            "timing": timing,
            "tokens": adapter_result.tokens.to_dict(),
            "resources": {
                "memory_mb": sample.get("memory_mb"),
                "gpu_memory_mb": sample.get("gpu_memory_mb"),
            },
            "scoring": scoring_result,
            "raw": {
                "request_path": _relativize(
                    adapter_result.raw.request_path, self.output_dir
                ),
                "response_path": _relativize(
                    adapter_result.raw.response_path, self.output_dir
                ),
            },
        }
        if repetition is not None:
            if isinstance(repetition, bool) or not isinstance(repetition, int):
                raise ValueError("repetition must be an integer >= 1")
            if repetition < 1:
                raise ValueError("repetition must be an integer >= 1")
            record["repetition"] = repetition
        if workspace is not None:
            record["workspace"] = dict(workspace)
        if patch is not None:
            record["patch"] = dict(patch)
        if task is not None:
            record["task"] = dict(task)
        if verify is not None:
            record["verify"] = dict(verify)
        if repo_task is not None:
            record["repo_task"] = dict(repo_task)
        if adapter_result.backend is not None:
            record["backend"] = adapter_result.backend
        if adapter_result.error is not None:
            record["error"] = adapter_result.error

        self.records.append(record)
        with self._jsonl_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
        return record

    def write_hardware(self, hardware: dict[str, Any]) -> None:
        (self.output_dir / "hardware.json").write_text(
            json.dumps(hardware, indent=2) + "\n"
        )

    def write_run_metadata(self, metadata: dict[str, Any]) -> None:
        write_run_metadata(self.output_dir, metadata)

    def write_summary(
        self,
        hardware: dict[str, Any],
        run_metadata: dict[str, Any] | None = None,
    ) -> None:
        lines: list[str] = []
        lines.append(f"# {self.pack.id} ({self.pack.version})")
        lines.append("")
        if self.pack.description:
            lines.append(self.pack.description)
            lines.append("")
        lines.append(
            f"Host: `{hardware.get('hostname', 'unknown')}` "
            f"({hardware.get('platform', 'unknown')})"
        )
        if hardware.get("cpu_model"):
            lines.append(f"CPU: {hardware['cpu_model']}")
        if hardware.get("ram_mb"):
            lines.append(f"RAM: {hardware['ram_mb']} MB")
        gpus = hardware.get("gpus") or []
        if gpus:
            parts = []
            for g in gpus:
                model = g.get("model", "?")
                vram = g.get("vram_mb")
                parts.append(f"{model} ({vram} MB)" if vram else model)
            lines.append("GPU: " + ", ".join(parts))
        if run_metadata is not None:
            lines.append("")
            lines.append("## Runtime Metadata")
            lines.append("")
            for label, section in (
                ("Runtime", "runtime"),
                ("Model", "model"),
                ("Operating conditions", "operating_conditions"),
            ):
                value = run_metadata.get(section)
                if isinstance(value, dict):
                    lines.append(f"{label}: {_compact_summary_mapping(value)}")
            notes = run_metadata.get("notes")
            if isinstance(notes, str) and notes:
                lines.append(f"Notes: {notes}")
        try:
            model_call_summaries = summarize_model_call_logs(self.output_dir)
        except ModelCallLogError as exc:
            lines.append("")
            lines.append("## External-Agent Model Calls")
            lines.append("")
            lines.append(f"Could not summarize model-call logs: {exc}")
        else:
            if model_call_summaries:
                lines.append("")
                lines.append("## External-Agent Model Calls")
                lines.append("")
                lines.append(
                    "| case | repetition | calls | valid | invalid | ok | failed | "
                    "errors | models | adapters | endpoints | duration_s | "
                    "prompt_tokens | output_tokens | cached_prompt_tokens | "
                    "response_formats | token_budget_fields | finish_reasons |"
                )
                lines.append(
                    "|------|------------|-------|-------|---------|----|--------|"
                    "--------|--------|----------|-----------|------------|"
                    "---------------|---------------|----------------------|"
                    "------------------|---------------------|----------------|"
                )
                for summary in model_call_summaries:
                    lines.append(_model_call_summary_row(summary))
        repo_task_outcomes = summarize_repo_task_outcomes(
            self.records,
            self.output_dir,
        )
        if repo_task_outcomes:
            lines.append("")
            lines.append("## Repo-Task Outcome Summary")
            lines.append("")
            lines.append(
                "| rows | passed | failed-no-mutation | failed-source-mutation | "
                "failed-non-source-mutation | failed-unknown-mutation | other |"
            )
            lines.append(
                "|------|--------|--------------------|------------------------|"
                "----------------------------|-------------------------|-------|"
            )
            counts = count_repo_task_outcomes(repo_task_outcomes)
            lines.append(
                "| {total} | {passed} | {failed_no_mutation} | "
                "{failed_source_mutation} | {failed_non_source_mutation} | "
                "{failed_unknown_mutation} | "
                "{other} |".format(
                    total=counts.total,
                    passed=counts.passed,
                    failed_no_mutation=counts.failed_no_mutation,
                    failed_source_mutation=counts.failed_source_mutation,
                    failed_non_source_mutation=counts.failed_non_source_mutation,
                    failed_unknown_mutation=counts.failed_unknown_mutation,
                    other=counts.other,
                )
            )
            lines.append("")
            lines.append("## Repo-Task Outcomes")
            lines.append("")
            lines.append(
                "| case | repetition | repo_task | verify_exit | scoring | "
                "patch_bytes | outcome |"
            )
            lines.append(
                "|------|------------|-----------|-------------|---------|"
                "-------------|---------|"
            )
            for outcome in repo_task_outcomes:
                lines.append(_repo_task_outcome_row(outcome))
        lines.append("")
        lines.append("| case | adapter | model | ok | wall_s | total_tps | scoring |")
        lines.append("|------|---------|-------|----|--------|-----------|---------|")
        for record in self.records:
            case_label = record["case"]
            if "repetition" in record:
                case_label = f"{case_label}#{record['repetition']}"
            scoring = record.get("scoring")
            scoring_cell = (
                "—"
                if scoring is None
                else f"{scoring['mode']}: {'pass' if scoring['passed'] else 'fail'}"
            )
            lines.append(
                "| {case} | {adapter} | {model} | {ok} | {wall:.3f} | {tps} | {sc} |".format(
                    case=case_label,
                    adapter=record["adapter"],
                    model=record["model"],
                    ok="yes" if record["ok"] else "no",
                    wall=record["timing"]["wall_s"],
                    tps=(
                        f"{record['timing']['total_tps']:.2f}"
                        if record["timing"]["total_tps"] is not None
                        else "—"
                    ),
                    sc=scoring_cell,
                )
            )
        lines.append("")
        (self.output_dir / "summary.md").write_text("\n".join(lines))


def _compact_summary_mapping(values: dict[str, Any]) -> str:
    if not values:
        return "—"
    return "; ".join(
        f"{key}={_compact_summary_value(value)}"
        for key, value in sorted(values.items())
        if value not in (None, "", [])
    ) or "—"


def _compact_summary_value(value: Any) -> str:
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True)
    if isinstance(value, list):
        return json.dumps(value)
    return str(value)


def _model_call_summary_row(summary: Any) -> str:
    return (
        "| {case} | {repetition} | {calls} | {valid} | {invalid} | {ok} | "
        "{failed} | {errors} | {models} | {adapters} | {endpoints} | "
        "{duration} | {prompt} | {output} | {cached} | {response_formats} | "
        "{token_budget_fields} | {finish_reasons} |"
    ).format(
        case=_summary_table_cell(summary.case),
        repetition=summary.repetition,
        calls=summary.calls,
        valid=summary.valid,
        invalid=summary.invalid,
        ok=summary.ok,
        failed=summary.failed,
        errors=summary.error_count,
        models=_summary_table_cell(_compact_summary_list(summary.models)),
        adapters=_summary_table_cell(_compact_summary_list(summary.adapters)),
        endpoints=_summary_table_cell(_compact_summary_list(summary.endpoints)),
        duration=(
            f"{summary.duration_s:.6f}" if summary.duration_s is not None else "—"
        ),
        prompt=summary.prompt_tokens if summary.prompt_tokens is not None else "—",
        output=summary.output_tokens if summary.output_tokens is not None else "—",
        cached=(
            summary.cached_prompt_tokens
            if summary.cached_prompt_tokens is not None
            else "—"
        ),
        response_formats=_summary_table_cell(
            _compact_summary_list(summary.response_formats)
        ),
        token_budget_fields=_summary_table_cell(
            _compact_summary_list(summary.token_budget_fields)
        ),
        finish_reasons=_summary_table_cell(
            _compact_summary_list(summary.finish_reasons)
        ),
    )


def _repo_task_outcome_row(outcome: Any) -> str:
    return (
        "| {case} | {repetition} | {repo_status} | {verify_exit} | {scoring} | "
        "{patch_bytes} | {result} |"
    ).format(
        case=_summary_table_cell(outcome.case),
        repetition=format_repetition(outcome.repetition),
        repo_status=_summary_table_cell(outcome.repo_status),
        verify_exit=format_verify_exit_code(outcome.verify_exit_code),
        scoring=_summary_table_cell(outcome.scoring),
        patch_bytes=format_patch_bytes(outcome.patch_bytes),
        result=_summary_table_cell(outcome.outcome),
    )


def _compact_summary_list(values: tuple[str, ...]) -> str:
    return ", ".join(values) if values else "—"


def _summary_table_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
