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


def call_http(mod):
    if hasattr(mod, '_call_local_model'):
        return mod._call_local_model(url='http://127.0.0.1:8000/model', case_id='case', repetition=1, model='test')
    return mod._call_chat_completion(endpoint='http://127.0.0.1:8000/v1', api_key='synthetic', model='test', prompt='task', allowed_paths=('a',), timeout_s=1, temperature=0, max_tokens=10, token_budget_field='max_tokens', response_format='default')


@pytest.mark.parametrize('name', ['openai-direct-edit-agent', 'model-call-agent'])
def test_http_success_body_has_actual_byte_limit(name, monkeypatch):
    import io
    mod = agent(name)
    class Counting(io.BytesIO):
        def read1(self, n=-1):
            assert 0 < n <= 65536, 'unbounded HTTP response read'
            return super().read(n)
    monkeypatch.setattr('benchpack.example_http.open_response', lambda *a, **k: Counting(b'x' * (17 * 1024 * 1024)))
    with pytest.raises(ValueError):
        call_http(mod)


@pytest.mark.parametrize('name', ['openai-direct-edit-agent', 'model-call-agent'])
def test_http_redirect_never_reaches_second_origin(name):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import threading
    seen = []
    class Destination(BaseHTTPRequestHandler):
        def do_POST(self):
            seen.append(dict(self.headers))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{}')
        do_GET = do_POST
        def log_message(self, *args): pass
    destination = ThreadingHTTPServer(('127.0.0.1', 0), Destination)
    class Redirect(Destination):
        def do_POST(self):
            self.send_response(302)
            self.send_header('Location', f'http://127.0.0.1:{destination.server_port}/stolen')
            self.end_headers()
    source = ThreadingHTTPServer(('127.0.0.1', 0), Redirect)
    threads = [threading.Thread(target=s.serve_forever, daemon=True) for s in (source, destination)]
    for t in threads: t.start()
    mod = agent(name)
    try:
        if name == 'model-call-agent':
            mod._call_local_model(url=f'http://127.0.0.1:{source.server_port}/model', case_id='case', repetition=1, model='test')
        else:
            mod._call_chat_completion(endpoint=f'http://127.0.0.1:{source.server_port}/v1', api_key='synthetic', model='test', prompt='task', allowed_paths=('a',), timeout_s=1, temperature=0, max_tokens=10, token_budget_field='max_tokens', response_format='default')
    except ValueError:
        pass
    finally:
        for s in (source, destination): s.shutdown(); s.server_close()
        for t in threads: t.join()
    assert seen == []


def test_http_slow_drip_uses_shared_deadline(monkeypatch):
    from benchpack import example_http
    import io
    import urllib.request
    now = [0.0]
    class Slow(io.BytesIO):
        def read1(self, size):
            now[0] += .4
            return super().read(1)
    monkeypatch.setattr(example_http.time, 'monotonic', lambda: now[0])
    monkeypatch.setattr(example_http, 'open_response', lambda *a: Slow(b'{}'))
    with pytest.raises(ValueError, match='deadline'):
        example_http.response_bytes(urllib.request.Request('http://127.0.0.1/'), .5)


def test_http_error_body_is_not_read(monkeypatch):
    from benchpack import example_http
    import io
    import urllib.request
    class Error(io.BytesIO):
        status = 500
        def read1(self, size):
            pytest.fail('error body must not be acquired')
    monkeypatch.setattr(example_http, 'open_response', lambda *a: Error(b'private'))
    with pytest.raises(ValueError, match='status 500'):
        example_http.response_bytes(urllib.request.Request('http://127.0.0.1/'), 1)


@pytest.mark.parametrize('name', ['openai-direct-edit-agent', 'pi-agent'])
@pytest.mark.parametrize('text', [
    '{"files":[],"files":[]}',
    '{"files":[{"path":"a","path":"b","content":"x"}]}',
    '{"files":[{"path":"a","content":"x","content":"y"}]}',
])
def test_edit_json_refuses_duplicate_members(name, text):
    with pytest.raises(ValueError):
        agent(name)._parse_edit_payload(text)


@pytest.mark.parametrize('name', ['openai-direct-edit-agent', 'pi-agent', 'model-call-agent', 'codex-oss-agent'])
def test_context_json_refuses_duplicate_members(name, tmp_path):
    p = tmp_path / 'context.json'
    p.write_text('{"workspace":{},"workspace":{"path":"other"}}')
    with pytest.raises(ValueError):
        agent(name)._load_context(p)


@pytest.mark.parametrize('reason,model,error', [
    ('length', 'test', False), ('content_filter', 'test', False),
    (None, 'test', False), ('stop', 'other', False), ('stop', 'test', True),
])
def test_incomplete_or_wrong_completion_cannot_publish(reason, model, error, tmp_path, monkeypatch):
    import json
    mod = agent('openai-direct-edit-agent')
    (tmp_path / 'a').write_bytes(b'old')
    log = tmp_path / 'calls.jsonl'
    monkeypatch.setattr(mod, '_load_and_validate_context', lambda args: (tmp_path, tmp_path, log, 'Allowed repo-root paths to edit:\n- `a`'))
    response = {'model': model, 'choices': [{'finish_reason': reason, 'message': {'content': '{"files":[{"path":"a","content":"new"}]}'}}]}
    if error:
        response['error'] = {'message': 'synthetic'}
    monkeypatch.setattr(mod, '_call_chat_completion', lambda **kw: (response, .1))
    monkeypatch.setenv('SYNTHETIC_KEY', 'synthetic')
    result = mod.main(['--endpoint','http://127.0.0.1/v1','--model','test','--api-key-env','SYNTHETIC_KEY', '--workspace',str(tmp_path),'--output-dir',str(tmp_path),'--case','case','--repetition','1','--context','unused'])
    assert result != 0
    assert (tmp_path / 'a').read_bytes() == b'old'
    assert not json.loads(log.read_text())['ok']


def test_complete_response_admits_stop_and_optional_model():
    mod = agent('openai-direct-edit-agent')
    for extra in ({}, {'model': 'test'}, {'model': 'test-2025-04-14'}):
        response = {'choices': [{'finish_reason': 'stop'}], **extra}
        mod._require_complete_response(response, 'test')


@pytest.mark.parametrize('reported', ['other', 'test-mini', 'test-2025-04-14x', 'xtest', None, 7])
def test_complete_response_refuses_other_models(reported):
    mod = agent('openai-direct-edit-agent')
    with pytest.raises(ValueError, match='model does not match'):
        mod._require_complete_response({'model': reported, 'choices': [{'finish_reason': 'stop'}]}, 'test')


@pytest.mark.parametrize('name', ['openai-direct-edit-agent', 'model-call-agent'])
def test_remote_json_refuses_duplicate_model(name, monkeypatch):
    import io
    monkeypatch.setattr('benchpack.example_http.open_response', lambda *a: io.BytesIO(b'{"model":"test","model":"other"}'))
    with pytest.raises(ValueError):
        call_http(agent(name))


@pytest.mark.parametrize('name', ['openai-direct-edit-agent', 'pi-agent'])
def test_deep_edit_json_is_controlled(name):
    with pytest.raises(ValueError):
        agent(name)._parse_edit_payload('[' * 2000 + ']' * 2000)


def test_remote_refusal_and_finish_reason_do_not_leak(tmp_path):
    import json
    mod = agent('openai-direct-edit-agent')
    secret = 'SYNTHETIC_PRIVATE\x1b[31m'
    with pytest.raises(ValueError) as caught:
        mod._assistant_content({'choices': [{'message': {'refusal': secret}}]})
    assert 'SYNTHETIC_PRIVATE' not in str(caught.value)
    path = tmp_path / 'telemetry'
    mod._write_telemetry(path, model='test', endpoint='http://127.0.0.1', response_format='default', token_budget_field='max_tokens', duration_s=.1, ok=False, error=secret, response={'choices':[{'finish_reason': 'SYNTHETIC_PRIVATE'}]})
    assert 'SYNTHETIC_PRIVATE' not in path.read_text()


def make_context(tmp_path):
    import json
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    (workspace / 'a').write_bytes(b'old')
    output = tmp_path / 'output'
    output.mkdir()
    context = tmp_path / 'context.json'
    log = output / 'calls.jsonl'
    context.write_text(json.dumps({'version':1, 'case': {'id':'case', 'prompt':'Allowed repo-root paths to edit:\n- `a`'}, 'run': {'repetition':1, 'output_dir':str(output), 'model_call_log_path':str(log)}, 'workspace': {'path':str(workspace)}, 'adapter':{'model':'test'}}))
    argv = ['--workspace',str(workspace),'--output-dir',str(output),'--case','case','--repetition','1','--context',str(context)]
    return workspace, log, argv


@pytest.mark.parametrize('exit_code', [0, 7])
def test_pi_failed_output_is_private(tmp_path, capsys, exit_code):
    import json
    workspace, log, argv = make_context(tmp_path)
    exe = tmp_path / 'fake-pi'
    exe.write_text('#!/bin/sh\nprintf "SYNTHETIC_PRIVATE\\033[31m"\nprintf "SYNTHETIC_PRIVATE\\033[31m" >&2\nexit '+str(exit_code)+'\n')
    exe.chmod(0o755)
    result = agent('pi-agent').main(['--pi-bin',str(exe),'--model','test',*argv])
    assert result != 0
    captured = capsys.readouterr()
    assert 'SYNTHETIC_PRIVATE' not in captured.out + captured.err + log.read_text()
    assert '\x1b' not in captured.out + captured.err
    assert (workspace / 'a').read_bytes() == b'old'
    assert json.loads(log.read_text())['ok'] is False


def test_telemetry_leaf_exchange_during_call_is_refused(tmp_path, monkeypatch):
    import json
    workspace, log, argv = make_context(tmp_path)
    sentinel = tmp_path / 'outside'
    sentinel.write_bytes(b'outside')
    mod = agent('openai-direct-edit-agent')
    def call(**kwargs):
        log.symlink_to(sentinel)
        return {'choices':[{'finish_reason':'stop','message':{'content':'{"files":[]}'}}]}, .1
    monkeypatch.setattr(mod, '_call_chat_completion', call)
    monkeypatch.setenv('SYNTHETIC_KEY', 'synthetic')
    assert mod.main(['--endpoint','http://127.0.0.1','--model','test','--api-key-env','SYNTHETIC_KEY',*argv]) != 0
    assert sentinel.read_bytes() == b'outside'


def test_telemetry_replace_failure_keeps_previous_file(tmp_path, monkeypatch):
    import os
    mod = agent('openai-direct-edit-agent')
    path = tmp_path / 'telemetry'
    path.write_bytes(b'{"ok":true}\n')
    monkeypatch.setattr(os, 'replace', lambda *a, **kw: (_ for _ in ()).throw(OSError('injected')))
    with pytest.raises(OSError):
        mod._write_telemetry(path, model='test', endpoint='http://127.0.0.1', response_format='default', token_budget_field='max_tokens', duration_s=.1, ok=False)
    assert path.read_bytes() == b'{"ok":true}\n'


def test_telemetry_partial_stage_failure_is_atomic(tmp_path, monkeypatch):
    import os
    from benchpack.example_io import publish_telemetry
    path = tmp_path / 'calls'
    path.write_bytes(b'previous')
    original = os.fdopen
    class Partial:
        def __init__(self, fd, mode, **kwargs): self.stream = original(fd, mode, **kwargs)
        def __enter__(self): return self
        def __exit__(self, *args): self.stream.close()
        def close(self): self.stream.close()
        def write(self, data):
            self.stream.write(data[:2])
            return 2
    monkeypatch.setattr(os, 'fdopen', Partial)
    with pytest.raises(OSError, match='short'):
        publish_telemetry(path, '{"ok":true}\n')
    assert path.read_bytes() == b'previous'
    assert list(tmp_path.iterdir()) == [path]


def test_pi_primary_failure_survives_telemetry_failure(tmp_path, monkeypatch):
    _, _, argv = make_context(tmp_path)
    exe = tmp_path / 'fake-pi'
    exe.write_text('#!/bin/sh\nexit 7\n')
    exe.chmod(0o755)
    mod = agent('pi-agent')
    monkeypatch.setattr(mod, '_write_telemetry', lambda *a, **kw: (_ for _ in ()).throw(OSError('injected')))
    assert mod.main(['--pi-bin',str(exe),'--model','test',*argv]) == 7


@pytest.mark.parametrize('name', ['openai-direct-edit-agent','model-call-agent','codex-oss-agent','pi-agent'])
def test_context_opened_regular_byte_limit(name, tmp_path):
    path = tmp_path / 'context'
    with path.open('wb') as f:
        f.write(b'{}')
        f.write(b' ' * (16 * 1024 * 1024))
    with pytest.raises(ValueError):
        agent(name)._load_context(path)


@pytest.mark.parametrize('name', ['openai-direct-edit-agent','model-call-agent','codex-oss-agent','pi-agent'])
def test_context_fifo_refused_without_blocking(name, tmp_path):
    import os
    import subprocess
    import sys
    fifo = tmp_path / 'context'
    os.mkfifo(fifo)
    script = f'''import importlib.util
from pathlib import Path
s=importlib.util.spec_from_file_location('example',{str(ROOT / 'examples/external-agent' / (name+'.py'))!r})
m=importlib.util.module_from_spec(s); s.loader.exec_module(m)
try: m._load_context(Path({str(fifo)!r}))
except (OSError,ValueError): raise SystemExit(2)
'''
    try:
        result = subprocess.run([sys.executable, '-c', script], capture_output=True, timeout=1)
    except subprocess.TimeoutExpired:
        pytest.fail('context FIFO blocked before admission')
    assert result.returncode == 2


def test_context_in_place_change_is_refused(tmp_path, monkeypatch):
    import os
    path = tmp_path / 'context'
    path.write_bytes(b'{}')
    read = os.read
    changed = [False]
    def rewrite(fd, size):
        data = read(fd, size)
        if not changed[0]:
            changed[0] = True
            path.write_bytes(b'[]')
        return data
    monkeypatch.setattr(os, 'read', rewrite)
    with pytest.raises(ValueError):
        agent('openai-direct-edit-agent')._load_context(path)


@pytest.mark.parametrize('kind', ['symlink', 'fifo'])
def test_pi_data_inputs_refuse_nonregular_or_outside_paths(tmp_path, kind):
    import os
    mod = agent('pi-agent')
    (tmp_path / 'data').mkdir()
    target = tmp_path / 'data/train.csv'
    if kind == 'fifo': os.mkfifo(target)
    else:
        outside = tmp_path / 'outside'
        outside.write_text('private\nsynthetic\n')
        target.symlink_to(outside)
    with pytest.raises((ValueError, OSError)):
        mod._data_context(tmp_path, preview_rows=1)


def test_pi_context_aggregate_editable_limit(tmp_path, monkeypatch):
    mod = agent('pi-agent')
    monkeypatch.setattr(mod, 'MAX_EDITABLE_BYTES', 10, raising=False)
    for p in ('a','b'): (tmp_path / p).write_bytes(b'abcdef')
    with pytest.raises(ValueError):
        mod._allowed_file_context(tmp_path, ('a','b'))


def test_pi_csv_total_read_limit(tmp_path, monkeypatch):
    mod = agent('pi-agent')
    monkeypatch.setattr(mod, 'MAX_DATA_BYTES', 10, raising=False)
    (tmp_path / 'data').mkdir()
    for p in ('train.csv','test_pairs.csv'): (tmp_path / 'data' / p).write_bytes(b'h\na\nb\n')
    with pytest.raises(ValueError):
        mod._data_context(tmp_path, preview_rows=1)


def test_pi_preview_counts_full_file_with_bounded_reads(tmp_path, monkeypatch):
    import os
    mod = agent('pi-agent')
    path = tmp_path / 'data.csv'
    path.write_bytes(b'h\n' + b'a,b,c\n' * 100000)
    reads = []
    original = os.read
    def counting(fd, size):
        reads.append(size)
        return original(fd, size)
    monkeypatch.setattr(os, 'read', counting)
    monkeypatch.setattr(Path, 'read_text', lambda *a, **kw: pytest.fail('whole-file text read'))
    text, rows, truncated = mod._preview_text(path, max_rows=2)
    assert text == 'h\na,b,c\na,b,c'
    assert rows == 100000 and truncated
    assert max(reads) <= 65536


def test_pi_refuses_input_before_spawning(tmp_path, monkeypatch):
    import os
    workspace, _, argv = make_context(tmp_path)
    (workspace / 'data').mkdir()
    os.mkfifo(workspace / 'data/train.csv')
    mod = agent('pi-agent')
    monkeypatch.setattr(mod, 'run_agent', lambda *a, **kw: pytest.fail('agent spawned'))
    assert mod.main(['--model','test',*argv]) != 0


def test_codex_prompt_is_delivered_only_on_stdin(tmp_path):
    import json
    workspace, log, argv = make_context(tmp_path)
    context = Path(argv[-1])
    payload = json.loads(context.read_text())
    secret = 'SYNTHETIC_PRIVATE_' + 'x' * 300000
    payload['case']['prompt'] = secret
    context.write_text(json.dumps(payload))
    exe = tmp_path / 'fake-codex'
    record = tmp_path / 'record'
    exe.write_text('#!'+__import__('sys').executable+'\nimport sys,json\nfrom pathlib import Path\nPath('+repr(str(record))+').write_text(json.dumps({"argv":sys.argv,"stdin":sys.stdin.read()}))\n')
    exe.chmod(0o755)
    assert agent('codex-oss-agent').main(['--codex-bin',str(exe),'--codex-model','test',*argv]) == 0
    captured = json.loads(record.read_text())
    assert secret in captured['stdin']
    assert all('SYNTHETIC_PRIVATE' not in arg and 'x' * 1000 not in arg for arg in captured['argv'])
    assert captured['argv'][-1] == '-'


def test_pi_overlimit_valid_output_cannot_publish(tmp_path):
    import sys
    workspace, log, argv = make_context(tmp_path)
    exe = tmp_path / 'fake-pi'
    exe.write_text('#!'+sys.executable+'\nimport json\nprint(json.dumps({"files":[{"path":"a","content":"new"}], "summary":"x"*(17*1024*1024)}))\n')
    exe.chmod(0o755)
    assert agent('pi-agent').main(['--pi-bin',str(exe),'--model','test',*argv]) != 0
    assert (workspace / 'a').read_bytes() == b'old'


def test_pi_retires_pipe_holding_descendant_on_wrapper_exit(tmp_path):
    import os
    import signal
    import sys
    import time
    import psutil
    workspace, log, argv = make_context(tmp_path)
    pidfile = tmp_path / 'child'
    exe = tmp_path / 'fake-pi'
    exe.write_text('#!'+sys.executable+'\nimport os,time\nfrom pathlib import Path\npid=os.fork()\nif pid==0:\n time.sleep(5)\n os._exit(0)\nPath('+repr(str(pidfile))+').write_text(str(pid))\nprint(\'{"files":[]}\',flush=True)\n')
    exe.chmod(0o755)
    try:
        result = agent('pi-agent').main(['--pi-bin',str(exe),'--model','test','--timeout-s','1',*argv])
        pid = int(pidfile.read_text())
        for _ in range(20):
            try:
                process = psutil.Process(pid)
                alive = process.is_running() and process.status() != psutil.STATUS_ZOMBIE
            except psutil.NoSuchProcess:
                alive = False
            if not alive: break
            time.sleep(.01)
        assert not alive, 'owned descendant survived wrapper exit'
        assert result == 0
    finally:
        if pidfile.exists():
            try: os.kill(int(pidfile.read_text()), signal.SIGKILL)
            except ProcessLookupError: pass


def test_owned_transport_rejects_incomplete_stdin(tmp_path):
    import sys
    from benchpack.example_process import run_agent
    exe = tmp_path / 'early.py'
    exe.write_text('import os\nos.close(0)\n')
    with pytest.raises(ValueError, match='prompt'):
        run_agent([sys.executable, str(exe)], cwd=tmp_path, timeout_s=1, prompt=b'x' * 300000)


def test_owned_transport_delivers_short_stdin_writes(tmp_path, monkeypatch):
    import os
    import sys
    from benchpack.example_process import run_agent
    exe = tmp_path / 'read.py'
    exe.write_text('import sys\nprint(len(sys.stdin.buffer.read()))\n')
    write = os.write
    monkeypatch.setattr(os, 'write', lambda fd, data: write(fd, data[:17]))
    result = run_agent([sys.executable, str(exe)], cwd=tmp_path, timeout_s=3, prompt=b'x' * 300000)
    assert result.returncode == 0 and result.stdout.strip() == '300000'


def test_pi_timeout_retires_child_and_prompt(tmp_path, monkeypatch):
    import sys
    import psutil
    workspace, log, argv = make_context(tmp_path)
    pidfile = tmp_path / 'pid'
    exe = tmp_path / 'fake-pi'
    exe.write_text('#!'+sys.executable+'\nimport os,time\nfrom pathlib import Path\nPath('+repr(str(pidfile))+').write_text(str(os.getpid()))\ntime.sleep(10)\n')
    exe.chmod(0o755)
    mod = agent('pi-agent')
    monkeypatch.setattr(mod.tempfile, 'tempdir', str(tmp_path))
    assert mod.main(['--pi-bin',str(exe),'--model','test','--timeout-s','.2',*argv]) == 124
    assert not psutil.pid_exists(int(pidfile.read_text()))
    assert not list(tmp_path.glob('benchpack-pi-agent-*'))


def test_pi_prompt_removed_after_staging_failure(tmp_path, monkeypatch):
    mod = agent('pi-agent')
    _, _, argv = make_context(tmp_path)
    monkeypatch.setattr(mod.tempfile, 'tempdir', str(tmp_path))
    create = mod.tempfile.NamedTemporaryFile
    class Broken:
        def __init__(self, *a, **kw):
            self.file = create(*a, **kw)
            self.name = self.file.name
        def __enter__(self): return self
        def __exit__(self, *args): self.file.close()
        def write(self, data):
            self.file.write(data[:2])
            raise OSError('injected')
    monkeypatch.setattr(mod.tempfile, 'NamedTemporaryFile', Broken)
    assert mod.main(['--model','test',*argv]) != 0
    assert not list(tmp_path.glob('benchpack-pi-agent-*'))


def test_pi_signal_retires_child_and_prompt(tmp_path):
    import os
    import signal
    import subprocess
    import sys
    import time
    import psutil
    _, _, argv = make_context(tmp_path)
    pidfile = tmp_path / 'pid'
    exe = tmp_path / 'fake-pi'
    exe.write_text('#!'+sys.executable+'\nimport os,time\nfrom pathlib import Path\nPath('+repr(str(pidfile))+').write_text(str(os.getpid()))\ntime.sleep(10)\n')
    exe.chmod(0o755)
    wrapper = ROOT / 'examples/external-agent/pi-agent.py'
    env = {**os.environ, 'TMPDIR':str(tmp_path)}
    process = subprocess.Popen([sys.executable,str(wrapper),'--pi-bin',str(exe),'--model','test',*argv], stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    try:
        until = time.monotonic() + 3
        while not pidfile.exists() and time.monotonic() < until:
            time.sleep(.01)
        assert pidfile.exists()
        process.send_signal(signal.SIGTERM)
        process.communicate(timeout=3)
        assert process.returncode == 143
        assert not psutil.pid_exists(int(pidfile.read_text()))
        assert not list(tmp_path.glob('benchpack-pi-agent-*'))
    finally:
        if process.poll() is None:
            process.kill(); process.communicate(timeout=1)
        if pidfile.exists():
            try: os.kill(int(pidfile.read_text()), signal.SIGKILL)
            except ProcessLookupError: pass


def test_workspace_rollback_does_not_overwrite_newer_leaf(tmp_path, monkeypatch):
    import os
    from benchpack.example_io import replace_workspace_files
    for p in ('a','b'): (tmp_path / p).write_bytes(p.encode())
    replace = os.replace
    def concurrent(src, dst, **kwargs):
        if dst == 'b':
            raise OSError('second publication failed')
        result = replace(src, dst, **kwargs)
        if dst == 'a':
            (tmp_path / 'a').unlink()
            (tmp_path / 'a').write_bytes(b'newer concurrent generation')
        return result
    monkeypatch.setattr(os, 'replace', concurrent)
    with pytest.raises(ValueError, match='rollback failed'):
        replace_workspace_files(tmp_path, [('a',b'new'),('b',b'new')])
    assert (tmp_path / 'a').read_bytes() == b'newer concurrent generation'
    backups = list(tmp_path.glob('.benchpack-example-*.tmp'))
    assert any(p.read_bytes() == b'a' for p in backups)


def test_replacement_admission_failure_is_value_error(tmp_path):
    import os
    from benchpack.example_io import replace_workspace_files
    root = tmp_path / 'root'
    root.mkdir()
    (tmp_path / 'sentinel').write_bytes(b'outside')
    os.link(tmp_path / 'sentinel', root / 'a')
    with pytest.raises(ValueError, match='could not stage'):
        replace_workspace_files(root, [('a', b'new')])
    assert (tmp_path / 'sentinel').read_bytes() == b'outside'


def test_replacement_publication_keeps_interrupts(tmp_path, monkeypatch):
    import os
    from benchpack.example_io import replace_workspace_files
    (tmp_path / 'a').write_bytes(b'old')
    def interrupted(*args, **kwargs):
        raise SystemExit(143)
    monkeypatch.setattr(os, 'replace', interrupted)
    with pytest.raises(SystemExit):
        replace_workspace_files(tmp_path, [('a', b'new')])
    assert (tmp_path / 'a').read_bytes() == b'old'


def test_pi_edit_admission_failure_writes_failure_telemetry(tmp_path, capsys):
    import json
    import os
    import sys
    workspace, log, argv = make_context(tmp_path)
    (workspace / 'a').unlink()
    (tmp_path / 'sentinel').write_bytes(b'outside')
    os.link(tmp_path / 'sentinel', workspace / 'a')
    exe = tmp_path / 'fake-pi'
    exe.write_text('#!'+sys.executable+'\nimport json\nprint(json.dumps({"files":[{"path":"a","content":"new"}]}))\n')
    exe.chmod(0o755)
    assert agent('pi-agent').main(['--pi-bin',str(exe),'--model','test',*argv]) != 0
    assert 'could not run pi' not in capsys.readouterr().err
    assert json.loads(log.read_text())['ok'] is False
    assert (tmp_path / 'sentinel').read_bytes() == b'outside'


def test_direct_edit_failure_telemetry_admission_keeps_primary_failure(tmp_path, monkeypatch, capsys):
    mod = agent('openai-direct-edit-agent')
    workspace, log, argv = make_context(tmp_path)
    log.write_bytes(b'x' * (16 * 1024 * 1024 + 1))
    monkeypatch.setenv('SYNTHETIC_KEY', 'synthetic')
    assert mod.main(['--endpoint','http://127.0.0.1','--model','test','--api-key-env','SYNTHETIC_KEY',*argv]) != 0
    assert 'byte limit' in capsys.readouterr().err
    assert (workspace / 'a').read_bytes() == b'old'


def test_pi_signal_after_child_still_removes_private_prompt(tmp_path, monkeypatch):
    import os
    import signal
    import tempfile
    mod = agent('pi-agent')
    workspace, log, argv = make_context(tmp_path)
    prompts = tmp_path / 'tmp'
    prompts.mkdir()
    monkeypatch.setattr(tempfile, 'tempdir', str(prompts))
    def finished(command, **kwargs):
        import subprocess
        os.kill(os.getpid(), signal.SIGTERM)
        return subprocess.CompletedProcess(command, 0, '{"files":[]}', '')
    monkeypatch.setattr(mod, 'run_agent', finished)
    previous = signal.getsignal(signal.SIGTERM)
    with pytest.raises(SystemExit):
        mod.main(['--pi-bin','pi','--model','test',*argv])
    assert signal.getsignal(signal.SIGTERM) == previous
    assert not list(prompts.glob('benchpack-pi-agent-*'))


def test_replacement_interrupt_with_failed_rollback_keeps_interrupt(tmp_path, monkeypatch):
    import os
    from benchpack.example_io import replace_workspace_files
    for name in ('a', 'b'):
        (tmp_path / name).write_bytes(name.encode())
    replace = os.replace
    def interrupted(src, dst, **kwargs):
        if dst == 'b':
            raise SystemExit(143)
        result = replace(src, dst, **kwargs)
        if dst == 'a':
            (tmp_path / 'a').unlink()
            (tmp_path / 'a').write_bytes(b'newer')
        return result
    monkeypatch.setattr(os, 'replace', interrupted)
    with pytest.raises(SystemExit) as caught:
        replace_workspace_files(tmp_path, [('a', b'new'), ('b', b'new')])
    assert any('rollback failed' in note for note in getattr(caught.value, '__notes__', []))
    assert (tmp_path / 'a').read_bytes() == b'newer'


def test_termination_scope_respects_ignored_signals():
    import signal
    from benchpack.example_process import exit_on_termination_signals
    previous = signal.signal(signal.SIGHUP, signal.SIG_IGN)
    try:
        with exit_on_termination_signals():
            assert signal.getsignal(signal.SIGHUP) is signal.SIG_IGN
            assert signal.getsignal(signal.SIGTERM) is not signal.SIG_DFL
    finally:
        signal.signal(signal.SIGHUP, previous)
