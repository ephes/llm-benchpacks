"""Tests for the tmux-assisted benchmark matrix helper."""

from __future__ import annotations

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

    benchpack_lines = [
        line for line in result.stdout.splitlines() if line.startswith("benchpack: ")
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


def test_dry_run_accepts_optional_force_stream_usage_and_custom_packs() -> None:
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
        "--run-metadata '<metadata-file>' --openai-stream-usage omit --force",
        "benchpack: uv run benchpack run custom-pack --adapter openai-chat "
        "--model '<model>' --host-label 'm4-max-llama-<stamp>-custom-pack' "
        "--run-metadata '<metadata-file>' --openai-stream-usage omit --force",
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
