"""Regressions for descriptor-bound evidence, bounded report sets and publishers."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from benchpack import registry, repo_task_outcomes
from benchpack.cli import main
from benchpack.output_paths import publication_lock_path
from benchpack.registry import (
    BUNDLE_MANIFEST_FILENAME,
    RegistryError,
    create_result_bundle,
    export_registry_static_site,
    import_result_dirs,
    validate_result_bundle,
)
from benchpack.report import MAX_REPORT_SET_BYTES, ReportError, load_report_set
from benchpack.repo_task_outcomes import summarize_repo_task_outcomes


def _record(case: str = "short", patch: str | None = None) -> dict:
    record = {
        "pack": {"id": "runtime-sweep", "version": "0.1.0"},
        "case": case,
        "adapter": "openai-chat",
        "endpoint": "http://example.test/v1/chat/completions",
        "model": "test-model",
        "ok": True,
        "timing": {"wall_s": 1.0, "ttft_s": 0.1, "prefill_tps": 10.0,
                   "decode_tps": 5.0, "total_tps": 4.0},
        "tokens": {"prompt": 10, "output": 5, "cached_prompt": 0},
        "resources": {"memory_mb": None, "gpu_memory_mb": None},
        "scoring": None,
        "raw": {"request_path": "raw/r.json", "response_path": "raw/s.json"},
    }
    if patch is not None:
        record["patch"] = {"path": patch}
    return record


def _write_run(path: Path, records: list[dict] | None = None) -> None:
    path.mkdir(parents=True)
    rows = records or [_record()]
    (path / "run.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))


def _failed_task(patch: str) -> dict:
    return {
        "case": "fix-repo",
        "repo_task": {"status": "failed", "verify_exit_code": 1},
        "scoring": {"mode": "verify-script", "passed": False},
        "patch": {"path": patch},
    }


def _tree(root: Path) -> dict[Path, bytes]:
    return {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}


# --- benchpack-outcome-patch-opened-snapshot ---------------------------------


def test_outcome_size_and_paths_come_from_one_snapshot(tmp_path, monkeypatch) -> None:
    result_dir = tmp_path / "run"
    patch = result_dir / "patch" / "rep-001.diff"
    patch.parent.mkdir(parents=True)
    patch.write_text("diff --git a/__pycache__/a.pyc b/__pycache__/a.pyc\n")
    calls = []
    original = repo_task_outcomes.read_contained_regular

    def read_then_swap(root, relative, limit):
        snapshot = original(root, relative, limit)
        calls.append(relative)
        # Replace the patch after the one read: a second stat/read would see
        # a different generation with another size and a source path.
        patch.write_text("diff --git a/src/app.py b/src/app.py\n" * 3)
        return snapshot

    monkeypatch.setattr(repo_task_outcomes, "read_contained_regular", read_then_swap)
    outcome = summarize_repo_task_outcomes([_failed_task("patch/rep-001.diff")], result_dir)[0]
    assert calls == ["patch/rep-001.diff"]
    assert outcome.patch_bytes == len("diff --git a/__pycache__/a.pyc b/__pycache__/a.pyc\n")
    assert outcome.outcome == "failed-non-source-mutation"


def test_outcome_oversized_patch_is_unknown_mutation(tmp_path, monkeypatch) -> None:
    result_dir = tmp_path / "run"
    patch = result_dir / "rep.diff"
    result_dir.mkdir()
    patch.write_text("diff --git a/src/app.py b/src/app.py\n" + "+x\n" * 100)
    monkeypatch.setattr(repo_task_outcomes, "MAX_PATCH_OUTPUT_BYTES", 64)
    outcome = summarize_repo_task_outcomes([_failed_task("rep.diff")], result_dir)[0]
    assert outcome.patch_bytes == patch.stat().st_size
    assert outcome.outcome == "failed-unknown-mutation"


def test_outcome_fifo_patch_does_not_block(tmp_path) -> None:
    result_dir = tmp_path / "run"
    result_dir.mkdir()
    os.mkfifo(result_dir / "rep.diff")
    started = time.monotonic()
    outcome = summarize_repo_task_outcomes([_failed_task("rep.diff")], result_dir)[0]
    assert time.monotonic() - started < 5
    assert outcome.patch_bytes is None
    assert outcome.outcome == "failed-unknown-mutation"


@pytest.mark.parametrize("link", ["file", "ancestor"])
def test_outcome_patch_through_symlink_is_unknown(tmp_path, link) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "rep.diff").write_text("diff --git a/src/app.py b/src/app.py\n")
    result_dir = tmp_path / "run"
    result_dir.mkdir()
    if link == "file":
        (result_dir / "rep.diff").symlink_to(outside / "rep.diff")
        relative = "rep.diff"
    else:
        (result_dir / "patch").symlink_to(outside, target_is_directory=True)
        relative = "patch/rep.diff"
    assert (result_dir / relative).is_file()  # the escaping target exists
    outcome = summarize_repo_task_outcomes([_failed_task(relative)], result_dir)[0]
    assert outcome.patch_bytes is None
    assert outcome.outcome == "failed-unknown-mutation"


# --- benchpack-report-set-bounded-decoder ------------------------------------


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (b'result_dirs = ["\xff"]\n', "not valid UTF-8"),
        (b"x = " + b"[" * 50_000 + b"]" * 50_000 + b"\n", "could not parse|nesting"),
        (b"#" * (MAX_REPORT_SET_BYTES + 1), "exceeds"),
    ],
    ids=["invalid-utf8", "deep-nesting", "over-budget"],
)
def test_report_set_decoder_failures_are_report_errors(tmp_path, content, message) -> None:
    manifest = tmp_path / "set.toml"
    manifest.write_bytes(content)
    with pytest.raises(ReportError, match=message):
        load_report_set(manifest)


def test_report_set_cli_reports_controlled_error(tmp_path, capsys) -> None:
    manifest = tmp_path / "set.toml"
    manifest.write_bytes(b'result_dirs = ["\xff"]\n')
    with pytest.raises(SystemExit) as exc:
        main(["report", "--set", str(manifest)])
    assert "not valid UTF-8" in str(exc.value.code)


def test_report_set_fifo_is_refused_without_blocking(tmp_path) -> None:
    manifest = tmp_path / "set.toml"
    os.mkfifo(manifest)
    with pytest.raises(ReportError, match="regular file"):
        load_report_set(manifest)


def test_report_set_relative_paths_still_expand(tmp_path) -> None:
    manifest = tmp_path / "sets" / "set.toml"
    manifest.parent.mkdir()
    manifest.write_text('version = 1\nresult_dirs = ["../runs/a", "/abs/b"]\n')
    assert load_report_set(manifest) == [manifest.parent / "../runs/a", Path("/abs/b")]


# --- benchpack-export-publisher-single-writer --------------------------------


_HOLDER = textwrap.dedent(
    """
    import fcntl, os, sys, time
    fd = os.open(sys.argv[1], os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX)
    print("locked", flush=True)
    time.sleep(60)
    """
)


def _hold_lock(output: Path) -> subprocess.Popen:
    holder = subprocess.Popen(
        [sys.executable, "-c", _HOLDER, str(publication_lock_path(output))],
        stdout=subprocess.PIPE,
        text=True,
    )
    assert holder.stdout is not None
    assert holder.stdout.readline().strip() == "locked"
    return holder


@pytest.mark.parametrize("exporter", ["bundle", "site"])
def test_concurrent_publisher_is_busy_until_owner_exits(tmp_path, exporter) -> None:
    source = tmp_path / "run-a"
    _write_run(source)
    out = tmp_path / exporter
    db = tmp_path / "registry.sqlite"
    if exporter == "bundle":
        publish = lambda: create_result_bundle([source], out, force=True)  # noqa: E731
    else:
        import_result_dirs([source], db)
        publish = lambda: export_registry_static_site(db, out, force=True)  # noqa: E731
    publish()
    # A backup abandoned by an earlier killed publisher is recovery evidence.
    abandoned = tmp_path / f".{exporter}-backup-abandoned"
    abandoned.mkdir()
    (abandoned / "evidence").write_text("previous generation")
    before = _tree(out)

    holder = _hold_lock(out)
    try:
        with pytest.raises(RegistryError, match="being published by another process"):
            publish()
        assert _tree(out) == before
        assert not list(tmp_path.glob(f".{exporter}-stage-*"))
    finally:
        holder.kill()
        holder.wait(timeout=30)

    publish()
    assert (abandoned / "evidence").read_text() == "previous generation"
    if exporter == "bundle":
        validate_result_bundle(out)


def test_publication_lock_refuses_symlinked_lock_file(tmp_path) -> None:
    source = tmp_path / "run-a"
    _write_run(source)
    target = tmp_path / "elsewhere"
    target.write_text("not a lock")
    publication_lock_path(tmp_path / "bundle").symlink_to(target)
    with pytest.raises(RegistryError, match="could not lock"):
        create_result_bundle([source], tmp_path / "bundle")
    assert target.read_text() == "not a lock"
    assert not (tmp_path / "bundle").exists()


# --- benchpack-bundle-copy-opened-source-containment -------------------------


@pytest.mark.parametrize("swap", ["file", "ancestor"])
def test_bundle_copy_refuses_source_swapped_to_outside_link(tmp_path, monkeypatch, swap) -> None:
    private = tmp_path / "private"
    private.mkdir()
    (private / "rep.diff").write_text("OUTSIDE-PRIVATE-BYTES\n")
    source = tmp_path / "run-a"
    _write_run(source, [_record(patch="patch/short/rep.diff")])
    (source / "patch" / "short").mkdir(parents=True)
    (source / "patch" / "short" / "rep.diff").write_text("diff --git a/a b/a\n")
    original = registry.copy_contained_regular

    def swap_then_copy(root, relative, destination, limit):
        if relative == "patch/short/rep.diff":
            if swap == "file":
                (source / "patch" / "short" / "rep.diff").unlink()
                (source / "patch" / "short" / "rep.diff").symlink_to(private / "rep.diff")
            else:
                (source / "patch" / "short" / "rep.diff").unlink()
                (source / "patch" / "short").rmdir()
                (source / "patch" / "short").symlink_to(private, target_is_directory=True)
        return original(root, relative, destination, limit)

    monkeypatch.setattr(registry, "copy_contained_regular", swap_then_copy)
    bundle = tmp_path / "bundle"
    create_result_bundle([source], bundle)
    for data in _tree(bundle).values():
        assert b"OUTSIDE-PRIVATE-BYTES" not in data
    manifest = json.loads((bundle / BUNDLE_MANIFEST_FILENAME).read_text())["runs"][0]
    omitted = {entry["path"]: entry for entry in manifest["omitted_artifacts"]}
    assert omitted["patch/short/rep.diff"]["reason"] == "missing-or-unsafe"
    assert "sha256" not in omitted["patch/short/rep.diff"]
    validate_result_bundle(bundle)


def test_bundle_copy_exports_ordinary_in_root_artifacts(tmp_path) -> None:
    source = tmp_path / "run-a"
    _write_run(source, [_record(patch="patch/short/rep.diff")])
    (source / "patch" / "short").mkdir(parents=True)
    (source / "patch" / "short" / "rep.diff").write_text("diff --git a/a b/a\n")
    bundle = tmp_path / "bundle"
    create_result_bundle([source], bundle)
    manifest = json.loads((bundle / BUNDLE_MANIFEST_FILENAME).read_text())["runs"][0]
    copied = bundle / manifest["bundle_path"] / "patch" / "short" / "rep.diff"
    assert copied.read_text() == "diff --git a/a b/a\n"
    assert any(entry["role"] == "patch" for entry in manifest["files"])


def test_bundle_copy_refuses_run_jsonl_symlink(tmp_path) -> None:
    private = tmp_path / "private.jsonl"
    private.write_text(json.dumps(_record()) + "\n")
    source = tmp_path / "run-a"
    _write_run(source)
    # Validation reads the real file; swap afterwards to a link at the copy seam.
    (source / "run.jsonl").unlink()
    (source / "run.jsonl").symlink_to(private)
    with pytest.raises(RegistryError):
        create_result_bundle([source], tmp_path / "bundle")
    assert not (tmp_path / "bundle").exists()
