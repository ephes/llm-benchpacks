"""Runner-owned artifacts cannot follow workspace-controlled links."""
import json
import os

import pytest

from benchpack import safe_files, tasks
from benchpack.external_agent_context import ExternalAgentContextError, write_external_agent_context
from tests.test_tasks import make_case


@pytest.mark.parametrize('destination', ['stdout', 'stderr', 'parent'])
@pytest.mark.parametrize('noop', [True, False])
def test_task_logs_refuse_links_before_mutation(tmp_path, destination, noop):
    out = tmp_path / 'output'
    parent = out / 'task' / make_case().id
    parent.mkdir(parents=True)
    outside = tmp_path / 'outside'
    outside.mkdir()
    sentinel = outside / 'sentinel'
    sentinel.write_text('keep')
    if destination == 'parent':
        parent.rmdir()
        parent.symlink_to(outside, target_is_directory=True)
    else:
        paths = tasks.task_artifact_paths(out, make_case(), 1)
        getattr(paths, destination).symlink_to(sentinel)
    with pytest.raises(tasks.TaskError):
        if noop:
            tasks.write_noop_task_logs(out, make_case(), 1)
        else:
            tasks.run_model_patch_task(out, make_case(), 1, tmp_path, '')
    assert sentinel.read_text() == 'keep'
    assert sorted(p.name for p in outside.iterdir()) == ['sentinel']


@pytest.mark.parametrize('failure', ['encoding', 'write', 'flush', 'replace'])
def test_context_failure_preserves_previous_generation(tmp_path, monkeypatch, failure):
    path = tmp_path / 'context.json'
    path.write_text('{"generation": "old"}\n')
    context = {'generation': 'new'}
    if failure == 'encoding':
        context['generation'] = object()
    elif failure == 'write':
        fdopen = os.fdopen
        class PartialWriter:
            def __init__(self, *args):
                self.stream = fdopen(*args)
            def __enter__(self):
                return self
            def __exit__(self, *args):
                self.stream.close()
            def write(self, data):
                self.stream.write(data[:2])
                raise OSError('short write')
        monkeypatch.setattr(os, 'fdopen', PartialWriter)
    else:
        def fail(*args, **kwargs):
            raise OSError('synthetic failure')
        monkeypatch.setattr(os, 'fsync' if failure == 'flush' else 'replace', fail)
    with pytest.raises(ExternalAgentContextError):
        write_external_agent_context(path, context)
    assert json.loads(path.read_text()) == {'generation': 'old'}
    assert list(tmp_path.iterdir()) == [path]


def test_task_directory_exchange_during_publication_is_reported(tmp_path, monkeypatch):
    out = tmp_path / 'output'
    parent = out / 'task' / make_case().id
    parent.mkdir(parents=True)
    outside = tmp_path / 'outside'
    outside.mkdir()
    publish = safe_files.atomic_write_at
    swapped = False

    def exchange(*args):
        nonlocal swapped
        if not swapped:
            swapped = True
            parent.rename(out / 'old')
            parent.symlink_to(outside, target_is_directory=True)
        return publish(*args)

    monkeypatch.setattr(tasks, 'atomic_write_at', exchange)
    with pytest.raises(tasks.TaskError):
        tasks.write_noop_task_logs(out, make_case(), 1)
    assert not list(outside.iterdir())


def test_context_reader_observes_complete_generations(tmp_path, monkeypatch):
    path = tmp_path / 'context.json'
    write_external_agent_context(path, {'generation': 'old'})
    replace = os.replace
    observations = []

    def observe(*args, **kwargs):
        observations.append(json.loads(path.read_text()))
        result = replace(*args, **kwargs)
        observations.append(json.loads(path.read_text()))
        return result

    monkeypatch.setattr(os, 'replace', observe)
    write_external_agent_context(path, {'generation': 'new'})
    assert observations == [{'generation': 'old'}, {'generation': 'new'}]


def test_task_artifact_escape_is_rejected_before_mutation(tmp_path):
    from dataclasses import replace
    out = tmp_path / 'output'
    out.mkdir()
    outside = tmp_path / 'outside'
    outside.mkdir()
    sentinel = outside / 'rep-001.stdout.log'
    sentinel.write_text('keep')
    case = replace(make_case(), id='../../outside')
    with pytest.raises(tasks.TaskError):
        tasks.write_noop_task_logs(out, case, 1)
    assert sentinel.read_text() == 'keep'
    assert not (outside / 'rep-001.stderr.log').exists()
