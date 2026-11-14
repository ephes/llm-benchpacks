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
        "supplemental_error": "invalid_json",
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

    monkeypatch.setattr("benchpack.verifiers._run_verifier_command", fake_run)

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

    monkeypatch.setattr("benchpack.verifiers._run_verifier_command", fake_run)

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
        kwargs["stdout"].write(b"partial stdout\n")
        kwargs["stderr"].write(b"partial stderr\n")
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr("benchpack.verifiers._run_verifier_command", timeout_run)

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

    monkeypatch.setattr("benchpack.verifiers._run_verifier_command", timeout_run)

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

    monkeypatch.setattr("benchpack.verifiers._run_verifier_command", timeout_run)

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
        "supplemental_error": "invalid_json",
        "exit_code": None,
        "passed": False,
        "timed_out": True,
        "timeout_s": 3.0,
    }


@pytest.mark.skipif(__import__('os').name != 'posix', reason='POSIX process groups')
@pytest.mark.parametrize(('parent_exits', 'child_closes_pipes'), [(False, False), (True, False), (False, True)])
def test_verifier_timeout_stops_descendants(tmp_path: Path, parent_exits: bool, child_closes_pipes: bool) -> None:
    import os
    import signal
    import time
    prepared = make_prepared(tmp_path)
    pack_dir = tmp_path / 'pack'
    marker = tmp_path / 'late-marker'
    ready = tmp_path / 'child-ready'
    child_body = (
        'import os, signal, time; from pathlib import Path; '
        'signal.signal(signal.SIGTERM, signal.SIG_IGN); '
        + ('os.close(1); os.close(2); ' if child_closes_pipes else '')
        + f'Path({str(ready)!r}).write_text(str(os.getpid())); '
        + f'time.sleep(4); Path({str(marker)!r}).write_text("escaped")'
    )
    write_script(pack_dir,
        'import subprocess, sys, time\nfrom pathlib import Path\n'
        + f'subprocess.Popen([sys.executable, "-c", {child_body!r}])\n'
        + f'while not Path({str(ready)!r}).exists(): time.sleep(0.01)\n'
        + 'print("ready", flush=True)\n'
        + ('sys.exit(0)\n' if parent_exits else 'time.sleep(30)\n')
    )
    pack = make_pack(pack_dir)
    started = time.monotonic()
    try:
        result = run_repo_task_verifier(pack=pack, case=pack.cases[0], scoring=pack.cases[0].scoring,
            prepared_workspace=prepared, patch_path=tmp_path / 'patch.diff', output_dir=tmp_path / 'run',
            repetition=1, timeout_s=2)
        assert time.monotonic() - started < 5
        assert ready.exists(), 'descendant must have started'
        assert result.scoring['passed'] is False
        payload = json.loads((tmp_path / 'run' / result.verify['path']).read_text())
        assert payload['timed_out'] is True
        assert payload['exit_code'] is None
        assert 'ready' in (tmp_path / 'run' / result.verify['stdout_path']).read_text()
        time.sleep(4.1)
        assert not marker.exists()
        pid = int(ready.read_text())
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            pass
        else:
            # On Linux an orphan may be dead but awaiting its init reaper.
            stat = Path(f'/proc/{pid}/stat')
            assert stat.exists() and stat.read_text().split()[2] == 'Z'
    finally:
        if ready.exists():
            try:
                os.kill(int(ready.read_text()), signal.SIGKILL)
            except ProcessLookupError:
                pass


@pytest.mark.skipif(__import__('os').name != 'posix', reason='POSIX process groups')
def test_verifier_interrupt_reaps_isolated_process(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import os
    prepared = make_prepared(tmp_path)
    pack_dir = tmp_path / 'pack'
    write_script(pack_dir, 'import time; time.sleep(30)')
    pack = make_pack(pack_dir)
    original = subprocess.Popen.wait
    seen = []

    def interrupt_once(process, *args, **kwargs):
        if not seen:
            seen.append(process)
            raise KeyboardInterrupt
        return original(process, *args, **kwargs)

    monkeypatch.setattr(subprocess.Popen, 'wait', interrupt_once)
    with pytest.raises(KeyboardInterrupt):
        run_repo_task_verifier(pack=pack, case=pack.cases[0], scoring=pack.cases[0].scoring,
            prepared_workspace=prepared, patch_path=tmp_path / 'patch.diff', output_dir=tmp_path / 'run',
            repetition=1, timeout_s=2)
    assert seen[0].returncode is not None
    assert seen[0].stdout.closed and seen[0].stderr.closed
    with pytest.raises(ProcessLookupError):
        os.kill(seen[0].pid, 0)


@pytest.mark.parametrize("outcome", ["success", "nonzero", "timeout"])
def test_noisy_verifier_uses_file_logs_and_bounded_tails(tmp_path, monkeypatch, outcome):
    import benchpack.verifiers as verifiers
    pack_dir = tmp_path / "pack"
    size = 2 * 1024 * 1024
    write_script(pack_dir,
        'import os, sys, time\n'
        + f'os.write(1, b"o" * {size})\n'
        + f'os.write(2, b"e" * {size})\n'
        + ('time.sleep(30)\n' if outcome == "timeout" else f'sys.exit({2 if outcome == "nonzero" else 0})\n'))
    pack = make_pack(pack_dir)
    prepared = make_prepared(tmp_path)
    popen = subprocess.Popen
    observed = []
    def spawn(*args, **kwargs):
        assert kwargs["stdout"] == subprocess.PIPE
        assert kwargs["stderr"] == subprocess.PIPE
        observed.append(True)
        return popen(*args, **kwargs)
    real_run = verifiers._run_verifier_command
    diagnostics = []
    def run(*args, **kwargs):
        try:
            completed = real_run(*args, **kwargs)
        except subprocess.TimeoutExpired as exc:
            diagnostics.extend((exc.stdout, exc.stderr))
            raise
        diagnostics.extend((completed.stdout, completed.stderr))
        return completed
    monkeypatch.setattr(verifiers.subprocess, "Popen", spawn)
    monkeypatch.setattr(verifiers, "_run_verifier_command", run)
    result = run_repo_task_verifier(
        pack=pack, case=pack.cases[0], scoring=pack.cases[0].scoring,
        prepared_workspace=prepared, patch_path=tmp_path / "patch.diff",
        output_dir=tmp_path / "run", repetition=1, timeout_s=2)
    assert observed
    assert (tmp_path / "run" / result.verify["stdout_path"]).read_bytes() == b"o" * size
    assert (tmp_path / "run" / result.verify["stderr_path"]).read_bytes() == b"e" * size
    assert diagnostics == ["o" * 65536, "e" * 65536]
    assert result.scoring["passed"] is (outcome == "success")
    payload = json.loads((tmp_path / "run" / result.verify["path"]).read_text())
    assert payload["exit_code"] == (None if outcome == "timeout" else 2 if outcome == "nonzero" else 0)
    if outcome == "timeout":
        assert payload["timed_out"] is True


def test_verifier_tail_preserves_writer_offset_and_decodes_bounded_bytes(tmp_path):
    from benchpack.verifiers import _log_tail
    path = tmp_path / "output.log"
    data = b"x" * 70000 + b"\xffend\r\n"
    with path.open("wb") as writer:
        writer.write(data)
        writer.flush()
        writer.seek(7)
        tail = _log_tail(writer)
        assert writer.tell() == 7
    assert tail.endswith("\ufffdend\r\n")
    assert len(tail) == 65536
    assert path.read_bytes() == data


@pytest.mark.parametrize('data', [b'\xff', b'[' * 1500 + b']' * 1500,
    b'{"n":' + b'9' * 5000 + b'}', b'{"n":NaN}', b'{"n":1e999}', b'x' * (1024 * 1024 + 1)])
@pytest.mark.parametrize('exit_code', [0, 2])
def test_supplemental_json_refusal_keeps_exit_authority(tmp_path, data, exit_code):
    from benchpack.verifiers import _write_authoritative_json
    path = tmp_path / 'verify.json'
    path.write_bytes(data)
    _write_authoritative_json(path, exit_code=exit_code, passed=exit_code == 0)
    payload = json.loads(path.read_text())
    assert payload['supplemental_error'] in {'read_error', 'invalid_json'}
    assert payload['exit_code'] == exit_code
    assert payload['passed'] is (exit_code == 0)


def test_supplemental_symlink_is_replaced_without_touching_target(tmp_path):
    from benchpack.verifiers import _write_authoritative_json
    target = tmp_path / 'outside'
    target.write_text('{"secret":true}')
    path = tmp_path / 'verify.json'
    path.symlink_to(target)
    _write_authoritative_json(path, exit_code=0, passed=True)
    assert target.read_text() == '{"secret":true}'
    assert not path.is_symlink()
    assert json.loads(path.read_text()) == {
        'exit_code': 0, 'passed': True, 'supplemental_error': 'read_error'}


@pytest.mark.skipif(__import__('os').name != 'posix', reason='FIFO')
def test_supplemental_fifo_does_not_block(tmp_path):
    import os
    import sys
    path = tmp_path / 'verify.json'
    os.mkfifo(path)
    subprocess.run([sys.executable, '-c',
        'from pathlib import Path; from benchpack.verifiers import _write_authoritative_json; '
        f'_write_authoritative_json(Path({str(path)!r}), exit_code=0, passed=True)'],
        check=True, timeout=3)
    assert json.loads(path.read_text())['supplemental_error'] == 'read_error'


@pytest.mark.parametrize('failure', ['write', 'partial_write', 'replace', 'interrupt'])
def test_json_publication_failure_preserves_old_bytes(tmp_path, monkeypatch, failure):
    import benchpack.verifiers as verifiers
    path = tmp_path / 'verify.json'
    old = b'{"evidence":"old"}\n'
    path.write_bytes(old)
    def fail(*args, **kwargs):
        if failure == 'interrupt':
            raise KeyboardInterrupt
        raise OSError('injected publication failure')
    if failure == 'partial_write':
        from contextlib import contextmanager
        fdopen = verifiers.os.fdopen
        @contextmanager
        def partial_writer(fd, *args, **kwargs):
            with fdopen(fd, *args, **kwargs) as stream:
                class Writer:
                    def write(self, data):
                        stream.write(data[:5])
                        raise OSError('injected partial write')
                yield Writer()
        monkeypatch.setattr(verifiers.os, 'fdopen', partial_writer)
    elif failure == 'write':
        monkeypatch.setattr(verifiers.os, 'fsync', fail)
    else:
        monkeypatch.setattr(verifiers.os, 'replace', fail)
    with pytest.raises(KeyboardInterrupt if failure == 'interrupt' else OSError):
        verifiers._write_authoritative_json(path, exit_code=0, passed=True)
    assert path.read_bytes() == old
    assert list(tmp_path.iterdir()) == [path]
    monkeypatch.undo()
    verifiers._write_authoritative_json(path, exit_code=0, passed=True)
    assert json.loads(path.read_text()) == {'evidence': 'old', 'exit_code': 0, 'passed': True}


@pytest.mark.parametrize('sizes,stream_cap,total_cap', [((9000, 0), 8192, 16384),
    ((6000, 6000), 8192, 10000), ((8192, 1808), 8192, 10000)])
def test_verifier_log_limits_are_exact_and_fail_overflow(tmp_path, monkeypatch, sizes, stream_cap, total_cap):
    import benchpack.verifiers as verifiers
    monkeypatch.setattr(verifiers, 'MAX_VERIFY_LOG_STREAM_BYTES', stream_cap, raising=False)
    monkeypatch.setattr(verifiers, 'MAX_VERIFY_LOG_TOTAL_BYTES', total_cap, raising=False)
    run = verifiers._run_verifier_command
    captured = []
    def observe(*args, **kwargs):
        try:
            return run(*args, **kwargs)
        except verifiers.VerifierOutputLimit as exc:
            captured.append((exc.stdout, exc.stderr))
            raise
    monkeypatch.setattr(verifiers, '_run_verifier_command', observe)
    pack_dir = tmp_path / 'pack'
    write_script(pack_dir, f'import os\nos.write(1, b"o" * {sizes[0]})\nos.write(2, b"e" * {sizes[1]})\n')
    pack = make_pack(pack_dir)
    result = run_repo_task_verifier(pack=pack, case=pack.cases[0], scoring=pack.cases[0].scoring,
        prepared_workspace=make_prepared(tmp_path), patch_path=tmp_path / 'patch',
        output_dir=tmp_path / 'run', repetition=1, timeout_s=2)
    logs = [(tmp_path / 'run' / result.verify[key]).read_bytes() for key in ['stdout_path', 'stderr_path']]
    overflow = max(sizes) > stream_cap or sum(sizes) > total_cap
    assert result.scoring['passed'] is (not overflow)
    assert all(len(log) <= stream_cap for log in logs)
    assert sum(map(len, logs)) <= total_cap
    payload = json.loads((tmp_path / 'run' / result.verify['path']).read_text())
    if overflow:
        assert captured and all(len(tail) <= 65536 for tail in captured[0])
        assert any(captured[0])
        assert payload['output_limit'] is True
        assert payload['exit_code'] is None
    else:
        assert logs == [b'o' * sizes[0], b'e' * sizes[1]]


@pytest.mark.skipif(__import__('os').name != 'posix', reason='POSIX process groups')
def test_log_overflow_stops_noisy_descendant(tmp_path, monkeypatch):
    import os
    import signal
    import time
    import benchpack.verifiers as verifiers
    monkeypatch.setattr(verifiers, 'MAX_VERIFY_LOG_STREAM_BYTES', 8192, raising=False)
    ready = tmp_path / 'child.pid'
    marker = tmp_path / 'survived'
    child = ('import os,time,signal; from pathlib import Path; '
        'signal.signal(signal.SIGTERM, signal.SIG_IGN); '
        f'Path({str(ready)!r}).write_text(str(os.getpid())); '
        'os.write(1,b"x"*1000000); time.sleep(2); '
        f'Path({str(marker)!r}).write_text("bad")')
    pack_dir = tmp_path / 'pack'
    write_script(pack_dir, f'import subprocess,sys,time\nsubprocess.Popen([sys.executable,"-c",{child!r}])\ntime.sleep(30)\n')
    pack = make_pack(pack_dir)
    try:
        started = time.monotonic()
        result = run_repo_task_verifier(pack=pack, case=pack.cases[0], scoring=pack.cases[0].scoring,
            prepared_workspace=make_prepared(tmp_path), patch_path=tmp_path / 'patch',
            output_dir=tmp_path / 'run', repetition=1, timeout_s=5)
        assert time.monotonic() - started < 3
        assert ready.exists()
        assert result.scoring['passed'] is False
        assert json.loads((tmp_path / 'run' / result.verify['path']).read_text())['output_limit'] is True
        assert (tmp_path / 'run' / result.verify['stdout_path']).stat().st_size <= 8192
        time.sleep(2.1)
        assert not marker.exists()
        pid = int(ready.read_text())
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            pass
        else:
            assert Path(f'/proc/{pid}/stat').read_text().split()[2] == 'Z'
    finally:
        if ready.exists():
            try:
                os.kill(int(ready.read_text()), signal.SIGKILL)
            except ProcessLookupError:
                pass


@pytest.mark.skipif(__import__("os").name != "posix", reason="POSIX process groups")
def test_pipe_eof_and_retired_group_still_require_reaping_leader(tmp_path, monkeypatch):
    """Group disappearance can race the preceding nonblocking leader wait."""
    import io
    import benchpack.verifiers as verifiers
    class Process:
        pid = 12345
        returncode = None
        stdout = io.BytesIO()
        stderr = io.BytesIO()
        waits = 0
        def wait(self, timeout):
            self.waits += 1
            if self.waits < 4:
                raise subprocess.TimeoutExpired(['synthetic'], timeout)
            self.returncode = 0
            return 0
    process = Process()
    monkeypatch.setattr(verifiers.subprocess, 'Popen', lambda *a, **kw: process)
    def group_gone(*args):
        assert process.returncode is not None, "probe the group only after reaping its leader"
        raise ProcessLookupError
    monkeypatch.setattr(verifiers.os, 'killpg', group_gone)
    with (tmp_path / 'stdout').open('wb') as stdout, (tmp_path / 'stderr').open('wb') as stderr:
        result = verifiers._run_verifier_command(['synthetic'], timeout=1, stdout=stdout, stderr=stderr)
    assert result.returncode == 0
    assert process.waits >= 4
    assert process.stdout.closed and process.stderr.closed


def _run(tmp_path: Path, body: str, timeout_s: float = 5.0):
    prepared = make_prepared(tmp_path)
    pack_dir = tmp_path / "pack"
    write_script(pack_dir, body)
    pack = make_pack(pack_dir)
    return run_repo_task_verifier(
        pack=pack, case=pack.cases[0], scoring=pack.cases[0].scoring,  # type: ignore[arg-type]
        prepared_workspace=prepared, patch_path=tmp_path / "patch.diff", output_dir=tmp_path / "run",
        repetition=1, timeout_s=timeout_s,
    )


@pytest.mark.skipif(__import__("os").name != "posix", reason="POSIX signals")
def test_verifier_output_written_after_sigterm_is_kept(tmp_path: Path) -> None:
    # The handler is installed before 'started' is printed; a generous timeout
    # leaves slow machines time to get there before SIGTERM arrives.
    body = (
        "import signal, sys, time\n"
        "def stop(*_):\n"
        "    sys.stderr.write('terminated cleanly\\n'); sys.stderr.flush(); sys.exit(3)\n"
        "signal.signal(signal.SIGTERM, stop)\n"
        "print('started', flush=True)\n"
        "time.sleep(30)\n"
    )
    result = _run(tmp_path, body, timeout_s=3.0)
    payload = json.loads((tmp_path / "run" / result.verify["path"]).read_text())
    assert payload["timed_out"] is True
    assert "started" in (tmp_path / "run" / result.verify["stdout_path"]).read_text()
    assert "terminated cleanly" in (tmp_path / "run" / result.verify["stderr_path"]).read_text()


@pytest.mark.skipif(__import__("os").name != "posix", reason="POSIX sessions")
def test_escaped_descendant_holding_pipes_does_not_turn_success_into_timeout(tmp_path: Path) -> None:
    import os
    import signal
    import time

    ready = tmp_path / "escaped-ready"
    child = (
        "import os, time; from pathlib import Path; os.setsid(); "
        f"Path({str(ready)!r}).write_text(str(os.getpid())); time.sleep(20)"
    )
    body = (
        "import subprocess, sys, time\nfrom pathlib import Path\n"
        f"subprocess.Popen([sys.executable, '-c', {child!r}])\n"
        f"while not Path({str(ready)!r}).exists(): time.sleep(0.01)\n"
        "print('done', flush=True)\n"
        "sys.exit(0)\n"
    )
    started = time.monotonic()
    try:
        result = _run(tmp_path, body, timeout_s=10.0)
        assert time.monotonic() - started < 8
        assert result.exit_code == 0
        assert result.scoring == {"mode": "verify-script", "passed": True}
        assert "done" in (tmp_path / "run" / result.verify["stdout_path"]).read_text()
    finally:
        if ready.exists():
            try:
                os.kill(int(ready.read_text()), signal.SIGKILL)
            except ProcessLookupError:
                pass


@pytest.mark.skipif(__import__("os").name != "posix", reason="POSIX modes")
def test_verifier_json_keeps_previous_mode_and_follows_umask(tmp_path: Path) -> None:
    import os
    import stat

    body = "import sys\nsys.exit(0)\n"
    old = os.umask(0o022)
    try:
        result = _run(tmp_path, body)
        path = tmp_path / "run" / result.verify["path"]
        assert stat.S_IMODE(path.stat().st_mode) == 0o644
        path.chmod(0o640)
        from benchpack import verifiers

        verifiers._write_authoritative_json(path, exit_code=0, passed=True)
        assert stat.S_IMODE(path.stat().st_mode) == 0o640
    finally:
        os.umask(old)
