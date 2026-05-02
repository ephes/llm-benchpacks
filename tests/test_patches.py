"""Tests for deterministic repo-task patch helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from benchpack.packs import Case, Fixture
from benchpack.patches import (
    capture_workspace_patch,
    directory_diff,
    patch_path,
)
from benchpack.workspaces import PreparedWorkspace


def make_case() -> Case:
    return Case(
        id="edit-repo",
        kind="repo-task",
        prompt="Change the repository.",
        scoring=None,
        raw={},
    )


def make_fixture(source: Path) -> Fixture:
    return Fixture(
        id="repo",
        kind="repo",
        path=source,
        description="",
        raw={"id": "repo", "kind": "repo", "path": "fixtures/repo"},
    )


def test_patch_path_uses_run_relative_layout(tmp_path: Path) -> None:
    assert patch_path(tmp_path / "run", make_case(), 1) == (
        tmp_path / "run" / "patch" / "edit-repo" / "rep-001.diff"
    )


@pytest.mark.parametrize("repetition", [0, -1, True, "1"])
def test_patch_path_rejects_invalid_repetition(
    tmp_path: Path,
    repetition: object,
) -> None:
    with pytest.raises(ValueError, match="repetition"):
        patch_path(tmp_path / "run", make_case(), repetition)  # type: ignore[arg-type]


def test_capture_workspace_patch_writes_empty_diff_for_no_changes(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    workspace = tmp_path / "run" / "workspace" / "edit-repo" / "rep-001"
    source.mkdir()
    workspace.mkdir(parents=True)
    (source / "README.md").write_text("same\n", encoding="utf-8")
    (workspace / "README.md").write_text("same\n", encoding="utf-8")
    prepared = PreparedWorkspace(source_fixture=make_fixture(source), path=workspace)

    record = capture_workspace_patch(prepared, tmp_path / "run", make_case(), 1)

    assert record == {"path": "patch/edit-repo/rep-001.diff"}
    assert (tmp_path / "run" / record["path"]).read_text(encoding="utf-8") == ""


def test_directory_diff_modified_text_file_is_unified_diff(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    workspace = tmp_path / "workspace"
    source.mkdir()
    workspace.mkdir()
    (source / "README.md").write_text("old\nshared\n", encoding="utf-8")
    (workspace / "README.md").write_text("new\nshared\n", encoding="utf-8")

    diff = directory_diff(source, workspace)

    assert "--- a/README.md\n" in diff
    assert "+++ b/README.md\n" in diff
    assert "-old\n" in diff
    assert "+new\n" in diff


def test_directory_diff_added_text_file_uses_dev_null(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    workspace = tmp_path / "workspace"
    source.mkdir()
    workspace.mkdir()
    (workspace / "added.txt").write_text("added\n", encoding="utf-8")

    assert directory_diff(source, workspace) == (
        "--- /dev/null\n"
        "+++ b/added.txt\n"
        "@@ -0,0 +1 @@\n"
        "+added\n"
    )


def test_directory_diff_deleted_text_file_uses_dev_null(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    workspace = tmp_path / "workspace"
    source.mkdir()
    workspace.mkdir()
    (source / "deleted.txt").write_text("deleted\n", encoding="utf-8")

    assert directory_diff(source, workspace) == (
        "--- a/deleted.txt\n"
        "+++ /dev/null\n"
        "@@ -1 +0,0 @@\n"
        "-deleted\n"
    )


def test_directory_diff_orders_paths_deterministically(tmp_path: Path) -> None:
    source = tmp_path / "source"
    workspace = tmp_path / "workspace"
    source.mkdir()
    workspace.mkdir()
    (source / "b.txt").write_text("old b\n", encoding="utf-8")
    (source / "a.txt").write_text("old a\n", encoding="utf-8")
    (workspace / "b.txt").write_text("new b\n", encoding="utf-8")
    (workspace / "a.txt").write_text("new a\n", encoding="utf-8")

    diff = directory_diff(source, workspace)

    assert diff.index("--- a/a.txt") < diff.index("--- a/b.txt")


def test_directory_diff_preserves_nested_posix_paths(tmp_path: Path) -> None:
    source = tmp_path / "source"
    workspace = tmp_path / "workspace"
    source.mkdir()
    (workspace / "subdir").mkdir(parents=True)
    (workspace / "subdir" / "foo.txt").write_text("nested\n", encoding="utf-8")

    assert directory_diff(source, workspace) == (
        "--- /dev/null\n"
        "+++ b/subdir/foo.txt\n"
        "@@ -0,0 +1 @@\n"
        "+nested\n"
    )


def test_directory_diff_binary_fallback_is_deterministic(tmp_path: Path) -> None:
    source = tmp_path / "source"
    workspace = tmp_path / "workspace"
    source.mkdir()
    workspace.mkdir()
    (source / "image.bin").write_bytes(b"\xffold")
    (workspace / "image.bin").write_bytes(b"\xffnew")

    assert directory_diff(source, workspace) == "Binary files differ: image.bin\n"


def test_directory_diff_binary_added_and_deleted_markers_are_deterministic(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    workspace = tmp_path / "workspace"
    source.mkdir()
    workspace.mkdir()
    (source / "deleted.bin").write_bytes(b"\xffdeleted")
    (workspace / "added.bin").write_bytes(b"\xffadded")

    assert directory_diff(source, workspace) == (
        "Binary file added: added.bin\n"
        "Binary file deleted: deleted.bin\n"
    )


def test_directory_diff_symlink_target_change_is_text_diff(tmp_path: Path) -> None:
    source = tmp_path / "source"
    workspace = tmp_path / "workspace"
    source.mkdir()
    workspace.mkdir()
    try:
        (source / "link.txt").symlink_to("old.txt")
        (workspace / "link.txt").symlink_to("new.txt")
    except OSError as exc:
        pytest.skip(f"symlinks cannot be created on this filesystem: {exc}")

    assert directory_diff(source, workspace) == (
        "--- a/link.txt\n"
        "+++ b/link.txt\n"
        "@@ -1 +1 @@\n"
        "-old.txt\n"
        "+new.txt\n"
    )


def test_directory_diff_symlink_added_and_deleted_use_target_text(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    workspace = tmp_path / "workspace"
    source.mkdir()
    workspace.mkdir()
    try:
        (source / "deleted-link.txt").symlink_to("deleted.txt")
        (workspace / "added-link.txt").symlink_to("added.txt")
    except OSError as exc:
        pytest.skip(f"symlinks cannot be created on this filesystem: {exc}")

    assert directory_diff(source, workspace) == (
        "--- /dev/null\n"
        "+++ b/added-link.txt\n"
        "@@ -0,0 +1 @@\n"
        "+added.txt\n"
        "--- a/deleted-link.txt\n"
        "+++ /dev/null\n"
        "@@ -1 +0,0 @@\n"
        "-deleted.txt\n"
    )
