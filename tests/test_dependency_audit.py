"""Exercise audit orchestration without a package index or advisory service."""

from pathlib import Path
import runpy
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("failure", [None, "export", "audit"])
def test_frozen_audit_propagates_each_failure(monkeypatch, failure):
    calls = []
    requirements = None
    fixture = "example-transport==1.0.0 --hash=sha256:" + "a" * 64 + "\n"

    def run(command, *, cwd, check, **kwargs):
        nonlocal requirements
        assert cwd == ROOT
        assert check is True
        stage = "export" if command[0] == "uv" else "audit"
        calls.append(stage)
        if stage == "export":
            assert command[1:7] == [
                "export", "--frozen", "--group", "dev", "--no-emit-project", "--format",
            ]
            requirements = Path(command[command.index("--output-file") + 1])
            requirements.write_text(fixture)
        else:
            assert command[:4] == [
                "uvx", "--python", sys.executable, "pip-audit==2.10.1",
            ]
            assert {"--require-hashes", "--disable-pip", "--strict"} <= set(command)
            exported = Path(command[command.index("--requirement") + 1])
            assert exported == requirements
            assert exported.read_text() == fixture
        if stage == failure:
            raise subprocess.CalledProcessError(1, command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(subprocess, "run", run)
    if failure:
        with pytest.raises(subprocess.CalledProcessError):
            runpy.run_path(str(ROOT / "scripts/audit-python.py"), run_name="__main__")
    else:
        runpy.run_path(str(ROOT / "scripts/audit-python.py"), run_name="__main__")
    assert calls == (["export"] if failure == "export" else ["export", "audit"])
    assert requirements is not None
    assert not requirements.parent.exists()
