"""Tests for the tmux-assisted benchmark matrix helper."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "benchpack-tmux-matrix"


def _run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        check=False,
        text=True,
        capture_output=True,
    )


def test_dry_run_generates_default_matrix_commands() -> None:
    result = _run_script(
        "--dry-run",
        "--session-name",
        "bench-test",
        "--adapter",
        "openai-chat",
        "--model",
        "<model>",
        "--endpoint",
        "<endpoint>",
        "--host-label-prefix",
        "m5-max-llama-<stamp>",
        "--run-metadata",
        "metadata/m5-llama-server.json",
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert result.stdout.splitlines()[0] == "# benchpack-tmux-matrix dry run"
    assert "# session: bench-test" in result.stdout
    assert "# pack-set:" not in result.stdout
    assert "tmux new-session -d -s bench-test -n smoke" in result.stdout
    assert "tmux new-window -t bench-test -n runtime" in result.stdout
    assert "tmux new-window -t bench-test -n wrap" in result.stdout
    assert "tmux new-window -t bench-test -n patch" in result.stdout
    assert "'/bin/sh -c " in result.stdout
    assert "tmux wait-for -S bench-test-001" in result.stdout
    assert "tmux wait-for bench-test-001" in result.stdout
    assert "tmux set-environment -t bench-test BENCHPACK_MATRIX_FAILED" in result.stdout
    assert "tmux show-environment -t bench-test BENCHPACK_MATRIX_FAILED" in result.stdout
    assert "signaling later benchmark windows to skip after failure" in result.stdout
    assert "benchpack run skipped for %s because earlier window failed" in result.stdout
    assert "attach: tmux attach-session -t bench-test" in result.stdout
    assert "--force" not in result.stdout
    assert "--openai-stream-usage" not in result.stdout
    assert "--openai-api-key-env" not in result.stdout

    benchpack_lines = [
        line for line in result.stdout.splitlines() if line.startswith("benchpack: ")
    ]
    assert [line.split()[5] for line in benchpack_lines] == [
        "smoke-chat",
        "runtime-sweep",
        "desktop-django-wrap",
        "patch-from-failure",
    ]
    assert all("--endpoint '<endpoint>'" in line for line in benchpack_lines)


def test_dry_run_requires_run_metadata() -> None:
    result = _run_script(
        "--dry-run",
        "--adapter",
        "openai-chat",
        "--model",
        "<model>",
        "--host-label-prefix",
        "m5-max-llama-<stamp>",
    )

    assert result.returncode == 2
    assert "--run-metadata" in result.stderr
    assert result.stdout == ""


def test_dry_run_propagates_metadata_to_each_benchpack_run() -> None:
    result = _run_script(
        "--dry-run",
        "--adapter",
        "openai-chat",
        "--model",
        "<model>",
        "--host-label-prefix",
        "m5-max-llama-<stamp>",
        "--run-metadata",
        "<metadata-file>",
    )

    assert result.returncode == 0, result.stderr
    benchpack_lines = [
        line for line in result.stdout.splitlines() if line.startswith("benchpack: ")
    ]
    assert len(benchpack_lines) == 4
    assert all("--run-metadata '<metadata-file>'" in line for line in benchpack_lines)
    assert all("--endpoint" not in line for line in benchpack_lines)


def test_dry_run_passes_openai_api_key_env_name_without_reading_value() -> None:
    secret_value = "test-token-value-that-must-not-render"
    env_name = "BENCHPACK_TEST_REMOTE_OPENAI_TOKEN"
    old_value = os.environ.get(env_name)
    os.environ[env_name] = secret_value
    try:
        result = _run_script(
            "--dry-run",
            "--adapter",
            "openai-chat",
            "--model",
            "<model>",
            "--endpoint",
            "<endpoint>",
            "--host-label-prefix",
            "hetzner-gemma4-<stamp>",
            "--run-metadata",
            "<metadata-file>",
            "--openai-api-key-env",
            env_name,
        )
    finally:
        if old_value is None:
            os.environ.pop(env_name, None)
        else:
            os.environ[env_name] = old_value

    assert result.returncode == 0, result.stderr
    benchpack_lines = [
        line for line in result.stdout.splitlines() if line.startswith("benchpack: ")
    ]
    assert len(benchpack_lines) == 4
    assert all(f"--openai-api-key-env {env_name}" in line for line in benchpack_lines)
    assert all(
        f"--run-metadata '<metadata-file>' --openai-api-key-env {env_name}" in line
        for line in benchpack_lines
    )
    assert secret_value not in result.stdout
    assert secret_value not in result.stderr


def test_dry_run_maps_default_pack_suffixes_to_host_labels() -> None:
    result = _run_script(
        "--dry-run",
        "--adapter",
        "openai-chat",
        "--model",
        "<model>",
        "--host-label-prefix",
        "m5-max-llama-<stamp>",
        "--run-metadata",
        "<metadata-file>",
    )

    assert result.returncode == 0, result.stderr
    assert "--host-label 'm5-max-llama-<stamp>-smoke'" in result.stdout
    assert "--host-label 'm5-max-llama-<stamp>-runtime'" in result.stdout
    assert "--host-label 'm5-max-llama-<stamp>-wrap'" in result.stdout
    assert "--host-label 'm5-max-llama-<stamp>-patch'" in result.stdout


def test_dry_run_pack_set_coding_tasks_generates_repo_task_commands() -> None:
    result = _run_script(
        "--dry-run",
        "--pack-set",
        "coding-tasks",
        "--session-name",
        "bench-coding",
        "--adapter",
        "openai-chat",
        "--model",
        "<model>",
        "--endpoint",
        "<endpoint>",
        "--host-label-prefix",
        "m5-max-coding-<stamp>",
        "--run-metadata",
        "<metadata-file>",
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert "# pack-set: coding-tasks" in result.stdout
    benchpack_lines = [
        line for line in result.stdout.splitlines() if line.startswith("benchpack: ")
    ]
    assert [line.split()[5] for line in benchpack_lines] == [
        "patch-from-failure",
        "python-regression-fix",
        "django-dashboard-regression-fix",
    ]
    assert "benchpack run smoke-chat" not in result.stdout
    assert "benchpack run runtime-sweep" not in result.stdout
    assert "benchpack run desktop-django-wrap" not in result.stdout
    assert "tmux new-session -d -s bench-coding -n patch" in result.stdout
    assert "tmux new-window -t bench-coding -n python-regression" in result.stdout
    assert "tmux new-window -t bench-coding -n dashboard-regression" in result.stdout
    assert "'/bin/sh -c " in result.stdout


def test_dry_run_pack_set_coding_tasks_external_agent_is_explicit() -> None:
    result = _run_script(
        "--dry-run",
        "--pack-set",
        "coding-tasks-external-agent",
        "--session-name",
        "bench-coding-agent",
        "--adapter",
        "ollama-generate",
        "--model",
        "<model>",
        "--host-label-prefix",
        "m5-max-coding-agent-<stamp>",
        "--run-metadata",
        "<metadata-file>",
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert "# pack-set: coding-tasks-external-agent" in result.stdout
    benchpack_lines = [
        line for line in result.stdout.splitlines() if line.startswith("benchpack: ")
    ]
    assert [line.split()[5] for line in benchpack_lines] == [
        "patch-from-failure-external-agent",
        "python-regression-fix-external-agent",
        "django-dashboard-regression-fix-external-agent",
    ]
    assert "benchpack run patch-from-failure " not in result.stdout
    assert "benchpack run python-regression-fix " not in result.stdout
    assert "benchpack run django-dashboard-regression-fix " not in result.stdout
    assert (
        "tmux new-session -d -s bench-coding-agent -n patch-external-agent"
        in result.stdout
    )
    assert (
        "tmux new-window -t bench-coding-agent -n "
        "python-regression-external-agent"
        in result.stdout
    )
    assert (
        "tmux new-window -t bench-coding-agent -n "
        "dashboard-regression-external-agent"
        in result.stdout
    )
    assert (
        "--host-label 'm5-max-coding-agent-<stamp>-patch-external-agent'"
        in result.stdout
    )
    assert (
        "--host-label 'm5-max-coding-agent-<stamp>-python-regression-external-agent'"
        in result.stdout
    )
    assert (
        "--host-label 'm5-max-coding-agent-<stamp>-dashboard-regression-external-agent'"
        in result.stdout
    )


def test_dry_run_pack_set_coding_tasks_uses_stable_host_label_suffixes() -> None:
    result = _run_script(
        "--dry-run",
        "--pack-set",
        "coding-tasks",
        "--adapter",
        "openai-chat",
        "--model",
        "<model>",
        "--host-label-prefix",
        "m5-max-coding-<stamp>",
        "--run-metadata",
        "<metadata-file>",
    )

    assert result.returncode == 0, result.stderr
    assert "--host-label 'm5-max-coding-<stamp>-patch'" in result.stdout
    assert "--host-label 'm5-max-coding-<stamp>-python-regression'" in result.stdout
    assert "--host-label 'm5-max-coding-<stamp>-dashboard-regression'" in result.stdout
    assert "# host-label: m5-max-coding-<stamp>-patch" in result.stdout
    assert "# host-label: m5-max-coding-<stamp>-python-regression" in result.stdout
    assert "# host-label: m5-max-coding-<stamp>-dashboard-regression" in result.stdout


def test_dry_run_pack_set_coding_tasks_passes_existing_options_to_each_pack() -> None:
    env_name = "BENCHPACK_TEST_REMOTE_OPENAI_TOKEN"
    result = _run_script(
        "--dry-run",
        "--pack-set",
        "coding-tasks",
        "--adapter",
        "openai-chat",
        "--model",
        "<model>",
        "--endpoint",
        "<endpoint>",
        "--host-label-prefix",
        "m5-max-coding-<stamp>",
        "--run-metadata",
        "<metadata-file>",
        "--openai-stream-usage",
        "omit",
        "--openai-api-key-env",
        env_name,
        "--force",
    )

    assert result.returncode == 0, result.stderr
    benchpack_lines = [
        line for line in result.stdout.splitlines() if line.startswith("benchpack: ")
    ]
    assert len(benchpack_lines) == 3
    assert all("--endpoint '<endpoint>'" in line for line in benchpack_lines)
    assert all("--run-metadata '<metadata-file>'" in line for line in benchpack_lines)
    assert all("--openai-stream-usage omit" in line for line in benchpack_lines)
    assert all(f"--openai-api-key-env {env_name}" in line for line in benchpack_lines)
    assert all(line.endswith("--force") for line in benchpack_lines)


def test_pack_set_rejects_positional_packs_before_dry_run_commands() -> None:
    result = _run_script(
        "--dry-run",
        "--pack-set",
        "coding-tasks",
        "--adapter",
        "openai-chat",
        "--model",
        "<model>",
        "--host-label-prefix",
        "m5-max-coding-<stamp>",
        "--run-metadata",
        "<metadata-file>",
        "custom-pack",
    )

    assert result.returncode == 2
    assert "positional packs cannot be combined with --pack-set" in result.stderr
    assert result.stdout == ""


def test_dry_run_accepts_optional_force_stream_usage_and_custom_packs() -> None:
    env_name = "BENCHPACK_TEST_REMOTE_OPENAI_TOKEN"
    result = _run_script(
        "--dry-run",
        "--session-name",
        "bench-custom",
        "--adapter",
        "openai-chat",
        "--model",
        "<model>",
        "--host-label-prefix",
        "m4-max-llama-<stamp>",
        "--run-metadata",
        "<metadata-file>",
        "--openai-stream-usage",
        "omit",
        "--openai-api-key-env",
        env_name,
        "--force",
        "runtime-sweep",
        "custom-pack",
    )

    assert result.returncode == 0, result.stderr
    benchpack_lines = [
        line for line in result.stdout.splitlines() if line.startswith("benchpack: ")
    ]
    assert benchpack_lines == [
        "benchpack: uv run benchpack run runtime-sweep --adapter openai-chat "
        "--model '<model>' --host-label 'm4-max-llama-<stamp>-runtime' "
        "--run-metadata '<metadata-file>' --openai-stream-usage omit "
        f"--openai-api-key-env {env_name} --force",
        "benchpack: uv run benchpack run custom-pack --adapter openai-chat "
        "--model '<model>' --host-label 'm4-max-llama-<stamp>-custom-pack' "
        "--run-metadata '<metadata-file>' --openai-stream-usage omit "
        f"--openai-api-key-env {env_name} --force",
    ]
    assert "tmux new-session -d -s bench-custom -n runtime" in result.stdout
    assert "tmux new-window -t bench-custom -n custom-pack" in result.stdout


def test_launch_rejects_missing_run_metadata_before_tmux(tmp_path: Path) -> None:
    result = _run_script(
        "--session-name",
        "bench-test",
        "--adapter",
        "openai-chat",
        "--model",
        "<model>",
        "--host-label-prefix",
        "m5-max-llama-<stamp>",
        "--run-metadata",
        str(tmp_path / "missing.json"),
    )

    assert result.returncode == 1
    assert "run metadata file not found" in result.stderr
    assert result.stdout == ""
