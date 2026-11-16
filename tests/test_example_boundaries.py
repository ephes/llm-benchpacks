"""Offline regression coverage for shipped external-agent examples."""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def agent(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'examples/external-agent' / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('name', ['openai-direct-edit-agent', 'pi-agent'])
def test_replacements_preencode_every_file(name, tmp_path):
    mod = agent(name)
    for name in ('a', 'b'):
        (tmp_path / name).write_bytes(name.encode())
    with pytest.raises(ValueError):
        mod._apply_edits(tmp_path, {'files': [
            {'path': 'a', 'content': 'new'}, {'path': 'b', 'content': '\ud800'},
        ]}, ('a', 'b'))
    assert [(tmp_path / p).read_bytes() for p in ('a', 'b')] == [b'a', b'b']


@pytest.mark.parametrize('name', ['openai-direct-edit-agent', 'pi-agent'])
def test_replacements_do_not_mutate_external_hardlink(name, tmp_path):
    import os
    mod = agent(name)
    root = tmp_path / 'root'
    root.mkdir()
    sentinel = tmp_path / 'sentinel'
    sentinel.write_bytes(b'outside')
    os.link(sentinel, root / 'a')
    try:
        mod._apply_edits(root, {'files': [{'path': 'a', 'content': 'new'}]}, ('a',))
    except (ValueError, OSError):
        pass
    assert sentinel.read_bytes() == b'outside'


@pytest.mark.parametrize('name', ['openai-direct-edit-agent', 'pi-agent'])
def test_replacements_refuse_parent_exchange(name, tmp_path, monkeypatch):
    mod = agent(name)
    root = tmp_path / 'root'
    (root / 'dir').mkdir(parents=True)
    (root / 'dir/a').write_bytes(b'old')
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'a').write_bytes(b'outside')
    original = mod._workspace_path
    def exchanged(workspace, relative):
        target = original(workspace, relative)
        (root / 'dir').rename(root / 'saved')
        (root / 'dir').symlink_to(outside, target_is_directory=True)
        return target
    monkeypatch.setattr(mod, '_workspace_path', exchanged)
    with pytest.raises((ValueError, OSError)):
        mod._apply_edits(root, {'files': [{'path': 'dir/a', 'content': 'new'}]}, ('dir/a',))
    assert (outside / 'a').read_bytes() == b'outside'


@pytest.mark.parametrize('name', ['openai-direct-edit-agent', 'pi-agent'])
def test_replacement_stages_roll_back_and_keep_modes(name, tmp_path, monkeypatch):
    import os
    mod = agent(name)
    for p in ('a', 'b'):
        (tmp_path / p).write_bytes(p.encode())
        (tmp_path / p).chmod(0o755)
    replace = os.replace
    def fail_second(src, dst, **kwargs):
        if dst == 'b':
            raise OSError('injected')
        return replace(src, dst, **kwargs)
    monkeypatch.setattr(os, 'replace', fail_second)
    with pytest.raises(ValueError):
        mod._apply_edits(tmp_path, {'files': [
            {'path': 'a', 'content': 'é'}, {'path': 'b', 'content': 'ok'},
        ]}, ('a', 'b'))
    assert [(tmp_path / p).read_bytes() for p in ('a', 'b')] == [b'a', b'b']
    monkeypatch.setattr(os, 'replace', replace)
    mod._apply_edits(tmp_path, {'files': [{'path': 'a', 'content': 'é'}]}, ('a',))
    assert (tmp_path / 'a').read_bytes() == 'é'.encode()
    assert (tmp_path / 'a').stat().st_mode & 0o777 == 0o755
    assert sorted(p.name for p in tmp_path.iterdir()) == ['a', 'b']


def test_generation_change_after_staging_is_refused(tmp_path, monkeypatch):
    from benchpack import example_io
    (tmp_path / 'a').write_bytes(b'old')
    stage = example_io._Target.stage
    def exchange(self, data, stack):
        result = stage(self, data, stack)
        (tmp_path / 'a').unlink()
        (tmp_path / 'a').symlink_to(tmp_path / 'outside')
        return result
    (tmp_path / 'outside').write_bytes(b'sentinel')
    monkeypatch.setattr(example_io._Target, 'stage', exchange)
    with pytest.raises(ValueError):
        example_io.replace_workspace_files(tmp_path, [('a', b'new')])
    assert (tmp_path / 'outside').read_bytes() == b'sentinel'
