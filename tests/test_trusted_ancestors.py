"""Symlinked ancestors (macOS /tmp, a linked home) stay usable; links below the trusted base do not."""
import os
import signal
import stat

import pytest

from benchpack import safe_files, tasks
from benchpack.external_agent_context import write_external_agent_context
from tests.test_tasks import make_case, make_harness_request


@pytest.fixture
def linked(tmp_path):
    real = tmp_path / 'real'
    real.mkdir()
    link = tmp_path / 'link'
    link.symlink_to(real, target_is_directory=True)
    return link


def test_task_logs_under_symlinked_output_ancestor(linked):
    out = linked / 'output'
    tasks.write_noop_task_logs(out, make_case(), 1)
    paths = tasks.task_artifact_paths(out, make_case(), 1)
    assert paths.stdout.exists() and paths.stderr.exists()


def test_context_under_symlinked_ancestor(linked):
    path = linked / 'run' / 'context.json'
    write_external_agent_context(path, {'generation': 'one'})
    assert path.read_text().startswith('{')


def test_workspace_under_symlinked_ancestor(linked):
    root = linked / 'workspace'
    (root / 'nested').mkdir(parents=True)
    (root / 'nested' / 'file').write_text('inside')
    request = make_harness_request(linked, root)
    assert request.read_workspace_text('nested/file') == 'inside'
    request.write_workspace_text('nested/new', 'written')
    assert request.workspace_file_exists('nested/new')
    assert 'nested/new' in request.list_workspace_paths()
    assert request.delete_workspace_file('nested/new')


def test_symlinked_workspace_root_is_still_refused(tmp_path):
    real = tmp_path / 'real-workspace'
    real.mkdir()
    (real / 'file').write_text('inside')
    root = tmp_path / 'workspace'
    root.symlink_to(real, target_is_directory=True)
    request = make_harness_request(tmp_path, root)
    with pytest.raises(tasks.TaskError):
        request.read_workspace_text('file')


def test_new_files_follow_the_process_umask(tmp_path):
    previous = os.umask(0o022)
    try:
        fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            safe_files.atomic_write_at(fd, 'fresh', b'data')
        finally:
            os.close(fd)
    finally:
        os.umask(previous)
    assert stat.S_IMODE((tmp_path / 'fresh').stat().st_mode) == 0o644


def test_final_group_kill_tolerates_exiting_group(monkeypatch):
    def eperm(pgid, signal_number):
        raise PermissionError(1, 'Operation not permitted')
    monkeypatch.setattr(tasks.os, 'killpg', eperm)
    tasks._signal_external_process_group(1, signal.SIGKILL, 'synthetic', exiting_ok=True)
    with pytest.raises(tasks.TaskError):
        tasks._signal_external_process_group(1, signal.SIGKILL, 'synthetic')
