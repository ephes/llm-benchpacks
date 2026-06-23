"""Tests for the one-shot agent wrapping benchmark helper."""

from __future__ import annotations

import subprocess
import sys
import time
import importlib.util
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import SimpleNamespace


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run-agent-wrap-oneshot"
PROMPT = Path(__file__).resolve().parent / "fixtures" / "wrap-prompt.md"

_LOADER = SourceFileLoader("run_agent_wrap_oneshot", str(SCRIPT))
_SPEC = importlib.util.spec_from_loader("run_agent_wrap_oneshot", _LOADER)
assert _SPEC is not None
RUNNER = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(RUNNER)


def _run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        check=False,
        text=True,
        capture_output=True,
    )


def _init_source_repo(path: Path) -> None:
    path.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    (path / "README.md").write_text("source\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Bench Tests",
            "-c",
            "user.email=bench-tests@example.test",
            "commit",
            "-qm",
            "init",
        ],
        cwd=path,
        check=True,
    )


def test_dry_run_codex_yolo_uses_llm_benchpacks_results_root() -> None:
    result = _run_script(
        "--dry-run",
        "--label",
        "gpt55-codex-yolo-main-high",
        "--runner",
        "codex-yolo",
        "--model",
        "gpt-5.5",
        "--reasoning-effort",
        "high",
        "--prompt",
        str(PROMPT),
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert result.stdout.splitlines()[0] == "# run-agent-wrap-oneshot dry run"
    assert "runner: codex-yolo" in result.stdout
    assert "results/agent-wrap-oneshot/gpt55-codex-yolo-main-high" in result.stdout
    assert ".bench-qwen36" not in result.stdout
    assert (
        "agent: codex exec --dangerously-bypass-approvals-and-sandbox "
        "-m gpt-5.5 -c 'model_reasoning_effort=\"high\"'"
    ) in result.stdout
    assert "verify: npm --prefix electron run smoke:packaged when declared" in result.stdout


def test_dry_run_pi_renders_provider_thinking_and_mode() -> None:
    result = _run_script(
        "--dry-run",
        "--label",
        "glm52-openrouter-main-off",
        "--runner",
        "pi",
        "--provider",
        "openrouter",
        "--model",
        "z-ai/glm-5.2",
        "--thinking",
        "off",
        "--pi-mode",
        "json",
        "--prompt",
        str(PROMPT),
    )

    assert result.returncode == 0, result.stderr
    assert "runner: pi" in result.stdout
    assert "results/agent-wrap-oneshot/glm52-openrouter-main-off" in result.stdout
    assert "agent: pi --provider openrouter --model z-ai/glm-5.2" in result.stdout
    assert "--thinking off" in result.stdout
    assert "--mode json" in result.stdout
    assert ".bench-qwen36" not in result.stdout


def test_dry_run_pi_renders_extension_before_provider() -> None:
    result = _run_script(
        "--dry-run",
        "--label",
        "opus48-openrouter-main-off",
        "--runner",
        "pi",
        "--provider",
        "openrouter",
        "--model",
        "anthropic/claude-opus-4.8",
        "--pi-extension",
        "some-extension",
        "--prompt",
        str(PROMPT),
    )

    assert result.returncode == 0, result.stderr
    assert (
        "agent: pi -e some-extension --provider openrouter "
        "--model anthropic/claude-opus-4.8"
    ) in result.stdout


def test_codex_yolo_requires_explicit_reasoning_effort() -> None:
    result = _run_script(
        "--dry-run",
        "--label",
        "missing-reasoning",
        "--runner",
        "codex-yolo",
        "--model",
        "gpt-5.5",
        "--prompt",
        str(PROMPT),
    )

    assert result.returncode == 2
    assert "--reasoning-effort is required with --runner codex-yolo" in result.stderr
    assert result.stdout == ""


def test_label_must_be_one_safe_path_segment() -> None:
    result = _run_script(
        "--dry-run",
        "--label",
        "../../escape",
        "--runner",
        "codex-yolo",
        "--model",
        "gpt-5.5",
        "--reasoning-effort",
        "low",
        "--prompt",
        str(PROMPT),
    )

    assert result.returncode == 2
    assert "--label must be one safe path segment" in result.stderr
    assert result.stdout == ""


def test_missing_prompt_file_is_reported(tmp_path: Path) -> None:
    result = _run_script(
        "--dry-run",
        "--label",
        "missing-prompt",
        "--runner",
        "codex-yolo",
        "--model",
        "gpt-5.5",
        "--reasoning-effort",
        "low",
        "--prompt",
        str(tmp_path / "missing.md"),
    )

    assert result.returncode == 2
    assert "prompt file does not exist:" in result.stderr
    assert result.stdout == ""


def test_target_must_not_equal_source(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    result = _run_script(
        "--dry-run",
        "--label",
        "unsafe-target",
        "--runner",
        "codex-yolo",
        "--model",
        "gpt-5.5",
        "--reasoning-effort",
        "low",
        "--source",
        str(source),
        "--target",
        str(source),
        "--prompt",
        str(PROMPT),
    )

    assert result.returncode == 2
    assert "--target must not be the same path as --source" in result.stderr
    assert result.stdout == ""


def test_target_must_not_equal_starter(tmp_path: Path) -> None:
    starter = tmp_path / "starter"
    starter.mkdir()
    result = _run_script(
        "--dry-run",
        "--label",
        "unsafe-target",
        "--runner",
        "codex-yolo",
        "--model",
        "gpt-5.5",
        "--reasoning-effort",
        "low",
        "--starter",
        str(starter),
        "--target",
        str(starter),
        "--prompt",
        str(PROMPT),
    )

    assert result.returncode == 2
    assert "--target must not be the same path as --starter" in result.stderr
    assert result.stdout == ""


def test_target_must_not_equal_repo_root() -> None:
    repo_root = SCRIPT.parents[1]
    result = _run_script(
        "--dry-run",
        "--label",
        "unsafe-target",
        "--runner",
        "codex-yolo",
        "--model",
        "gpt-5.5",
        "--reasoning-effort",
        "low",
        "--target",
        str(repo_root),
        "--prompt",
        str(PROMPT),
    )

    assert result.returncode == 2
    assert "--target must not be the llm-benchpacks repository root" in result.stderr
    assert result.stdout == ""


def test_target_must_not_equal_output_dir(tmp_path: Path) -> None:
    results_root = tmp_path / "results"
    target = results_root / "unsafe-target"
    result = _run_script(
        "--dry-run",
        "--label",
        "unsafe-target",
        "--runner",
        "codex-yolo",
        "--model",
        "gpt-5.5",
        "--reasoning-effort",
        "low",
        "--results-root",
        str(results_root),
        "--target",
        str(target),
        "--prompt",
        str(PROMPT),
    )

    assert result.returncode == 2
    assert "--target must not be the same path as the output directory" in result.stderr
    assert result.stdout == ""


def test_target_must_not_be_inside_results_root(tmp_path: Path) -> None:
    results_root = tmp_path / "results"
    target = results_root / "other" / "nested-target"
    result = _run_script(
        "--dry-run",
        "--label",
        "unsafe-target",
        "--runner",
        "codex-yolo",
        "--model",
        "gpt-5.5",
        "--reasoning-effort",
        "low",
        "--results-root",
        str(results_root),
        "--target",
        str(target),
        "--prompt",
        str(PROMPT),
    )

    assert result.returncode == 2
    assert "--target must not be inside the results root" in result.stderr
    assert result.stdout == ""


def test_pi_requires_provider() -> None:
    result = _run_script(
        "--dry-run",
        "--label",
        "missing-provider",
        "--runner",
        "pi",
        "--model",
        "gpt-5.5",
        "--prompt",
        str(PROMPT),
    )

    assert result.returncode == 2
    assert "--provider is required with --runner pi" in result.stderr
    assert result.stdout == ""


def test_app_served_requires_health_and_root_or_redirect_chain() -> None:
    assert RUNNER._is_app_served(0, 1, 1, 0, 0)
    assert RUNNER._is_app_served(0, 1, 0, 1, 1)
    assert not RUNNER._is_app_served(0, 1, 0, 1, 0)
    assert not RUNNER._is_app_served(1, 1, 1, 0, 0)
    assert not RUNNER._is_app_served("NA", 1, 1, 0, 0)


def test_verify_served_app_without_node_tests_is_not_pass(
    tmp_path: Path,
    monkeypatch,
) -> None:
    target = tmp_path / "target"
    output = tmp_path / "output"
    (target / "electron" / "scripts").mkdir(parents=True)
    output.mkdir()
    (target / "electron" / "package.json").write_text("{}", encoding="utf-8")

    def fake_run_to_file(command, *, cwd, output_path, timeout_s=None, stdin_text=None):
        if command == ["npm", "--prefix", "electron", "run", "smoke:packaged"]:
            output_path.write_text(
                'GET /health/ HTTP/1.1" 200\nGET / HTTP/1.1" 200\n',
                encoding="utf-8",
            )
        else:
            output_path.write_text("", encoding="utf-8")
        return 0

    def fake_run_capture(command, *, cwd):
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="smoke:packaged\n",
            stderr="",
        )

    monkeypatch.setattr(RUNNER, "_run_to_file", fake_run_to_file)
    monkeypatch.setattr(RUNNER, "_run_capture", fake_run_capture)

    verification = RUNNER._verify(target, output)

    assert verification["app_served"] == 1
    assert verification["node_tests"] == "NA"
    assert RUNNER._outcome(verification) == "FAIL"


def test_summary_outcome_requires_served_app_and_passing_node_tests(tmp_path: Path) -> None:
    args = SimpleNamespace(
        label="unit",
        runner="codex-yolo",
        model="gpt-5.5",
        reasoning_effort="low",
        source=tmp_path / "source",
        target=tmp_path / "target",
        output=tmp_path,
    )
    verification = {
        "electron_exists": 1,
        "npm_install_ok": 1,
        "node_tests": "pass",
        "smoke_exit": 0,
        "health200": 1,
        "root200": 0,
        "root302": 1,
        "resume200": 1,
        "app_served": 1,
    }

    summary = RUNNER._write_summary(
        args,
        exit_label="codex_exit",
        agent_exit=0,
        duration_s=1.2,
        files_changed=3,
        verification=verification,
    )
    assert "outcome=PASS" in summary

    verification["node_tests"] = "fail"
    summary = RUNNER._write_summary(
        args,
        exit_label="codex_exit",
        agent_exit=0,
        duration_s=1.2,
        files_changed=3,
        verification=verification,
    )
    assert "outcome=FAIL" in summary

    verification["node_tests"] = "NA"
    summary = RUNNER._write_summary(
        args,
        exit_label="codex_exit",
        agent_exit=0,
        duration_s=1.2,
        files_changed=3,
        verification=verification,
    )
    assert "outcome=FAIL" in summary


def test_summary_records_pi_runner_options(tmp_path: Path) -> None:
    args = SimpleNamespace(
        label="unit",
        runner="pi",
        provider="anthropic",
        model="claude-opus-4.8",
        thinking="off",
        pi_extension="none",
        pi_mode=None,
        source=tmp_path / "source",
        target=tmp_path / "target",
        output=tmp_path,
    )
    verification = {
        "electron_exists": 1,
        "npm_install_ok": 1,
        "node_tests": "pass",
        "smoke_exit": 0,
        "health200": 1,
        "root200": 1,
        "root302": 0,
        "resume200": 0,
        "app_served": 1,
    }

    summary = RUNNER._write_summary(
        args,
        exit_label="pi_exit",
        agent_exit=0,
        duration_s=1.2,
        files_changed=3,
        verification=verification,
    )

    assert (
        "runner=pi provider=anthropic model=claude-opus-4.8 "
        "thinking=off pi_extension=none pi_mode="
    ) in summary
    assert "outcome=PASS" in summary


def test_capture_model_diff_records_staged_names_before_verification(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    output = tmp_path / "output"
    workspace.mkdir()
    output.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=workspace, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Bench Tests",
            "-c",
            "user.email=bench-tests@example.test",
            "commit",
            "--allow-empty",
            "-qm",
            "init",
        ],
        cwd=workspace,
        check=True,
    )
    (workspace / "electron").mkdir()
    (workspace / "electron" / "package.json").write_text("{}", encoding="utf-8")
    (workspace / "README.md").write_text("changed\n", encoding="utf-8")

    files_changed = RUNNER._capture_model_diff(workspace, output)

    assert files_changed == 2
    assert "README.md" in (output / "files-changed.txt").read_text(encoding="utf-8")
    assert "electron/package.json" in (output / "files-changed.txt").read_text(
        encoding="utf-8"
    )
    assert "2 files changed" in (output / "diff-stat.txt").read_text(encoding="utf-8")
    index = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=workspace,
        check=True,
        text=True,
        capture_output=True,
    )
    assert index.stdout == ""


def test_run_to_file_accepts_stdin_text(tmp_path: Path) -> None:
    output = tmp_path / "agent.log"
    exit_code = RUNNER._run_to_file(
        [sys.executable, "-c", "import sys; print(sys.stdin.read())"],
        cwd=tmp_path,
        output_path=output,
        stdin_text="prompt text",
    )

    assert exit_code == 0
    assert output.read_text(encoding="utf-8") == "prompt text\n"


def test_run_to_file_kills_timed_out_process(tmp_path: Path) -> None:
    output = tmp_path / "agent.log"
    marker = tmp_path / "marker.txt"
    code = (
        "import pathlib, sys, time; "
        "time.sleep(0.5); "
        "pathlib.Path(sys.argv[1]).write_text('survived', encoding='utf-8')"
    )

    exit_code = RUNNER._run_to_file(
        [sys.executable, "-c", code, str(marker)],
        cwd=tmp_path,
        output_path=output,
        timeout_s=0.05,
    )
    time.sleep(0.6)

    assert exit_code == 124
    assert not marker.exists()
    assert "[benchpack] timeout after 0.05s" in output.read_text(encoding="utf-8")


def test_clone_source_refuses_existing_paths_without_force(tmp_path: Path) -> None:
    source = tmp_path / "source"
    _init_source_repo(source)
    output = tmp_path / "results"
    target = tmp_path / "target"
    output.mkdir()
    target.mkdir()
    (output / "keep.txt").write_text("old result\n", encoding="utf-8")
    (target / "keep.txt").write_text("old target\n", encoding="utf-8")
    args = SimpleNamespace(output=output, target=target, source=source, force=False)

    try:
        RUNNER._clone_source(args)
    except SystemExit as exc:
        assert "output or target already exists" in str(exc)
    else:  # pragma: no cover - defensive; existing paths should fail.
        raise AssertionError("expected existing paths to fail without --force")

    assert (output / "keep.txt").read_text(encoding="utf-8") == "old result\n"
    assert (target / "keep.txt").read_text(encoding="utf-8") == "old target\n"


def test_clone_source_force_replaces_existing_paths(tmp_path: Path) -> None:
    source = tmp_path / "source"
    _init_source_repo(source)
    output = tmp_path / "results"
    target = tmp_path / "target"
    output.mkdir()
    target.mkdir()
    (output / "old.txt").write_text("old result\n", encoding="utf-8")
    (target / "old.txt").write_text("old target\n", encoding="utf-8")
    args = SimpleNamespace(output=output, target=target, source=source, force=True)

    RUNNER._clone_source(args)

    assert output.is_dir()
    assert not (output / "old.txt").exists()
    assert (target / "README.md").read_text(encoding="utf-8") == "source\n"
    assert not (target / "old.txt").exists()


def test_clone_failure_removes_empty_output_dir(tmp_path: Path) -> None:
    args = SimpleNamespace(
        output=tmp_path / "results" / "failed-clone",
        target=tmp_path / "target",
        source=tmp_path / "missing-source",
        force=False,
    )

    try:
        RUNNER._clone_source(args)
    except SystemExit as exc:
        assert "git clone failed" in str(exc)
    else:  # pragma: no cover - defensive; git clone should fail for missing source.
        raise AssertionError("expected clone failure")

    assert not args.output.exists()
    assert not args.target.exists()
