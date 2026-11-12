"""Regressions for linear case grouping, pack-scoped case identity and escaping."""

import re
from pathlib import Path

from benchpack.compare import (
    ResultRun,
    load_result_run,
    markdown_cell,
    prefill_parity_statuses,
    render_comparison,
    summarize_runs,
)
from benchpack.report import render_report
from tests.test_compare import _record, _write_run

_UNESCAPED_PIPE = re.compile(r"(?<!\\)\|")


class _CountingRecord(dict):
    case_reads = 0

    def get(self, key, default=None):
        if key == "case":
            type(self).case_reads += 1
        return super().get(key, default)


def test_summary_grouping_reads_each_record_case_once_per_run() -> None:
    records = [_CountingRecord(_record(f"case-{i}")) for i in range(300)]
    runs = [
        ResultRun(path=Path(f"run-{n}"), label=f"run-{n}", records=list(records))
        for n in range(2)
    ]
    _CountingRecord.case_reads = 0
    summaries = summarize_runs(runs)
    assert len(summaries) == 600
    assert all(summary.rows == 1 for summary in summaries)
    # The previous per-case rescans read every record once per case.
    assert _CountingRecord.case_reads <= 2 * len(records)


def test_equal_case_ids_from_different_packs_are_distinct(tmp_path: Path) -> None:
    run_a, run_b = tmp_path / "run-a", tmp_path / "run-b"
    _write_run(run_a, rows=[_record("short", pack_id="pack-a", wall_s=1.0)])
    _write_run(run_b, rows=[_record("short", pack_id="pack-b", wall_s=9.0)])
    runs = [load_result_run(run_a), load_result_run(run_b)]

    summaries = summarize_runs(runs)
    assert [(s.run_label, s.pack_id, s.rows) for s in summaries] == [
        ("run-a", "pack-a", 1), ("run-b", "pack-a", 0),
        ("run-a", "pack-b", 0), ("run-b", "pack-b", 1),
    ]
    assert prefill_parity_statuses(summaries) == {
        ("pack-a", "short"): "missing-case",
        ("pack-b", "short"): "missing-case",
    }
    output = render_comparison(runs)
    assert "| run-a | pack-a/short | 1 |" in output
    assert "| run-b | pack-b/short | 1 |" in output
    assert "| run-b | pack-a/short | 0 |" in output


def test_single_pack_keeps_plain_case_labels(tmp_path: Path) -> None:
    run_a = tmp_path / "run-a"
    _write_run(run_a)
    output = render_comparison([load_result_run(run_a)])
    assert "| run-a | short | 2 |" in output


def _hostile_run(tmp_path: Path) -> Path:
    run = tmp_path / "evil|`run`<b>"
    case = "c|<img src=x onerror=alert(1)>\n[x](javascript:alert(1))`"
    _write_run(run, rows=[_record(case), _record(case)])
    return run


def _table_lines(output: str) -> list[str]:
    return [line for line in output.splitlines() if line.startswith("|")]


def test_compare_and_report_escape_untrusted_labels(tmp_path: Path) -> None:
    run = load_result_run(_hostile_run(tmp_path))
    for output in (render_comparison([run]), render_report([run])):
        # Code spans are inert; everything outside them must carry no markup.
        prose = re.sub(r"(?<!\\)(`+)(?!`).*?(?<!`)\1(?!`)", "", output)
        assert "<img" not in prose and "<b>" not in prose
        assert not re.search(r"(?<!\\)\]\(javascript", prose)
        tables: dict[str, int] = {}
        for line in _table_lines(output):
            if set(line) <= {"|", "-"}:
                continue
            cells = len(_UNESCAPED_PIPE.findall(line))
            assert cells >= 2
            tables.setdefault(line.split("|")[1].strip(), cells)
        for line in output.splitlines():
            if line.startswith("- "):
                # Input bullets keep the label inside balanced code spans.
                assert line.startswith("- ``evil|`run`<b>``: ``")
    table = render_comparison([run])
    header = next(line for line in _table_lines(table) if line.startswith("| run |"))
    rows = [line for line in _table_lines(table) if "evil" in line]
    assert rows and all(
        len(_UNESCAPED_PIPE.findall(row)) == len(_UNESCAPED_PIPE.findall(header))
        for row in rows
    )


def test_markdown_cell_neutralizes_structure() -> None:
    value = "a|b\r\n <i>&`[l](u)\\"
    rendered = markdown_cell(value)
    assert "\n" not in rendered and "\r" not in rendered and " " not in rendered
    assert not _UNESCAPED_PIPE.search(rendered)
    assert rendered == "a\\|b &lt;i&gt;&amp;\\`\\[l\\](u)\\\\"
    assert markdown_cell("plain-label_1.0") == "plain-label_1.0"


def test_hostile_case_survives_report_case_outcomes(tmp_path: Path) -> None:
    run = load_result_run(_hostile_run(tmp_path))
    output = render_report([run])
    section = output.split("## Case Outcomes", 1)[1].split("##", 1)[0]
    header = next(line for line in _table_lines(section) if line.startswith("| run |"))
    rows = [line for line in _table_lines(section) if "evil" in line]
    assert len(rows) == 1
    assert len(_UNESCAPED_PIPE.findall(rows[0])) == len(_UNESCAPED_PIPE.findall(header))
