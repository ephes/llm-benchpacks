from __future__ import annotations

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
