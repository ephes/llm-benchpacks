"""Synthetic storage-boundary regressions for the deterministic reference agent."""
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / 'examples/external-agent/reference-agent.py'


def agent():
    spec = importlib.util.spec_from_file_location('reference_agent', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def handoff(tmp_path):
    workspace, output = tmp_path / 'workspace', tmp_path / 'output'
    workspace.mkdir()
    (output / 'task').mkdir(parents=True)
    log = output / 'task/calls.jsonl'
    marker = workspace / 'external-agent-example.txt'
    marker.write_bytes(b'previous marker')
    log.write_bytes(b'previous log')
    context = tmp_path / 'context.json'
    payload = {'version': 1, 'case': {'id': 'case'},
               'run': {'repetition': 1, 'output_dir': str(output), 'model_call_log_path': str(log)},
               'workspace': {'path': str(workspace)}, 'adapter': {'model': 'synthetic'}}
    context.write_text(json.dumps(payload))
    argv = ['--workspace', str(workspace), '--output-dir', str(output), '--case', 'case',
            '--repetition', '1', '--context', str(context)]
    return context, payload, marker, log, argv


@pytest.mark.parametrize('invalid', ['fifo', 'oversized', 'duplicate', 'nested-duplicate',
                                     'utf8', 'depth', 'version-bool', 'version-float',
                                     'repetition-bool', 'repetition-float'])
def test_reference_context_refused_before_artifacts(tmp_path, invalid):
    context, payload, marker, log, argv = handoff(tmp_path)
    if invalid == 'fifo':
        context.unlink()
        os.mkfifo(context)
    elif invalid == 'oversized':
        context.write_text(json.dumps(payload) + ' ' * (16 * 1024 * 1024))
    elif invalid == 'duplicate':
        context.write_text('{"version": 0,' + json.dumps(payload)[1:])
    elif invalid == 'nested-duplicate':
        context.write_text(json.dumps(payload).replace('"id": "case"', '"id":"other","id":"case"'))
    elif invalid == 'utf8':
        context.write_bytes(b'\xff')
    elif invalid == 'depth':
        context.write_text('[' * 2000 + ']' * 2000)
    else:
        field, kind = invalid.split('-')
        target = payload if field == 'version' else payload['run']
        target[field] = True if kind == 'bool' else 1.0
        context.write_text(json.dumps(payload))
    try:
        result = subprocess.run([sys.executable, str(SCRIPT), *argv], capture_output=True, timeout=3)
    except subprocess.TimeoutExpired:
        pytest.fail('reference context admission blocked')
    assert result.returncode == 2
    assert b'Traceback' not in result.stderr
    assert marker.read_bytes() == b'previous marker'
    assert log.read_bytes() == b'previous log'


def test_reference_missing_context_uses_fixed_diagnostic(tmp_path):
    _, _, marker, log, argv = handoff(tmp_path)
    missing = tmp_path / 'synthetic-missing-context.json'
    result = subprocess.run(
        [sys.executable, str(SCRIPT), *argv[:-1], str(missing)],
        capture_output=True, timeout=3,
    )

    assert result.returncode == 2
    assert result.stderr == b'reference-agent: could not read stable UTF-8 context\n'
    assert marker.read_bytes() == b'previous marker'
    assert log.read_bytes() == b'previous log'


def test_reference_context_in_place_mutation_is_refused(tmp_path, monkeypatch):
    from benchpack import safe_files
    context, _, marker, log, argv = handoff(tmp_path)
    read = safe_files.os.read
    changed = []
    def mutate(fd, size):
        data = read(fd, size)
        if data and not changed:
            changed.append(True)
            context.write_bytes(context.read_bytes() + b' ')
        return data
    monkeypatch.setattr(safe_files.os, 'read', mutate)
    assert agent().main(argv) == 2
    assert changed
    assert marker.read_bytes() == b'previous marker'
    assert log.read_bytes() == b'previous log'


def test_reference_context_exchange_keeps_one_opened_authority(tmp_path, monkeypatch):
    from benchpack import safe_files
    context, payload, marker, log, argv = handoff(tmp_path)
    payload['case']['id'] = 'wrong-old-case'
    context.write_text(json.dumps(payload))
    payload['case']['id'] = 'case'
    replacement = tmp_path / 'new-context'
    replacement.write_text(json.dumps(payload))
    read = safe_files.os.read
    changed = []
    def exchange(fd, size):
        data = read(fd, size)
        if data and not changed:
            changed.append(True)
            replacement.replace(context)
        return data
    monkeypatch.setattr(safe_files.os, 'read', exchange)
    assert agent().main(argv) == 2
    assert changed
    assert marker.read_bytes() == b'previous marker'
    assert log.read_bytes() == b'previous log'


@pytest.mark.parametrize('artifact', ['marker', 'log'])
@pytest.mark.parametrize('link', ['symlink', 'hardlink'])
def test_reference_refuses_linked_artifacts_without_writes(tmp_path, artifact, link):
    _, _, marker, log, argv = handoff(tmp_path)
    sentinel = tmp_path / 'outside'
    sentinel.write_bytes(b'outside sentinel')
    target = marker if artifact == 'marker' else log
    target.unlink()
    if link == 'symlink':
        target.symlink_to(sentinel)
    else:
        os.link(sentinel, target)
    assert agent().main(argv) == 2
    assert sentinel.read_bytes() == b'outside sentinel'
    other = log if artifact == 'marker' else marker
    assert other.read_bytes() == (b'previous log' if artifact == 'marker' else b'previous marker')


def test_reference_second_publication_failure_restores_both(tmp_path, monkeypatch):
    _, _, marker, log, argv = handoff(tmp_path)
    replace, write = os.replace, Path.write_text
    def fail_replace(src, dst, **kwargs):
        if dst == log.name:
            raise OSError('second publication failed')
        return replace(src, dst, **kwargs)
    def fail_write(path, *args, **kwargs):
        if path == log:
            raise OSError('second publication failed')
        return write(path, *args, **kwargs)
    monkeypatch.setattr(os, 'replace', fail_replace)
    monkeypatch.setattr(Path, 'write_text', fail_write)
    assert agent().main(argv) == 2
    assert marker.read_bytes() == b'previous marker'
    assert log.read_bytes() == b'previous log'
    assert not list(tmp_path.rglob('.benchpack-example-*.tmp'))


@pytest.mark.parametrize('when', ['encoding', 'staging'])
def test_reference_parent_exchange_never_writes_outside(tmp_path, monkeypatch, when):
    from benchpack import example_io
    _, _, marker, log, argv = handoff(tmp_path)
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / log.name).write_bytes(b'outside sentinel')
    moved = tmp_path / 'retired-task'
    changed = []
    def exchange():
        if not changed:
            changed.append(True)
            log.parent.rename(moved)
            log.parent.symlink_to(outside, target_is_directory=True)
    if when == 'encoding':
        dumps = json.dumps
        def encode(*args, **kwargs):
            exchange()
            return dumps(*args, **kwargs)
        monkeypatch.setattr(json, 'dumps', encode)
    else:
        stage = example_io._Target.stage
        def stage_then_exchange(self, *args, **kwargs):
            result = stage(self, *args, **kwargs)
            if self.name == log.name:
                exchange()
            return result
        monkeypatch.setattr(example_io._Target, 'stage', stage_then_exchange)
    assert agent().main(argv) == 2
    assert changed
    assert (outside / log.name).read_bytes() == b'outside sentinel'
    assert (moved / log.name).read_bytes() == b'previous log'
    assert marker.read_bytes() == b'previous marker'


def test_reference_rollback_failure_reports_retained_original(tmp_path, monkeypatch, capsys):
    _, _, marker, log, argv = handoff(tmp_path)
    replace = os.replace
    published = []
    def fail_replace(src, dst, **kwargs):
        if dst == log.name or (dst == marker.name and published):
            raise OSError('injected replacement failure')
        result = replace(src, dst, **kwargs)
        if dst == marker.name:
            published.append(True)
        return result
    monkeypatch.setattr(os, 'replace', fail_replace)
    assert agent().main(argv) == 2
    assert 'rollback failed' in capsys.readouterr().err
    assert log.read_bytes() == b'previous log'
    assert any(p.read_bytes() == b'previous marker' for p in marker.parent.glob('.benchpack-example-*.tmp'))
