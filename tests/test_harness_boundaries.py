"""Synthetic workspace admission and publication regressions."""
import os
from pathlib import Path

import pytest

from benchpack import tasks
from tests.test_tasks import make_harness_request


@pytest.mark.parametrize('operation', ['read', 'write', 'delete'])
def test_workspace_parent_exchange_is_refused(tmp_path, monkeypatch, operation):
    root = tmp_path / 'workspace'
    parent = root / 'nested'
    parent.mkdir(parents=True)
    (parent / 'file').write_text('inside')
    outside = tmp_path / 'outside'
    outside.mkdir()
    sentinel = outside / 'file'
    sentinel.write_text('outside')
    request = make_harness_request(tmp_path, root)
    resolve = tasks._resolve_workspace_relative_path

    def exchange(path, workspace):
        admitted = resolve(path, workspace)
        if parent.is_dir() and not parent.is_symlink():
            parent.rename(root / 'old')
            parent.symlink_to(outside, target_is_directory=True)
        return admitted

    monkeypatch.setattr(tasks, '_resolve_workspace_relative_path', exchange)
    with pytest.raises(tasks.TaskError):
        if operation == 'read':
            request.read_workspace_text('nested/file')
        elif operation == 'write':
            request.write_workspace_text('nested/file', 'changed')
        else:
            request.delete_workspace_file('nested/file')
    assert sentinel.read_text() == 'outside'


def test_workspace_read_byte_cap_and_nonregular(tmp_path, monkeypatch):
    root = tmp_path / 'workspace'
    root.mkdir()
    request = make_harness_request(tmp_path, root)
    monkeypatch.setattr(tasks, 'MAX_WORKSPACE_READ_BYTES', 4, raising=False)
    (root / 'file').write_text('12345')
    with pytest.raises(tasks.TaskError):
        request.read_workspace_text('file')
    os.mkfifo(root / 'pipe')
    with pytest.raises(tasks.TaskError):
        request.read_workspace_text('pipe')


@pytest.mark.parametrize('method', ['list_workspace_paths', 'list_workspace_dirs'])
def test_workspace_inventory_counts_all_entries(tmp_path, monkeypatch, method):
    root = tmp_path / 'workspace'
    root.mkdir()
    for index in range(5):
        (root / str(index)).mkdir()
    request = make_harness_request(tmp_path, root)
    monkeypatch.setattr(tasks, 'MAX_WORKSPACE_ENTRIES', 4, raising=False)
    with pytest.raises(tasks.TaskError):
        getattr(request, method)()


def test_workspace_read_growing_file_stops_at_cap(tmp_path, monkeypatch):
    root = tmp_path / 'workspace'
    root.mkdir()
    (root / 'file').write_text('small')
    request = make_harness_request(tmp_path, root)
    monkeypatch.setattr(tasks, 'MAX_WORKSPACE_READ_BYTES', 4)
    read = os.read
    consumed = []

    def growing(fd, size):
        consumed.append(size)
        return b'x' * size

    monkeypatch.setattr(os, 'read', growing)
    with pytest.raises(tasks.TaskError):
        request.read_workspace_text('file')
    assert sum(consumed) == 5
    monkeypatch.setattr(os, 'read', read)


@pytest.mark.parametrize('component', ['file', 'workspace'])
def test_workspace_read_final_or_root_exchange(tmp_path, monkeypatch, component):
    root = tmp_path / 'workspace'
    root.mkdir()
    (root / 'file').write_text('inside')
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'file').write_text('outside')
    request = make_harness_request(tmp_path, root)
    resolve = tasks._resolve_workspace_relative_path

    def exchange(path, workspace):
        admitted = resolve(path, workspace)
        if component == 'file':
            (root / 'file').unlink()
            (root / 'file').symlink_to(outside / 'file')
        else:
            root.rename(tmp_path / 'old')
            root.symlink_to(outside, target_is_directory=True)
        return admitted

    monkeypatch.setattr(tasks, '_resolve_workspace_relative_path', exchange)
    with pytest.raises(tasks.TaskError):
        request.read_workspace_text('file')
