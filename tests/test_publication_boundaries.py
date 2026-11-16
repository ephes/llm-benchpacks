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


@pytest.mark.parametrize('exporter', ['bundle', 'site'])
@pytest.mark.parametrize('unsafe', ['fifo', 'hardlink', 'exchanged'])
def test_publication_lock_admits_only_current_single_link_inode(tmp_path, monkeypatch, exporter, unsafe):
    from benchpack import output_paths
    source = tmp_path / 'source'
    _write_run(source)
    out = tmp_path / exporter
    db = tmp_path / 'registry.sqlite'
    if exporter == 'bundle':
        publish = lambda: create_result_bundle([source], out, force=True)
    else:
        import_result_dirs([source], db)
        publish = lambda: export_registry_static_site(db, out, force=True)
    publish()
    before = _tree(out)
    lock = publication_lock_path(out)
    if unsafe == 'fifo':
        lock.unlink()
        os.mkfifo(lock)
    elif unsafe == 'hardlink':
        os.link(lock, tmp_path / 'alias')
    else:
        flock = output_paths.fcntl.flock
        holders = []
        def exchange(fd, operation):
            flock(fd, operation)
            if operation == output_paths.fcntl.LOCK_EX | output_paths.fcntl.LOCK_NB:
                lock.rename(tmp_path / 'retired-lock')
                holders.append(_hold_lock(out))
        monkeypatch.setattr(output_paths.fcntl, 'flock', exchange)
    try:
        with pytest.raises(RegistryError):
            publish()
        assert _tree(out) == before
        assert not list(tmp_path.glob(f'.{exporter}-stage-*'))
        assert not list(tmp_path.glob(f'.{exporter}-backup-*'))
    finally:
        if unsafe == 'exchanged':
            for holder in holders:
                holder.kill()
                holder.communicate(timeout=5)


def test_publication_lock_open_is_nonblocking(tmp_path, monkeypatch):
    from benchpack import output_paths
    opened = output_paths.os.open
    def require_nonblocking(path, flags, *args, **kwargs):
        if str(path).endswith('.benchpack-publish.lock'):
            assert flags & os.O_NONBLOCK
            assert flags & os.O_NOFOLLOW
        return opened(path, flags, *args, **kwargs)
    monkeypatch.setattr(output_paths.os, 'open', require_nonblocking)
    with output_paths.publication_lock(tmp_path / 'bundle'):
        pass


@pytest.mark.parametrize('body_error_type', [None, RuntimeError, SystemExit])
@pytest.mark.parametrize('faults', [('unlock',), ('close',), ('unlock', 'close')])
def test_publication_lock_release_keeps_primary_and_attempts_close(tmp_path, monkeypatch, body_error_type, faults):
    body_error = body_error_type('publication failed') if body_error_type else None
    from benchpack import output_paths
    flock, close = output_paths.fcntl.flock, output_paths.os.close
    attempts = []
    def fail_unlock(fd, operation):
        if operation == output_paths.fcntl.LOCK_UN:
            attempts.append('unlock')
            if 'unlock' in faults:
                raise OSError('private unlock detail')
        return flock(fd, operation)
    def fail_close(fd):
        attempts.append('close')
        close(fd)
        if 'close' in faults:
            raise OSError('private close detail')
    monkeypatch.setattr(output_paths.fcntl, 'flock', fail_unlock)
    monkeypatch.setattr(output_paths.os, 'close', fail_close)
    with pytest.raises(BaseException) as caught:
        with output_paths.publication_lock(tmp_path / 'bundle'):
            if body_error is not None:
                raise body_error
    assert attempts == ['unlock', 'close']
    if body_error is not None:
        assert caught.value is body_error
        assert caught.value.__notes__ == [f'publication lock {fault} failed' for fault in faults]
    else:
        assert str(caught.value) == f'publication lock {faults[0]} failed'


def test_bundle_rollback_error_survives_failed_lock_release(tmp_path, monkeypatch):
    from benchpack import output_paths
    source, out = tmp_path / 'source', tmp_path / 'bundle'
    _write_run(source)
    create_result_bundle([source], out)
    before = _tree(out)
    rename, flock = Path.rename, output_paths.fcntl.flock
    failed = []
    def fail_publish(path, target):
        if Path(target) == out and path != out and '-backup-' not in path.name and not failed:
            failed.append(True)
            raise OSError('injected publication failure')
        return rename(path, target)
    def fail_unlock(fd, operation):
        if operation == output_paths.fcntl.LOCK_UN:
            raise OSError('injected unlock failure')
        return flock(fd, operation)
    monkeypatch.setattr(Path, 'rename', fail_publish)
    monkeypatch.setattr(output_paths.fcntl, 'flock', fail_unlock)
    with pytest.raises(RegistryError, match='injected publication failure') as caught:
        create_result_bundle([source], out, force=True)
    assert caught.value.__notes__ == ['publication lock unlock failed']
    assert _tree(out) == before


@pytest.mark.parametrize('with_primary', [False, True])
def test_lock_release_interrupt_still_closes(tmp_path, monkeypatch, with_primary):
    from benchpack import output_paths
    flock, close = output_paths.fcntl.flock, output_paths.os.close
    primary, interrupt = RuntimeError('publication failed'), SystemExit(143)
    closed = []
    def interrupt_unlock(fd, operation):
        if operation == output_paths.fcntl.LOCK_UN:
            raise interrupt
        return flock(fd, operation)
    def record_close(fd):
        close(fd)
        closed.append(fd)
    monkeypatch.setattr(output_paths.fcntl, 'flock', interrupt_unlock)
    monkeypatch.setattr(output_paths.os, 'close', record_close)
    with pytest.raises(BaseException) as caught:
        with output_paths.publication_lock(tmp_path / 'bundle'):
            if with_primary:
                raise primary
    assert len(closed) == 1
    assert caught.value is (primary if with_primary else interrupt)
    assert caught.value.__notes__ == ['publication lock unlock failed']


def _fail_lock_release(monkeypatch, faults):
    from benchpack import output_paths
    opened, flock, close = output_paths.os.open, output_paths.fcntl.flock, output_paths.os.close
    lock_fds = set()
    def record_lock_open(path, flags, *args, **kwargs):
        fd = opened(path, flags, *args, **kwargs)
        if str(path).endswith('.benchpack-publish.lock'):
            lock_fds.add(fd)
        return fd
    def fail_unlock(fd, operation):
        if fd in lock_fds and operation == output_paths.fcntl.LOCK_UN and 'unlock' in faults:
            raise OSError('secret unlock detail')
        return flock(fd, operation)
    def fail_close(fd):
        close(fd)
        if fd in lock_fds:
            lock_fds.discard(fd)
            if 'close' in faults:
                raise OSError('secret close detail')
    monkeypatch.setattr(output_paths.os, 'open', record_lock_open)
    monkeypatch.setattr(output_paths.fcntl, 'flock', fail_unlock)
    monkeypatch.setattr(output_paths.os, 'close', fail_close)


@pytest.mark.parametrize('exporter', ['bundle', 'site'])
@pytest.mark.parametrize('faults', [('unlock',), ('close',), ('unlock', 'close')])
def test_release_only_lock_failure_is_a_registry_error(tmp_path, monkeypatch, exporter, faults):
    source = tmp_path / 'source'
    _write_run(source)
    out = tmp_path / exporter
    db = tmp_path / 'registry.sqlite'
    if exporter == 'bundle':
        publish = lambda: create_result_bundle([source], out)
    else:
        import_result_dirs([source], db)
        publish = lambda: export_registry_static_site(db, out)
    _fail_lock_release(monkeypatch, faults)
    with pytest.raises(RegistryError) as caught:
        publish()
    message = str(caught.value)
    assert 'was completed, but releasing its publication lock failed' in message
    for fault in faults:
        assert f'publication lock {fault} failed' in message
    assert 'secret' not in message
    assert out.is_dir()


@pytest.mark.parametrize('exporter', ['bundle', 'site'])
def test_cli_reports_release_only_lock_failure(tmp_path, monkeypatch, exporter):
    source = tmp_path / 'source'
    _write_run(source)
    out = tmp_path / exporter
    if exporter == 'bundle':
        argv = ['registry', 'bundle', 'create', '--out', str(out), str(source)]
    else:
        db = tmp_path / 'registry.sqlite'
        import_result_dirs([source], db)
        argv = ['registry', 'site', '--db', str(db), '--out', str(out)]
    _fail_lock_release(monkeypatch, ('unlock', 'close'))
    with pytest.raises(SystemExit) as caught:
        main(argv)
    message = str(caught.value.code)
    assert 'publication lock unlock failed' in message
    assert 'publication lock close failed' in message


def test_cli_shows_release_notes_of_publication_failure(tmp_path, monkeypatch):
    from benchpack import output_paths
    source, out = tmp_path / 'source', tmp_path / 'bundle'
    _write_run(source)
    create_result_bundle([source], out)
    rename = Path.rename
    def fail_publish(path, target):
        if Path(target) == out and path != out and '-backup-' not in path.name:
            raise OSError('injected publication failure')
        return rename(path, target)
    monkeypatch.setattr(Path, 'rename', fail_publish)
    _fail_lock_release(monkeypatch, ('unlock',))
    with pytest.raises(SystemExit) as caught:
        main(['registry', 'bundle', 'create', '--force', '--out', str(out), str(source)])
    message = str(caught.value.code)
    assert 'injected publication failure' in message
    assert message.endswith('; publication lock unlock failed')


def test_cli_shows_close_note_of_refused_lock_admission(tmp_path, monkeypatch):
    source, out = tmp_path / 'source', tmp_path / 'bundle'
    _write_run(source)
    os.link(_touch(publication_lock_path(out)), tmp_path / 'alias')
    _fail_lock_release(monkeypatch, ('close',))
    with pytest.raises(SystemExit) as caught:
        main(['registry', 'bundle', 'create', '--out', str(out), str(source)])
    message = str(caught.value.code)
    assert 'single-link regular file' in message
    assert message.endswith('; publication lock close failed')
    assert not out.exists()


def _touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    return path
