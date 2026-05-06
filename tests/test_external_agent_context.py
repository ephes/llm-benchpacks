"""Tests for runner-owned external-agent context files."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchpack.adapters.openai_chat import OPENAI_STREAM_USAGE_KEY
from benchpack.external_agent_context import (
    ExternalAgentContextError,
    build_external_agent_context,
    external_agent_context_path,
    write_external_agent_context,
)
from benchpack.packs import load_pack
from benchpack.tasks import task_artifact_paths
from benchpack.workspaces import PreparedWorkspace, prepare_repo_task_workspace


def test_external_agent_context_contents_and_path_are_deterministic(
    tmp_path: Path,
) -> None:
    pack_dir = tmp_path / "pack"
    repo_dir = pack_dir / "fixtures" / "repo"
    repo_dir.mkdir(parents=True)
    (repo_dir / "README.md").write_text("source repo\n", encoding="utf-8")
    (pack_dir / "fixtures" / "notes.md").write_text(
        "fixture prompt text\n",
        encoding="utf-8",
    )
    (pack_dir / "benchpack.toml").write_text(
        """
[pack]
id = "context-pack"
version = "0.1.0"
description = "Context handoff pack"

[defaults]
temperature = 0
max_tokens = 32
stream = true

[[fixtures]]
id = "notes"
kind = "context"
path = "fixtures/notes.md"
description = "Prompt notes"

[[fixtures]]
id = "repo"
kind = "repo"
path = "fixtures/repo"
description = "Source repo"

[[cases]]
id = "edit-repo"
kind = "repo-task"
prompt = "Change the repository."
fixture_refs = ["notes", "repo"]
harness = { id = "external-agent", timeout_s = 120 }
""",
        encoding="utf-8",
    )
    pack = load_pack(pack_dir)
    case = pack.cases[0]
    out = tmp_path / "run"
    prepared = prepare_repo_task_workspace(pack, case, out, 2)
    task_paths = task_artifact_paths(out, case, 2)
    run_metadata_path = out / "run-metadata.json"
    original_pack_defaults = dict(pack.defaults)
    defaults = {
        "temperature": 0,
        "max_tokens": 32,
        "stream": True,
        OPENAI_STREAM_USAGE_KEY: "omit",
    }
    original_defaults = dict(defaults)

    context_path = external_agent_context_path(out, case, 2)
    context = build_external_agent_context(
        pack=pack,
        case=case,
        prepared_workspace=prepared,
        output_dir=out,
        repetition=2,
        task_paths=task_paths,
        adapter_id="openai-chat",
        model="test-model",
        endpoint="http://example.test/v1",
        adapter_defaults=defaults,
        run_metadata_path=run_metadata_path,
    )
    assert pack.defaults == original_pack_defaults
    defaults["temperature"] = 1
    written = write_external_agent_context(context_path, context)

    assert written == out / "task" / "edit-repo" / "rep-002.context.json"
    loaded = json.loads(written.read_text(encoding="utf-8"))
    assert loaded["version"] == 1
    assert loaded["pack"] == {
        "id": "context-pack",
        "version": "0.1.0",
        "description": "Context handoff pack",
    }
    assert loaded["case"]["id"] == "edit-repo"
    assert loaded["case"]["kind"] == "repo-task"
    assert loaded["case"]["fixture_refs"] == ["notes", "repo"]
    assert loaded["case"]["harness"] == {
        "id": "external-agent",
        "timeout_s": 120.0,
    }
    assert loaded["case"]["prompt"] == (
        "Change the repository.\n\n"
        "--- BEGIN FIXTURE notes (context, fixtures/notes.md) ---\n"
        "fixture prompt text\n"
        "--- END FIXTURE notes ---"
    )
    assert loaded["workspace"] == {
        "path": str((out / "workspace" / "edit-repo" / "rep-002").resolve()),
        "source_fixture_id": "repo",
        "source_path": "fixtures/repo",
    }
    assert loaded["run"] == {
        "output_dir": str(out.resolve()),
        "repetition": 2,
        "task_stdout_path": str(
            (out / "task" / "edit-repo" / "rep-002.stdout.log").resolve()
        ),
        "task_stderr_path": str(
            (out / "task" / "edit-repo" / "rep-002.stderr.log").resolve()
        ),
        "run_metadata_path": str(run_metadata_path.resolve()),
    }
    assert loaded["adapter"] == {
        "id": "openai-chat",
        "model": "test-model",
        "endpoint": "http://example.test/v1",
        "defaults": original_defaults,
    }
    assert loaded["fixtures"] == [
        {
            "id": "notes",
            "kind": "context",
            "path": "fixtures/notes.md",
            "description": "Prompt notes",
        },
        {
            "id": "repo",
            "kind": "repo",
            "path": "fixtures/repo",
            "description": "Source repo",
        },
    ]


def test_external_agent_context_handles_absent_run_metadata_path(
    tmp_path: Path,
) -> None:
    pack_dir = tmp_path / "pack"
    repo_dir = pack_dir / "fixtures" / "repo"
    repo_dir.mkdir(parents=True)
    (repo_dir / "README.md").write_text("source repo\n", encoding="utf-8")
    (pack_dir / "benchpack.toml").write_text(
        """
[pack]
id = "context-pack"
version = "0.1.0"

[[fixtures]]
id = "repo"
kind = "repo"
path = "fixtures/repo"

[[cases]]
id = "edit-repo"
kind = "repo-task"
prompt = "Change the repository."
fixture_refs = ["repo"]
harness = { id = "external-agent" }
""",
        encoding="utf-8",
    )
    pack = load_pack(pack_dir)
    case = pack.cases[0]
    out = tmp_path / "run"
    prepared = prepare_repo_task_workspace(pack, case, out, 1)

    context = build_external_agent_context(
        pack=pack,
        case=case,
        prepared_workspace=prepared,
        output_dir=out,
        repetition=1,
        task_paths=task_artifact_paths(out, case, 1),
        adapter_id="openai-chat",
        model="test-model",
        endpoint=None,
        adapter_defaults={},
        run_metadata_path=None,
    )

    assert context["run"]["run_metadata_path"] is None


def test_external_agent_context_missing_workspace_failure_is_clear(
    tmp_path: Path,
) -> None:
    pack_dir = tmp_path / "pack"
    pack_dir.mkdir()
    pack = load_pack(
        _write_minimal_context_pack(
            pack_dir,
            harness='harness = { id = "external-agent" }',
        )
    )
    case = pack.cases[0]
    fixture = pack.fixtures[0]
    missing_workspace = tmp_path / "missing-workspace"
    prepared = PreparedWorkspace(source_fixture=fixture, path=missing_workspace)

    with pytest.raises(ExternalAgentContextError, match="workspace path"):
        build_external_agent_context(
            pack=pack,
            case=case,
            prepared_workspace=prepared,
            output_dir=tmp_path / "run",
            repetition=1,
            task_paths=task_artifact_paths(tmp_path / "run", case, 1),
            adapter_id="openai-chat",
            model="test-model",
            endpoint=None,
            adapter_defaults={},
            run_metadata_path=None,
        )


def test_external_agent_context_write_failure_is_clear(tmp_path: Path) -> None:
    with pytest.raises(ExternalAgentContextError, match="could not write"):
        write_external_agent_context(
            tmp_path / "context.json",
            {"bad": object()},
        )


def _write_minimal_context_pack(pack_dir: Path, *, harness: str) -> Path:
    repo_dir = pack_dir / "fixtures" / "repo"
    repo_dir.mkdir(parents=True)
    (repo_dir / "README.md").write_text("source repo\n", encoding="utf-8")
    (pack_dir / "benchpack.toml").write_text(
        f"""
[pack]
id = "context-pack"
version = "0.1.0"

[[fixtures]]
id = "repo"
kind = "repo"
path = "fixtures/repo"

[[cases]]
id = "edit-repo"
kind = "repo-task"
prompt = "Change the repository."
fixture_refs = ["repo"]
{harness}
""",
        encoding="utf-8",
    )
    return pack_dir
