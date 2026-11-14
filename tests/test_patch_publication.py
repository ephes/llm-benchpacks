"""Failure-atomic replacements and one patch execution budget."""
import os
import stat
import subprocess

import pytest

from benchpack import tasks


@pytest.mark.parametrize('failure', ['encoding', 'flush', 'replace'])
def test_replacement_failure_preserves_bytes_and_mode(tmp_path, monkeypatch, failure):
    path = tmp_path / 'source.py'
    path.write_bytes(b'old\n')
    path.chmod(0o751)
    content = 'new\n'
    if failure == 'encoding':
        content = '\ud800'
    else:
        def fail(*args, **kwargs):
            raise OSError('synthetic publication failure')
        monkeypatch.setattr(os, 'fsync' if failure == 'flush' else 'replace', fail)
    block = f'*** Begin File: source.py\n{content}\n*** End File\n'
    ok, _, error = tasks.apply_fenced_edit_to_workspace(block, tmp_path)
    assert not ok
    assert 'unchanged' in error
    assert path.read_bytes() == b'old\n'
    assert stat.S_IMODE(path.stat().st_mode) == 0o751
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize('elapsed, expected_calls', [(0.6, 2), (0.4, 3)])
def test_patch_checks_and_apply_share_deadline(tmp_path, monkeypatch, elapsed, expected_calls):
    clock = [0.0]
    monkeypatch.setattr(tasks, 'monotonic', lambda: clock[0], raising=False)
    calls = []

    def run(command, **kwargs):
        calls.append(kwargs['timeout'])
        clock[0] += elapsed
        return subprocess.CompletedProcess(command, 1 if len(calls) == 1 else 0, '', '')

    monkeypatch.setattr(tasks.subprocess, 'run', run)
    ok, _, error = tasks.apply_unified_diff_to_workspace(
        '--- a/file\n+++ b/file\n@@ -1 +1 @@\n-old\n+new\n', tmp_path, timeout_s=1,
    )
    assert len(calls) == expected_calls
    assert calls == pytest.approx([1 - elapsed * i for i in range(expected_calls)])
    assert ok == (expected_calls == 3)
    if not ok:
        assert 'unchanged' in error


def test_replacement_success_preserves_executable_mode(tmp_path):
    path = tmp_path / 'run'
    path.write_bytes(b'old')
    path.chmod(0o751)
    assert tasks.apply_fenced_edit_to_workspace(
        '*** Begin File: run\nnew\n*** End File', tmp_path,
    )[0]
    assert path.read_bytes() == b'new\n'
    assert stat.S_IMODE(path.stat().st_mode) == 0o751
