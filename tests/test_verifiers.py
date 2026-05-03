"""Tests for repo-task verifier helpers."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from benchpack.packs import Case, Fixture, Pack, Scoring
from benchpack.verifiers import (
    VerifierError,
    resolve_verify_script,
    run_repo_task_verifier,
    verify_artifact_paths,
)
from benchpack.workspaces import PreparedWorkspace


def make_case() -> Case:
    return Case(
        id="edit-repo",
        kind="repo-task",
        prompt="Change the repository.",
        scoring=Scoring(mode="verify-script", script="verify/check.py"),
        raw={},
    )


def make_pack(pack_dir: Path, scoring: Scoring | None = None) -> Pack:
    return Pack(
        id="repo-pack",
        version="0.1.0",
        description="",
        defaults={},
        cases=[make_case()],
        scoring=scoring,
        path=pack_dir,
    )


def make_fixture(source: Path) -> Fixture:
    return Fixture(
        id="repo",
        kind="repo",
        path=source,
        description="",
        raw={"id": "repo", "kind": "repo", "path": "fixtures/repo"},
    )


def make_prepared(tmp_path: Path) -> PreparedWorkspace:
    source = tmp_path / "pack" / "fixtures" / "repo"
    workspace = tmp_path / "run" / "workspace" / "edit-repo" / "rep-001"
    source.mkdir(parents=True)
    workspace.mkdir(parents=True)
    return PreparedWorkspace(source_fixture=make_fixture(source), path=workspace)


def write_script(pack_dir: Path, body: str) -> Path:
    script = pack_dir / "verify" / "check.py"
    script.parent.mkdir(parents=True)
    script.write_text(body, encoding="utf-8")
    return script


def test_verify_artifact_paths_use_run_relative_layout(tmp_path: Path) -> None:
    paths = verify_artifact_paths(tmp_path / "run", make_case(), 1)

    assert paths.json == tmp_path / "run" / "verify" / "edit-repo" / "rep-001.json"
    assert paths.stdout == (
        tmp_path / "run" / "verify" / "edit-repo" / "rep-001.stdout.log"
    )
    assert paths.stderr == (
        tmp_path / "run" / "verify" / "edit-repo" / "rep-001.stderr.log"
    )


@pytest.mark.parametrize("repetition", [0, -1, True, "1"])
def test_verify_artifact_paths_reject_invalid_repetition(
    tmp_path: Path,
    repetition: object,
) -> None:
    with pytest.raises(ValueError, match="repetition"):
        verify_artifact_paths(
            tmp_path / "run",
            make_case(),
            repetition,  # type: ignore[arg-type]
        )


def test_resolve_verify_script_rejects_absolute_path(tmp_path: Path) -> None:
    pack_dir = tmp_path / "pack"
    pack_dir.mkdir()
    pack = make_pack(pack_dir)

    with pytest.raises(VerifierError, match="relative"):
        resolve_verify_script(pack, Scoring(mode="verify-script", script="/tmp/x.py"))


def test_resolve_verify_script_rejects_pack_escape(tmp_path: Path) -> None:
    pack_dir = tmp_path / "pack"
    pack_dir.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text("", encoding="utf-8")
    pack = make_pack(pack_dir)

    with pytest.raises(VerifierError, match="escapes"):
        resolve_verify_script(pack, Scoring(mode="verify-script", script="../outside.py"))


def test_resolve_verify_script_requires_existing_file(tmp_path: Path) -> None:
    pack_dir = tmp_path / "pack"
    pack_dir.mkdir()
    pack = make_pack(pack_dir)

    with pytest.raises(VerifierError, match="does not exist"):
        resolve_verify_script(pack, Scoring(mode="verify-script", script="verify/missing.py"))


def test_resolve_verify_script_rejects_symlink_escape(tmp_path: Path) -> None:
    pack_dir = tmp_path / "pack"
    script = pack_dir / "verify" / "check.py"
    script.parent.mkdir(parents=True)
    outside = tmp_path / "outside.py"
    outside.write_text("", encoding="utf-8")
    try:
        script.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"symlinks cannot be created on this filesystem: {exc}")
    pack = make_pack(pack_dir)

    with pytest.raises(VerifierError, match="escapes"):
        resolve_verify_script(pack, Scoring(mode="verify-script", script="verify/check.py"))


def test_run_verifier_writes_fallback_json_and_logs(tmp_path: Path) -> None:
    pack_dir = tmp_path / "pack"
    pack_dir.mkdir()
    write_script(
        pack_dir,
        """
import sys
print("out")
print("err", file=sys.stderr)
""",
    )
    pack = make_pack(pack_dir)
    prepared = make_prepared(tmp_path)
    patch = tmp_path / "run" / "patch" / "edit-repo" / "rep-001.diff"
    patch.parent.mkdir(parents=True)
    patch.write_text("", encoding="utf-8")

    result = run_repo_task_verifier(
        pack=pack,
        case=pack.cases[0],
        scoring=pack.cases[0].scoring,  # type: ignore[arg-type]
        prepared_workspace=prepared,
        patch_path=patch,
        output_dir=tmp_path / "run",
        repetition=1,
    )

    assert result.repo_task == {"status": "passed", "verify_exit_code": 0}
    assert result.scoring == {"mode": "verify-script", "passed": True}
    assert result.verify == {
        "path": "verify/edit-repo/rep-001.json",
        "stdout_path": "verify/edit-repo/rep-001.stdout.log",
        "stderr_path": "verify/edit-repo/rep-001.stderr.log",
    }
    assert json.loads((tmp_path / "run" / result.verify["path"]).read_text()) == {
        "exit_code": 0,
        "passed": True,
    }
    assert (tmp_path / "run" / result.verify["stdout_path"]).read_text() == "out\n"
    assert (tmp_path / "run" / result.verify["stderr_path"]).read_text() == "err\n"


def test_run_verifier_preserves_and_corrects_script_json(tmp_path: Path) -> None:
    pack_dir = tmp_path / "pack"
    pack_dir.mkdir()
    write_script(
        pack_dir,
        """
import argparse
import json
parser = argparse.ArgumentParser()
parser.add_argument("--workspace")
parser.add_argument("--case")
parser.add_argument("--pack-id")
parser.add_argument("--pack-version")
parser.add_argument("--source-fixture-id")
parser.add_argument("--patch")
parser.add_argument("--output")
args = parser.parse_args()
with open(args.output, "w", encoding="utf-8") as fh:
    json.dump({"detail": "kept", "exit_code": 99, "passed": True}, fh)
raise SystemExit(3)
""",
    )
    pack = make_pack(pack_dir)
    prepared = make_prepared(tmp_path)
    patch = tmp_path / "run" / "patch" / "edit-repo" / "rep-001.diff"
    patch.parent.mkdir(parents=True)
    patch.write_text("", encoding="utf-8")

    result = run_repo_task_verifier(
        pack=pack,
        case=pack.cases[0],
        scoring=pack.cases[0].scoring,  # type: ignore[arg-type]
        prepared_workspace=prepared,
        patch_path=patch,
        output_dir=tmp_path / "run",
        repetition=1,
    )

    payload = json.loads((tmp_path / "run" / result.verify["path"]).read_text())
    assert payload == {"detail": "kept", "exit_code": 3, "passed": False}
    assert result.repo_task == {"status": "failed", "verify_exit_code": 3}
    assert result.scoring == {"mode": "verify-script", "passed": False}


def test_run_verifier_replaces_non_object_script_json(tmp_path: Path) -> None:
    pack_dir = tmp_path / "pack"
    pack_dir.mkdir()
    write_script(
        pack_dir,
        """
import argparse
import json
parser = argparse.ArgumentParser()
parser.add_argument("--workspace")
parser.add_argument("--case")
parser.add_argument("--pack-id")
parser.add_argument("--pack-version")
parser.add_argument("--source-fixture-id")
parser.add_argument("--patch")
parser.add_argument("--output")
args = parser.parse_args()
with open(args.output, "w", encoding="utf-8") as fh:
    json.dump(["not", "an", "object"], fh)
""",
    )
    pack = make_pack(pack_dir)
    prepared = make_prepared(tmp_path)
    patch = tmp_path / "run" / "patch" / "edit-repo" / "rep-001.diff"
    patch.parent.mkdir(parents=True)
    patch.write_text("", encoding="utf-8")

    result = run_repo_task_verifier(
        pack=pack,
        case=pack.cases[0],
        scoring=pack.cases[0].scoring,  # type: ignore[arg-type]
        prepared_workspace=prepared,
        patch_path=patch,
        output_dir=tmp_path / "run",
        repetition=1,
    )

    assert json.loads((tmp_path / "run" / result.verify["path"]).read_text()) == {
        "exit_code": 0,
        "passed": True,
    }
    assert result.repo_task == {"status": "passed", "verify_exit_code": 0}
    assert result.scoring == {"mode": "verify-script", "passed": True}


def test_run_verifier_overlays_manifest_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pack_dir = tmp_path / "pack"
    pack_dir.mkdir()
    write_script(pack_dir, "")
    scoring = Scoring(
        mode="verify-script",
        script="verify/check.py",
        environment={"BENCHPACK_MANIFEST_VAR": "from-manifest"},
    )
    pack = make_pack(pack_dir)
    prepared = make_prepared(tmp_path)
    patch = tmp_path / "run" / "patch" / "edit-repo" / "rep-001.diff"
    patch.parent.mkdir(parents=True)
    patch.write_text("", encoding="utf-8")
    monkeypatch.setenv("BENCHPACK_HOST_VAR", "from-host")
    run_kwargs: dict[str, object] = {}

    def fake_run(command, **kwargs):
        run_kwargs.update(kwargs)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("benchpack.verifiers.subprocess.run", fake_run)

    run_repo_task_verifier(
        pack=pack,
        case=pack.cases[0],
        scoring=scoring,
        prepared_workspace=prepared,
        patch_path=patch,
        output_dir=tmp_path / "run",
        repetition=1,
    )

    env = run_kwargs["env"]
    assert isinstance(env, dict)
    assert env["BENCHPACK_MANIFEST_VAR"] == "from-manifest"
    assert env["BENCHPACK_HOST_VAR"] == "from-host"
    assert env != {"BENCHPACK_MANIFEST_VAR": "from-manifest"}


def test_run_verifier_omits_subprocess_env_when_manifest_environment_absent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pack_dir = tmp_path / "pack"
    pack_dir.mkdir()
    write_script(pack_dir, "")
    pack = make_pack(pack_dir)
    prepared = make_prepared(tmp_path)
    patch = tmp_path / "run" / "patch" / "edit-repo" / "rep-001.diff"
    patch.parent.mkdir(parents=True)
    patch.write_text("", encoding="utf-8")
    run_kwargs: dict[str, object] = {}

    def fake_run(command, **kwargs):
        run_kwargs.update(kwargs)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("benchpack.verifiers.subprocess.run", fake_run)

    run_repo_task_verifier(
        pack=pack,
        case=pack.cases[0],
        scoring=pack.cases[0].scoring,  # type: ignore[arg-type]
        prepared_workspace=prepared,
        patch_path=patch,
        output_dir=tmp_path / "run",
        repetition=1,
    )

    assert "env" not in run_kwargs


def test_run_verifier_timeout_writes_captured_logs_and_failed_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pack_dir = tmp_path / "pack"
    pack_dir.mkdir()
    write_script(pack_dir, "")
    pack = make_pack(pack_dir)
    prepared = make_prepared(tmp_path)
    patch = tmp_path / "run" / "patch" / "edit-repo" / "rep-001.diff"
    patch.parent.mkdir(parents=True)
    patch.write_text("", encoding="utf-8")

    def timeout_run(command, **kwargs):
        raise subprocess.TimeoutExpired(
            command,
            kwargs["timeout"],
            output="partial stdout\n",
            stderr=b"partial stderr\n",
        )

    monkeypatch.setattr("benchpack.verifiers.subprocess.run", timeout_run)

    result = run_repo_task_verifier(
        pack=pack,
        case=pack.cases[0],
        scoring=pack.cases[0].scoring,  # type: ignore[arg-type]
        prepared_workspace=prepared,
        patch_path=patch,
        output_dir=tmp_path / "run",
        repetition=1,
        timeout_s=12.5,
    )

    assert result.exit_code is None
    assert result.repo_task == {"status": "failed", "verify_exit_code": None}
    assert result.scoring == {"mode": "verify-script", "passed": False}
    assert (tmp_path / "run" / result.verify["stdout_path"]).read_text() == (
        "partial stdout\n"
    )
    assert (tmp_path / "run" / result.verify["stderr_path"]).read_text() == (
        "partial stderr\n"
    )
    assert json.loads((tmp_path / "run" / result.verify["path"]).read_text()) == {
        "exit_code": None,
        "passed": False,
        "timed_out": True,
        "timeout_s": 12.5,
    }


def test_run_verifier_timeout_preserves_object_json_with_authoritative_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pack_dir = tmp_path / "pack"
    pack_dir.mkdir()
    write_script(pack_dir, "")
    pack = make_pack(pack_dir)
    prepared = make_prepared(tmp_path)
    patch = tmp_path / "run" / "patch" / "edit-repo" / "rep-001.diff"
    patch.parent.mkdir(parents=True)
    patch.write_text("", encoding="utf-8")

    def timeout_run(command, **kwargs):
        output_path = Path(command[command.index("--output") + 1])
        output_path.write_text(
            json.dumps(
                {
                    "detail": "kept",
                    "exit_code": 0,
                    "passed": True,
                    "timed_out": False,
                    "timeout_s": 99,
                }
            ),
            encoding="utf-8",
        )
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr("benchpack.verifiers.subprocess.run", timeout_run)

    result = run_repo_task_verifier(
        pack=pack,
        case=pack.cases[0],
        scoring=pack.cases[0].scoring,  # type: ignore[arg-type]
        prepared_workspace=prepared,
        patch_path=patch,
        output_dir=tmp_path / "run",
        repetition=1,
        timeout_s=7.0,
    )

    assert json.loads((tmp_path / "run" / result.verify["path"]).read_text()) == {
        "detail": "kept",
        "exit_code": None,
        "passed": False,
        "timed_out": True,
        "timeout_s": 7.0,
    }
    assert (tmp_path / "run" / result.verify["stdout_path"]).read_text() == ""
    assert (tmp_path / "run" / result.verify["stderr_path"]).read_text() == ""
    assert result.repo_task == {"status": "failed", "verify_exit_code": None}
    assert result.scoring == {"mode": "verify-script", "passed": False}


@pytest.mark.parametrize("script_json", ["[\"not\", \"an\", \"object\"]", "{bad json"])
def test_run_verifier_timeout_replaces_invalid_script_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    script_json: str,
) -> None:
    pack_dir = tmp_path / "pack"
    pack_dir.mkdir()
    write_script(pack_dir, "")
    pack = make_pack(pack_dir)
    prepared = make_prepared(tmp_path)
    patch = tmp_path / "run" / "patch" / "edit-repo" / "rep-001.diff"
    patch.parent.mkdir(parents=True)
    patch.write_text("", encoding="utf-8")

    def timeout_run(command, **kwargs):
        output_path = Path(command[command.index("--output") + 1])
        output_path.write_text(script_json, encoding="utf-8")
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr("benchpack.verifiers.subprocess.run", timeout_run)

    result = run_repo_task_verifier(
        pack=pack,
        case=pack.cases[0],
        scoring=pack.cases[0].scoring,  # type: ignore[arg-type]
        prepared_workspace=prepared,
        patch_path=patch,
        output_dir=tmp_path / "run",
        repetition=1,
        timeout_s=3.0,
    )

    assert json.loads((tmp_path / "run" / result.verify["path"]).read_text()) == {
        "exit_code": None,
        "passed": False,
        "timed_out": True,
        "timeout_s": 3.0,
    }
