"""Tests for repo-task workspace helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from benchpack.packs import Fixture
from benchpack.workspaces import (
    PreparedWorkspace,
    WorkspaceError,
    workspace_record,
)


def make_fixture(tmp_path: Path) -> Fixture:
    return Fixture(
        id="repo",
        kind="repo",
        path=tmp_path / "pack" / "fixtures" / "repo",
        description="",
        raw={"id": "repo", "kind": "repo", "path": "fixtures/repo"},
    )


def test_workspace_record_uses_run_relative_path_and_manifest_source_path(
    tmp_path: Path,
) -> None:
    out = tmp_path / "run"
    prepared = PreparedWorkspace(
        source_fixture=make_fixture(tmp_path),
        path=out / "workspace" / "edit-repo" / "rep-001",
    )

    assert workspace_record(prepared, out) == {
        "path": "workspace/edit-repo/rep-001",
        "source_fixture_id": "repo",
        "source_path": "fixtures/repo",
    }


def test_workspace_record_rejects_path_outside_output_dir(tmp_path: Path) -> None:
    prepared = PreparedWorkspace(
        source_fixture=make_fixture(tmp_path),
        path=tmp_path / "other-run" / "workspace" / "edit-repo" / "rep-001",
    )

    with pytest.raises(WorkspaceError, match="not under run output directory"):
        workspace_record(prepared, tmp_path / "run")
