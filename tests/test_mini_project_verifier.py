from __future__ import annotations

import io
import json
import runpy
import sys
from pathlib import Path

import pytest


@pytest.fixture
def verifier(monkeypatch):
    script = (
        Path(__file__).resolve().parents[1]
        / "benchpacks/mini-project-completion/verify/check.py"
    )
    monkeypatch.setattr(sys, "dont_write_bytecode", True)
    return runpy.run_path(str(script))


@pytest.mark.parametrize(
    ("body", "expected_executed", "expected_skipped", "expected_passed"),
    [
        ('self.skipTest("synthetic skip")', 0, 3, False),
        ("pass", 3, 0, True),
        (
            'for value in range(2):\n'
            '            with self.subTest(value=value):\n'
            '                self.skipTest("synthetic subtest skip")',
            3, 6, True,
        ),
    ],
)
def test_visible_suite_requires_executed_tests(
    tmp_path, monkeypatch, verifier, body,
    expected_executed, expected_skipped, expected_passed,
):
    tests = tmp_path / "tests"
    tests.mkdir()
    name = "test_notes_cli"
    (tests / f"{name}.py").write_text(
        "import unittest\n\n"
        "class SyntheticTests(unittest.TestCase):\n"
        + "".join(f"    def test_{index}(self):\n        {body}\n" for index in range(3)),
        encoding="utf-8",
    )
    monkeypatch.setattr(sys, "path", sys.path.copy())
    monkeypatch.setitem(sys.modules, name, None)
    monkeypatch.delitem(sys.modules, name)

    check = verifier["_check_unittest_suite"](tmp_path)

    assert check["passed"] is expected_passed
    assert check["tests_run"] == 3
    assert check["tests_executed"] == expected_executed
    assert check["skipped"] == expected_skipped
    assert check["failures"] == check["errors"] == 0


@pytest.mark.parametrize("interrupted", [False, True], ids=["short-write", "interrupt"])
def test_receipt_preserves_previous_publication(tmp_path, monkeypatch, verifier, interrupted):
    output = tmp_path / "receipt.json"
    previous = b'{"passed": true}\n'
    output.write_bytes(previous)
    main = verifier["main"]
    monkeypatch.setitem(main.__globals__, "_load_project", lambda _: (None, None))
    monkeypatch.setattr(sys, "argv", [
        "check.py", "--workspace", str(tmp_path), "--case", "synthetic",
        "--pack-id", "mini-project-completion", "--pack-version", "0.1.0",
        "--source-fixture-id", "repo", "--patch", str(tmp_path / "missing.diff"),
        "--output", str(output),
    ])
    open_file = io.open

    class PartialWriter:
        def __init__(self, stream):
            self.stream = stream

        def __getattr__(self, name):
            return getattr(self.stream, name)

        def __enter__(self):
            self.stream.__enter__()
            return self

        def __exit__(self, *exc):
            return self.stream.__exit__(*exc)

        def write(self, data):
            self.stream.write(data[:4])
            if interrupted:
                raise KeyboardInterrupt("synthetic interruption")
            return 4

    def failing_open(file, mode="r", *args, **kwargs):
        stream = open_file(file, mode, *args, **kwargs)
        if file in (output, tmp_path, str(tmp_path)) and mode.startswith("w"):
            return PartialWriter(stream)
        return stream

    with monkeypatch.context() as fault:
        fault.setattr(io, "open", failing_open)
        expected_error = KeyboardInterrupt if interrupted else OSError
        with pytest.raises(expected_error):
            main()

    assert output.read_bytes() == previous
    assert list(tmp_path.iterdir()) == [output]

    assert main() == 1
    receipt = json.loads(output.read_bytes())
    assert receipt["case"] == "synthetic"
    assert receipt["passed"] is False
    assert list(tmp_path.iterdir()) == [output]
