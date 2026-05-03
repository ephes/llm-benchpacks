"""End-to-end CLI smoke test using a mocked adapter."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import httpx
import pytest

from benchpack import adapters as adapters_pkg
from benchpack.adapters import (
    AdapterRequest,
    AdapterResult,
    RawPaths,
    Timing,
    Tokens,
)
from benchpack.adapters.openai_chat import (
    OpenAIChatAdapter,
    OPENAI_STREAM_USAGE_INCLUDE,
    OPENAI_STREAM_USAGE_KEY,
    OPENAI_STREAM_USAGE_OMIT,
)
from benchpack.cli import main
from benchpack.packs import InvalidHarnessError


NO_PATCH_TASK_STDERR = (
    "No fenced diff or patch block found in model output; "
    "workspace left unchanged.\n"
)


def _install_fake_adapter(monkeypatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": "Paris."}}],
                "usage": {"prompt_tokens": 7, "completion_tokens": 2},
            },
        )

    transport = httpx.MockTransport(handler)

    class FakeAdapter(OpenAIChatAdapter):
        def __init__(self) -> None:
            super().__init__(transport=transport)

    monkeypatch.setitem(adapters_pkg.ADAPTERS, "openai-chat", FakeAdapter)
    return calls


def _install_recording_adapter(monkeypatch) -> list[dict[str, str]]:
    calls: list[dict[str, str]] = []

    class RecordingAdapter:
        name = "openai-chat"

        def run(self, request: AdapterRequest) -> AdapterResult:
            calls.append(
                {
                    "prompt": request.prompt,
                    "request_path": request.request_path.name,
                    "response_path": request.response_path.name,
                }
            )
            request.request_path.write_text(json.dumps({"prompt": request.prompt}))
            request.response_path.write_text(
                json.dumps(
                    {
                        "choices": [
                            {"message": {"role": "assistant", "content": "Paris."}}
                        ],
                        "usage": {"prompt_tokens": 7, "completion_tokens": 2},
                    }
                )
            )
            return AdapterResult(
                adapter=self.name,
                endpoint="http://example.test/v1/chat/completions",
                model=request.model,
                ok=True,
                timing=Timing(wall_s=1.0),
                tokens=Tokens(prompt=7, output=2),
                raw=RawPaths(
                    request_path=str(request.request_path),
                    response_path=str(request.response_path),
                ),
                output_text="Paris.",
            )

    monkeypatch.setitem(adapters_pkg.ADAPTERS, "openai-chat", RecordingAdapter)
    return calls


def _install_output_adapter(monkeypatch, output_text: str) -> list[dict[str, str]]:
    calls: list[dict[str, str]] = []

    class OutputAdapter:
        name = "openai-chat"

        def run(self, request: AdapterRequest) -> AdapterResult:
            calls.append(
                {
                    "prompt": request.prompt,
                    "request_path": request.request_path.name,
                    "response_path": request.response_path.name,
                }
            )
            request.request_path.write_text(json.dumps({"prompt": request.prompt}))
            request.response_path.write_text(
                json.dumps(
                    {
                        "choices": [
                            {
                                "message": {
                                    "role": "assistant",
                                    "content": output_text,
                                }
                            }
                        ],
                        "usage": {"prompt_tokens": 7, "completion_tokens": 2},
                    }
                )
            )
            return AdapterResult(
                adapter=self.name,
                endpoint="http://example.test/v1/chat/completions",
                model=request.model,
                ok=True,
                timing=Timing(wall_s=1.0),
                tokens=Tokens(prompt=7, output=2),
                raw=RawPaths(
                    request_path=str(request.request_path),
                    response_path=str(request.response_path),
                ),
                output_text=output_text,
            )

    monkeypatch.setitem(adapters_pkg.ADAPTERS, "openai-chat", OutputAdapter)
    return calls


def _install_defaults_recording_adapter(monkeypatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    class RecordingAdapter:
        name = "openai-chat"

        def run(self, request: AdapterRequest) -> AdapterResult:
            calls.append(
                {
                    "request_path": request.request_path.name,
                    "defaults": dict(request.defaults),
                }
            )
            request.request_path.write_text(json.dumps({"prompt": request.prompt}))
            request.response_path.write_text(json.dumps({"choices": []}))
            return AdapterResult(
                adapter=self.name,
                endpoint="http://example.test/v1/chat/completions",
                model=request.model,
                ok=True,
                timing=Timing(wall_s=1.0),
                tokens=Tokens(),
                raw=RawPaths(
                    request_path=str(request.request_path),
                    response_path=str(request.response_path),
                ),
            )

    monkeypatch.setitem(adapters_pkg.ADAPTERS, "openai-chat", RecordingAdapter)
    return calls


def _write_smoke_pack(tmp_path: Path, defaults_extra: str = "") -> None:
    pack_dir = tmp_path / "benchpacks" / "smoke-chat"
    pack_dir.mkdir(parents=True)
    (pack_dir / "benchpack.toml").write_text(
        f"""
[pack]
id = "smoke-chat"
version = "0.1.0"

[defaults]
temperature = 0
max_tokens = 32
stream = false
{defaults_extra}

[[cases]]
id = "capital"
kind = "chat"
prompt = "What is the capital of France?"

[scoring]
mode = "contains"
expected = "Paris"
"""
    )


def _write_streaming_pack(tmp_path: Path, defaults_extra: str = "") -> None:
    pack_dir = tmp_path / "benchpacks" / "smoke-chat"
    pack_dir.mkdir(parents=True)
    (pack_dir / "benchpack.toml").write_text(
        f"""
[pack]
id = "smoke-chat"
version = "0.1.0"

[defaults]
temperature = 0
max_tokens = 32
stream = true
{defaults_extra}

[[cases]]
id = "capital"
kind = "chat"
prompt = "What is the capital of France?"

[scoring]
mode = "none"
"""
    )


def _write_two_case_pack(tmp_path: Path, defaults_extra: str = "") -> None:
    pack_dir = tmp_path / "benchpacks" / "smoke-chat"
    pack_dir.mkdir(parents=True)
    (pack_dir / "benchpack.toml").write_text(
        f"""
[pack]
id = "smoke-chat"
version = "0.1.0"

[defaults]
temperature = 0
max_tokens = 32
stream = false
{defaults_extra}

[[cases]]
id = "alpha"
kind = "chat"
prompt = "Prompt A"

[[cases]]
id = "beta"
kind = "chat"
prompt = "Prompt B"

[scoring]
mode = "contains"
expected = "Paris"
"""
    )


def _write_repo_task_pack(
    tmp_path: Path,
    *,
    defaults_extra: str = "",
    fixture_entries: str | None = None,
    fixture_refs: str = '["repo"]',
    case_kind: str = "repo-task",
    case_extra: str = "",
    scoring: str | None = None,
) -> Path:
    pack_dir = tmp_path / "benchpacks" / "smoke-chat"
    pack_dir.mkdir(parents=True)
    fixtures_dir = pack_dir / "fixtures"
    repo_dir = fixtures_dir / "repo"
    repo_dir.mkdir(parents=True)
    (repo_dir / "README.md").write_text("source repo\n", encoding="utf-8")

    if fixture_entries is None:
        fixture_entries = """
[[fixtures]]
id = "repo"
kind = "repo"
path = "fixtures/repo"
"""
    if scoring is None:
        scoring = """
[scoring]
mode = "contains"
expected = "Paris"
"""

    (pack_dir / "benchpack.toml").write_text(
        f"""
[pack]
id = "smoke-chat"
version = "0.1.0"

[defaults]
temperature = 0
max_tokens = 32
stream = false
{defaults_extra}

{fixture_entries}

[[cases]]
id = "edit-repo"
kind = "{case_kind}"
prompt = "Change the repository."
fixture_refs = {fixture_refs}
{case_extra}

{scoring}
"""
    )
    return pack_dir


def _write_verifier_script(pack_dir: Path, body: str) -> Path:
    script = pack_dir / "verify" / "check.py"
    script.parent.mkdir(parents=True)
    script.write_text(body, encoding="utf-8")
    return script


def _argv(extra: list[str] | None = None) -> list[str]:
    return [
        "run",
        "smoke-chat",
        "--adapter",
        "openai-chat",
        "--model",
        "test-model",
        "--endpoint",
        "http://example.test/v1",
        "--host-label",
        "unit-test",
        *(extra or []),
    ]


def _patch_from_failure_argv(extra: list[str] | None = None) -> list[str]:
    return [
        "run",
        "patch-from-failure",
        "--adapter",
        "openai-chat",
        "--model",
        "test-model",
        "--endpoint",
        "http://example.test/v1",
        "--host-label",
        "unit-test",
        *(extra or []),
    ]


def test_cli_run_produces_full_artifact_tree(tmp_path: Path, monkeypatch) -> None:
    _install_fake_adapter(monkeypatch)
    monkeypatch.chdir(tmp_path)
    _write_smoke_pack(tmp_path)

    rc = main(_argv())
    assert rc == 0

    out_dirs = list((tmp_path / "results").iterdir())
    assert len(out_dirs) == 1
    out = out_dirs[0]
    assert out.name.endswith("-unit-test")

    assert (out / "run.jsonl").exists()
    assert (out / "summary.md").exists()
    assert (out / "hardware.json").exists()
    assert (out / "raw").is_dir()
    assert (out / "raw" / "capital.request.json").exists()
    assert (out / "raw" / "capital.response.json").exists()

    record = json.loads((out / "run.jsonl").read_text().strip())
    # The combined record must carry the documented fields.
    assert record["pack"] == {"id": "smoke-chat", "version": "0.1.0"}
    assert record["case"] == "capital"
    assert record["adapter"] == "openai-chat"
    assert record["endpoint"] == "http://example.test/v1/chat/completions"
    assert record["scoring"] == {"mode": "contains", "passed": True}
    assert record["raw"]["request_path"] == "raw/capital.request.json"
    assert record["resources"].keys() == {"memory_mb", "gpu_memory_mb"}
    assert "repetition" not in record


def test_cli_repetitions_write_distinct_measured_records(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _install_fake_adapter(monkeypatch)
    monkeypatch.chdir(tmp_path)
    _write_smoke_pack(tmp_path, defaults_extra="repetitions = 2")

    assert main(_argv()) == 0

    out = next((tmp_path / "results").iterdir())
    records = [
        json.loads(line)
        for line in (out / "run.jsonl").read_text().strip().splitlines()
    ]
    assert [record["repetition"] for record in records] == [1, 2]
    assert [record["raw"]["request_path"] for record in records] == [
        "raw/capital.rep-001.request.json",
        "raw/capital.rep-002.request.json",
    ]
    assert (out / "raw" / "capital.rep-001.request.json").exists()
    assert (out / "raw" / "capital.rep-001.response.json").exists()
    assert (out / "raw" / "capital.rep-002.request.json").exists()
    assert (out / "raw" / "capital.rep-002.response.json").exists()
    assert not (out / "raw" / "capital.request.json").exists()

    summary = (out / "summary.md").read_text()
    assert "capital#1" in summary
    assert "capital#2" in summary


def test_cli_repo_task_creates_run_owned_workspace(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _install_fake_adapter(monkeypatch)
    monkeypatch.chdir(tmp_path)
    _write_repo_task_pack(tmp_path)
    out = tmp_path / "run"

    assert main(_argv(["--out", str(out)])) == 0

    workspace = out / "workspace" / "edit-repo" / "rep-001"
    assert workspace.is_dir()
    assert (workspace / "README.md").read_text(encoding="utf-8") == "source repo\n"

    record = json.loads((out / "run.jsonl").read_text())
    assert record["case"] == "edit-repo"
    assert record["pack"] == {"id": "smoke-chat", "version": "0.1.0"}
    assert record["adapter"] == "openai-chat"
    assert record["scoring"] == {"mode": "contains", "passed": True}
    assert record["raw"] == {
        "request_path": "raw/edit-repo.request.json",
        "response_path": "raw/edit-repo.response.json",
    }
    assert record["workspace"] == {
        "path": "workspace/edit-repo/rep-001",
        "source_fixture_id": "repo",
        "source_path": "fixtures/repo",
    }
    assert record["patch"] == {"path": "patch/edit-repo/rep-001.diff"}
    assert record["task"] == {
        "stdout_path": "task/edit-repo/rep-001.stdout.log",
        "stderr_path": "task/edit-repo/rep-001.stderr.log",
    }
    assert (out / "patch" / "edit-repo" / "rep-001.diff").read_text(
        encoding="utf-8"
    ) == ""
    assert (out / record["task"]["stdout_path"]).read_text(encoding="utf-8") == ""
    assert (
        out / record["task"]["stderr_path"]
    ).read_text(encoding="utf-8") == NO_PATCH_TASK_STDERR
    assert "verify" not in record
    assert "repo_task" not in record
    assert "artifacts" not in record


def test_cli_repo_task_applies_fenced_diff_before_patch_capture(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output = """Applied change.

```diff
--- a/README.md
+++ b/README.md
@@ -1 +1 @@
-source repo
+patched repo
```
"""
    _install_output_adapter(monkeypatch, output)
    monkeypatch.chdir(tmp_path)
    _write_repo_task_pack(tmp_path, scoring='[scoring]\nmode = "none"\n')
    out = tmp_path / "run"

    assert main(_argv(["--out", str(out)])) == 0

    workspace = out / "workspace" / "edit-repo" / "rep-001"
    assert (workspace / "README.md").read_text(encoding="utf-8") == "patched repo\n"
    source = tmp_path / "benchpacks" / "smoke-chat" / "fixtures" / "repo" / "README.md"
    assert source.read_text(encoding="utf-8") == "source repo\n"

    record = json.loads((out / "run.jsonl").read_text())
    assert record["task"] == {
        "stdout_path": "task/edit-repo/rep-001.stdout.log",
        "stderr_path": "task/edit-repo/rep-001.stderr.log",
    }
    assert (out / record["task"]["stdout_path"]).read_text(encoding="utf-8") == (
        "Applied fenced model patch to workspace.\n"
    )
    assert (out / record["task"]["stderr_path"]).read_text(encoding="utf-8") == ""
    assert (out / record["patch"]["path"]).read_text(encoding="utf-8") == (
        "--- a/README.md\n"
        "+++ b/README.md\n"
        "@@ -1 +1 @@\n"
        "-source repo\n"
        "+patched repo\n"
    )
    assert "artifacts" not in record


def test_cli_repo_task_explicit_fenced_patch_harness_matches_default_shape(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output = """Applied change.

```diff
--- a/README.md
+++ b/README.md
@@ -1 +1 @@
-source repo
+patched repo
```
"""
    _install_output_adapter(monkeypatch, output)
    monkeypatch.chdir(tmp_path)
    _write_repo_task_pack(
        tmp_path,
        case_extra='harness = { id = "fenced-patch", timeout_s = 2.5 }',
        scoring='[scoring]\nmode = "none"\n',
    )
    out = tmp_path / "run"

    assert main(_argv(["--out", str(out)])) == 0

    record = json.loads((out / "run.jsonl").read_text())
    assert record["raw"] == {
        "request_path": "raw/edit-repo.request.json",
        "response_path": "raw/edit-repo.response.json",
    }
    assert record["workspace"] == {
        "path": "workspace/edit-repo/rep-001",
        "source_fixture_id": "repo",
        "source_path": "fixtures/repo",
    }
    assert record["patch"] == {"path": "patch/edit-repo/rep-001.diff"}
    assert record["task"] == {
        "stdout_path": "task/edit-repo/rep-001.stdout.log",
        "stderr_path": "task/edit-repo/rep-001.stderr.log",
    }
    assert "verify" not in record
    assert "repo_task" not in record
    assert "artifacts" not in record
    assert (out / record["task"]["stdout_path"]).read_text(encoding="utf-8") == (
        "Applied fenced model patch to workspace.\n"
    )
    assert (out / record["task"]["stderr_path"]).read_text(encoding="utf-8") == ""
    assert (out / record["patch"]["path"]).read_text(encoding="utf-8") == (
        "--- a/README.md\n"
        "+++ b/README.md\n"
        "@@ -1 +1 @@\n"
        "-source repo\n"
        "+patched repo\n"
    )


def test_cli_invalid_harness_manifest_fails_before_execution(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls = _install_output_adapter(monkeypatch, "unused")
    monkeypatch.chdir(tmp_path)
    _write_repo_task_pack(
        tmp_path,
        case_extra='harness = { id = "external-agent" }',
    )
    out = tmp_path / "run"

    with pytest.raises(InvalidHarnessError, match="external-agent"):
        main(_argv(["--out", str(out)]))

    assert calls == []
    assert not out.exists()


def test_cli_invalid_harness_timeout_manifest_fails_before_execution(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls = _install_output_adapter(monkeypatch, "unused")
    monkeypatch.chdir(tmp_path)
    _write_repo_task_pack(
        tmp_path,
        case_extra='harness = { id = "fenced-patch", timeout_s = "slow" }',
    )
    out = tmp_path / "run"

    with pytest.raises(InvalidHarnessError, match="harness.timeout_s"):
        main(_argv(["--out", str(out)]))

    assert calls == []
    assert not out.exists()


def test_cli_repo_task_harness_timeout_preflight_keeps_patch_then_verify_order(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output = """```diff
--- a/README.md
+++ b/README.md
@@ -1 +1 @@
-source repo
+patched repo
```
"""
    _install_output_adapter(monkeypatch, output)
    monkeypatch.chdir(tmp_path)
    pack_dir = _write_repo_task_pack(
        tmp_path,
        case_extra='harness = { id = "fenced-patch", timeout_s = 0.1 }',
        scoring='[scoring]\nmode = "verify-script"\nscript = "verify/check.py"\n',
    )
    _write_verifier_script(
        pack_dir,
        """
import argparse
import json
from pathlib import Path
parser = argparse.ArgumentParser()
parser.add_argument("--workspace")
parser.add_argument("--case")
parser.add_argument("--pack-id")
parser.add_argument("--pack-version")
parser.add_argument("--source-fixture-id")
parser.add_argument("--patch")
parser.add_argument("--output")
args = parser.parse_args()
content = Path(args.workspace, "README.md").read_text(encoding="utf-8")
patch_text = Path(args.patch).read_text(encoding="utf-8")
if content != "source repo\\n":
    raise SystemExit(2)
if patch_text != "":
    raise SystemExit(3)
with open(args.output, "w", encoding="utf-8") as fh:
    json.dump({"content": content, "patch_text": patch_text}, fh)
""",
    )
    real_run = subprocess.run
    timeouts: list[float] = []

    def timeout_task_preflight(command, *args, **kwargs):
        if command == ["git", "apply", "--check", "--whitespace=nowarn"]:
            timeouts.append(kwargs["timeout"])
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])
        return real_run(command, *args, **kwargs)

    monkeypatch.setattr("benchpack.tasks.subprocess.run", timeout_task_preflight)
    out = tmp_path / "run"

    assert main(_argv(["--out", str(out)])) == 0

    record = json.loads((out / "run.jsonl").read_text())
    assert record["raw"] == {
        "request_path": "raw/edit-repo.request.json",
        "response_path": "raw/edit-repo.response.json",
    }
    assert record["workspace"] == {
        "path": "workspace/edit-repo/rep-001",
        "source_fixture_id": "repo",
        "source_path": "fixtures/repo",
    }
    assert record["patch"] == {"path": "patch/edit-repo/rep-001.diff"}
    assert record["task"] == {
        "stdout_path": "task/edit-repo/rep-001.stdout.log",
        "stderr_path": "task/edit-repo/rep-001.stderr.log",
    }
    assert record["verify"] == {
        "path": "verify/edit-repo/rep-001.json",
        "stdout_path": "verify/edit-repo/rep-001.stdout.log",
        "stderr_path": "verify/edit-repo/rep-001.stderr.log",
    }
    assert record["repo_task"] == {"status": "passed", "verify_exit_code": 0}
    assert record["scoring"] == {"mode": "verify-script", "passed": True}
    assert "artifacts" not in record
    assert timeouts == [0.1]
    assert (out / record["patch"]["path"]).read_text(encoding="utf-8") == ""
    assert (out / record["task"]["stdout_path"]).read_text(encoding="utf-8") == ""
    assert (out / record["task"]["stderr_path"]).read_text(encoding="utf-8") == (
        "Patch rejected: git apply --check timed out; workspace left unchanged.\n"
    )
    assert json.loads((out / record["verify"]["path"]).read_text()) == {
        "content": "source repo\n",
        "exit_code": 0,
        "passed": True,
        "patch_text": "",
    }


def test_cli_repo_task_verify_script_observes_applied_diff(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output = """```diff
--- a/README.md
+++ b/README.md
@@ -1 +1 @@
-source repo
+verified repo
```
"""
    _install_output_adapter(monkeypatch, output)
    monkeypatch.chdir(tmp_path)
    pack_dir = _write_repo_task_pack(
        tmp_path,
        scoring='[scoring]\nmode = "verify-script"\nscript = "verify/check.py"\n',
    )
    _write_verifier_script(
        pack_dir,
        """
import argparse
import json
from pathlib import Path
parser = argparse.ArgumentParser()
parser.add_argument("--workspace")
parser.add_argument("--case")
parser.add_argument("--pack-id")
parser.add_argument("--pack-version")
parser.add_argument("--source-fixture-id")
parser.add_argument("--patch")
parser.add_argument("--output")
args = parser.parse_args()
content = Path(args.workspace, "README.md").read_text(encoding="utf-8")
if content != "verified repo\\n":
    raise SystemExit(2)
with open(args.output, "w", encoding="utf-8") as fh:
    json.dump({"content": content}, fh)
""",
    )
    out = tmp_path / "run"

    assert main(_argv(["--out", str(out)])) == 0

    record = json.loads((out / "run.jsonl").read_text())
    assert record["repo_task"] == {"status": "passed", "verify_exit_code": 0}
    assert record["scoring"] == {"mode": "verify-script", "passed": True}
    assert json.loads((out / record["verify"]["path"]).read_text()) == {
        "content": "verified repo\n",
        "exit_code": 0,
        "passed": True,
    }
    assert (out / record["task"]["stderr_path"]).read_text(encoding="utf-8") == ""


def test_cli_bundled_patch_from_failure_runs_repo_task_flow(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output = """```diff
--- a/greeter.py
+++ b/greeter.py
@@ -1,2 +1,2 @@
 def greet(name: str) -> str:
-    return f"Hello {name}."
+    return f"Hello, {name}!"
```
"""
    calls = _install_output_adapter(monkeypatch, output)
    repo_root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(repo_root)
    out = tmp_path / "run"

    assert main(_patch_from_failure_argv(["--out", str(out)])) == 0

    workspace_file = out / "workspace" / "fix-greeting" / "rep-001" / "greeter.py"
    assert workspace_file.read_text(encoding="utf-8") == (
        'def greet(name: str) -> str:\n    return f"Hello, {name}!"\n'
    )
    source_file = (
        repo_root
        / "benchpacks"
        / "patch-from-failure"
        / "fixtures"
        / "repo"
        / "greeter.py"
    )
    assert source_file.read_text(encoding="utf-8") == (
        'def greet(name: str) -> str:\n    return f"Hello {name}."\n'
    )

    assert len(calls) == 1
    assert calls[0]["request_path"] == "fix-greeting.request.json"
    assert "Return only one fenced code block" in calls[0]["prompt"]
    assert "`greeter.py`" in calls[0]["prompt"]

    record = json.loads((out / "run.jsonl").read_text())
    assert record["pack"] == {"id": "patch-from-failure", "version": "0.1.0"}
    assert record["case"] == "fix-greeting"
    assert record["adapter"] == "openai-chat"
    assert record["raw"] == {
        "request_path": "raw/fix-greeting.request.json",
        "response_path": "raw/fix-greeting.response.json",
    }
    assert record["workspace"] == {
        "path": "workspace/fix-greeting/rep-001",
        "source_fixture_id": "repo",
        "source_path": "fixtures/repo",
    }
    assert record["patch"] == {"path": "patch/fix-greeting/rep-001.diff"}
    assert record["task"] == {
        "stdout_path": "task/fix-greeting/rep-001.stdout.log",
        "stderr_path": "task/fix-greeting/rep-001.stderr.log",
    }
    assert record["verify"] == {
        "path": "verify/fix-greeting/rep-001.json",
        "stdout_path": "verify/fix-greeting/rep-001.stdout.log",
        "stderr_path": "verify/fix-greeting/rep-001.stderr.log",
    }
    assert record["repo_task"] == {"status": "passed", "verify_exit_code": 0}
    assert record["scoring"] == {"mode": "verify-script", "passed": True}
    assert "artifacts" not in record

    patch = (out / record["patch"]["path"]).read_text(encoding="utf-8")
    assert patch
    assert "--- a/greeter.py" in patch
    assert '+    return f"Hello, {name}!"' in patch
    assert (out / record["task"]["stdout_path"]).read_text(encoding="utf-8") == (
        "Applied fenced model patch to workspace.\n"
    )
    assert (out / record["task"]["stderr_path"]).read_text(encoding="utf-8") == ""
    assert (out / record["verify"]["stdout_path"]).read_text(encoding="utf-8") == ""
    assert (out / record["verify"]["stderr_path"]).read_text(encoding="utf-8") == ""

    verify_json = json.loads((out / record["verify"]["path"]).read_text())
    assert verify_json["actual"] == "Hello, Ada!"
    assert verify_json["expected"] == "Hello, Ada!"
    assert verify_json["case"] == "fix-greeting"
    assert verify_json["pack_id"] == "patch-from-failure"
    assert verify_json["pack_version"] == "0.1.0"
    assert verify_json["source_fixture_id"] == "repo"
    assert verify_json["patch_exists"] is True
    assert verify_json["patch_bytes"] > 0
    assert verify_json["exit_code"] == 0
    assert verify_json["passed"] is True


def test_cli_repo_task_verify_script_success_records_artifacts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _install_fake_adapter(monkeypatch)
    monkeypatch.chdir(tmp_path)
    pack_dir = _write_repo_task_pack(
        tmp_path,
        scoring='[scoring]\nmode = "verify-script"\nscript = "verify/check.py"\n',
    )
    _write_verifier_script(
        pack_dir,
        """
import argparse
import json
import sys
parser = argparse.ArgumentParser()
parser.add_argument("--workspace")
parser.add_argument("--case")
parser.add_argument("--pack-id")
parser.add_argument("--pack-version")
parser.add_argument("--source-fixture-id")
parser.add_argument("--patch")
parser.add_argument("--output")
args = parser.parse_args()
print("verified stdout")
print("verified stderr", file=sys.stderr)
with open(args.output, "w", encoding="utf-8") as fh:
    json.dump({"case": args.case, "workspace": args.workspace}, fh)
""",
    )
    out = tmp_path / "run"

    assert main(_argv(["--out", str(out)])) == 0

    record = json.loads((out / "run.jsonl").read_text())
    assert record["workspace"] == {
        "path": "workspace/edit-repo/rep-001",
        "source_fixture_id": "repo",
        "source_path": "fixtures/repo",
    }
    assert record["patch"] == {"path": "patch/edit-repo/rep-001.diff"}
    assert record["task"] == {
        "stdout_path": "task/edit-repo/rep-001.stdout.log",
        "stderr_path": "task/edit-repo/rep-001.stderr.log",
    }
    assert record["verify"] == {
        "path": "verify/edit-repo/rep-001.json",
        "stdout_path": "verify/edit-repo/rep-001.stdout.log",
        "stderr_path": "verify/edit-repo/rep-001.stderr.log",
    }
    assert record["repo_task"] == {"status": "passed", "verify_exit_code": 0}
    assert record["scoring"] == {"mode": "verify-script", "passed": True}
    verify_json = json.loads((out / record["verify"]["path"]).read_text())
    assert verify_json["case"] == "edit-repo"
    assert verify_json["exit_code"] == 0
    assert verify_json["passed"] is True
    assert (out / record["task"]["stdout_path"]).read_text() == ""
    assert (out / record["task"]["stderr_path"]).read_text() == NO_PATCH_TASK_STDERR
    assert (out / record["verify"]["stdout_path"]).read_text() == "verified stdout\n"
    assert (out / record["verify"]["stderr_path"]).read_text() == "verified stderr\n"


def test_cli_repo_task_verify_script_manifest_environment_reaches_verifier(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _install_fake_adapter(monkeypatch)
    monkeypatch.chdir(tmp_path)
    pack_dir = _write_repo_task_pack(
        tmp_path,
        scoring=(
            'scoring = { mode = "verify-script", script = "verify/check.py", '
            'environment = { BENCHPACK_TEST_VAR = "from-manifest" } }\n'
        ),
    )
    _write_verifier_script(
        pack_dir,
        """
import argparse
import json
import os
parser = argparse.ArgumentParser()
parser.add_argument("--workspace")
parser.add_argument("--case")
parser.add_argument("--pack-id")
parser.add_argument("--pack-version")
parser.add_argument("--source-fixture-id")
parser.add_argument("--patch")
parser.add_argument("--output")
args = parser.parse_args()
with open(args.output, "w", encoding="utf-8") as fh:
    json.dump({"manifest_env": os.environ["BENCHPACK_TEST_VAR"]}, fh)
""",
    )
    out = tmp_path / "run"

    assert main(_argv(["--out", str(out)])) == 0

    record = json.loads((out / "run.jsonl").read_text())
    assert record["workspace"] == {
        "path": "workspace/edit-repo/rep-001",
        "source_fixture_id": "repo",
        "source_path": "fixtures/repo",
    }
    assert record["patch"] == {"path": "patch/edit-repo/rep-001.diff"}
    assert record["task"] == {
        "stdout_path": "task/edit-repo/rep-001.stdout.log",
        "stderr_path": "task/edit-repo/rep-001.stderr.log",
    }
    assert record["verify"] == {
        "path": "verify/edit-repo/rep-001.json",
        "stdout_path": "verify/edit-repo/rep-001.stdout.log",
        "stderr_path": "verify/edit-repo/rep-001.stderr.log",
    }
    assert record["repo_task"] == {"status": "passed", "verify_exit_code": 0}
    assert record["scoring"] == {"mode": "verify-script", "passed": True}
    assert record["raw"] == {
        "request_path": "raw/edit-repo.request.json",
        "response_path": "raw/edit-repo.response.json",
    }
    assert json.loads((out / record["verify"]["path"]).read_text()) == {
        "exit_code": 0,
        "manifest_env": "from-manifest",
        "passed": True,
    }
    assert "environment" not in record
    assert "env" not in record
    assert "artifacts" not in record


def test_cli_repo_task_verify_script_failure_records_completed_row(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _install_fake_adapter(monkeypatch)
    monkeypatch.chdir(tmp_path)
    pack_dir = _write_repo_task_pack(
        tmp_path,
        scoring='[scoring]\nmode = "verify-script"\nscript = "verify/check.py"\n',
    )
    _write_verifier_script(pack_dir, "raise SystemExit(5)\n")
    out = tmp_path / "run"

    assert main(_argv(["--out", str(out)])) == 0

    record = json.loads((out / "run.jsonl").read_text())
    assert record["repo_task"] == {"status": "failed", "verify_exit_code": 5}
    assert record["scoring"] == {"mode": "verify-script", "passed": False}
    assert json.loads((out / record["verify"]["path"]).read_text()) == {
        "exit_code": 5,
        "passed": False,
    }


def test_cli_repo_task_verify_script_timeout_records_completed_row(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _install_fake_adapter(monkeypatch)
    monkeypatch.chdir(tmp_path)
    pack_dir = _write_repo_task_pack(
        tmp_path,
        scoring='[scoring]\nmode = "verify-script"\nscript = "verify/check.py"\n',
    )
    _write_verifier_script(pack_dir, "")
    real_run = subprocess.run
    timeouts: list[float] = []

    def timeout_verifier_run(command, *args, **kwargs):
        if isinstance(command, list) and any(
            str(part).endswith("verify/check.py") for part in command
        ):
            timeouts.append(kwargs["timeout"])
            raise subprocess.TimeoutExpired(
                command,
                kwargs["timeout"],
                output="timeout stdout\n",
                stderr="timeout stderr\n",
            )
        return real_run(command, *args, **kwargs)

    monkeypatch.setattr("benchpack.verifiers.subprocess.run", timeout_verifier_run)
    out = tmp_path / "run"

    assert main(_argv(["--out", str(out)])) == 0

    record = json.loads((out / "run.jsonl").read_text())
    assert record["workspace"] == {
        "path": "workspace/edit-repo/rep-001",
        "source_fixture_id": "repo",
        "source_path": "fixtures/repo",
    }
    assert record["patch"] == {"path": "patch/edit-repo/rep-001.diff"}
    assert record["task"] == {
        "stdout_path": "task/edit-repo/rep-001.stdout.log",
        "stderr_path": "task/edit-repo/rep-001.stderr.log",
    }
    assert record["verify"] == {
        "path": "verify/edit-repo/rep-001.json",
        "stdout_path": "verify/edit-repo/rep-001.stdout.log",
        "stderr_path": "verify/edit-repo/rep-001.stderr.log",
    }
    assert record["repo_task"] == {"status": "failed", "verify_exit_code": None}
    assert record["scoring"] == {"mode": "verify-script", "passed": False}
    assert json.loads((out / record["verify"]["path"]).read_text()) == {
        "exit_code": None,
        "passed": False,
        "timed_out": True,
        "timeout_s": 300.0,
    }
    assert timeouts == [300.0]
    assert (out / record["verify"]["stdout_path"]).read_text() == "timeout stdout\n"
    assert (out / record["verify"]["stderr_path"]).read_text() == "timeout stderr\n"


def test_cli_repo_task_verify_script_manifest_timeout_reaches_verifier(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _install_fake_adapter(monkeypatch)
    monkeypatch.chdir(tmp_path)
    pack_dir = _write_repo_task_pack(
        tmp_path,
        scoring=(
            'scoring = { mode = "verify-script", script = "verify/check.py", '
            "timeout_s = 2.5 }\n"
        ),
    )
    _write_verifier_script(pack_dir, "")
    real_run = subprocess.run
    timeouts: list[float] = []

    def timeout_verifier_run(command, *args, **kwargs):
        if isinstance(command, list) and any(
            str(part).endswith("verify/check.py") for part in command
        ):
            timeouts.append(kwargs["timeout"])
            raise subprocess.TimeoutExpired(
                command,
                kwargs["timeout"],
                output="timeout stdout\n",
                stderr="timeout stderr\n",
            )
        return real_run(command, *args, **kwargs)

    monkeypatch.setattr("benchpack.verifiers.subprocess.run", timeout_verifier_run)
    out = tmp_path / "run"

    assert main(_argv(["--out", str(out)])) == 0

    record = json.loads((out / "run.jsonl").read_text())
    assert record["workspace"] == {
        "path": "workspace/edit-repo/rep-001",
        "source_fixture_id": "repo",
        "source_path": "fixtures/repo",
    }
    assert record["patch"] == {"path": "patch/edit-repo/rep-001.diff"}
    assert record["task"] == {
        "stdout_path": "task/edit-repo/rep-001.stdout.log",
        "stderr_path": "task/edit-repo/rep-001.stderr.log",
    }
    assert record["verify"] == {
        "path": "verify/edit-repo/rep-001.json",
        "stdout_path": "verify/edit-repo/rep-001.stdout.log",
        "stderr_path": "verify/edit-repo/rep-001.stderr.log",
    }
    assert record["repo_task"] == {"status": "failed", "verify_exit_code": None}
    assert record["scoring"] == {"mode": "verify-script", "passed": False}
    assert json.loads((out / record["verify"]["path"]).read_text()) == {
        "exit_code": None,
        "passed": False,
        "timed_out": True,
        "timeout_s": 2.5,
    }
    assert timeouts == [2.5]
    assert (out / record["verify"]["stdout_path"]).read_text() == "timeout stdout\n"
    assert (out / record["verify"]["stderr_path"]).read_text() == "timeout stderr\n"
    assert "artifacts" not in record


def test_cli_repo_task_verify_script_repetitions_get_separate_artifacts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _install_fake_adapter(monkeypatch)
    monkeypatch.chdir(tmp_path)
    pack_dir = _write_repo_task_pack(
        tmp_path,
        defaults_extra="repetitions = 2",
        scoring='[scoring]\nmode = "verify-script"\nscript = "verify/check.py"\n',
    )
    _write_verifier_script(pack_dir, "")
    out = tmp_path / "run"

    assert main(_argv(["--out", str(out)])) == 0

    records = [
        json.loads(line)
        for line in (out / "run.jsonl").read_text().strip().splitlines()
    ]
    assert [record["verify"]["path"] for record in records] == [
        "verify/edit-repo/rep-001.json",
        "verify/edit-repo/rep-002.json",
    ]
    assert [record["verify"]["stdout_path"] for record in records] == [
        "verify/edit-repo/rep-001.stdout.log",
        "verify/edit-repo/rep-002.stdout.log",
    ]
    assert [record["task"]["stdout_path"] for record in records] == [
        "task/edit-repo/rep-001.stdout.log",
        "task/edit-repo/rep-002.stdout.log",
    ]
    assert [record["task"]["stderr_path"] for record in records] == [
        "task/edit-repo/rep-001.stderr.log",
        "task/edit-repo/rep-002.stderr.log",
    ]
    assert (out / "verify" / "edit-repo" / "rep-001.json").is_file()
    assert (out / "verify" / "edit-repo" / "rep-002.json").is_file()
    assert (out / "task" / "edit-repo" / "rep-001.stdout.log").read_text() == ""
    assert (
        out / "task" / "edit-repo" / "rep-002.stderr.log"
    ).read_text() == NO_PATCH_TASK_STDERR


def test_cli_repo_task_allows_additional_file_fixture_refs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls = _install_recording_adapter(monkeypatch)
    monkeypatch.chdir(tmp_path)
    fixture_entries = """
[[fixtures]]
id = "repo"
kind = "repo"
path = "fixtures/repo"

[[fixtures]]
id = "context"
kind = "context"
path = "fixtures/context.md"
"""
    pack_dir = _write_repo_task_pack(
        tmp_path,
        fixture_entries=fixture_entries,
        fixture_refs='["repo", "context"]',
    )
    (pack_dir / "fixtures" / "context.md").write_text("context\n", encoding="utf-8")
    out = tmp_path / "run"

    assert main(_argv(["--out", str(out)])) == 0

    assert (out / "workspace" / "edit-repo" / "rep-001").is_dir()
    assert len(calls) == 1
    assert "--- BEGIN FIXTURE context" in calls[0]["prompt"]
    assert "context\n--- END FIXTURE context ---" in calls[0]["prompt"]


def test_cli_repo_task_repetitions_get_separate_workspaces(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _install_fake_adapter(monkeypatch)
    monkeypatch.chdir(tmp_path)
    pack_dir = _write_repo_task_pack(tmp_path, defaults_extra="repetitions = 2")
    out = tmp_path / "run"

    assert main(_argv(["--out", str(out)])) == 0

    rep1 = out / "workspace" / "edit-repo" / "rep-001"
    rep2 = out / "workspace" / "edit-repo" / "rep-002"
    assert rep1.is_dir()
    assert rep2.is_dir()

    records = [
        json.loads(line)
        for line in (out / "run.jsonl").read_text().strip().splitlines()
    ]
    assert [record["workspace"]["path"] for record in records] == [
        "workspace/edit-repo/rep-001",
        "workspace/edit-repo/rep-002",
    ]
    assert [record["workspace"]["source_fixture_id"] for record in records] == [
        "repo",
        "repo",
    ]
    assert [record["workspace"]["source_path"] for record in records] == [
        "fixtures/repo",
        "fixtures/repo",
    ]
    assert [record["patch"]["path"] for record in records] == [
        "patch/edit-repo/rep-001.diff",
        "patch/edit-repo/rep-002.diff",
    ]
    assert [record["task"]["stdout_path"] for record in records] == [
        "task/edit-repo/rep-001.stdout.log",
        "task/edit-repo/rep-002.stdout.log",
    ]
    assert [record["task"]["stderr_path"] for record in records] == [
        "task/edit-repo/rep-001.stderr.log",
        "task/edit-repo/rep-002.stderr.log",
    ]
    assert (out / "patch" / "edit-repo" / "rep-001.diff").is_file()
    assert (out / "patch" / "edit-repo" / "rep-002.diff").is_file()
    assert (out / "task" / "edit-repo" / "rep-001.stdout.log").read_text() == ""
    assert (
        out / "task" / "edit-repo" / "rep-002.stderr.log"
    ).read_text() == NO_PATCH_TASK_STDERR

    (rep1 / "README.md").write_text("changed copy\n", encoding="utf-8")

    source = pack_dir / "fixtures" / "repo" / "README.md"
    assert source.read_text(encoding="utf-8") == "source repo\n"
    assert (rep2 / "README.md").read_text(encoding="utf-8") == "source repo\n"


def test_cli_repo_task_source_fixture_is_isolated_from_workspace_mutation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _install_fake_adapter(monkeypatch)
    monkeypatch.chdir(tmp_path)
    pack_dir = _write_repo_task_pack(tmp_path)
    out = tmp_path / "run"

    assert main(_argv(["--out", str(out)])) == 0

    copied_file = out / "workspace" / "edit-repo" / "rep-001" / "README.md"
    copied_file.write_text("mutated workspace\n", encoding="utf-8")

    source_file = pack_dir / "fixtures" / "repo" / "README.md"
    assert source_file.read_text(encoding="utf-8") == "source repo\n"


def test_cli_repo_task_missing_repo_fixture_fails_before_adapter(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls = _install_recording_adapter(monkeypatch)
    monkeypatch.chdir(tmp_path)
    fixture_entries = """
[[fixtures]]
id = "context"
kind = "context"
path = "fixtures/context.md"
"""
    pack_dir = _write_repo_task_pack(
        tmp_path,
        fixture_entries=fixture_entries,
        fixture_refs='["context"]',
    )
    (pack_dir / "fixtures" / "context.md").write_text("context\n", encoding="utf-8")

    with pytest.raises(SystemExit, match="exactly one kind='repo'"):
        main(_argv(["--out", str(tmp_path / "run")]))

    assert calls == []


def test_cli_repo_task_multiple_repo_fixtures_fail_before_adapter(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls = _install_recording_adapter(monkeypatch)
    monkeypatch.chdir(tmp_path)
    fixture_entries = """
[[fixtures]]
id = "repo-a"
kind = "repo"
path = "fixtures/repo-a"

[[fixtures]]
id = "repo-b"
kind = "repo"
path = "fixtures/repo-b"
"""
    pack_dir = _write_repo_task_pack(
        tmp_path,
        fixture_entries=fixture_entries,
        fixture_refs='["repo-a", "repo-b"]',
    )
    (pack_dir / "fixtures" / "repo-a").mkdir()
    (pack_dir / "fixtures" / "repo-b").mkdir()

    with pytest.raises(SystemExit, match="found 2"):
        main(_argv(["--out", str(tmp_path / "run")]))

    assert calls == []


def test_cli_repo_task_non_repo_directory_fixture_fails_before_adapter(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls = _install_recording_adapter(monkeypatch)
    monkeypatch.chdir(tmp_path)
    fixture_entries = """
[[fixtures]]
id = "repo"
kind = "repo"
path = "fixtures/repo"

[[fixtures]]
id = "docs"
kind = "context"
path = "fixtures/docs"
"""
    pack_dir = _write_repo_task_pack(
        tmp_path,
        fixture_entries=fixture_entries,
        fixture_refs='["repo", "docs"]',
    )
    (pack_dir / "fixtures" / "docs").mkdir()

    with pytest.raises(SystemExit, match="non-repo directory fixture"):
        main(_argv(["--out", str(tmp_path / "run")]))

    assert calls == []


def test_cli_repo_task_repo_fixture_must_be_directory(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls = _install_recording_adapter(monkeypatch)
    monkeypatch.chdir(tmp_path)
    fixture_entries = """
[[fixtures]]
id = "repo"
kind = "repo"
path = "fixtures/repo-file.md"
"""
    pack_dir = _write_repo_task_pack(tmp_path, fixture_entries=fixture_entries)
    (pack_dir / "fixtures" / "repo-file.md").write_text("not a dir\n", encoding="utf-8")

    with pytest.raises(SystemExit, match="not a directory"):
        main(_argv(["--out", str(tmp_path / "run")]))

    assert calls == []


def test_cli_repo_task_rejects_fixture_symlink_escape_before_adapter(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls = _install_recording_adapter(monkeypatch)
    monkeypatch.chdir(tmp_path)
    pack_dir = _write_repo_task_pack(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text("outside\n", encoding="utf-8")
    try:
        (pack_dir / "fixtures" / "repo" / "escape.txt").symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"symlinks cannot be created on this filesystem: {exc}")

    with pytest.raises(SystemExit, match="absolute symlink"):
        main(_argv(["--out", str(tmp_path / "run")]))

    assert calls == []


def test_cli_repo_task_rejects_relative_fixture_symlink_escape_before_adapter(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls = _install_recording_adapter(monkeypatch)
    monkeypatch.chdir(tmp_path)
    pack_dir = _write_repo_task_pack(tmp_path)
    try:
        (pack_dir / "fixtures" / "repo" / "escape.txt").symlink_to("../outside.txt")
    except OSError as exc:
        pytest.skip(f"symlinks cannot be created on this filesystem: {exc}")

    with pytest.raises(SystemExit, match="escaping the repo fixture"):
        main(_argv(["--out", str(tmp_path / "run")]))

    assert calls == []


def test_cli_repo_task_allows_internal_relative_fixture_symlink(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _install_fake_adapter(monkeypatch)
    monkeypatch.chdir(tmp_path)
    pack_dir = _write_repo_task_pack(tmp_path)
    try:
        (pack_dir / "fixtures" / "repo" / "readme-link.md").symlink_to("README.md")
    except OSError as exc:
        pytest.skip(f"symlinks cannot be created on this filesystem: {exc}")
    out = tmp_path / "run"

    assert main(_argv(["--out", str(out)])) == 0

    copied_link = out / "workspace" / "edit-repo" / "rep-001" / "readme-link.md"
    assert copied_link.is_symlink()
    assert copied_link.read_text(encoding="utf-8") == "source repo\n"


def test_cli_repo_task_warmup_is_rejected_before_adapter(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls = _install_recording_adapter(monkeypatch)
    monkeypatch.chdir(tmp_path)
    _write_repo_task_pack(tmp_path, defaults_extra="warmup = 1")

    with pytest.raises(SystemExit, match="repo-task warmups are not supported"):
        main(_argv(["--out", str(tmp_path / "run")]))

    assert calls == []


def test_cli_repo_task_existing_workspace_destination_fails_before_adapter(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls = _install_recording_adapter(monkeypatch)
    monkeypatch.chdir(tmp_path)
    _write_repo_task_pack(tmp_path)
    out = tmp_path / "run"
    stale_workspace = out / "workspace" / "edit-repo" / "rep-001"
    stale_workspace.mkdir(parents=True)

    with pytest.raises(SystemExit, match="workspace destination already exists"):
        main(_argv(["--out", str(out)]))

    assert calls == []


def test_cli_chat_case_with_repo_directory_fixture_does_not_create_workspace(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _install_fake_adapter(monkeypatch)
    monkeypatch.chdir(tmp_path)
    _write_repo_task_pack(tmp_path, case_kind="chat")
    out = tmp_path / "run"

    assert main(_argv(["--out", str(out)])) == 0

    assert not (out / "workspace").exists()
    assert not (out / "patch").exists()
    assert not (out / "task").exists()
    assert not (out / "verify").exists()
    record = json.loads((out / "run.jsonl").read_text())
    assert record["case"] == "edit-repo"
    assert "workspace" not in record
    assert "patch" not in record
    assert "task" not in record
    assert "verify" not in record
    assert "repo_task" not in record


def test_cli_non_repo_task_verify_script_fails_clearly_before_adapter(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls = _install_recording_adapter(monkeypatch)
    monkeypatch.chdir(tmp_path)
    pack_dir = _write_repo_task_pack(
        tmp_path,
        case_kind="chat",
        scoring='[scoring]\nmode = "verify-script"\nscript = "verify/check.py"\n',
    )
    _write_verifier_script(pack_dir, "")

    with pytest.raises(SystemExit, match="only supported for measured repo-task"):
        main(_argv(["--out", str(tmp_path / "run")]))

    assert calls == []


def test_cli_missing_verify_script_fails_before_adapter(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls = _install_recording_adapter(monkeypatch)
    monkeypatch.chdir(tmp_path)
    _write_repo_task_pack(
        tmp_path,
        scoring='[scoring]\nmode = "verify-script"\nscript = "verify/missing.py"\n',
    )

    with pytest.raises(SystemExit, match="does not exist"):
        main(_argv(["--out", str(tmp_path / "run")]))

    assert calls == []


def test_cli_escaping_verify_script_fails_before_adapter(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls = _install_recording_adapter(monkeypatch)
    monkeypatch.chdir(tmp_path)
    outside = tmp_path / "outside.py"
    outside.write_text("", encoding="utf-8")
    _write_repo_task_pack(
        tmp_path,
        scoring='[scoring]\nmode = "verify-script"\nscript = "../../outside.py"\n',
    )

    with pytest.raises(SystemExit, match="escapes the pack directory"):
        main(_argv(["--out", str(tmp_path / "run")]))

    assert calls == []


def test_cli_warmup_is_unrecorded_and_measured_repetitions_are_recorded(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls = _install_fake_adapter(monkeypatch)
    monkeypatch.chdir(tmp_path)
    _write_smoke_pack(tmp_path, defaults_extra="warmup = 1\nrepetitions = 2")

    assert main(_argv()) == 0

    out = next((tmp_path / "results").iterdir())
    records = [
        json.loads(line)
        for line in (out / "run.jsonl").read_text().strip().splitlines()
    ]
    assert len(calls) == 3
    assert len(records) == 2
    assert [record["repetition"] for record in records] == [1, 2]
    assert (out / "raw" / "capital.warmup-001.request.json").exists()
    assert (out / "raw" / "capital.warmup-001.response.json").exists()
    assert all("warmup" not in record["raw"]["request_path"] for record in records)
    assert "warmup" not in (out / "summary.md").read_text()


def test_cli_repetitions_one_keeps_legacy_raw_paths_and_record_shape(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _install_fake_adapter(monkeypatch)
    monkeypatch.chdir(tmp_path)
    _write_smoke_pack(tmp_path, defaults_extra="repetitions = 1")

    assert main(_argv()) == 0

    out = next((tmp_path / "results").iterdir())
    assert (out / "raw" / "capital.request.json").exists()
    assert (out / "raw" / "capital.response.json").exists()
    assert not (out / "raw" / "capital.rep-001.request.json").exists()
    record = json.loads((out / "run.jsonl").read_text().strip())
    assert "repetition" not in record
    assert record["raw"] == {
        "request_path": "raw/capital.request.json",
        "response_path": "raw/capital.response.json",
    }


def test_cli_warmup_with_one_repetition_keeps_legacy_measured_paths(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls = _install_fake_adapter(monkeypatch)
    monkeypatch.chdir(tmp_path)
    _write_smoke_pack(tmp_path, defaults_extra="warmup = 1\nrepetitions = 1")

    assert main(_argv()) == 0

    out = next((tmp_path / "results").iterdir())
    assert len(calls) == 2
    assert (out / "raw" / "capital.warmup-001.request.json").exists()
    assert (out / "raw" / "capital.warmup-001.response.json").exists()
    assert (out / "raw" / "capital.request.json").exists()
    assert (out / "raw" / "capital.response.json").exists()
    assert not (out / "raw" / "capital.rep-001.request.json").exists()

    record = json.loads((out / "run.jsonl").read_text().strip())
    assert "repetition" not in record
    assert record["raw"] == {
        "request_path": "raw/capital.request.json",
        "response_path": "raw/capital.response.json",
    }


def test_cli_runs_warmup_then_measured_per_case(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls = _install_recording_adapter(monkeypatch)
    monkeypatch.chdir(tmp_path)
    _write_two_case_pack(tmp_path, defaults_extra="warmup = 1\nrepetitions = 1")

    assert main(_argv()) == 0

    assert calls == [
        {
            "prompt": "Prompt A",
            "request_path": "alpha.warmup-001.request.json",
            "response_path": "alpha.warmup-001.response.json",
        },
        {
            "prompt": "Prompt A",
            "request_path": "alpha.request.json",
            "response_path": "alpha.response.json",
        },
        {
            "prompt": "Prompt B",
            "request_path": "beta.warmup-001.request.json",
            "response_path": "beta.warmup-001.response.json",
        },
        {
            "prompt": "Prompt B",
            "request_path": "beta.request.json",
            "response_path": "beta.response.json",
        },
    ]


def test_cli_default_openai_stream_usage_is_include(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls = _install_defaults_recording_adapter(monkeypatch)
    monkeypatch.chdir(tmp_path)
    _write_streaming_pack(tmp_path)

    assert main(_argv()) == 0

    assert len(calls) == 1
    defaults = calls[0]["defaults"]
    assert defaults["stream"] is True
    assert defaults["temperature"] == 0
    assert defaults["max_tokens"] == 32
    assert defaults[OPENAI_STREAM_USAGE_KEY] == OPENAI_STREAM_USAGE_INCLUDE


def test_cli_openai_stream_usage_flag_reaches_measured_requests(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls = _install_defaults_recording_adapter(monkeypatch)
    monkeypatch.chdir(tmp_path)
    _write_streaming_pack(tmp_path, defaults_extra="warmup = 1\nrepetitions = 2")

    assert main(_argv(["--openai-stream-usage", "omit"])) == 0

    measured = [
        call for call in calls if ".rep-" in call["request_path"]
    ]
    assert [call["request_path"] for call in measured] == [
        "capital.rep-001.request.json",
        "capital.rep-002.request.json",
    ]
    assert all(
        call["defaults"][OPENAI_STREAM_USAGE_KEY] == OPENAI_STREAM_USAGE_OMIT
        for call in measured
    )
    warmup = [
        call for call in calls if ".warmup-" in call["request_path"]
    ]
    assert [call["request_path"] for call in warmup] == [
        "capital.warmup-001.request.json"
    ]
    assert warmup[0]["defaults"][OPENAI_STREAM_USAGE_KEY] == OPENAI_STREAM_USAGE_OMIT


def test_cli_refuses_to_overwrite_existing_run(tmp_path: Path, monkeypatch) -> None:
    _install_fake_adapter(monkeypatch)
    monkeypatch.chdir(tmp_path)
    _write_smoke_pack(tmp_path)

    assert main(_argv()) == 0
    with pytest.raises(SystemExit) as excinfo:
        main(_argv())
    assert "run.jsonl" in str(excinfo.value)
    assert "--force" in str(excinfo.value) or "--out" in str(excinfo.value)


def test_cli_force_replaces_existing_run(tmp_path: Path, monkeypatch) -> None:
    _install_fake_adapter(monkeypatch)
    monkeypatch.chdir(tmp_path)
    _write_smoke_pack(tmp_path)

    assert main(_argv()) == 0
    out_dirs = list((tmp_path / "results").iterdir())
    assert len(out_dirs) == 1
    out = out_dirs[0]

    # Drop a sentinel file in raw/ to confirm --force wipes it.
    sentinel = out / "raw" / "stale-from-prior-run.json"
    sentinel.write_text("{}")

    assert main(_argv(["--force"])) == 0
    assert not sentinel.exists()
    # New run.jsonl has exactly one record.
    lines = (out / "run.jsonl").read_text().strip().splitlines()
    assert len(lines) == 1


def _write_compare_run(
    path: Path,
    *,
    version: str = "0.1.0",
    wall_s: float | None = 1.0,
    ttft_s: float | None = 0.1,
) -> None:
    path.mkdir(parents=True)
    record = {
        "pack": {"id": "runtime-sweep", "version": version},
        "case": "short",
        "adapter": "openai-chat",
        "endpoint": "http://example.test/v1/chat/completions",
        "model": "model",
        "ok": True,
        "timing": {
            "wall_s": wall_s,
            "ttft_s": ttft_s,
            "prefill_tps": 100.0,
            "decode_tps": 40.0,
            "total_tps": 30.0,
        },
        "tokens": {"prompt": 10, "output": 60},
        "resources": {"memory_mb": None, "gpu_memory_mb": None},
        "scoring": None,
        "raw": {
            "request_path": "raw/short.request.json",
            "response_path": "raw/short.response.json",
        },
    }
    (path / "run.jsonl").write_text(json.dumps(record) + "\n")


def test_cli_compare_prints_table_for_two_result_dirs(
    tmp_path: Path,
    capsys,
) -> None:
    run_a = tmp_path / "run-a"
    run_b = tmp_path / "run-b"
    _write_compare_run(run_a, wall_s=1.0)
    _write_compare_run(run_b, wall_s=2.0)

    assert main(["compare", str(run_a), str(run_b)]) == 0

    output = capsys.readouterr().out
    assert "# benchpack compare" in output
    assert "Pack: `runtime-sweep` version `0.1.0`" in output
    assert (
        "| run | case | rows | ok | wall_s med | ttft_s med | prefill_tps med |"
        in output
    )
    assert (
        "| run-a | short | 1 | 1 | 1.000 | 0.100 | — | 40.00 | 30.00 | 60 | "
        "10 | — | 0/1 | cache-missing |"
    ) in output
    assert "WARNING: cache metadata incomplete for case `short`" in output
    assert "`prefill_tps med` is shown only when" in output
    assert "`tokens.cached_prompt`" in output


def test_cli_compare_warns_on_pack_version_mismatch(
    tmp_path: Path,
    capsys,
) -> None:
    run_a = tmp_path / "run-a"
    run_b = tmp_path / "run-b"
    _write_compare_run(run_a, version="0.1.0")
    _write_compare_run(run_b, version="0.2.0")

    assert main(["compare", str(run_a), str(run_b)]) == 0

    assert "WARNING: compared records use different pack ids or versions" in (
        capsys.readouterr().out
    )


def test_cli_compare_rejects_missing_run_jsonl(tmp_path: Path) -> None:
    run_a = tmp_path / "run-a"
    run_b = tmp_path / "run-b"
    _write_compare_run(run_a)
    run_b.mkdir()

    with pytest.raises(SystemExit, match="missing run.jsonl"):
        main(["compare", str(run_a), str(run_b)])


def test_cli_compare_rejects_run_jsonl_with_no_records(tmp_path: Path) -> None:
    run_a = tmp_path / "run-a"
    run_b = tmp_path / "run-b"
    _write_compare_run(run_a)
    run_b.mkdir()
    (run_b / "run.jsonl").write_text("\n  \n")

    with pytest.raises(SystemExit, match="has no records"):
        main(["compare", str(run_a), str(run_b)])


def test_cli_compare_rejects_malformed_jsonl(tmp_path: Path) -> None:
    run_a = tmp_path / "run-a"
    run_b = tmp_path / "run-b"
    _write_compare_run(run_a)
    run_b.mkdir()
    (run_b / "run.jsonl").write_text("{bad json}\n")

    with pytest.raises(SystemExit, match="could not parse"):
        main(["compare", str(run_a), str(run_b)])


def test_cli_compare_displays_placeholder_for_null_metrics(
    tmp_path: Path,
    capsys,
) -> None:
    run_a = tmp_path / "run-a"
    run_b = tmp_path / "run-b"
    _write_compare_run(run_a, wall_s=None, ttft_s=None)
    _write_compare_run(run_b)

    assert main(["compare", str(run_a), str(run_b)]) == 0

    output = capsys.readouterr().out
    assert (
        "| run-a | short | 1 | 1 | — | — | — | 40.00 | 30.00 | 60 | 10 | "
        "— | 0/1 | cache-missing |"
        in output
    )


def test_cli_compare_rejects_single_result_dir(tmp_path: Path) -> None:
    run_a = tmp_path / "run-a"
    _write_compare_run(run_a)

    with pytest.raises(SystemExit, match="at least two result directories"):
        main(["compare", str(run_a)])


def test_cli_report_prints_markdown_for_result_dirs(
    tmp_path: Path,
    capsys,
) -> None:
    run_a = tmp_path / "run-a"
    run_b = tmp_path / "run-b"
    _write_compare_run(run_a, wall_s=1.0)
    _write_compare_run(run_b, wall_s=2.0)
    (run_a / "hardware.json").write_text(
        json.dumps({"hostname": "atlas.local", "chip": "Apple M5 Max"}) + "\n"
    )

    assert main(["report", str(run_a), str(run_b)]) == 0

    output = capsys.readouterr().out
    assert "# benchpack report" in output
    assert "## Run Metadata" in output
    assert "hostname=atlas.local; chip=Apple M5 Max" in output
    assert "## Case Outcomes" in output
    assert "## Compare Medians" in output
    assert (
        "| run-a | short | 1 | 1 | 1.000 | 0.100 | — | 40.00 | 30.00 | "
        "60 | 10 | — | 0/1 | cache-missing |"
    ) in output


def test_cli_report_rejects_missing_run_jsonl(tmp_path: Path) -> None:
    run_a = tmp_path / "run-a"
    _write_compare_run(run_a)
    run_b = tmp_path / "run-b"
    run_b.mkdir()

    with pytest.raises(SystemExit, match="missing run.jsonl"):
        main(["report", str(run_a), str(run_b)])
