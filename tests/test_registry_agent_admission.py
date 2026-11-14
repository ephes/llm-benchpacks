"""Synthetic agent-dataset admission and atomic replacement regressions."""

import json
import os
import sqlite3
import subprocess
import sys
from contextlib import closing

import pytest

import benchpack.registry as registry
from tests.test_registry_ingestion import _dataset


@pytest.mark.parametrize("budget", ["BYTES", "ROWS"])
def test_dataset_limits_before_mutation(tmp_path, monkeypatch, budget):
    data, db = tmp_path / "data.json", tmp_path / "db.sqlite"
    _dataset(data)
    limit = data.stat().st_size if budget == "BYTES" else 2
    monkeypatch.setattr(registry, f"MAX_AGENT_DATASET_{budget}", limit, raising=False)
    registry.import_agent_wrap_results(data, db)
    before = db.read_bytes()
    monkeypatch.setattr(registry, f"MAX_AGENT_DATASET_{budget}", limit - 1)
    for target in (db, tmp_path / "new.sqlite"):
        with pytest.raises(registry.RegistryError, match="limit"):
            registry.import_agent_wrap_results(data, target)
    assert db.read_bytes() == before
    assert not (tmp_path / "new.sqlite").exists()


@pytest.mark.parametrize("section,key,value", [
    ("timing", "wall_seconds", value)
    for value in (-1, float("nan"), float("inf"), -float("inf"), 10**400)
] + [
    (section, key, 2**63)
    for section, key in (("diff", "files_changed"), ("diff", "insertions"),
                         ("diff", "deletions"), ("verification", "node_tests"))
])
def test_agent_metric_domain_before_mutation(tmp_path, section, key, value):
    data, db = tmp_path / "data.json", tmp_path / "db.sqlite"
    _dataset(data)
    registry.import_agent_wrap_results(data, db)
    before = db.read_bytes()
    dataset = _dataset(data, labels=("replacement",))
    dataset["rows"][0][section][key] = value
    data.write_text(json.dumps(dataset))
    for target in (db, tmp_path / "new.sqlite"):
        with pytest.raises(registry.RegistryError, match=key):
            registry.import_agent_wrap_results(data, target)
    assert db.read_bytes() == before
    assert not (tmp_path / "new.sqlite").exists()


def test_agent_metric_storage_boundaries(tmp_path):
    data, db = tmp_path / "data.json", tmp_path / "db.sqlite"
    dataset = _dataset(data)
    for row, wall in zip(dataset["rows"], (0, sys.float_info.max)):
        row["timing"]["wall_seconds"] = wall
        row["diff"] = dict(files_changed=2**63-1, insertions=0, deletions=2**63-1)
        row["verification"]["node_tests"] = 2**63-1
    data.write_text(json.dumps(dataset))
    registry.import_agent_wrap_results(data, db)
    rows = registry.query_agent_wrap_results(db)
    assert len(rows) == 2


@pytest.mark.parametrize("failure", [sqlite3.OperationalError, KeyboardInterrupt])
def test_agent_replacement_rolls_back_prune_and_earlier_upsert(tmp_path, monkeypatch, failure):
    data, other, db = tmp_path / "data.json", tmp_path / "other.json", tmp_path / "db.sqlite"
    _dataset(data, labels=("stale", "keep"))
    _dataset(other, source="unrelated", labels=("unrelated",))
    registry.import_agent_wrap_results(data, db)
    registry.import_agent_wrap_results(other, db)
    connect = sqlite3.connect

    def dump():
        with closing(connect(db)) as conn:
            return list(conn.iterdump())

    before = dump()
    dataset = _dataset(data, labels=("keep", "new"))
    dataset["rows"][0]["notes"] = "Replacement"
    data.write_text(json.dumps(dataset))

    class FailingConnection(sqlite3.Connection):
        inserts = 0

        def execute(self, sql, parameters=()):
            if sql.lstrip().startswith("INSERT INTO agent_wrap_runs("):
                self.inserts += 1
                # The stale row is gone and the first upsert has happened.
                assert self.execute("SELECT COUNT(*) FROM agent_wrap_runs WHERE label='stale'").fetchone()[0] == 0
                if self.inserts == 2:
                    assert self.execute("SELECT notes FROM agent_wrap_runs WHERE label='keep'").fetchone()[0] == "Replacement"
                    raise failure("synthetic late insert failure")
            return super().execute(sql, parameters)

    with monkeypatch.context() as patch:
        patch.setattr(registry.sqlite3, "connect", lambda *a, **kw: connect(*a, factory=FailingConnection, **kw))
        expected = registry.RegistryError if issubclass(failure, sqlite3.Error) else failure
        with pytest.raises(expected):
            registry.import_agent_wrap_results(data, db)
    # Reopen independently: schema, metadata, unrelated rows and old rows survive.
    assert dump() == before
    registry.import_agent_wrap_results(data, db)
    registry.import_agent_wrap_results(data, db)
    assert {row["label"] for row in registry.query_agent_wrap_results(db)} == {"keep", "new", "unrelated"}


@pytest.mark.parametrize("kind", ["fifo", "fifo-link", "file-link", "directory"])
def test_dataset_requires_regular_unlinked_file(tmp_path, kind):
    data, db = tmp_path / "data.json", tmp_path / "db.sqlite"
    target = tmp_path / "target"
    if kind.startswith("fifo"):
        os.mkfifo(target)
        if kind == "fifo":
            target.rename(data)
        else:
            data.symlink_to(target)
    elif kind == "file-link":
        _dataset(target)
        data.symlink_to(target)
    else:
        data.mkdir()
    script = """
import sys
from benchpack.registry import import_agent_wrap_results, RegistryError
try:
    import_agent_wrap_results(sys.argv[1], sys.argv[2])
except RegistryError:
    sys.exit(0)
sys.exit(1)
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(data), str(db)],
        capture_output=True, timeout=3,
    )
    assert result.returncode == 0, result.stderr.decode()
    assert not db.exists()


def test_dataset_growth_checked_on_open_descriptor(tmp_path, monkeypatch):
    data, db = tmp_path / "data.json", tmp_path / "db.sqlite"
    _dataset(data)
    monkeypatch.setattr(registry, "MAX_AGENT_DATASET_BYTES", data.stat().st_size, raising=False)
    original = os.fdopen

    def grow(*args, **kwargs):
        with data.open("ab") as fh:
            fh.write(b" " * 10)
        return original(*args, **kwargs)

    monkeypatch.setattr(registry.os, "fdopen", grow)
    with pytest.raises(registry.RegistryError, match="byte limit"):
        registry.import_agent_wrap_results(data, db)
    assert not db.exists()


def test_dataset_replacement_after_open_keeps_descriptor(tmp_path, monkeypatch):
    data, db = tmp_path / "data.json", tmp_path / "db.sqlite"
    _dataset(data)
    fifo = tmp_path / "fifo"
    os.mkfifo(fifo)
    original = registry.open_contained_regular

    def swap(*args):
        fd = original(*args)
        data.unlink()
        data.symlink_to(fifo)
        return fd

    monkeypatch.setattr(registry, "open_contained_regular", swap)
    assert registry.import_agent_wrap_results(data, db).rows_imported == 2


def test_dataset_repeated_array_values_are_valid(tmp_path):
    data, db = tmp_path / "data.json", tmp_path / "db.sqlite"
    dataset = _dataset(data)
    dataset["extra"] = ["same", "same", {"key": 1}, {"key": 1}]
    data.write_text(json.dumps(dataset))
    assert registry.import_agent_wrap_results(data, db).rows_imported == 2


def test_dataset_invalid_utf8_is_domain_error(tmp_path):
    data, db = tmp_path / "data.json", tmp_path / "db.sqlite"
    data.write_bytes(b"\xff")
    with pytest.raises(registry.RegistryError, match="decode"):
        registry.import_agent_wrap_results(data, db)
    assert not db.exists()


@pytest.mark.parametrize("member", ["generated_from", "rows", "label", "wall_seconds"])
def test_duplicate_dataset_members_refused_without_mutation(tmp_path, member):
    data, db = tmp_path / "data.json", tmp_path / "db.sqlite"
    dataset = _dataset(data)
    registry.import_agent_wrap_results(data, db)
    before = db.read_bytes()
    # Equal duplicates are ambiguous too; never include names/values in errors.
    value = {
        "generated_from": dataset["generated_from"], "rows": dataset["rows"],
        "label": "one", "wall_seconds": 1,
    }[member]
    entry = json.dumps(member) + ": " + json.dumps(value)
    data.write_text(data.read_text().replace(entry, entry + ", " + entry, 1))
    for target in (db, tmp_path / "new.sqlite"):
        with pytest.raises(registry.RegistryError, match="duplicate JSON member") as error:
            registry.import_agent_wrap_results(data, target)
        assert member not in str(error.value)
        assert "Synthetic" not in str(error.value)
    assert db.read_bytes() == before
    assert not (tmp_path / "new.sqlite").exists()


def test_agent_replacement_prunes_within_small_variable_budget(tmp_path, monkeypatch):
    data, db = tmp_path / "data.json", tmp_path / "db.sqlite"
    _dataset(data, labels=[f"row-{i:03}" for i in range(200)])
    registry.import_agent_wrap_results(data, db)
    connect = sqlite3.connect

    def limited(*args, **kwargs):
        conn = connect(*args, **kwargs)
        # Above one row upsert's parameters, below the kept and the stale label counts.
        conn.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, 80)
        return conn

    monkeypatch.setattr(registry.sqlite3, "connect", limited)
    # More kept labels and more stale labels than one statement may bind.
    kept = [f"row-{i:03}" for i in range(0, 200, 2)] + [f"new-{i:02}" for i in range(5)]
    _dataset(data, labels=kept)
    registry.import_agent_wrap_results(data, db)
    with closing(connect(db)) as conn:
        labels = {label for (label,) in conn.execute("SELECT label FROM agent_wrap_runs")}
    assert labels == set(kept)


def test_missing_and_symlinked_datasets_name_the_path(tmp_path):
    db = tmp_path / "db.sqlite"
    missing = tmp_path / "missing.json"
    with pytest.raises(registry.RegistryError, match="could not read .*missing.json: no such file"):
        registry.import_agent_wrap_results(missing, db)
    real, link = tmp_path / "real.json", tmp_path / "link.json"
    _dataset(real)
    link.symlink_to(real)
    with pytest.raises(registry.RegistryError, match="link.json requires a readable regular file"):
        registry.import_agent_wrap_results(link, db)
    assert not db.exists()
