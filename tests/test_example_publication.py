"""Offline namespace durability and cleanup faults for example edit publication."""
import os
import stat
import sys

import pytest

from benchpack.example_io import replace_example_files, replace_workspace_files


def roots(tmp_path):
    paths = [tmp_path / name for name in ('workspace', 'output')]
    for path in paths:
        path.mkdir()
        (path / 'a').write_bytes(b'old')
    return paths


def directory_syncs(monkeypatch, callback=None):
    synced = []
    fsync = os.fsync

    def sync(fd):
        info = os.fstat(fd)
        if stat.S_ISDIR(info.st_mode):
            synced.append((info.st_dev, info.st_ino))
            if callback:
                callback(fd)
        return fsync(fd)

    monkeypatch.setattr(os, 'fsync', sync)
    return synced


def identities(paths):
    return {(path.stat().st_dev, path.stat().st_ino) for path in paths}


def test_success_syncs_each_distinct_held_parent_after_all_replacements(tmp_path, monkeypatch):
    paths = roots(tmp_path)
    (paths[0] / 'b').write_bytes(b'old')
    def complete(fd):
        assert all((path / 'a').read_bytes() == b'new' for path in paths)
        assert (paths[0] / 'b').read_bytes() == b'new'
    synced = directory_syncs(monkeypatch, complete)
    replace_example_files([(path, 'a', b'new') for path in paths] + [(paths[0], 'b', b'new')])
    assert set(synced) == identities(paths)
    assert len(synced) == 2


def test_directory_sync_failure_retains_complete_two_root_publication(tmp_path, monkeypatch):
    paths = roots(tmp_path)
    failure = OSError('injected directory sync')
    def fail(fd):
        raise failure
    synced = directory_syncs(monkeypatch, fail)
    with pytest.raises(ValueError, match='edits published; directory durability uncertain') as caught:
        replace_example_files([(path, 'a', b'new') for path in paths])
    assert caught.value.__cause__ is failure
    assert set(synced) == identities(paths)
    assert all((path / 'a').read_bytes() == b'new' for path in paths)


@pytest.mark.parametrize('existing', [False, True])
@pytest.mark.parametrize('sync_failure', [False, True])
def test_rollback_syncs_compensating_namespace_changes(tmp_path, monkeypatch, existing, sync_failure):
    paths = roots(tmp_path)
    if not existing:
        (paths[0] / 'a').unlink()
    publication = OSError('primary publication fault')
    replace = os.replace
    def fail_second(src, dst, **kwargs):
        if kwargs['dst_dir_fd'] and os.fstat(kwargs['dst_dir_fd']).st_ino == paths[1].stat().st_ino:
            raise publication
        return replace(src, dst, **kwargs)
    monkeypatch.setattr(os, 'replace', fail_second)
    def sync(fd):
        assert (paths[0] / 'a').exists() == existing
        if existing:
            assert (paths[0] / 'a').read_bytes() == b'old'
        if sync_failure:
            raise OSError('secondary rollback sync fault')
    synced = directory_syncs(monkeypatch, sync)
    message = 'rollback directory durability uncertain' if sync_failure else 'could not apply'
    with pytest.raises(ValueError, match=message) as caught:
        replace_example_files([(path, 'a', b'new') for path in paths], missing=True)
    assert caught.value.__cause__ is publication
    assert set(synced) == identities(paths[:1])
    assert (paths[1] / 'a').read_bytes() == b'old'


def test_staging_failure_never_acknowledges_publication(tmp_path, monkeypatch):
    (tmp_path / 'a').write_bytes(b'old')
    synced = []
    def fail_regular(fd):
        # Record directory acknowledgements; fail only the staged file sync.
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            synced.append(fd)
            return None
        raise OSError('stage fsync fault')
    monkeypatch.setattr(os, 'fsync', fail_regular)
    with pytest.raises(ValueError, match='could not stage'):
        replace_workspace_files(tmp_path, [('a', b'new')])
    assert not synced
    assert (tmp_path / 'a').read_bytes() == b'old'


@pytest.mark.parametrize('make_primary', [
    lambda: OSError('publication'), KeyboardInterrupt, lambda: SystemExit(143),
], ids=['oserror', 'interrupt', 'exit'])
@pytest.mark.parametrize('rollback_failure', [False, True])
def test_cleanup_preserves_publication_verdict_and_attempts_every_resource(
    tmp_path, monkeypatch, make_primary, rollback_failure,
):
    from benchpack import example_io
    # A fresh exception per case keeps notes from leaking between parameters.
    primary = make_primary()
    for name in ('a', 'b'):
        (tmp_path / name).write_bytes(name.encode())
    staged = []
    stage = example_io._Target.stage
    def remember(self, *args, **kwargs):
        result = stage(self, *args, **kwargs)
        staged.append(result)
        return result
    monkeypatch.setattr(example_io._Target, 'stage', remember)
    replace = os.replace
    calls = []
    def publication(src, dst, **kwargs):
        calls.append(dst)
        if dst == 'b':
            raise primary
        if len(calls) == 3 and rollback_failure:
            raise OSError('rollback')
        return replace(src, dst, **kwargs)
    monkeypatch.setattr(os, 'replace', publication)
    discarded = []
    def unlink(name, **kwargs):
        discarded.append(name)
        raise OSError('SECONDARY secret cleanup payload')
    monkeypatch.setattr(os, 'unlink', unlink)
    closed = []
    close = os.close
    def close_then_fail(fd):
        close(fd)
        closed.append(fd)
        raise OSError('SECONDARY close payload')
    monkeypatch.setattr(os, 'close', close_then_fail)
    expected = ValueError if isinstance(primary, OSError) else type(primary)
    with pytest.raises(expected) as caught:
        replace_workspace_files(tmp_path, [('a', b'new'), ('b', b'new')])
    if expected is ValueError:
        assert caught.value.__cause__ is primary
        assert ('rollback failed' in str(caught.value)) == rollback_failure
    else:
        assert caught.value is primary
        notes = getattr(primary, '__notes__', [])
        assert any('rollback failed' in note for note in notes) == rollback_failure
    notes = getattr(caught.value, '__notes__', [])
    assert any('temporary cleanup failed' in note for note in notes)
    assert any('descriptor close failed' in note for note in notes)
    assert 'SECONDARY' not in str(caught.value) + ' '.join(notes)
    retained = {staged[1]} if rollback_failure else set()
    assert set(discarded) == set(staged) - retained
    assert len(discarded) == len(staged) - len(retained)
    # Two ancestors + one source + two stage and two held descriptors per target.
    assert len(closed) == 14
    if rollback_failure:
        assert (tmp_path / staged[1]).read_bytes() == b'a'
    assert (tmp_path / 'b').read_bytes() == b'b'


def test_successful_edits_keep_applied_verdict_and_report_cleanup_residue(tmp_path, monkeypatch, capsys):
    (tmp_path / 'a').write_bytes(b'old')
    unlinks = []
    unlink = os.unlink
    def fail_existing(name, **kwargs):
        unlinks.append(name)
        if len(unlinks) == 1:
            raise OSError('private cleanup payload')
        return unlink(name, **kwargs)
    monkeypatch.setattr(os, 'unlink', fail_existing)
    replace_workspace_files(tmp_path, [('a', b'new')])
    assert (tmp_path / 'a').read_bytes() == b'new'
    assert len(unlinks) == 2
    residue = list(tmp_path.glob('.benchpack-example-*.tmp'))
    assert len(residue) == 1
    assert residue[0].read_bytes() == b'old'
    error = capsys.readouterr().err
    assert 'temporary cleanup failed' in error
    assert 'publication verdict unchanged' in error
    assert 'private cleanup payload' not in error


def test_cleanup_does_not_mask_uncertain_publication(tmp_path, monkeypatch):
    paths = roots(tmp_path)
    def fail_sync(fd):
        raise OSError('sync')
    directory_syncs(monkeypatch, fail_sync)
    def fail_unlink(*args, **kwargs):
        raise OSError('cleanup')
    monkeypatch.setattr(os, 'unlink', fail_unlink)
    with pytest.raises(ValueError, match='edits published; directory durability uncertain') as caught:
        replace_example_files([(path, 'a', b'new') for path in paths])
    assert any('temporary cleanup failed' in note for note in caught.value.__notes__)
    assert all((path / 'a').read_bytes() == b'new' for path in paths)


def test_stage_stream_close_cannot_mask_staging_failure(tmp_path, monkeypatch):
    (tmp_path / 'a').write_bytes(b'old')
    primary = OSError('stage sync')
    def fail_sync(fd):
        raise primary
    monkeypatch.setattr(os, 'fsync', fail_sync)
    fdopen = os.fdopen
    class CloseFailure:
        def __init__(self, *args, **kwargs):
            self.stream = fdopen(*args, **kwargs)
        def __getattr__(self, name):
            return getattr(self.stream, name)
        def close(self):
            self.stream.close()
            raise OSError('secondary stream close')
        def __enter__(self):
            return self
        def __exit__(self, *args):
            self.close()
    monkeypatch.setattr(os, 'fdopen', CloseFailure)
    with pytest.raises(ValueError, match='could not stage') as caught:
        replace_workspace_files(tmp_path, [('a', b'new')])
    assert caught.value.__cause__ is primary
    assert any('descriptor close failed' in note for note in primary.__notes__)
    assert (tmp_path / 'a').read_bytes() == b'old'
    assert not list(tmp_path.glob('.benchpack-example-*.tmp'))


def test_cleanup_residue_is_reported_when_caller_is_handling_unrelated_exception(
    tmp_path, monkeypatch, capsys,
):
    (tmp_path / 'a').write_bytes(b'old')
    unlink = os.unlink
    unlinks = []
    def fail_first(name, **kwargs):
        unlinks.append(name)
        if len(unlinks) == 1:
            raise OSError('private cleanup payload')
        return unlink(name, **kwargs)
    monkeypatch.setattr(os, 'unlink', fail_first)
    unrelated = RuntimeError('caller fallback context')
    try:
        raise unrelated
    except RuntimeError:
        replace_workspace_files(tmp_path, [('a', b'new')])
    assert (tmp_path / 'a').read_bytes() == b'new'
    assert not getattr(unrelated, '__notes__', [])
    error = capsys.readouterr().err
    assert 'temporary cleanup failed' in error
    assert 'private cleanup payload' not in error


def test_directory_identity_failure_still_reports_uncertain_publication(tmp_path, monkeypatch):
    paths = roots(tmp_path)
    fstat = os.fstat
    failure = OSError('injected directory fstat')
    def fail_directory(fd):
        # Only the durability acknowledgement loses directory identity.
        if sys._getframe(1).f_code.co_name == '_sync_parents':
            raise failure
        return fstat(fd)
    monkeypatch.setattr(os, 'fstat', fail_directory)
    synced = []
    fsync = os.fsync
    def record(fd):
        if stat.S_ISDIR(fstat(fd).st_mode):
            synced.append(fd)
        return fsync(fd)
    monkeypatch.setattr(os, 'fsync', record)
    with pytest.raises(ValueError, match='edits published; directory durability uncertain') as caught:
        replace_example_files([(path, 'a', b'new') for path in paths])
    assert caught.value.__cause__ is failure
    assert len(synced) == len(paths)
    assert all((path / 'a').read_bytes() == b'new' for path in paths)


def test_example_entry_point_reports_residue_on_publication_failure(tmp_path, monkeypatch, capsys):
    import importlib.util
    from pathlib import Path
    script = Path(__file__).resolve().parents[1] / 'examples/external-agent/openai-direct-edit-agent.py'
    spec = importlib.util.spec_from_file_location('openai_direct_edit_agent', script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    (tmp_path / 'a').write_bytes(b'old')
    def fail_replace(*args, **kwargs):
        raise OSError('primary publication fault')
    monkeypatch.setattr(os, 'replace', fail_replace)
    def fail_unlink(*args, **kwargs):
        raise OSError('private cleanup payload')
    monkeypatch.setattr(os, 'unlink', fail_unlink)
    with pytest.raises(ValueError) as caught:
        module._apply_edits(tmp_path, {'files': [{'path': 'a', 'content': 'new'}]}, ('a',))
    # Example callers report only str(exc); the residue must still be visible.
    assert 'temporary cleanup failed' not in str(caught.value)
    error = capsys.readouterr().err
    assert 'example cleanup warning' in error
    assert 'temporary cleanup failed' in error
    assert 'private cleanup payload' not in error
    assert (tmp_path / 'a').read_bytes() == b'old'
    assert len(list(tmp_path.glob('.benchpack-example-*.tmp'))) == 2


@pytest.mark.parametrize('make_interrupt', [KeyboardInterrupt, lambda: SystemExit(143)],
                         ids=['interrupt', 'exit'])
def test_interrupt_during_acknowledgement_notes_visible_publication(tmp_path, monkeypatch, make_interrupt):
    paths = roots(tmp_path)
    interrupt = make_interrupt()
    def stop(fd):
        raise interrupt
    directory_syncs(monkeypatch, stop)
    with pytest.raises(type(interrupt)) as caught:
        replace_example_files([(path, 'a', b'new') for path in paths])
    assert caught.value is interrupt
    assert any('edits published; directory durability uncertain' in note
               for note in interrupt.__notes__)
    assert all((path / 'a').read_bytes() == b'new' for path in paths)


@pytest.mark.parametrize('rollback_failure', [False, True])
def test_interrupt_during_rollback_acknowledgement_keeps_rollback_verdict(
    tmp_path, monkeypatch, rollback_failure,
):
    paths = roots(tmp_path)
    publication = OSError('primary publication fault')
    replace = os.replace
    calls = []
    def fail_second(src, dst, **kwargs):
        calls.append(dst)
        if len(calls) == 2:
            raise publication
        if len(calls) == 3 and rollback_failure:
            raise OSError('rollback')
        return replace(src, dst, **kwargs)
    monkeypatch.setattr(os, 'replace', fail_second)
    interrupt = KeyboardInterrupt()
    def stop(fd):
        raise interrupt
    directory_syncs(monkeypatch, stop)
    with pytest.raises(KeyboardInterrupt) as caught:
        replace_example_files([(path, 'a', b'new') for path in paths])
    assert caught.value is interrupt
    assert interrupt.__context__ is publication
    notes = interrupt.__notes__
    assert any('rollback directory durability uncertain' in note for note in notes)
    assert any('rollback failed' in note for note in notes) == rollback_failure
    assert (paths[1] / 'a').read_bytes() == b'old'
    expected = b'new' if rollback_failure else b'old'
    assert (paths[0] / 'a').read_bytes() == expected
