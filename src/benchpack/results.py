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
from .packs import Case, Pack
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
        if repetition < 1:
            raise ValueError("repetition must be >= 1")
        if total_repetitions < 1:
            raise ValueError("total_repetitions must be >= 1")
        if repetition > total_repetitions:
            raise ValueError("repetition must be <= total_repetitions")
        if total_repetitions == 1:
            return self.case_paths(case)
        prefix = f"{case.id}.rep-{repetition:03d}"
        return (
            self.raw_dir / f"{prefix}.request.json",
            self.raw_dir / f"{prefix}.response.json",
        )

    def warmup_paths(self, case: Case, warmup: int) -> tuple[Path, Path]:
        if warmup < 1:
            raise ValueError("warmup must be >= 1")
        prefix = f"{case.id}.warmup-{warmup:03d}"
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
    ) -> dict[str, Any]:
        scoring_cfg = case.scoring or self.pack.scoring
        scoring_result = evaluate(scoring_cfg, adapter_result.output_text)

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
            record["repetition"] = repetition
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

    def write_summary(self, hardware: dict[str, Any]) -> None:
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
