"""Real SQLite ownership and selection capacity regressions."""

import gc
import json
import sqlite3
from contextlib import closing

import pytest

import benchpack.registry as registry
from tests.test_registry import _write_result_dir
from tests.test_registry_ingestion import _dataset


def test_owned_registry_connections_close_on_every_exit(tmp_path, monkeypatch):
    run, data, db = tmp_path / "run", tmp_path / "data.json", tmp_path / "db.sqlite"
    _write_result_dir(run)
    _dataset(data)
    registry.import_result_dirs([run], db)
    bundle = tmp_path / "bundle"
    registry.create_result_bundle([run], bundle)
    connect = sqlite3.connect
    owned = []

    class TrackedConnection(sqlite3.Connection):
        closed = False

        def close(self):
            self.closed = True
            return super().close()

    def track(*args, **kwargs):
        conn = connect(*args, factory=TrackedConnection, **kwargs)
        owned.append(conn)
        return conn

    monkeypatch.setattr(registry.sqlite3, "connect", track)
    operations = [
        lambda: registry.import_result_dirs([run], db),
        lambda: registry.import_result_bundles([bundle], db),
        lambda: registry.import_agent_wrap_results(data, db),
        lambda: registry.load_registry_report_runs(db),
        lambda: registry.find_registry_duplicate_runs(db),
        lambda: registry.query_registry_results(db),
        lambda: registry.query_agent_wrap_results(db),
        lambda: registry.export_registry_static_site(db, tmp_path / "site", force=True),
    ]
    enabled = gc.isenabled()
    gc.disable()
    try:
        for _ in range(2):
            for operation in operations:
                operation()
                assert all(conn.closed for conn in owned)
        for error in (sqlite3.OperationalError, KeyboardInterrupt):
            with monkeypatch.context() as patch:
                def fail(*args):
                    raise error("synthetic")
                patch.setattr(registry, "_assert_report_schema", fail)
                with pytest.raises(registry.RegistryError if issubclass(error, sqlite3.Error) else error):
                    registry.load_registry_report_runs(db)
            assert all(conn.closed for conn in owned)
            with monkeypatch.context() as patch:
                patch.setattr(registry, "_ensure_schema", fail)
                with pytest.raises(registry.RegistryError if issubclass(error, sqlite3.Error) else error):
                    registry.import_agent_wrap_results(data, db)
            assert all(conn.closed for conn in owned)
    finally:
        for conn in owned:
            if not conn.closed:
                conn.close()
        if enabled:
            gc.enable()
    # A helper borrows its connection; it must remain usable by its owner.
    with closing(connect(db)) as conn:
        conn.row_factory = sqlite3.Row
        registry._select_report_run_rows(conn, run_ids=None, labels=None, command="test")
        assert conn.execute("SELECT 1").fetchone()[0] == 1


@pytest.mark.parametrize("selector", ["ids", "labels", "all"])
def test_registry_selection_exceeds_sql_variable_limit(tmp_path, monkeypatch, selector):
    db = tmp_path / "db.sqlite"
    runs = [tmp_path / f"run-{i:02}" for i in range(40)]
    for run in runs:
        _write_result_dir(run)
    registry.import_result_dirs(runs, db)
    all_rows = registry.query_registry_results(db)
    ids = [row["run_id"] for row in all_rows]
    selection = {
        "ids": {"run_ids": ids[::-1] + ids[:2]},
        "labels": {"labels": [run.name for run in runs[::-1] + runs[:2]]},
        "all": {},
    }[selector]
    expected_query = registry.query_registry_results(db, **selection, model="test-model", ok=True, limit=21)
    expected_runs = registry.load_registry_report_runs(db, **selection)
    normal_site = tmp_path / "normal-site"
    registry.export_registry_static_site(db, normal_site, **selection)
    expected_site = json.loads((normal_site / "snapshot.json").read_text())
    connect = sqlite3.connect

    def limited(*args, **kwargs):
        conn = connect(*args, **kwargs)
        conn.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, 16)
        return conn

    monkeypatch.setattr(registry.sqlite3, "connect", limited)
    assert registry.query_registry_results(db, **selection, model="test-model", ok=True, limit=21) == expected_query
    assert registry.query_registry_results(db, **selection) == all_rows
    assert registry.load_registry_report_runs(db, **selection) == expected_runs
    site = tmp_path / "limited-site"
    registry.export_registry_static_site(db, site, **selection)
    actual = json.loads((site / "snapshot.json").read_text())
    actual.pop("generated_at")
    expected_site.pop("generated_at")
    assert actual == expected_site
    assert (site / "report.md").read_text() == (normal_site / "report.md").read_text()
    # A missing selector in a later batch cannot publish partial files.
    bad_selection = {"run_ids": ids + [9999]} if selector != "labels" else {"labels": [r.name for r in runs] + ["missing"]}
    before = {p.name: p.read_bytes() for p in site.iterdir()}
    with pytest.raises(registry.RegistryError, match="not found"):
        registry.export_registry_static_site(db, site, force=True, **bad_selection)
    assert {p.name: p.read_bytes() for p in site.iterdir()} == before


@pytest.mark.parametrize("operation", ["report", "query", "site"])
def test_batched_selection_keeps_one_read_snapshot(tmp_path, monkeypatch, operation):
    db = tmp_path / "db.sqlite"
    runs = [tmp_path / f"run-{i:02}" for i in range(20)]
    for run in runs:
        _write_result_dir(run)
    registry.import_result_dirs(runs, db)
    connect = sqlite3.connect
    with closing(connect(db)) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
    expected_query = registry.query_registry_results(db)
    ids = [row["run_id"] for row in expected_query]
    expected_runs = registry.load_registry_report_runs(db)
    expected_site = tmp_path / "expected-site"
    registry.export_registry_static_site(db, expected_site)
    changed = []

    class ConcurrentConnection(sqlite3.Connection):
        def execute(self, sql, parameters=()):
            cursor = super().execute(sql, parameters)
            if "WHERE id IN (" in sql and not changed:
                changed.append(True)
                with closing(connect(db)) as writer, writer:
                    writer.execute("UPDATE runs SET label='changed' WHERE id=?", (ids[-1],))
                    writer.execute("UPDATE result_rows SET wall_s=99 WHERE run_id=?", (ids[-1],))
            return cursor

    def concurrent(*args, **kwargs):
        conn = connect(*args, factory=ConcurrentConnection, **kwargs)
        conn.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, 16)
        return conn

    monkeypatch.setattr(registry.sqlite3, "connect", concurrent)
    if operation == "report":
        assert registry.load_registry_report_runs(db, run_ids=ids) == expected_runs
    elif operation == "query":
        assert registry.query_registry_results(db, run_ids=ids) == expected_query
    else:
        site = tmp_path / "site"
        registry.export_registry_static_site(db, site, run_ids=ids)
        actual = json.loads((site / "snapshot.json").read_text())
        expected = json.loads((expected_site / "snapshot.json").read_text())
        actual.pop("generated_at")
        expected.pop("generated_at")
        assert actual == expected
        assert (site / "report.md").read_text() == (expected_site / "report.md").read_text()
    assert changed
    with closing(connect(db)) as conn:
        assert conn.execute("SELECT label FROM runs WHERE id=?", (ids[-1],)).fetchone()[0] == "changed"
