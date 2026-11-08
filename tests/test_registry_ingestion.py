"""Synthetic regressions for registry import admission and migration work."""

import json
import sqlite3
from pathlib import Path

import pytest

import benchpack.registry as registry
from tests.test_registry import _record, _write_result_dir


def _dataset(path, source="synthetic-a", labels=("one", "two")):
    dataset = {
        "schema_version": 1, "generated_from": source,
        "target": dict(project="synthetic", version="1", commit="abc", workload="wrap"),
        "rows": [dict(
            label=label, date="2026-11-08", status="pass",
            model=dict(id="test-model", name="Test", family="test"),
            harness=dict(id="test", name="Test"), provider=dict(id="test", name="Test"),
            runner_provider_display="Test", thinking=dict(kind="effort", level="none", display="None"),
            timing=dict(wall_seconds=1, wall_display="1s"),
            diff=dict(files_changed=1, insertions=1, deletions=0),
            verification=dict(node_tests=1, smoke="http-ok", smoke_display="Pass"),
            artifact=dict(result_dir="synthetic/result", legacy=False), notes="Synthetic",
        ) for label in labels],
    }
    path.write_text(json.dumps(dataset))
    return dataset


def test_current_identity_revision_does_not_rewrite_history(tmp_path, monkeypatch):
    old, new = tmp_path / "old", tmp_path / "new"
    _write_result_dir(old, [_record(f"case-{i}") for i in range(200)])
    _write_result_dir(new)
    db = tmp_path / "registry.sqlite"
    registry.import_result_dirs([old], db)
    statements = []
    connect = sqlite3.connect

    def traced(*args, **kwargs):
        conn = connect(*args, **kwargs)
        conn.set_trace_callback(statements.append)
        return conn

    monkeypatch.setattr(registry.sqlite3, "connect", traced)
    registry.import_result_dirs([new], db)
    assert not [sql for sql in statements if sql.lstrip().upper().startswith("UPDATE RESULT_ROWS")]
    assert not [sql for sql in statements if sql.lstrip().upper().startswith("UPDATE RUNS")]


@pytest.mark.parametrize("source", [None, "", "  ", 123, ["invalid"]])
def test_dataset_source_required_before_database_creation(tmp_path, source):
    data, db = tmp_path / "data.json", tmp_path / "db.sqlite"
    _dataset(data, source)
    with pytest.raises(registry.RegistryError, match="generated_from"):
        registry.import_agent_wrap_results(data, db)
    assert not db.exists()


def test_dataset_sources_cannot_take_over_labels_or_prune_each_other(tmp_path):
    a, b, db = tmp_path / "a.json", tmp_path / "b.json", tmp_path / "db.sqlite"
    _dataset(a)
    _dataset(b, "synthetic-b", ("three",))
    registry.import_agent_wrap_results(a, db)
    registry.import_agent_wrap_results(b, db)
    before = db.read_bytes()
    _dataset(b, "synthetic-b", ("one",))
    with pytest.raises(registry.RegistryError, match="owned by another dataset"):
        registry.import_agent_wrap_results(b, db)
    assert db.read_bytes() == before
    _dataset(a, labels=("two",))
    registry.import_agent_wrap_results(a, db)
    assert {r["label"] for r in registry.query_agent_wrap_results(db)} == {"two", "three"}


@pytest.mark.parametrize("kind", ["runs", "records", "bytes"])
def test_bundle_aggregate_admission_before_database_mutation(tmp_path, monkeypatch, kind):
    runs = [tmp_path / f"run-{i}" for i in range(3)]
    for run in runs:
        _write_result_dir(run)
    bundle = tmp_path / "bundle"
    registry.create_result_bundle(runs, bundle)
    db = tmp_path / "db.sqlite"
    size = (runs[0] / "run.jsonl").stat().st_size
    monkeypatch.setattr(registry, f"MAX_BUNDLE_{kind.upper()}", 2 * size if kind == "bytes" else 2, raising=False)
    calls = []
    loader = registry._load_and_validate_result_dir

    def load(path, **kwargs):
        calls.append(Path(path))
        return loader(path, **kwargs)

    monkeypatch.setattr(registry, "_load_and_validate_result_dir", load)
    with pytest.raises(registry.RegistryError, match="limit"):
        registry.import_result_bundles([bundle], db)
    assert not db.exists()
    assert len(calls) <= 3
    monkeypatch.setattr(registry, f"MAX_BUNDLE_{kind.upper()}", 3 * size if kind == "bytes" else 3, raising=False)
    assert len(registry.import_result_bundles([bundle], db)) == 3


def test_identity_format_revision_recomputes_existing_rows(tmp_path, monkeypatch):
    run, db = tmp_path / "run", tmp_path / "db.sqlite"
    _write_result_dir(run)
    registry.import_result_dirs([run], db)
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE result_rows SET model_identity='obsolete'")
    monkeypatch.setattr(registry, "IDENTITY_VERSION", registry.IDENTITY_VERSION + 1)
    data = tmp_path / "data.json"
    _dataset(data)
    registry.import_agent_wrap_results(data, db)
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT model_identity FROM result_rows").fetchone() == ("test-model",)


def test_bundle_import_shares_budget_across_inputs(tmp_path, monkeypatch):
    bundles = []
    for i in range(2):
        run, bundle = tmp_path / f"run-{i}", tmp_path / f"bundle-{i}"
        _write_result_dir(run)
        registry.create_result_bundle([run], bundle)
        bundles.append(bundle)
    monkeypatch.setattr(registry, "MAX_BUNDLE_RUNS", 1)
    db = tmp_path / "db.sqlite"
    with pytest.raises(registry.RegistryError, match="limit"):
        registry.import_result_bundles(bundles, db)
    assert not db.exists()
