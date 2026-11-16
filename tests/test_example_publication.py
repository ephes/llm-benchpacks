"""Offline namespace durability and cleanup faults for example edit publication."""
import os
import stat

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
    synced = directory_syncs(monkeypatch)
    def fail(fd):
        raise OSError('stage fsync fault')
    monkeypatch.setattr(os, 'fsync', fail)
    with pytest.raises(ValueError, match='could not stage'):
        replace_workspace_files(tmp_path, [('a', b'new')])
    assert not synced
    assert (tmp_path / 'a').read_bytes() == b'old'
