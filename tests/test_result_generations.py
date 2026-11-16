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
        loaded = action()
        if loader != "registry":
            assert [row["case"] for row in loaded.records] == ["old", "old"]
            assert loaded.source_sha256 == hashlib.sha256(old).hexdigest()
    assert changed
