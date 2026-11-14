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
    import benchpack.workspaces as workspaces
    from benchpack.workspaces import prepare_repo_task_workspace, workspace_path

    pack, case = _repo_task(tmp_path)
    out = tmp_path / "run"
    real_copytree = workspaces._copy_fixture_tree
    copied = []

    def fail_copy(source, destination, **kwargs):
        destination = Path(destination)
        destination.mkdir(exist_ok=kwargs.get("dirs_exist_ok", False))
        (destination / "first.txt").write_text("partial")
        copied.append(destination)
        raise OSError("injected copy failure")

    monkeypatch.setattr(workspaces, "_copy_fixture_tree", fail_copy)
    with pytest.raises(WorkspaceError) as error:
        prepare_repo_task_workspace(pack, case, out, 1)
    assert len(copied) == 1
    assert not workspace_path(out, case, 1).exists()
    assert str(copied[0]) in str(error.value)
    assert (copied[0] / "first.txt").read_text() == "partial"
    monkeypatch.setattr(workspaces, "_copy_fixture_tree", real_copytree)
    prepared = prepare_repo_task_workspace(pack, case, out, 1)
    assert (prepared.path / "first.txt").read_text() == "source"


@pytest.mark.parametrize("foreign_kind", ["empty", "file", "symlink"])
def test_concurrent_destination_is_preserved(tmp_path, monkeypatch, foreign_kind):
    import benchpack.workspaces as workspaces
    from benchpack.workspaces import prepare_repo_task_workspace, workspace_path

    pack, case = _repo_task(tmp_path)
    out = tmp_path / "run"
    destination = workspace_path(out, case, 1)
    real_copytree = workspaces._copy_fixture_tree
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

    monkeypatch.setattr(workspaces, "_copy_fixture_tree", concurrent_copy)
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
    import benchpack.workspaces as workspaces
    from benchpack.workspaces import prepare_repo_task_workspace, workspace_path

    pack, case = _repo_task(tmp_path)
    out = tmp_path / "run"
    destination = workspace_path(out, case, 1)
    original_copy = workspaces._copy_fixture_tree
    def fail_baseline(source, target, **kwargs):
        if source == destination:
            Path(target).mkdir()
            (Path(target) / "partial").write_text("partial")
            raise OSError("injected baseline failure")
        return original_copy(source, target, **kwargs)
    monkeypatch.setattr(workspaces, "_copy_fixture_tree", fail_baseline)
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


@pytest.mark.parametrize('limit_kind', ['entries', 'bytes'])
def test_fixture_preflight_refuses_before_allocating_output(tmp_path, monkeypatch, limit_kind):
    import benchpack.workspaces as workspaces
    pack, case = _repo_task(tmp_path)
    source = pack.fixtures[0].path
    if limit_kind == 'entries':
        for i in range(5):
            (source / str(i)).mkdir()
        monkeypatch.setattr(workspaces, 'MAX_FIXTURE_COPY_ENTRIES', 10, raising=False)
    else:
        monkeypatch.setattr(workspaces, 'MAX_FIXTURE_COPY_BYTES', 11, raising=False)
    with pytest.raises(WorkspaceError, match='limit'):
        workspaces.prepare_repo_task_workspace(pack, case, tmp_path / 'run', 1)
    assert not (tmp_path / 'run').exists()
    assert (source / 'first.txt').read_text() == 'source'


def test_fixture_growth_is_bounded_during_copy(tmp_path, monkeypatch):
    import os
    import benchpack.workspaces as workspaces
    pack, case = _repo_task(tmp_path)
    source = pack.fixtures[0].path / 'first.txt'
    monkeypatch.setattr(workspaces, 'MAX_FIXTURE_COPY_BYTES', 20, raising=False)
    read = os.read
    grown = []
    def grow_after_read(fd, count):
        chunk = read(fd, min(count, 3))
        if chunk and not grown:
            with source.open('ab') as stream:
                stream.write(b'g' * 100)
            grown.append(True)
        return chunk
    monkeypatch.setattr(os, 'read', grow_after_read)
    with pytest.raises(WorkspaceError, match='limit') as error:
        workspaces.prepare_repo_task_workspace(pack, case, tmp_path / 'run', 1)
    assert grown
    assert 'staging retained at' in str(error.value)
    assert sum(p.stat().st_size for p in (tmp_path / 'run').rglob('*') if p.is_file()) <= 20


def test_fixture_budget_includes_baseline_and_preserves_links(tmp_path, monkeypatch):
    import benchpack.workspaces as workspaces
    pack, case = _repo_task(tmp_path)
    source = pack.fixtures[0].path
    (source / 'link').symlink_to('first.txt')
    monkeypatch.setattr(workspaces, 'MAX_FIXTURE_COPY_BYTES', 12, raising=False)
    monkeypatch.setattr(workspaces, 'MAX_FIXTURE_COPY_ENTRIES', 6, raising=False)
    prepared = workspaces.prepare_repo_task_workspace(pack, case, tmp_path / 'run', 1)
    for root in [prepared.path, prepared.baseline_path]:
        assert (root / 'first.txt').read_text() == 'source'
        assert (root / 'link').is_symlink()
        assert (root / 'link').readlink() == Path('first.txt')


def test_fixture_entry_growth_is_bounded_during_copy(tmp_path, monkeypatch):
    import os
    import benchpack.workspaces as workspaces
    pack, case = _repo_task(tmp_path)
    source = pack.fixtures[0].path
    monkeypatch.setattr(workspaces, 'MAX_FIXTURE_COPY_ENTRIES', 6, raising=False)
    scan = os.scandir
    seen = []
    def add_entries(path):
        if Path(path) == source:
            seen.append(path)
            if len(seen) == 2:
                for i in range(10):
                    (source / str(i)).mkdir()
        return scan(path)
    monkeypatch.setattr(os, 'scandir', add_entries)
    with pytest.raises(WorkspaceError, match='entry limit') as error:
        workspaces.prepare_repo_task_workspace(pack, case, tmp_path / 'run', 1)
    assert 'staging retained' in str(error.value)
    assert len(list((tmp_path / 'run' / 'workspace' / case.id).rglob('*'))) <= 7


def test_fixture_growth_consumes_shared_baseline_allowance(tmp_path, monkeypatch):
    import os
    import benchpack.workspaces as workspaces
    pack, case = _repo_task(tmp_path)
    source = pack.fixtures[0].path / 'first.txt'
    monkeypatch.setattr(workspaces, 'MAX_FIXTURE_COPY_BYTES', 16, raising=False)
    read = os.read
    grown = []
    def grow_once(fd, count):
        chunk = read(fd, min(count, 3))
        if chunk and not grown:
            with source.open('ab') as out:
                out.write(b'grow')
            grown.append(True)
        return chunk
    monkeypatch.setattr(os, 'read', grow_once)
    with pytest.raises(WorkspaceError, match='copy prepared baseline.*byte limit') as error:
        workspaces.prepare_repo_task_workspace(pack, case, tmp_path / 'run', 1)
    assert 'baseline:' in str(error.value)
    assert (tmp_path / 'run' / 'workspace' / case.id / 'rep-001' / 'first.txt').read_bytes() == b'sourcegrow'
    assert sum(p.stat().st_size for p in (tmp_path / 'run').rglob('*') if p.is_file()) <= 16
