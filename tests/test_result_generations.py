"""Synthetic barriers at result evidence read/publication boundaries."""

import hashlib
import json
import os

import pytest

from benchpack import compare, registry, safe_files
from tests.test_registry import _record, _write_result_dir


@pytest.mark.parametrize("operation", ["read", "copy", "bundle", "outcome"])
@pytest.mark.parametrize("mutation", ["inplace", "replace"])
def test_contained_read_generation(tmp_path, monkeypatch, operation, mutation):
    from benchpack.repo_task_outcomes import summarize_repo_task_outcomes

    run = tmp_path / "run"
    _write_result_dir(run)
    source = run / "patch" / "fix" / "rep.diff"
    source.parent.mkdir(parents=True)
    old = b"diff --git a/old.py b/old.py\n" * 8
    new = old.replace(b"old", b"new")
    source.write_bytes(old)
    if operation == "bundle":
        row = _record()
        row["patch"] = {"path": "patch/fix/rep.diff"}
        (run / "run.jsonl").write_text(json.dumps(row) + "\n")
    original = os.read
    changed = False

    def read(fd, count):
        nonlocal changed
        chunk = original(fd, min(count, 32))
        if not changed and os.fstat(fd).st_ino == source.stat().st_ino:
            changed = True
            if mutation == "inplace":
                source.write_bytes(new)
            else:
                other = run / "new.diff"
                other.write_bytes(new)
                other.replace(source)
        return chunk

    monkeypatch.setattr(os, "read", read)
    destination = tmp_path / "copy.diff"
    bundle = tmp_path / "bundle"

    def action():
        if operation == "copy":
            return safe_files.copy_contained_regular(run, "patch/fix/rep.diff", destination, 4096)
        if operation == "bundle":
            return registry.create_result_bundle([run], bundle)
        if operation == "outcome":
            return summarize_repo_task_outcomes([{"case": "fix", "repo_task": {"status": "failed"}, "patch": {"path": "patch/fix/rep.diff"}}], run)
        return safe_files.read_contained_regular(run, "patch/fix/rep.diff", 4096)

    if mutation == "inplace":
        with pytest.raises((OSError, registry.RegistryError), match="changed|unstable"):
            action()
        assert not destination.exists() and not bundle.exists()
    else:
        result = action()
        if operation == "read":
            assert result.data == old
        elif operation == "copy":
            assert destination.read_bytes() == old
        elif operation == "bundle":
            assert next((bundle / "runs").glob("*/patch/fix/rep.diff")).read_bytes() == old
        else:
            assert result[0].patch_bytes == len(old)
    assert changed


@pytest.mark.parametrize("loader", ["single", "multiple", "registry"])
@pytest.mark.parametrize("mutation", ["inplace", "replace"])
def test_jsonl_read_generation(tmp_path, monkeypatch, loader, mutation):
    run = tmp_path / "run"
    _write_result_dir(run, [_record("old"), _record("old")])
    path = run / "run.jsonl"
    old = path.read_bytes()
    hook = compare.unique_json_object
    changed = False

    def decode(pairs):
        nonlocal changed
        if not changed:
            changed = True
            if mutation == "inplace":
                path.write_bytes(old.replace(b'"old"', b'"new"'))
            else:
                other = run / "new.jsonl"
                other.write_bytes(old.replace(b'"old"', b'"new"'))
                other.replace(path)
        return hook(pairs)

    monkeypatch.setattr(compare, "unique_json_object", decode)
    db = tmp_path / "db.sqlite"

    def action():
        if loader == "registry":
            return registry.import_result_dirs([run], db)
        if loader == "multiple":
            return compare.load_result_runs([run])[0]
        return compare.load_result_run(run)

    if mutation == "inplace":
        with pytest.raises((compare.CompareError, registry.RegistryError)):
            action()
        assert not db.exists()
    else:
        try:
            loaded = action()
        except registry.RegistryError:
            # Registry additionally fences directory entries across sidecar reads.
            assert loader == "registry" and not db.exists()
            return
        if loader != "registry":
            assert [row["case"] for row in loaded.records] == ["old", "old"]
            assert loaded.source_sha256 == hashlib.sha256(old).hexdigest()
    assert changed


@pytest.mark.parametrize("boundary", ["jsonl", "validation"])
def test_registry_directory_exchange_never_mixes_generations(tmp_path, monkeypatch, boundary):
    import sqlite3

    run, db = tmp_path / "run", tmp_path / "db.sqlite"
    _write_result_dir(run, [_record("old")])
    (run / "hardware.json").write_text('{"hostname":"old-host"}')
    (run / "run-metadata.json").write_text('{"runtime":{"name":"old-runtime"}}')
    registry.import_result_dirs([run], db)
    before = db.read_bytes()
    changed = False

    def exchange():
        nonlocal changed
        if changed:
            return
        changed = True
        run.rename(tmp_path / "retired")
        _write_result_dir(run, [_record("new")])
        (run / "hardware.json").write_text('{"hostname":"new-host"}')
        (run / "run-metadata.json").write_text('{"runtime":{"name":"new-runtime"}}')

    if boundary == "jsonl":
        hook = compare.unique_json_object

        def decode(pairs):
            exchange()
            return hook(pairs)

        monkeypatch.setattr(compare, "unique_json_object", decode)
    else:
        hook = registry._load_and_validate_result_dir

        def validate(path, **kwargs):
            result = hook(path, **kwargs)
            exchange()
            return result

        monkeypatch.setattr(registry, "_load_and_validate_result_dir", validate)
    try:
        registry.import_result_dirs([run], db)
    except registry.RegistryError:
        assert db.read_bytes() == before
    else:
        with sqlite3.connect(db) as conn:
            host, runtime = conn.execute("SELECT host_hostname, runtime_name FROM runs").fetchone()
            (row,) = conn.execute("SELECT raw_json FROM result_rows").fetchone()
        assert (json.loads(row)["case"], host, runtime) == ("old", "old-host", "old-runtime")
    assert changed


@pytest.mark.parametrize("filename", ["hardware.json", "run-metadata.json"])
def test_registry_uses_validated_sidecars_after_admission(tmp_path, monkeypatch, filename):
    import sqlite3

    run, db = tmp_path / "run", tmp_path / "db.sqlite"
    _write_result_dir(run)
    (run / "hardware.json").write_text('{"hostname":"old-host"}')
    (run / "run-metadata.json").write_text('{"runtime":{"name":"old-runtime"}}')
    hook = registry._ensure_schema

    def schema(conn):
        hook(conn)
        (run / filename).write_text('invalid replacement')

    monkeypatch.setattr(registry, "_ensure_schema", schema)
    registry.import_result_dirs([run], db)
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT host_hostname, runtime_name FROM runs").fetchone() == ("old-host", "old-runtime")


@pytest.mark.parametrize("mutation", ["rewrite", "replace", "create"])
def test_registry_sidecars_fenced_across_jsonl_parse(tmp_path, monkeypatch, mutation):
    run, db = tmp_path / "run", tmp_path / "db.sqlite"
    _write_result_dir(run)
    sidecar = run / "hardware.json"
    if mutation != "create":
        sidecar.write_text('{"hostname":"old"}')
    registry.import_result_dirs([run], db)
    before = db.read_bytes()
    hook = compare.unique_json_object
    changed = False

    def decode(pairs):
        nonlocal changed
        if not changed:
            changed = True
            if mutation == "replace":
                other = run / "new.json"
                other.write_text('{"hostname":"new"}')
                other.replace(sidecar)
            else:
                sidecar.write_text('{"hostname":"new"}')
        return hook(pairs)

    monkeypatch.setattr(compare, "unique_json_object", decode)
    with pytest.raises(registry.RegistryError):
        registry.import_result_dirs([run], db)
    assert changed and db.read_bytes() == before


def test_registry_directory_alias_keeps_input_label(tmp_path):
    run, alias = tmp_path / "run", tmp_path / "alias"
    _write_result_dir(run)
    alias.symlink_to(run, target_is_directory=True)
    loaded = registry._load_and_validate_result_dir(alias)
    assert loaded.label == "alias" and loaded.path == run.resolve()


@pytest.mark.parametrize("artifact", ["hardware.json", "run-metadata.json", "summary.md", "context.json"])
@pytest.mark.parametrize("failure", ["file", "directory"])
@pytest.mark.parametrize("error_code", [5, 28])  # EIO and ENOSPC
def test_artifact_sync_failure_keeps_complete_visible_generation(tmp_path, monkeypatch, artifact, failure, error_code):
    import stat
    from benchpack.external_agent_context import ExternalAgentContextError, write_external_agent_context
    from benchpack.results import RunReporter
    from tests.test_results import make_pack

    out = tmp_path / "run"
    reporter = RunReporter(out, make_pack(tmp_path))
    final = out / artifact
    old = b"old generation\n"
    final.write_bytes(old)
    final.chmod(0o640)
    original = os.fsync
    synced = []

    def fsync(fd):
        kind = "directory" if stat.S_ISDIR(os.fstat(fd).st_mode) else "file"
        synced.append(kind)
        if kind == failure:
            raise OSError(error_code, "synthetic sync failure")
        original(fd)

    actions = {
        "hardware.json": lambda: reporter.write_hardware({"hostname": "synthetic"}),
        "run-metadata.json": lambda: reporter.write_run_metadata({"notes": "synthetic"}),
        "summary.md": lambda: reporter.write_summary({}),
        "context.json": lambda: write_external_agent_context(final, {"synthetic": True}),
    }
    monkeypatch.setattr(os, "fsync", fsync)
    with pytest.raises((OSError, ExternalAgentContextError)) as error:
        actions[artifact]()
    if failure == "directory":
        assert synced == ["file", "directory"]
        assert "published" in str(error.value) and "uncertain" in str(error.value)
        visible = final.read_bytes()
        assert visible != old
        if artifact == "summary.md":
            assert visible.startswith(b"# smoke-chat")
        else:
            assert isinstance(json.loads(visible), dict)
    else:
        assert synced == ["file"] and final.read_bytes() == old
    assert stat.S_IMODE(final.stat().st_mode) == 0o640
    assert not list(out.glob(".benchpack-*.tmp"))
    # An uncertain sync never releases the reporter's generation ownership.
    out.rename(tmp_path / "retired")
    out.mkdir()
    with pytest.raises(OSError, match="exchanged"):
        reporter.write_hardware({})
    assert not list(out.iterdir())


def test_atomic_artifact_sync_order(tmp_path, monkeypatch):
    import stat

    events = []
    sync, replace = os.fsync, os.replace

    def fsync(fd):
        events.append("directory" if stat.S_ISDIR(os.fstat(fd).st_mode) else "file")
        sync(fd)

    def publish(*args, **kwargs):
        events.append("replace")
        replace(*args, **kwargs)

    monkeypatch.setattr(os, "fsync", fsync)
    monkeypatch.setattr(os, "replace", publish)
    with safe_files.admitted_directory(tmp_path) as directory:
        safe_files.atomic_write_at(directory, "artifact.json", b"{}\n")
    assert events == ["file", "replace", "directory"]



def test_replacement_sync_failure_does_not_claim_unchanged_workspace(tmp_path, monkeypatch):
    import stat
    from benchpack.tasks import TaskError, _apply_replacement_file_to_workspace

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "app.py").write_text("old")
    original = os.fsync

    def fsync(fd):
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            raise OSError("synthetic directory sync failure")
        original(fd)

    monkeypatch.setattr(os, "fsync", fsync)
    with pytest.raises(TaskError, match="published.*uncertain"):
        _apply_replacement_file_to_workspace("app.py", "complete new generation", workspace)
    assert (workspace / "app.py").read_text() == "complete new generation"
