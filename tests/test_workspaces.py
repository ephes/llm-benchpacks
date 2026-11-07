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


def _repo_task(tmp_path):
    from benchpack.packs import Case, Pack

    fixture = make_fixture(tmp_path)
    fixture.path.mkdir(parents=True)
    (fixture.path / "first.txt").write_text("source")
    case = Case(id="edit-repo", kind="repo-task", prompt="edit", scoring=None,
                raw={}, fixture_refs=["repo"])
    pack = Pack(id="test", version="1", description="", defaults={}, cases=[case],
                scoring=None, path=tmp_path / "pack", fixtures=[fixture])
    return pack, case


def test_copy_failure_leaves_reported_staging_and_allows_retry(tmp_path, monkeypatch):
    import shutil
    from benchpack.workspaces import prepare_repo_task_workspace, workspace_path

    pack, case = _repo_task(tmp_path)
    out = tmp_path / "run"
    real_copytree = shutil.copytree
    copied = []

    def fail_copy(source, destination, **kwargs):
        destination = Path(destination)
        destination.mkdir(exist_ok=kwargs.get("dirs_exist_ok", False))
        (destination / "first.txt").write_text("partial")
        copied.append(destination)
        raise OSError("injected copy failure")

    monkeypatch.setattr(shutil, "copytree", fail_copy)
    with pytest.raises(WorkspaceError) as error:
        prepare_repo_task_workspace(pack, case, out, 1)
    assert len(copied) == 1
    assert not workspace_path(out, case, 1).exists()
    assert str(copied[0]) in str(error.value)
    assert (copied[0] / "first.txt").read_text() == "partial"
    monkeypatch.setattr(shutil, "copytree", real_copytree)
    prepared = prepare_repo_task_workspace(pack, case, out, 1)
    assert (prepared.path / "first.txt").read_text() == "source"


@pytest.mark.parametrize("foreign_kind", ["empty", "file", "symlink"])
def test_concurrent_destination_is_preserved(tmp_path, monkeypatch, foreign_kind):
    import shutil
    from benchpack.workspaces import prepare_repo_task_workspace, workspace_path

    pack, case = _repo_task(tmp_path)
    out = tmp_path / "run"
    destination = workspace_path(out, case, 1)
    real_copytree = shutil.copytree
    called = []

    def concurrent_copy(source, target, **kwargs):
        result = real_copytree(source, target, **kwargs)
        if foreign_kind == "empty":
            destination.mkdir()
        elif foreign_kind == "file":
            destination.write_text("foreign")
        else:
            destination.symlink_to(tmp_path / "missing")
        called.append(True)
        return result

    monkeypatch.setattr(shutil, "copytree", concurrent_copy)
    with pytest.raises(WorkspaceError) as error:
        prepare_repo_task_workspace(pack, case, out, 1)
    assert called == [True]
    staging = list(destination.parent.glob(".rep-001-*"))
    assert len(staging) == 1
    assert str(staging[0]) in str(error.value)
    assert (staging[0] / "first.txt").read_text() == "source"
    if foreign_kind == "empty":
        assert destination.is_dir() and list(destination.iterdir()) == []
    elif foreign_kind == "file":
        assert destination.read_text() == "foreign"
    else:
        assert destination.is_symlink()


def test_preexisting_dangling_destination_is_refused(tmp_path):
    from benchpack.workspaces import prepare_repo_task_workspace, workspace_path

    pack, case = _repo_task(tmp_path)
    out = tmp_path / "run"
    destination = workspace_path(out, case, 1)
    destination.parent.mkdir(parents=True)
    destination.symlink_to(tmp_path / "missing")
    with pytest.raises(WorkspaceError, match="already exists"):
        prepare_repo_task_workspace(pack, case, out, 1)
    assert destination.is_symlink()


def test_staging_allocation_failure_is_workspace_error(tmp_path, monkeypatch):
    import benchpack.workspaces as workspaces

    pack, case = _repo_task(tmp_path)

    def fail_allocation(**kwargs):
        raise OSError("injected allocation failure")

    monkeypatch.setattr(workspaces.tempfile, "mkdtemp", fail_allocation)
    with pytest.raises(WorkspaceError, match="allocate staging") as error:
        workspaces.prepare_repo_task_workspace(pack, case, tmp_path / "run", 1)
    assert "staging retained" not in str(error.value)


def test_rename_failure_reports_and_retains_staging_and_reservation(tmp_path, monkeypatch):
    from benchpack.workspaces import prepare_repo_task_workspace, workspace_path

    pack, case = _repo_task(tmp_path)
    out = tmp_path / "run"
    staged = []

    def fail_rename(source, destination):
        staged.append(source)
        raise OSError("injected rename failure")

    monkeypatch.setattr(Path, "rename", fail_rename)
    with pytest.raises(WorkspaceError, match="reservation retained") as error:
        prepare_repo_task_workspace(pack, case, out, 1)
    assert len(staged) == 1
    assert str(staged[0]) in str(error.value)
    assert (staged[0] / "first.txt").read_text() == "source"
    destination = workspace_path(out, case, 1)
    assert str(destination) in str(error.value)
    assert destination.is_dir() and list(destination.iterdir()) == []


@pytest.mark.parametrize("mutation", ["content", "mode", "delete"])
def test_patch_uses_prepared_generation_after_source_mutation(tmp_path, monkeypatch, mutation):
    import os
    from benchpack.patches import capture_workspace_patch
    from benchpack.workspaces import prepare_repo_task_workspace

    pack, case = _repo_task(tmp_path)
    out = tmp_path / "run"
    prepared = prepare_repo_task_workspace(pack, case, out, 1)
    source = pack.fixtures[0].path / "first.txt"
    if mutation == "content":
        source.write_text("unrelated fixture change")
    elif mutation == "delete":
        source.unlink()
    else:
        original_stat = Path.stat
        def changed_mode(path, *args, **kwargs):
            result = original_stat(path, *args, **kwargs)
            if path == source:
                fields = list(result)
                fields[0] ^= 0o100
                return os.stat_result(fields)
            return result
        monkeypatch.setattr(Path, "stat", changed_mode)
    record = capture_workspace_patch(prepared, out, case, 1)
    assert (out / record["path"]).read_bytes() == b""


def test_model_patch_uses_copied_baseline_not_live_fixture(tmp_path):
    from benchpack.patches import capture_workspace_patch
    from benchpack.workspaces import prepare_repo_task_workspace

    pack, case = _repo_task(tmp_path)
    out = tmp_path / "run"
    prepared = prepare_repo_task_workspace(pack, case, out, 1)
    (pack.fixtures[0].path / "first.txt").write_text("unrelated")
    (prepared.path / "first.txt").write_text("model edit")
    record = capture_workspace_patch(prepared, out, case, 1)
    diff = (out / record["path"]).read_text()
    assert "-source\n" in diff
    assert "+model edit\n" in diff
    assert "unrelated" not in diff


def test_baseline_copy_failure_reports_retained_workspace_and_partial_baseline(tmp_path, monkeypatch):
    import shutil
    from benchpack.workspaces import prepare_repo_task_workspace, workspace_path

    pack, case = _repo_task(tmp_path)
    out = tmp_path / "run"
    destination = workspace_path(out, case, 1)
    original_copy = shutil.copytree
    def fail_baseline(source, target, **kwargs):
        if source == destination:
            Path(target).mkdir()
            (Path(target) / "partial").write_text("partial")
            raise OSError("injected baseline failure")
        return original_copy(source, target, **kwargs)
    monkeypatch.setattr(shutil, "copytree", fail_baseline)
    with pytest.raises(WorkspaceError, match="copy prepared baseline") as error:
        prepare_repo_task_workspace(pack, case, out, 1)
    baseline = out / "baseline" / case.id / "rep-001"
    assert str(destination) in str(error.value)
    assert str(baseline) in str(error.value)
    assert (baseline / "partial").read_text() == "partial"
    assert (destination / "first.txt").read_text() == "source"


def test_capture_large_synthetic_fixture_with_ordinary_code_edit(tmp_path):
    """Represent the largest shipped fixture's scale without using its data."""
    from benchpack.patches import capture_workspace_patch
    from benchpack.workspaces import prepare_repo_task_workspace

    pack, case = _repo_task(tmp_path)
    source = pack.fixtures[0].path
    # Large unchanged CSV-shaped inputs must fit alongside a 3,028-line module.
    for name, count in (("test.csv", 220_000), ("train.csv", 130_000), ("eval.csv", 40_000)):
        with (source / name).open("wb") as handle:
            for _ in range(count // 1000):
                handle.write(b"synthetic,data\n" * 1000)
    lines = [f"constant_{i} = {i}\n" for i in range(3028)]
    (source / "module.py").write_text("".join(lines))
    out = tmp_path / "run"
    prepared = prepare_repo_task_workspace(pack, case, out, 1)
    lines[1514] = "constant_1514 = -1\n"
    (prepared.path / "module.py").write_text("".join(lines))
    record = capture_workspace_patch(prepared, out, case, 1)
    diff = (out / record["path"]).read_text()
    assert "-constant_1514 = 1514\n" in diff
    assert "+constant_1514 = -1\n" in diff
    assert "test.csv" not in diff
