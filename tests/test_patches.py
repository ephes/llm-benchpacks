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
        "diff --git a/added.txt b/added.txt\n"
        "new file mode 100644\n"
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
        "diff --git a/deleted.txt b/deleted.txt\n"
        "deleted file mode 100644\n"
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
        "diff --git a/subdir/foo.txt b/subdir/foo.txt\n"
        "new file mode 100644\n"
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
        "diff --git a/link.txt b/link.txt\n"
        "old mode 120000\n"
        "new mode 120000\n"
        "--- a/link.txt\n"
        "+++ b/link.txt\n"
        "@@ -1 +1 @@\n"
        "-old.txt\n"
        "\\ No newline at end of file\n"
        "+new.txt\n"
        "\\ No newline at end of file\n"
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
        "diff --git a/added-link.txt b/added-link.txt\n"
        "new file mode 120000\n"
        "--- /dev/null\n"
        "+++ b/added-link.txt\n"
        "@@ -0,0 +1 @@\n"
        "+added.txt\n"
        "\\ No newline at end of file\n"
        "diff --git a/deleted-link.txt b/deleted-link.txt\n"
        "deleted file mode 120000\n"
        "--- a/deleted-link.txt\n"
        "+++ /dev/null\n"
        "@@ -1 +0,0 @@\n"
        "-deleted.txt\n"
        "\\ No newline at end of file\n"
    )


@pytest.mark.parametrize(('before', 'after'), [
    (b'hello\n', b'hello'), (b'hello', b'hello\n'),
    (b'hello\r\n', b'hello\n'), (b'old\r\n', b'new\r\n'),
    (b'hello\r', b'hello'),
])
def test_patch_replays_exact_line_endings(tmp_path: Path, before: bytes, after: bytes) -> None:
    import subprocess
    source, workspace = tmp_path / 'source', tmp_path / 'workspace'
    source.mkdir()
    workspace.mkdir()
    (source / 'file.txt').write_bytes(before)
    (workspace / 'file.txt').write_bytes(after)
    patch = directory_diff(source, workspace)
    assert patch
    subprocess.run(['git', 'apply', '-'], input=patch.encode(), cwd=source, check=True)
    assert (source / 'file.txt').read_bytes() == after


@pytest.mark.parametrize(('old_mode', 'new_mode'), [(0o644, 0o755), (0o755, 0o644)])
@pytest.mark.parametrize('edit_content', [False, True])
def test_patch_replays_executable_mode(tmp_path: Path, old_mode: int, new_mode: int, edit_content: bool) -> None:
    import subprocess
    source, workspace = tmp_path / 'source', tmp_path / 'workspace'
    source.mkdir()
    workspace.mkdir()
    (source / 'script').write_bytes(b'old\n')
    (source / 'script').chmod(old_mode)
    expected = b'new' if edit_content else b'old\n'
    (workspace / 'script').write_bytes(expected)
    (workspace / 'script').chmod(new_mode)
    patch = directory_diff(source, workspace)
    assert f'old mode {old_mode | 0o100000:o}' in patch
    subprocess.run(['git', 'apply', '-'], input=patch.encode(), cwd=source, check=True)
    assert (source / 'script').stat().st_mode & 0o777 == new_mode
    assert (source / 'script').read_bytes() == expected


@pytest.mark.parametrize('content', [b'', b'echo hello', b'echo hello\r\n'])
@pytest.mark.parametrize('mode', [0o644, 0o755])
@pytest.mark.parametrize('delete', [False, True])
def test_patch_replays_file_creation_deletion(tmp_path: Path, content: bytes, mode: int, delete: bool) -> None:
    import subprocess
    source, workspace = tmp_path / 'source', tmp_path / 'workspace'
    source.mkdir()
    workspace.mkdir()
    original = (source if delete else workspace) / 'script'
    original.write_bytes(content)
    original.chmod(mode)
    patch = directory_diff(source, workspace)
    subprocess.run(['git', 'apply', '-'], input=patch.encode(), cwd=source, check=True)
    result = source / 'script'
    if delete:
        assert not result.exists()
    else:
        assert result.read_bytes() == content
        assert result.stat().st_mode & 0o777 == mode


@pytest.mark.parametrize('empty_addition', [False, True])
def test_patch_replays_multiple_files(tmp_path: Path, empty_addition: bool) -> None:
    import subprocess
    source, workspace = tmp_path / 'source', tmp_path / 'workspace'
    source.mkdir()
    workspace.mkdir()
    if empty_addition:
        (workspace / 'a').write_bytes(b'')
    else:
        (source / 'a').write_bytes(b'script\n')
        (workspace / 'a').write_bytes(b'script\n')
        (source / 'a').chmod(0o644)
        (workspace / 'a').chmod(0o755)
    (source / 'b').write_bytes(b'old\n')
    (workspace / 'b').write_bytes(b'new\n')
    subprocess.run(['git', 'apply', '-'], input=directory_diff(source, workspace).encode(), cwd=source, check=True)
    for name in ['a', 'b']:
        assert (source / name).read_bytes() == (workspace / name).read_bytes()
        assert (source / name).stat().st_mode & 0o777 == (workspace / name).stat().st_mode & 0o777


@pytest.mark.parametrize('operation', ['change', 'add', 'delete', 'file-to-link', 'link-to-file'])
def test_captured_mixed_symlink_patch_replays(tmp_path: Path, operation: str) -> None:
    import os
    import shutil
    import subprocess
    from benchpack.tasks import apply_unified_diff_to_workspace

    source, workspace, replay = (tmp_path / name for name in ('source', 'workspace', 'replay'))
    source.mkdir()
    (source / 'regular').write_bytes(b'old\r\n')
    if operation == 'file-to-link':
        (source / 'link').write_bytes(b'old file')
    elif operation != 'add':
        os.symlink('./missing//old', source / 'link')
    shutil.copytree(source, workspace, symlinks=True)
    shutil.copytree(source, replay, symlinks=True)
    (workspace / 'regular').write_bytes(b'new')
    (workspace / 'regular').chmod(0o755)
    if operation != 'add':
        (workspace / 'link').unlink()
    if operation == 'link-to-file':
        (workspace / 'link').write_bytes(b'new file')
        (workspace / 'link').chmod(0o755)
    elif operation != 'delete':
        os.symlink('./missing//new', workspace / 'link')

    prepared = PreparedWorkspace(source_fixture=make_fixture(source), path=workspace)
    record = capture_workspace_patch(prepared, tmp_path / 'run', make_case(), 1)
    patch = (tmp_path / 'run' / record['path']).read_bytes().decode('utf-8')
    subprocess.run(['git', 'apply', '-'], input=patch.encode(), cwd=source, check=True)
    applied, _, stderr = apply_unified_diff_to_workspace(patch, replay)
    assert applied, stderr
    for root in (source, replay):
        assert (root / 'regular').read_bytes() == b'new'
        assert (root / 'regular').stat().st_mode & 0o777 == 0o755
        if operation == 'delete':
            assert not (root / 'link').exists()
            assert not (root / 'link').is_symlink()
        elif operation == 'link-to-file':
            assert not (root / 'link').is_symlink()
            assert (root / 'link').read_bytes() == b'new file'
            assert (root / 'link').stat().st_mode & 0o777 == 0o755
        else:
            assert (root / 'link').is_symlink()
            assert os.readlink(root / 'link') == './missing//new'
