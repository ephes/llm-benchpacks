"""End-to-end CLI smoke test using a mocked adapter."""

from __future__ import annotations

import http.server
import json
import subprocess
import sys
import threading
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
    OPENAI_API_KEY_ENV_KEY,
    OpenAIChatAdapter,
    OPENAI_STREAM_USAGE_INCLUDE,
    OPENAI_STREAM_USAGE_KEY,
    OPENAI_STREAM_USAGE_OMIT,
)
from benchpack.cli import main
from benchpack.external_agent_context import ExternalAgentContextError
from benchpack.packs import (
    InvalidHarnessError,
    PROVISIONAL_EXTERNAL_AGENT_HARNESS_ID,
    PUBLIC_HARNESS_EXTERNAL_AGENT,
    PUBLIC_HARNESS_FENCED_PATCH,
)


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


def _write_mixed_repo_task_harness_pack(tmp_path: Path) -> Path:
    pack_dir = tmp_path / "benchpacks" / "smoke-chat"
    pack_dir.mkdir(parents=True)
    repo_dir = pack_dir / "fixtures" / "repo"
    repo_dir.mkdir(parents=True)
    (repo_dir / "README.md").write_text("source repo\n", encoding="utf-8")
    (pack_dir / "benchpack.toml").write_text(
        f"""
[pack]
id = "smoke-chat"
version = "0.1.0"

[defaults]
temperature = 0
max_tokens = 32
stream = false

[[fixtures]]
id = "repo"
kind = "repo"
path = "fixtures/repo"

[[cases]]
id = "external-repo"
kind = "repo-task"
prompt = "Change the repository with an external agent."
fixture_refs = ["repo"]
harness = {{ id = "{PUBLIC_HARNESS_EXTERNAL_AGENT}", timeout_s = 5 }}

[[cases]]
id = "fenced-repo"
kind = "repo-task"
prompt = "Change the repository with a fenced patch."
fixture_refs = ["repo"]
harness = {{ id = "{PUBLIC_HARNESS_FENCED_PATCH}", timeout_s = 5 }}

[scoring]
mode = "none"
""",
        encoding="utf-8",
    )
    return pack_dir


def _write_verifier_script(pack_dir: Path, body: str) -> Path:
    script = pack_dir / "verify" / "check.py"
    script.parent.mkdir(parents=True)
    script.write_text(body, encoding="utf-8")
    return script


def _write_fake_external_agent(tmp_path: Path, body: str) -> Path:
    script = tmp_path / "fake_external_agent.py"
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


def _endpoint_python_correctness_argv(extra: list[str] | None = None) -> list[str]:
    return [
        "run",
        "endpoint-python-correctness",
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


def _python_regression_fix_argv(extra: list[str] | None = None) -> list[str]:
    return [
        "run",
        "python-regression-fix",
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


def _django_dashboard_regression_fix_argv(
    extra: list[str] | None = None,
) -> list[str]:
    return [
        "run",
        "django-dashboard-regression-fix",
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


def _mini_project_completion_argv(extra: list[str] | None = None) -> list[str]:
    return [
        "run",
        "mini-project-completion",
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


def test_cli_run_metadata_writes_small_result_artifact(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _install_fake_adapter(monkeypatch)
    monkeypatch.chdir(tmp_path)
    _write_smoke_pack(tmp_path)
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "runtime": {
                    "name": "llama-server",
                    "version": "9010",
                    "command": "llama-server --model <model>",
                    "options": {"ctx_size": 4096},
                },
                "model": {
                    "id": "qwen2.5-0.5b-instruct-q4_k_m",
                    "quantization": "Q4_K_M",
                },
                "operating_conditions": {
                    "power": "not captured",
                    "thermal": "not captured",
                    "background_load": "no intentional throttling setup",
                },
                "notes": "unit metadata",
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "run"

    assert main(_argv(["--out", str(out), "--run-metadata", str(metadata_path)])) == 0

    persisted = json.loads((out / "run-metadata.json").read_text(encoding="utf-8"))
    assert persisted["runtime"]["name"] == "llama-server"
    assert persisted["runtime"]["options"] == {"ctx_size": 4096}
    assert persisted["model"]["quantization"] == "Q4_K_M"
    assert persisted["operating_conditions"]["power"] == "not captured"
    assert json.loads((out / "run.jsonl").read_text())["case"] == "capital"

    summary = (out / "summary.md").read_text(encoding="utf-8")
    assert "## Runtime Metadata" in summary
    assert "name=llama-server" in summary
    assert "quantization=Q4_K_M" in summary


def test_cli_run_metadata_missing_file_fails_before_output(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _install_fake_adapter(monkeypatch)
    monkeypatch.chdir(tmp_path)
    _write_smoke_pack(tmp_path)
    out = tmp_path / "run"

    with pytest.raises(SystemExit, match="could not read run metadata"):
        main(
            _argv(
                [
                    "--out",
                    str(out),
                    "--run-metadata",
                    str(tmp_path / "missing.json"),
                ]
            )
        )

    assert not out.exists()


def test_cli_run_metadata_malformed_json_fails_before_output(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _install_fake_adapter(monkeypatch)
    monkeypatch.chdir(tmp_path)
    _write_smoke_pack(tmp_path)
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text("{bad json}\n", encoding="utf-8")
    out = tmp_path / "run"

    with pytest.raises(SystemExit, match="could not parse run metadata"):
        main(_argv(["--out", str(out), "--run-metadata", str(metadata_path)]))

    assert not out.exists()


def test_cli_run_metadata_non_object_root_fails_before_output(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _install_fake_adapter(monkeypatch)
    monkeypatch.chdir(tmp_path)
    _write_smoke_pack(tmp_path)
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text("[]\n", encoding="utf-8")
    out = tmp_path / "run"

    with pytest.raises(SystemExit, match="expected JSON object"):
        main(_argv(["--out", str(out), "--run-metadata", str(metadata_path)]))

    assert not out.exists()


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


def test_cli_external_agent_missing_argv_fails_before_execution(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls = _install_output_adapter(monkeypatch, "unused")
    monkeypatch.chdir(tmp_path)
    _write_repo_task_pack(
        tmp_path,
        case_extra=(
            f'harness = {{ id = "{PROVISIONAL_EXTERNAL_AGENT_HARNESS_ID}" }}'
        ),
    )
    out = tmp_path / "run"

    monkeypatch.delenv("BENCHPACK_EXTERNAL_AGENT_ARGV", raising=False)

    with pytest.raises(SystemExit) as excinfo:
        main(_argv(["--out", str(out)]))

    message = str(excinfo.value)
    assert "BENCHPACK_EXTERNAL_AGENT_ARGV is required" in message
    assert PROVISIONAL_EXTERNAL_AGENT_HARNESS_ID in message
    assert calls == []
    assert not out.exists()


@pytest.mark.parametrize(
    "raw_env",
    [
        "python fake-agent.py",
        '"python fake-agent.py"',
        "[]",
        '[""]',
        '["python", 3]',
        '["python", "bad\\u0000arg"]',
        '{"cmd": "python"}',
    ],
)
def test_cli_external_agent_malformed_argv_fails_before_execution(
    tmp_path: Path,
    monkeypatch,
    raw_env: str,
) -> None:
    calls = _install_output_adapter(monkeypatch, "unused")
    monkeypatch.chdir(tmp_path)
    _write_repo_task_pack(
        tmp_path,
        case_extra=f'harness = {{ id = "{PUBLIC_HARNESS_EXTERNAL_AGENT}" }}',
    )
    out = tmp_path / "run"
    monkeypatch.setenv("BENCHPACK_EXTERNAL_AGENT_ARGV", raw_env)

    with pytest.raises(SystemExit) as excinfo:
        main(_argv(["--out", str(out)]))

    assert "BENCHPACK_EXTERNAL_AGENT_ARGV must be a JSON array" in str(excinfo.value)
    assert calls == []
    assert not out.exists()


def test_cli_ignores_external_agent_argv_when_pack_does_not_select_it(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _install_output_adapter(monkeypatch, "Paris.")
    monkeypatch.chdir(tmp_path)
    _write_smoke_pack(tmp_path)
    monkeypatch.setenv("BENCHPACK_EXTERNAL_AGENT_ARGV", "not json")
    out = tmp_path / "run"

    assert main(_argv(["--out", str(out)])) == 0
    assert (out / "run.jsonl").exists()


def test_cli_repo_task_external_agent_runs_configured_subprocess(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls = _install_output_adapter(monkeypatch, "adapter output should be preserved")
    monkeypatch.chdir(tmp_path)
    pack_dir = _write_repo_task_pack(
        tmp_path,
        case_extra=f'harness = {{ id = "{PUBLIC_HARNESS_EXTERNAL_AGENT}", timeout_s = 5 }}',
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
if content != "external repo\\n":
    raise SystemExit(2)
if "+external repo\\n" not in patch_text:
    raise SystemExit(3)
with open(args.output, "w", encoding="utf-8") as fh:
    json.dump({"content": content, "patch_has_external": True}, fh)
""",
    )
    script = _write_fake_external_agent(
        tmp_path,
        """
import argparse
import json
import sys
from pathlib import Path
parser = argparse.ArgumentParser()
parser.add_argument("--workspace", required=True)
parser.add_argument("--case", required=True)
parser.add_argument("--output-dir", required=True)
parser.add_argument("--repetition", required=True)
parser.add_argument("--context", required=True)
args = parser.parse_args()
context = json.loads(Path(args.context).read_text(encoding="utf-8"))
workspace = Path(context["workspace"]["path"])
if args.case != "edit-repo" or args.repetition != "1":
    raise SystemExit(2)
if context["case"]["id"] != args.case or context["run"]["repetition"] != 1:
    raise SystemExit(4)
if context["adapter"]["model"] != "test-model":
    raise SystemExit(5)
if context["run"]["run_metadata_path"] is not None:
    raise SystemExit(6)
if Path(args.workspace).resolve() != workspace.resolve():
    raise SystemExit(7)
if Path.cwd().resolve() != workspace.resolve():
    raise SystemExit(3)
Path(context["run"]["model_call_log_path"]).write_text(
    json.dumps(
        {
            "schema_version": 1,
            "sequence": 1,
            "model": "test-model",
            "ok": True,
        }
    )
    + "\\n",
    encoding="utf-8",
)
(workspace / "README.md").write_text("external repo\\n", encoding="utf-8")
print(f"external stdout case={args.case} rep={args.repetition}")
print("external stderr trace", file=sys.stderr)
""",
    )
    monkeypatch.setenv(
        "BENCHPACK_EXTERNAL_AGENT_ARGV",
        json.dumps([sys.executable, str(script)]),
    )
    out = tmp_path / "run"

    assert main(_argv(["--out", str(out)])) == 0

    assert len(calls) == 1
    workspace = out / "workspace" / "edit-repo" / "rep-001"
    assert (workspace / "README.md").read_text(encoding="utf-8") == "external repo\n"
    context_file = out / "task" / "edit-repo" / "rep-001.context.json"
    assert context_file.is_file()
    context = json.loads(context_file.read_text(encoding="utf-8"))
    assert context["case"]["prompt"] == "Change the repository."
    assert context["case"]["harness"] == {
        "id": PUBLIC_HARNESS_EXTERNAL_AGENT,
        "timeout_s": 5.0,
    }
    assert context["workspace"]["path"] == str(workspace.resolve())
    assert context["run"]["task_stdout_path"] == str(
        (out / "task" / "edit-repo" / "rep-001.stdout.log").resolve()
    )
    model_call_log_path = out / "task" / "edit-repo" / "rep-001.model-calls.jsonl"
    assert context["run"]["model_call_log_path"] == str(
        model_call_log_path.resolve()
    )
    assert "raw" not in model_call_log_path.relative_to(out).parts
    assert context["adapter"]["endpoint"] == "http://example.test/v1"
    source = tmp_path / "benchpacks" / "smoke-chat" / "fixtures" / "repo" / "README.md"
    assert source.read_text(encoding="utf-8") == "source repo\n"
    assert model_call_log_path.read_text(encoding="utf-8") == (
        '{"schema_version": 1, "sequence": 1, '
        '"model": "test-model", "ok": true}\n'
    )

    record = json.loads((out / "run.jsonl").read_text())
    assert record["raw"] == {
        "request_path": "raw/edit-repo.request.json",
        "response_path": "raw/edit-repo.response.json",
    }
    assert "model_call_log_path" not in record
    assert "model_call_log_path" not in record["task"]
    assert record["task"] == {
        "stdout_path": "task/edit-repo/rep-001.stdout.log",
        "stderr_path": "task/edit-repo/rep-001.stderr.log",
    }
    assert record["patch"] == {"path": "patch/edit-repo/rep-001.diff"}
    assert record["verify"] == {
        "path": "verify/edit-repo/rep-001.json",
        "stdout_path": "verify/edit-repo/rep-001.stdout.log",
        "stderr_path": "verify/edit-repo/rep-001.stderr.log",
    }
    assert record["repo_task"] == {"status": "passed", "verify_exit_code": 0}
    assert record["scoring"] == {"mode": "verify-script", "passed": True}
    assert (out / record["task"]["stdout_path"]).read_text(encoding="utf-8") == (
        "external stdout case=edit-repo rep=1\n"
    )
    assert (out / record["task"]["stderr_path"]).read_text(encoding="utf-8") == (
        "external stderr trace\n"
    )
    assert (out / record["patch"]["path"]).read_text(encoding="utf-8") == (
        "--- a/README.md\n"
        "+++ b/README.md\n"
        "@@ -1 +1 @@\n"
        "-source repo\n"
        "+external repo\n"
    )
    assert json.loads((out / record["verify"]["path"]).read_text()) == {
        "content": "external repo\n",
        "exit_code": 0,
        "passed": True,
        "patch_has_external": True,
    }


def test_cli_openai_api_key_env_reaches_defaults_without_token(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls = _install_defaults_recording_adapter(monkeypatch)
    monkeypatch.chdir(tmp_path)
    _write_smoke_pack(tmp_path)
    monkeypatch.setenv("BENCHPACK_OPENAI_TOKEN", "dont-leak-cli-token")

    assert main(_argv(["--openai-api-key-env", "BENCHPACK_OPENAI_TOKEN"])) == 0

    assert len(calls) == 1
    defaults = calls[0]["defaults"]
    assert defaults[OPENAI_API_KEY_ENV_KEY] == "BENCHPACK_OPENAI_TOKEN"
    serialized = json.dumps(defaults, sort_keys=True)
    assert "dont-leak-cli-token" not in serialized
    assert "Bearer" not in serialized
    assert "Authorization" not in serialized


def test_cli_openai_api_key_env_missing_fails_without_token(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _install_fake_adapter(monkeypatch)
    monkeypatch.chdir(tmp_path)
    _write_smoke_pack(tmp_path)
    monkeypatch.delenv("BENCHPACK_OPENAI_TOKEN", raising=False)
    out = tmp_path / "run"

    with pytest.raises(SystemExit) as excinfo:
        main(
            _argv(
                [
                    "--out",
                    str(out),
                    "--openai-api-key-env",
                    "BENCHPACK_OPENAI_TOKEN",
                ]
            )
        )

    message = str(excinfo.value)
    assert "BENCHPACK_OPENAI_TOKEN" in message
    assert "not set or is empty" in message
    assert "Bearer" not in message
    assert "Authorization" not in message
    assert not (out / "run.jsonl").exists()


def test_cli_external_agent_reference_example_runs_public_handoff(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls = _install_output_adapter(monkeypatch, "adapter output remains separate")
    monkeypatch.chdir(tmp_path)
    pack_dir = _write_repo_task_pack(
        tmp_path,
        case_extra=f'harness = {{ id = "{PUBLIC_HARNESS_EXTERNAL_AGENT}", timeout_s = 5 }}',
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
marker = Path(args.workspace, "external-agent-example.txt")
content = marker.read_text(encoding="utf-8")
expected = (
    "external-agent reference harness\\n"
    "case=edit-repo\\n"
    "repetition=1\\n"
)
if content != expected:
    raise SystemExit(2)
patch_text = Path(args.patch).read_text(encoding="utf-8")
if "+external-agent reference harness\\n" not in patch_text:
    raise SystemExit(3)
with open(args.output, "w", encoding="utf-8") as fh:
    json.dump({"marker": content, "patch_has_marker": True}, fh)
""",
    )
    example_script = (
        Path(__file__).resolve().parents[1]
        / "examples"
        / "external-agent"
        / "reference-agent.py"
    )
    monkeypatch.setenv(
        "BENCHPACK_EXTERNAL_AGENT_ARGV",
        json.dumps([sys.executable, str(example_script)]),
    )
    out = tmp_path / "run"

    assert main(_argv(["--out", str(out)])) == 0

    assert len(calls) == 1
    workspace = out / "workspace" / "edit-repo" / "rep-001"
    marker = workspace / "external-agent-example.txt"
    assert marker.read_text(encoding="utf-8") == (
        "external-agent reference harness\n"
        "case=edit-repo\n"
        "repetition=1\n"
    )
    source_repo = tmp_path / "benchpacks" / "smoke-chat" / "fixtures" / "repo"
    assert (source_repo / "README.md").read_text(encoding="utf-8") == (
        "source repo\n"
    )
    assert not (source_repo / "external-agent-example.txt").exists()

    context_file = out / "task" / "edit-repo" / "rep-001.context.json"
    assert context_file.is_file()
    context = json.loads(context_file.read_text(encoding="utf-8"))
    model_call_log_path = Path(context["run"]["model_call_log_path"])
    assert model_call_log_path == (
        out / "task" / "edit-repo" / "rep-001.model-calls.jsonl"
    ).resolve()
    assert "raw" not in model_call_log_path.relative_to(out).parts
    assert (out / "raw").is_dir()
    assert not any("model-calls" in path.name for path in (out / "raw").iterdir())
    model_call_lines = model_call_log_path.read_text(encoding="utf-8").splitlines()
    assert len(model_call_lines) == 1
    assert json.loads(model_call_lines[0]) == {
        "schema_version": 1,
        "sequence": 1,
        "model": "test-model",
        "ok": True,
    }

    record = json.loads((out / "run.jsonl").read_text())
    assert "model_call_log_path" not in record
    assert "model_call_log_path" not in record["task"]
    assert record["task"] == {
        "stdout_path": "task/edit-repo/rep-001.stdout.log",
        "stderr_path": "task/edit-repo/rep-001.stderr.log",
    }
    assert record["patch"] == {"path": "patch/edit-repo/rep-001.diff"}
    assert record["verify"] == {
        "path": "verify/edit-repo/rep-001.json",
        "stdout_path": "verify/edit-repo/rep-001.stdout.log",
        "stderr_path": "verify/edit-repo/rep-001.stderr.log",
    }
    assert record["repo_task"] == {"status": "passed", "verify_exit_code": 0}
    assert record["scoring"] == {"mode": "verify-script", "passed": True}
    assert (out / record["task"]["stdout_path"]).read_text(encoding="utf-8") == (
        "reference-agent wrote external-agent-example.txt for edit-repo\n"
    )
    assert (out / record["task"]["stderr_path"]).read_text(encoding="utf-8") == ""
    assert (out / record["patch"]["path"]).read_text(encoding="utf-8") == (
        "--- /dev/null\n"
        "+++ b/external-agent-example.txt\n"
        "@@ -0,0 +1,3 @@\n"
        "+external-agent reference harness\n"
        "+case=edit-repo\n"
        "+repetition=1\n"
    )
    assert json.loads((out / record["verify"]["path"]).read_text()) == {
        "marker": (
            "external-agent reference harness\n"
            "case=edit-repo\n"
            "repetition=1\n"
        ),
        "exit_code": 0,
        "passed": True,
        "patch_has_marker": True,
    }


@pytest.mark.parametrize(
    ("url", "message"),
    [
        ("http://example.test/model-call", "must use a loopback host"),
        ("http://u:p@127.0.0.1/model-call", "must not contain credentials"),
        (
            "http://127.0.0.1/model-call?api_key=secret",
            "must not contain a query string",
        ),
    ],
)
def test_external_agent_model_call_example_rejects_non_local_or_secret_urls(
    tmp_path: Path,
    url: str,
    message: str,
) -> None:
    example_script = (
        Path(__file__).resolve().parents[1]
        / "examples"
        / "external-agent"
        / "model-call-agent.py"
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(example_script),
            "--model-call-url",
            url,
            "--workspace",
            str(tmp_path),
            "--case",
            "edit-repo",
            "--output-dir",
            str(tmp_path),
            "--repetition",
            "1",
            "--context",
            str(tmp_path / "missing.context.json"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 2
    assert message in completed.stderr


def test_cli_external_agent_model_call_example_runs_local_http_harness(
    tmp_path: Path,
    monkeypatch,
) -> None:
    events: list[str] = []
    adapter_calls: list[dict[str, str]] = []

    class RecordingAdapter:
        name = "openai-chat"

        def run(self, request: AdapterRequest) -> AdapterResult:
            events.append("adapter")
            adapter_calls.append(
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
                                    "content": "adapter output remains separate",
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
                output_text="adapter output remains separate",
            )

    monkeypatch.setitem(adapters_pkg.ADAPTERS, "openai-chat", RecordingAdapter)
    monkeypatch.chdir(tmp_path)
    pack_dir = _write_repo_task_pack(
        tmp_path,
        case_extra=f'harness = {{ id = "{PUBLIC_HARNESS_EXTERNAL_AGENT}", timeout_s = 5 }}',
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
marker = Path(args.workspace, "external-agent-model-call.txt")
content = marker.read_text(encoding="utf-8")
expected = "model-call content for edit-repo\\n"
if content != expected:
    raise SystemExit(2)
patch_text = Path(args.patch).read_text(encoding="utf-8")
if "+model-call content for edit-repo\\n" not in patch_text:
    raise SystemExit(3)
with open(args.output, "w", encoding="utf-8") as fh:
    json.dump({"marker": content, "patch_has_marker": True}, fh)
""",
    )

    model_requests: list[dict[str, Any]] = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8")
            model_requests.append(
                {
                    "path": self.path,
                    "headers": dict(self.headers),
                    "body_text": body,
                    "body": json.loads(body),
                }
            )
            events.append("model_call")
            response = {
                "ok": True,
                "workspace_file": "external-agent-model-call.txt",
                "content": "model-call content for edit-repo\n",
                "model": "test-model",
                "prompt_tokens": 3,
                "output_tokens": 5,
            }
            payload = json.dumps(response).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    endpoint = f"http://127.0.0.1:{server.server_port}/model-call"
    example_script = (
        Path(__file__).resolve().parents[1]
        / "examples"
        / "external-agent"
        / "model-call-agent.py"
    )
    monkeypatch.setenv(
        "BENCHPACK_EXTERNAL_AGENT_ARGV",
        json.dumps(
            [
                sys.executable,
                str(example_script),
                "--model-call-url",
                endpoint,
            ]
        ),
    )
    out = tmp_path / "run"

    try:
        assert main(_argv(["--out", str(out)])) == 0
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert events == ["adapter", "model_call"]
    assert [call["request_path"] for call in adapter_calls] == [
        "edit-repo.request.json"
    ]
    assert len(model_requests) == 1
    request = model_requests[0]
    assert request["path"] == "/model-call"
    assert request["body"] == {
        "case": "edit-repo",
        "repetition": 1,
        "model": "test-model",
    }
    assert "Authorization" not in request["headers"]
    forbidden_fragments = [
        "Change the repository.",
        "adapter output remains separate",
        "model-call content for edit-repo",
        "external-agent-model-call.txt",
        "BENCHPACK_EXTERNAL_AGENT_ARGV",
        "Authorization",
        "Bearer",
        "password",
        "credential",
        "secret",
        "raw/edit-repo.request.json",
        "raw/edit-repo.response.json",
    ]
    for fragment in forbidden_fragments:
        assert fragment not in request["body_text"]

    workspace = out / "workspace" / "edit-repo" / "rep-001"
    marker = workspace / "external-agent-model-call.txt"
    assert marker.read_text(encoding="utf-8") == "model-call content for edit-repo\n"
    source_repo = tmp_path / "benchpacks" / "smoke-chat" / "fixtures" / "repo"
    assert (source_repo / "README.md").read_text(encoding="utf-8") == (
        "source repo\n"
    )
    assert not (source_repo / "external-agent-model-call.txt").exists()

    context_file = out / "task" / "edit-repo" / "rep-001.context.json"
    assert context_file.is_file()
    context = json.loads(context_file.read_text(encoding="utf-8"))
    model_call_log_path = Path(context["run"]["model_call_log_path"])
    assert model_call_log_path == (
        out / "task" / "edit-repo" / "rep-001.model-calls.jsonl"
    ).resolve()
    assert "raw" not in model_call_log_path.relative_to(out).parts
    raw_files = sorted(path.name for path in (out / "raw").iterdir())
    assert raw_files == ["edit-repo.request.json", "edit-repo.response.json"]
    assert not any("model-call" in name or "model-calls" in name for name in raw_files)

    model_call_lines = model_call_log_path.read_text(encoding="utf-8").splitlines()
    assert len(model_call_lines) == 1
    telemetry = json.loads(model_call_lines[0])
    assert telemetry["schema_version"] == 1
    assert telemetry["sequence"] == 1
    assert telemetry["model"] == "test-model"
    assert telemetry["ok"] is True
    assert telemetry["adapter"] == "example-local-http"
    assert telemetry["endpoint"] == "local-http"
    assert telemetry["prompt_tokens"] == 3
    assert telemetry["output_tokens"] == 5
    assert isinstance(telemetry["duration_s"], float)
    assert telemetry["duration_s"] >= 0
    assert "content" not in telemetry
    assert "prompt" not in telemetry
    assert "request" not in telemetry
    assert "headers" not in telemetry
    assert "authorization" not in telemetry

    record = json.loads((out / "run.jsonl").read_text())
    assert "model_call_log_path" not in record
    assert "model_call_log_path" not in record["task"]
    assert record["raw"] == {
        "request_path": "raw/edit-repo.request.json",
        "response_path": "raw/edit-repo.response.json",
    }
    assert record["task"] == {
        "stdout_path": "task/edit-repo/rep-001.stdout.log",
        "stderr_path": "task/edit-repo/rep-001.stderr.log",
    }
    assert record["patch"] == {"path": "patch/edit-repo/rep-001.diff"}
    assert record["verify"] == {
        "path": "verify/edit-repo/rep-001.json",
        "stdout_path": "verify/edit-repo/rep-001.stdout.log",
        "stderr_path": "verify/edit-repo/rep-001.stderr.log",
    }
    assert record["repo_task"] == {"status": "passed", "verify_exit_code": 0}
    assert record["scoring"] == {"mode": "verify-script", "passed": True}
    assert (out / record["task"]["stdout_path"]).read_text(encoding="utf-8") == (
        "model-call-agent wrote external-agent-model-call.txt for edit-repo\n"
    )
    assert (out / record["task"]["stderr_path"]).read_text(encoding="utf-8") == ""
    assert (out / record["patch"]["path"]).read_text(encoding="utf-8") == (
        "--- /dev/null\n"
        "+++ b/external-agent-model-call.txt\n"
        "@@ -0,0 +1 @@\n"
        "+model-call content for edit-repo\n"
    )
    assert json.loads((out / record["verify"]["path"]).read_text()) == {
        "marker": "model-call content for edit-repo\n",
        "exit_code": 0,
        "passed": True,
        "patch_has_marker": True,
    }


def test_cli_repo_task_mixed_external_agent_and_fenced_patch_cases(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output = """```diff
--- a/README.md
+++ b/README.md
@@ -1 +1 @@
-source repo
+fenced repo
```
"""
    calls = _install_output_adapter(monkeypatch, output)
    monkeypatch.chdir(tmp_path)
    _write_mixed_repo_task_harness_pack(tmp_path)
    script = _write_fake_external_agent(
        tmp_path,
        """
import argparse
import json
from pathlib import Path
parser = argparse.ArgumentParser()
parser.add_argument("--workspace", required=True)
parser.add_argument("--case", required=True)
parser.add_argument("--output-dir", required=True)
parser.add_argument("--repetition", required=True)
parser.add_argument("--context", required=True)
args = parser.parse_args()
if args.case != "external-repo" or args.repetition != "1":
    raise SystemExit(2)
context = json.loads(Path(args.context).read_text(encoding="utf-8"))
workspace = Path(context["workspace"]["path"])
if context["case"]["id"] != "external-repo":
    raise SystemExit(4)
if Path.cwd().resolve() != workspace.resolve():
    raise SystemExit(3)
Path(context["run"]["model_call_log_path"]).write_text(
    json.dumps(
        {
            "schema_version": 1,
            "sequence": 1,
            "model": "test-model",
            "ok": True,
        }
    )
    + "\\n",
    encoding="utf-8",
)
(workspace / "README.md").write_text("external repo\\n", encoding="utf-8")
print(f"external stdout case={args.case} rep={args.repetition}")
""",
    )
    monkeypatch.setenv(
        "BENCHPACK_EXTERNAL_AGENT_ARGV",
        json.dumps([sys.executable, str(script)]),
    )
    out = tmp_path / "run"

    assert main(_argv(["--out", str(out)])) == 0

    assert [call["request_path"] for call in calls] == [
        "external-repo.request.json",
        "fenced-repo.request.json",
    ]
    source = tmp_path / "benchpacks" / "smoke-chat" / "fixtures" / "repo" / "README.md"
    assert source.read_text(encoding="utf-8") == "source repo\n"
    assert (
        out / "workspace" / "external-repo" / "rep-001" / "README.md"
    ).read_text(encoding="utf-8") == "external repo\n"
    assert (
        out / "workspace" / "fenced-repo" / "rep-001" / "README.md"
    ).read_text(encoding="utf-8") == "fenced repo\n"
    assert (out / "task" / "external-repo" / "rep-001.context.json").is_file()
    assert not (out / "task" / "fenced-repo" / "rep-001.context.json").exists()
    assert (
        out / "task" / "external-repo" / "rep-001.model-calls.jsonl"
    ).read_text(encoding="utf-8") == (
        '{"schema_version": 1, "sequence": 1, '
        '"model": "test-model", "ok": true}\n'
    )
    assert not (
        out / "task" / "fenced-repo" / "rep-001.model-calls.jsonl"
    ).exists()

    records = [
        json.loads(line)
        for line in (out / "run.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [record["case"] for record in records] == ["external-repo", "fenced-repo"]
    external_record, fenced_record = records
    assert (out / external_record["task"]["stdout_path"]).read_text(
        encoding="utf-8"
    ) == "external stdout case=external-repo rep=1\n"
    assert (out / external_record["task"]["stderr_path"]).read_text(
        encoding="utf-8"
    ) == ""
    assert (out / fenced_record["task"]["stdout_path"]).read_text(
        encoding="utf-8"
    ) == "Applied fenced model patch to workspace.\n"
    assert (out / fenced_record["task"]["stderr_path"]).read_text(
        encoding="utf-8"
    ) == ""
    assert (out / external_record["patch"]["path"]).read_text(encoding="utf-8") == (
        "--- a/README.md\n"
        "+++ b/README.md\n"
        "@@ -1 +1 @@\n"
        "-source repo\n"
        "+external repo\n"
    )
    assert (out / fenced_record["patch"]["path"]).read_text(encoding="utf-8") == (
        "--- a/README.md\n"
        "+++ b/README.md\n"
        "@@ -1 +1 @@\n"
        "-source repo\n"
        "+fenced repo\n"
    )


def test_cli_external_agent_context_write_failure_skips_subprocess(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls = _install_output_adapter(monkeypatch, "adapter output still runs first")
    monkeypatch.chdir(tmp_path)
    _write_repo_task_pack(
        tmp_path,
        case_extra=f'harness = {{ id = "{PUBLIC_HARNESS_EXTERNAL_AGENT}" }}',
        scoring='[scoring]\nmode = "none"\n',
    )
    marker = tmp_path / "subprocess-ran.txt"
    script = _write_fake_external_agent(
        tmp_path,
        f"""
from pathlib import Path
Path({str(marker)!r}).write_text("ran\\n", encoding="utf-8")
""",
    )
    monkeypatch.setenv(
        "BENCHPACK_EXTERNAL_AGENT_ARGV",
        json.dumps([sys.executable, str(script)]),
    )

    def fail_context_write(path, context):
        raise ExternalAgentContextError("could not write external-agent context file")

    monkeypatch.setattr("benchpack.cli.write_external_agent_context", fail_context_write)
    out = tmp_path / "run"

    with pytest.raises(SystemExit, match="could not write external-agent context"):
        main(_argv(["--out", str(out)]))

    assert len(calls) == 1
    assert not marker.exists()
    assert not (out / "task" / "edit-repo" / "rep-001.stdout.log").exists()
    assert not (out / "patch" / "edit-repo" / "rep-001.diff").exists()
    assert not (out / "run.jsonl").exists()


def test_cli_external_agent_context_build_failure_skips_subprocess(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls = _install_output_adapter(monkeypatch, "adapter output still runs first")
    monkeypatch.chdir(tmp_path)
    _write_repo_task_pack(
        tmp_path,
        case_extra=f'harness = {{ id = "{PUBLIC_HARNESS_EXTERNAL_AGENT}" }}',
        scoring='[scoring]\nmode = "none"\n',
    )
    marker = tmp_path / "subprocess-ran.txt"
    script = _write_fake_external_agent(
        tmp_path,
        f"""
from pathlib import Path
Path({str(marker)!r}).write_text("ran\\n", encoding="utf-8")
""",
    )
    monkeypatch.setenv(
        "BENCHPACK_EXTERNAL_AGENT_ARGV",
        json.dumps([sys.executable, str(script)]),
    )

    def fail_context_build(**kwargs):
        raise ExternalAgentContextError("could not build external-agent context")

    monkeypatch.setattr("benchpack.cli.build_external_agent_context", fail_context_build)
    out = tmp_path / "run"

    with pytest.raises(SystemExit, match="could not build external-agent context"):
        main(_argv(["--out", str(out)]))

    assert len(calls) == 1
    assert not marker.exists()
    assert not (out / "task" / "edit-repo" / "rep-001.stdout.log").exists()
    assert not (out / "patch" / "edit-repo" / "rep-001.diff").exists()
    assert not (out / "run.jsonl").exists()


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
        if command == [
            "git",
            "apply",
            "--check",
            "--whitespace=nowarn",
            "--recount",
        ]:
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
    assert "Your entire response must be one fenced code block" in calls[0]["prompt"]
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


def test_cli_bundled_endpoint_python_correctness_runs_repo_task_flow(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output = "\n".join(
        [
            "```diff",
            "--- a/inventory.py",
            "+++ b/inventory.py",
            "@@ -3,20 +3,29 @@",
            " from typing import Any",
            " ",
            " ",
            "+def _normalize_sku(value: Any) -> str:",
            '+    return str(value).strip().upper()',
            "+",
            "+",
            " def aggregate_stock(rows: list[dict[str, Any]]) -> dict[str, int]:",
            "     stock: dict[str, int] = {}",
            " ",
            "     for row in rows:",
            '-        sku = str(row.get("sku", ""))',
            "+        sku = _normalize_sku(row.get(\"sku\", \"\"))",
            "+        if not sku:",
            "+            continue",
            "         quantity = int(row.get(\"quantity\", 0))",
            "-        stock[sku] = quantity",
            "+        stock[sku] = stock.get(sku, 0) + quantity",
            " ",
            "     return stock",
            " ",
            " ",
            " def reorder_list(rows: list[dict[str, Any]], minimum: int) -> list[str]:",
            "-    return sorted(",
            "-        sku",
            "-        for sku, quantity in aggregate_stock(rows).items()",
            "-        if quantity <= minimum",
            "-    )",
            "+    return [",
            "+        sku",
            "+        for sku, quantity in sorted(",
            "+            aggregate_stock(rows).items(),",
            "+            key=lambda item: (item[1], item[0]),",
            "+        )",
            "+        if quantity < minimum",
            "+    ]",
            "```",
            "",
        ]
    )
    calls = _install_output_adapter(monkeypatch, output)
    repo_root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(repo_root)
    out = tmp_path / "run"

    source_file = (
        repo_root
        / "benchpacks"
        / "endpoint-python-correctness"
        / "fixtures"
        / "repo"
        / "inventory.py"
    )
    source_before = source_file.read_text(encoding="utf-8")

    assert main(_endpoint_python_correctness_argv(["--out", str(out)])) == 0

    workspace_file = (
        out
        / "workspace"
        / "fix-inventory-aggregation"
        / "rep-001"
        / "inventory.py"
    )
    workspace_text = workspace_file.read_text(encoding="utf-8")
    assert "def _normalize_sku" in workspace_text
    assert "stock[sku] = stock.get(sku, 0) + quantity" in workspace_text
    assert "if quantity < minimum" in workspace_text
    assert source_file.read_text(encoding="utf-8") == source_before

    assert len(calls) == 1
    assert calls[0]["request_path"] == "fix-inventory-aggregation.request.json"
    assert "Your entire response must be one fenced code block" in calls[0]["prompt"]
    assert "`inventory.py`" in calls[0]["prompt"]
    assert "Quantities may be integers or numeric strings" in calls[0]["prompt"]

    record = json.loads((out / "run.jsonl").read_text())
    assert record["pack"] == {
        "id": "endpoint-python-correctness",
        "version": "0.2.0",
    }
    assert record["case"] == "fix-inventory-aggregation"
    assert record["adapter"] == "openai-chat"
    assert record["raw"] == {
        "request_path": "raw/fix-inventory-aggregation.request.json",
        "response_path": "raw/fix-inventory-aggregation.response.json",
    }
    assert record["workspace"] == {
        "path": "workspace/fix-inventory-aggregation/rep-001",
        "source_fixture_id": "repo",
        "source_path": "fixtures/repo",
    }
    assert record["patch"] == {
        "path": "patch/fix-inventory-aggregation/rep-001.diff"
    }
    assert record["task"] == {
        "stdout_path": "task/fix-inventory-aggregation/rep-001.stdout.log",
        "stderr_path": "task/fix-inventory-aggregation/rep-001.stderr.log",
    }
    assert record["verify"] == {
        "path": "verify/fix-inventory-aggregation/rep-001.json",
        "stdout_path": "verify/fix-inventory-aggregation/rep-001.stdout.log",
        "stderr_path": "verify/fix-inventory-aggregation/rep-001.stderr.log",
    }
    assert record["repo_task"] == {"status": "passed", "verify_exit_code": 0}
    assert record["scoring"] == {"mode": "verify-script", "passed": True}
    assert "artifacts" not in record

    patch = (out / record["patch"]["path"]).read_text(encoding="utf-8")
    assert patch
    assert "--- a/inventory.py" in patch
    assert "def _normalize_sku" in patch
    assert "stock[sku] = stock.get(sku, 0) + quantity" in patch
    assert (out / record["task"]["stdout_path"]).read_text(encoding="utf-8") == (
        "Applied fenced model patch to workspace.\n"
    )
    assert (out / record["task"]["stderr_path"]).read_text(encoding="utf-8") == ""
    assert (out / record["verify"]["stdout_path"]).read_text(encoding="utf-8") == ""
    assert (out / record["verify"]["stderr_path"]).read_text(encoding="utf-8") == ""

    verify_json = json.loads((out / record["verify"]["path"]).read_text())
    assert verify_json["case"] == "fix-inventory-aggregation"
    assert verify_json["pack_id"] == "endpoint-python-correctness"
    assert verify_json["pack_version"] == "0.2.0"
    assert verify_json["source_fixture_id"] == "repo"
    assert verify_json["patch_exists"] is True
    assert verify_json["patch_bytes"] > 0
    assert verify_json["passed"] is True
    assert [check["name"] for check in verify_json["checks"]] == [
        "aggregate_stock_visible",
        "reorder_list_visible",
        "hidden_numeric_string_blank_aggregate",
        "hidden_strict_threshold_quantity_then_sku_reorder",
    ]
    assert all(check["passed"] for check in verify_json["checks"])


def test_cli_endpoint_python_correctness_accepts_replacement_file_block(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output = "\n".join(
        [
            "```diff",
            "*** Begin File: inventory.py",
            "from __future__ import annotations",
            "",
            "from typing import Any",
            "",
            "",
            "def _normalize_sku(value: Any) -> str:",
            "    return str(value).strip().upper()",
            "",
            "",
            "def aggregate_stock(rows: list[dict[str, Any]]) -> dict[str, int]:",
            "    stock: dict[str, int] = {}",
            "",
            "    for row in rows:",
            '        sku = _normalize_sku(row.get("sku", ""))',
            "        if not sku:",
            "            continue",
            '        quantity = int(row.get("quantity", 0))',
            "        stock[sku] = stock.get(sku, 0) + quantity",
            "",
            "    return stock",
            "",
            "",
            "def reorder_list(rows: list[dict[str, Any]], minimum: int) -> list[str]:",
            "    return [",
            "        sku",
            "        for sku, quantity in sorted(",
            "            aggregate_stock(rows).items(),",
            "            key=lambda item: (item[1], item[0]),",
            "        )",
            "        if quantity < minimum",
            "    ]",
            "*** End File",
            "```",
            "",
        ]
    )
    _install_output_adapter(monkeypatch, output)
    monkeypatch.chdir(Path(__file__).resolve().parents[1])
    out = tmp_path / "run"

    assert main(_endpoint_python_correctness_argv(["--out", str(out)])) == 0

    record = json.loads((out / "run.jsonl").read_text())
    assert record["pack"] == {
        "id": "endpoint-python-correctness",
        "version": "0.2.0",
    }
    assert record["repo_task"] == {"status": "passed", "verify_exit_code": 0}
    assert record["scoring"] == {"mode": "verify-script", "passed": True}
    assert (out / record["task"]["stdout_path"]).read_text(encoding="utf-8") == (
        "Applied fenced model replacement file to workspace.\n"
    )
    assert (out / record["task"]["stderr_path"]).read_text(encoding="utf-8") == ""
    patch = (out / record["patch"]["path"]).read_text(encoding="utf-8")
    assert "--- a/inventory.py" in patch
    assert "def _normalize_sku" in patch


def test_cli_bundled_python_regression_fix_runs_repo_task_flow(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output = "\n".join(
        [
            "```diff",
            "--- a/task_summary.py",
            "+++ b/task_summary.py",
            (
                "@@ -12,27 +12,29 @@ def summarize_tasks(tasks: "
                "list[dict[str, Any]]) -> dict[str, dict[str, int]]:"
            ),
            " ",
            "     for task in tasks:",
            '         status = task.get("status", "todo")',
            '-        owner = task.setdefault("owner", "unassigned")',
            '+        owner = task.get("owner") or "unassigned"',
            "         by_status[status] += 1",
            '-        if status != "done":',
            "-            by_owner[owner] += 1",
            "+        by_owner[owner] += 1",
            " ",
            "     return {",
            '         "by_status": dict(by_status),',
            '         "by_owner": dict(by_owner),',
            "     }",
            " ",
            " ",
            " def overdue_titles(tasks: list[dict[str, Any]], today: date | str) -> list[str]:",
            "     if isinstance(today, date):",
            "-        today_text = today.isoformat()",
            "+        today_value = today",
            "     else:",
            "-        today_text = today",
            "+        today_value = date.fromisoformat(today)",
            " ",
            "-    overdue: list[str] = []",
            "+    overdue: list[tuple[date, str]] = []",
            "     for task in tasks:",
            '         due = task.get("due")',
            "-        if due and due < today_text:",
            '-            overdue.append(str(task.get("title", "")))',
            '+        if not due or task.get("status") == "done":',
            "+            continue",
            "+        due_date = date.fromisoformat(str(due))",
            "+        if due_date < today_value:",
            '+            overdue.append((due_date, str(task.get("title", ""))))',
            " ",
            "-    return sorted(overdue)",
            "+    return [title for _, title in sorted(overdue)]",
            "```",
            "",
        ]
    )
    calls = _install_output_adapter(monkeypatch, output)
    repo_root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(repo_root)
    out = tmp_path / "run"

    source_file = (
        repo_root
        / "benchpacks"
        / "python-regression-fix"
        / "fixtures"
        / "repo"
        / "task_summary.py"
    )
    source_before = source_file.read_text(encoding="utf-8")

    assert main(_python_regression_fix_argv(["--out", str(out)])) == 0

    workspace_file = (
        out / "workspace" / "fix-task-summary" / "rep-001" / "task_summary.py"
    )
    workspace_text = workspace_file.read_text(encoding="utf-8")
    assert 'owner = task.get("owner") or "unassigned"' in workspace_text
    assert "task.setdefault" not in workspace_text
    assert "if status != \"done\"" not in workspace_text
    assert "return [title for _, title in sorted(overdue)]" in workspace_text
    assert source_file.read_text(encoding="utf-8") == source_before

    assert len(calls) == 1
    assert calls[0]["request_path"] == "fix-task-summary.request.json"
    assert "Your entire response must be one fenced code block" in calls[0]["prompt"]
    assert "`task_summary.py`" in calls[0]["prompt"]
    assert "must not mutate the input task dictionaries" in calls[0]["prompt"]

    record = json.loads((out / "run.jsonl").read_text())
    assert record["pack"] == {"id": "python-regression-fix", "version": "0.1.0"}
    assert record["case"] == "fix-task-summary"
    assert record["adapter"] == "openai-chat"
    assert record["raw"] == {
        "request_path": "raw/fix-task-summary.request.json",
        "response_path": "raw/fix-task-summary.response.json",
    }
    assert record["workspace"] == {
        "path": "workspace/fix-task-summary/rep-001",
        "source_fixture_id": "repo",
        "source_path": "fixtures/repo",
    }
    assert record["patch"] == {"path": "patch/fix-task-summary/rep-001.diff"}
    assert record["task"] == {
        "stdout_path": "task/fix-task-summary/rep-001.stdout.log",
        "stderr_path": "task/fix-task-summary/rep-001.stderr.log",
    }
    assert record["verify"] == {
        "path": "verify/fix-task-summary/rep-001.json",
        "stdout_path": "verify/fix-task-summary/rep-001.stdout.log",
        "stderr_path": "verify/fix-task-summary/rep-001.stderr.log",
    }
    assert record["repo_task"] == {"status": "passed", "verify_exit_code": 0}
    assert record["scoring"] == {"mode": "verify-script", "passed": True}
    assert "artifacts" not in record

    patch = (out / record["patch"]["path"]).read_text(encoding="utf-8")
    assert patch
    assert "--- a/task_summary.py" in patch
    assert 'owner = task.get("owner") or "unassigned"' in patch
    assert "return [title for _, title in sorted(overdue)]" in patch
    assert (out / record["task"]["stdout_path"]).read_text(encoding="utf-8") == (
        "Applied fenced model patch to workspace.\n"
    )
    assert (out / record["task"]["stderr_path"]).read_text(encoding="utf-8") == ""
    assert (out / record["verify"]["stdout_path"]).read_text(encoding="utf-8") == ""
    assert (out / record["verify"]["stderr_path"]).read_text(encoding="utf-8") == ""

    verify_json = json.loads((out / record["verify"]["path"]).read_text())
    assert verify_json["case"] == "fix-task-summary"
    assert verify_json["pack_id"] == "python-regression-fix"
    assert verify_json["pack_version"] == "0.1.0"
    assert verify_json["source_fixture_id"] == "repo"
    assert verify_json["patch_exists"] is True
    assert verify_json["patch_bytes"] > 0
    assert verify_json["exit_code"] == 0
    assert verify_json["passed"] is True
    assert {check["name"] for check in verify_json["checks"]} == {
        "summarize_tasks_counts_and_no_mutation",
        "overdue_titles_date_input",
        "overdue_titles_string_input",
    }
    assert all(check["passed"] for check in verify_json["checks"])


def test_cli_bundled_django_dashboard_regression_fix_runs_repo_task_flow(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output = "\n".join(
        [
            "```diff",
            "--- a/dashboard/permissions.py",
            "+++ b/dashboard/permissions.py",
            "@@ -6,16 +6,18 @@ from typing import Any",
            " def can_view_project(project: dict[str, Any], user: dict[str, Any] | None) -> bool:",
            "     \"\"\"Return whether a user can see a dashboard project.\"\"\"",
            " ",
            "-    if project.get(\"visibility\") == \"public\":",
            "-        return True",
            "-    if project.get(\"visibility\") == \"private\":",
            "-        return user is not None",
            "+    if user is not None and user.get(\"role\") == \"admin\":",
            "+        return True",
            "+    if project.get(\"status\") == \"draft\":",
            "+        return user is not None and project.get(\"owner_id\") == user.get(\"id\")",
            "+",
            "+    visibility = project.get(\"visibility\", \"private\")",
            "+    if visibility == \"public\":",
            "+        return True",
            "     if user is None:",
            "         return False",
            "-    if user.get(\"role\") == \"admin\":",
            "-        return True",
            "     if project.get(\"owner_id\") == user.get(\"id\"):",
            "         return True",
            "-    if user.get(\"id\") in project.get(\"member_ids\", []):",
            "+    if visibility == \"team\" and user.get(\"id\") in project.get(\"member_ids\", []):",
            "         return True",
            "     return False",
            "--- a/dashboard/formatting.py",
            "+++ b/dashboard/formatting.py",
            "@@ -6,15 +6,15 @@ from typing import Any",
            " def format_project_row(project: dict[str, Any]) -> dict[str, str]:",
            "     \"\"\"Return the compact row shape rendered by the dashboard.\"\"\"",
            " ",
            "-    owner = project.setdefault(\"owner\", {})",
            "+    owner = project.get(\"owner\") or {}",
            "     if isinstance(owner, dict):",
            "         owner_name = owner.get(\"name\") or \"Unassigned\"",
            "     else:",
            "         owner_name = str(owner)",
            " ",
            "-    status = project.setdefault(\"status\", \"unknown\")",
            "+    status = project.get(\"status\") or \"unknown\"",
            "     due = project.get(\"due\") or \"\"",
            "-    priority = project.get(\"priority\", \"normal\")",
            "+    priority = project.get(\"priority\") or \"normal\"",
            "     title = str(project.get(\"title\", \"\"))",
            " ",
            "     return {",
            "--- a/dashboard/views.py",
            "+++ b/dashboard/views.py",
            "@@ -3,6 +3,7 @@ from __future__ import annotations",
            " from typing import Any",
            " ",
            " from .formatting import format_project_row",
            "+from .models import due_sort_value, priority_rank",
            " from .permissions import can_view_project",
            " ",
            " ",
            "@@ -17,8 +18,15 @@ def dashboard_rows(",
            "     rows: list[dict[str, str]] = []",
            "     for project in projects:",
            "         if project.get(\"archived\") and not include_archived:",
            "-            rows.append(format_project_row(project))",
            "-        elif can_view_project(project, user):",
            "+            continue",
            "+        if can_view_project(project, user):",
            "             rows.append(format_project_row(project))",
            " ",
            "-    return sorted(rows, key=lambda row: row[\"title\"])",
            "+    return sorted(",
            "+        rows,",
            "+        key=lambda row: (",
            "+            due_sort_value(row[\"due\"]),",
            "+            priority_rank(row[\"priority\"]),",
            "+            row[\"title\"].casefold(),",
            "+        ),",
            "+    )",
            "```",
            "",
        ]
    )
    calls = _install_output_adapter(monkeypatch, output)
    repo_root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(repo_root)
    out = tmp_path / "run"

    pack_dir = repo_root / "benchpacks" / "django-dashboard-regression-fix"
    source_files = [
        pack_dir / "fixtures" / "repo" / "dashboard" / "permissions.py",
        pack_dir / "fixtures" / "repo" / "dashboard" / "formatting.py",
        pack_dir / "fixtures" / "repo" / "dashboard" / "views.py",
    ]
    source_before = {
        path.relative_to(pack_dir).as_posix(): path.read_text(encoding="utf-8")
        for path in source_files
    }

    assert main(_django_dashboard_regression_fix_argv(["--out", str(out)])) == 0

    workspace = out / "workspace" / "fix-dashboard-regressions" / "rep-001"
    permissions_text = (workspace / "dashboard" / "permissions.py").read_text(
        encoding="utf-8",
    )
    formatting_text = (workspace / "dashboard" / "formatting.py").read_text(
        encoding="utf-8",
    )
    views_text = (workspace / "dashboard" / "views.py").read_text(encoding="utf-8")
    assert "visibility = project.get(\"visibility\", \"private\")" in permissions_text
    assert "project.setdefault" not in formatting_text
    assert "due_sort_value(row[\"due\"])" in views_text
    assert "priority_rank(row[\"priority\"])" in views_text
    assert {
        path.relative_to(pack_dir).as_posix(): path.read_text(encoding="utf-8")
        for path in source_files
    } == source_before

    assert len(calls) == 1
    assert calls[0]["request_path"] == "fix-dashboard-regressions.request.json"
    assert "Your entire response must be one fenced code block" in calls[0]["prompt"]
    assert "`dashboard/permissions.py`" in calls[0]["prompt"]
    assert "`dashboard/formatting.py`" in calls[0]["prompt"]
    assert "`dashboard/views.py`" in calls[0]["prompt"]
    assert "Rendering rows must not mutate" in calls[0]["prompt"]

    record = json.loads((out / "run.jsonl").read_text())
    assert record["pack"] == {
        "id": "django-dashboard-regression-fix",
        "version": "0.1.0",
    }
    assert record["case"] == "fix-dashboard-regressions"
    assert record["adapter"] == "openai-chat"
    assert record["raw"] == {
        "request_path": "raw/fix-dashboard-regressions.request.json",
        "response_path": "raw/fix-dashboard-regressions.response.json",
    }
    assert record["workspace"] == {
        "path": "workspace/fix-dashboard-regressions/rep-001",
        "source_fixture_id": "repo",
        "source_path": "fixtures/repo",
    }
    assert record["patch"] == {
        "path": "patch/fix-dashboard-regressions/rep-001.diff",
    }
    assert record["task"] == {
        "stdout_path": "task/fix-dashboard-regressions/rep-001.stdout.log",
        "stderr_path": "task/fix-dashboard-regressions/rep-001.stderr.log",
    }
    assert record["verify"] == {
        "path": "verify/fix-dashboard-regressions/rep-001.json",
        "stdout_path": "verify/fix-dashboard-regressions/rep-001.stdout.log",
        "stderr_path": "verify/fix-dashboard-regressions/rep-001.stderr.log",
    }
    assert record["repo_task"] == {"status": "passed", "verify_exit_code": 0}
    assert record["scoring"] == {"mode": "verify-script", "passed": True}
    assert "artifacts" not in record

    patch = (out / record["patch"]["path"]).read_text(encoding="utf-8")
    assert patch
    assert "--- a/dashboard/permissions.py" in patch
    assert "--- a/dashboard/formatting.py" in patch
    assert "--- a/dashboard/views.py" in patch
    assert (out / record["task"]["stdout_path"]).read_text(encoding="utf-8") == (
        "Applied fenced model patch to workspace.\n"
    )
    assert (out / record["task"]["stderr_path"]).read_text(encoding="utf-8") == ""
    assert (out / record["verify"]["stdout_path"]).read_text(encoding="utf-8") == ""
    assert (out / record["verify"]["stderr_path"]).read_text(encoding="utf-8") == ""

    verify_json = json.loads((out / record["verify"]["path"]).read_text())
    assert verify_json["case"] == "fix-dashboard-regressions"
    assert verify_json["pack_id"] == "django-dashboard-regression-fix"
    assert verify_json["pack_version"] == "0.1.0"
    assert verify_json["source_fixture_id"] == "repo"
    assert verify_json["patch_exists"] is True
    assert verify_json["patch_bytes"] > 0
    assert verify_json["exit_code"] == 0
    assert verify_json["passed"] is True
    assert {check["name"] for check in verify_json["checks"]} == {
        "dashboard_rows_filters_private_and_draft",
        "can_view_project_enforces_visibility_rules",
        "dashboard_rows_excludes_archived_by_default",
        "dashboard_rows_include_archived_when_requested",
        "dashboard_rows_sorting_missing_values_and_no_mutation",
    }
    assert all(check["passed"] for check in verify_json["checks"])


def test_cli_bundled_mini_project_completion_runs_repo_task_flow(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output = "\n".join(
        [
            "```diff",
            "--- a/notes/store.py",
            "+++ b/notes/store.py",
            "@@ -6,13 +6,20 @@",
            " Note = dict[str, object]",
            " ",
            " ",
            "+def _normalized_tags(raw: str) -> list[str]:",
            '+    tags = {tag.strip().lower() for tag in raw.split(",") if tag.strip()}',
            '+    return sorted(tags) or ["untagged"]',
            "+",
            "+",
            " def parse_notes(lines: Iterable[str]) -> list[Note]:",
            "     notes: list[Note] = []",
            "     for line in lines:",
            "         text = line.strip()",
            "-        if not text:",
            '+        if not text or text.startswith("#"):',
            "             continue",
            '-        notes.append({"title": text, "tags": []})',
            '+        title, separator, raw_tags = text.partition("|")',
            '+        tags = _normalized_tags(raw_tags) if separator else ["untagged"]',
            '+        notes.append({"title": title.strip(), "tags": tags})',
            "     return notes",
            " ",
            " ",
            "@@ -21,14 +28,22 @@",
            "     for note in notes:",
            '         for tag in note.get("tags", []):',
            "             counts[str(tag)] += 1",
            "-    return dict(counts)",
            "+    return {tag: counts[tag] for tag in sorted(counts)}",
            "+",
            "+",
            "+def _normalize_tag(tag: object) -> str:",
            "+    return str(tag).strip().lower()",
            " ",
            " ",
            " def filter_titles(notes: Iterable[Note], tag: str) -> list[str]:",
            '-    return [str(note.get("title", "")) for note in notes]',
            "+    needle = _normalize_tag(tag)",
            "+    return [",
            '+        str(note.get("title", ""))',
            "+        for note in notes",
            '+        if needle in {_normalize_tag(tag_value) for tag_value in note.get("tags", [])}',
            "+    ]",
            " ",
            " ",
            " def render_report(notes: Iterable[Note]) -> str:",
            "     counts = summarize_by_tag(notes)",
            '-    lines = [f"{tag}\\t{count}" for tag, count in counts.items()]',
            '-    return "\\n".join(lines)',
            '+    return "".join(f"{tag}\\t{count}\\n" for tag, count in counts.items())',
            "--- a/notes/cli.py",
            "+++ b/notes/cli.py",
            "@@ -3,7 +3,7 @@",
            " import argparse",
            " from pathlib import Path",
            " ",
            "-from .store import parse_notes, render_report",
            "+from .store import filter_titles, parse_notes, render_report",
            " ",
            " ",
            " def main(argv: list[str] | None = None) -> int:",
            "@@ -14,5 +14,9 @@",
            " ",
            '     lines = Path(args.input).read_text(encoding="utf-8").splitlines()',
            "     notes = parse_notes(lines)",
            "-    print(render_report(notes))",
            "+    if args.tag:",
            "+        for title in filter_titles(notes, args.tag):",
            "+            print(title)",
            "+    else:",
            '+        print(render_report(notes), end="")',
            "     return 0",
            "```",
            "",
        ]
    )
    calls = _install_output_adapter(monkeypatch, output)
    repo_root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(repo_root)
    out = tmp_path / "run"

    pack_dir = repo_root / "benchpacks" / "mini-project-completion"
    source_files = [
        pack_dir / "fixtures" / "repo" / "notes" / "store.py",
        pack_dir / "fixtures" / "repo" / "notes" / "cli.py",
    ]
    source_before = {
        path.relative_to(pack_dir).as_posix(): path.read_text(encoding="utf-8")
        for path in source_files
    }

    assert main(_mini_project_completion_argv(["--out", str(out)])) == 0

    workspace = out / "workspace" / "complete-notes-cli" / "rep-001"
    store_text = (workspace / "notes" / "store.py").read_text(encoding="utf-8")
    cli_text = (workspace / "notes" / "cli.py").read_text(encoding="utf-8")
    assert "def _normalized_tags" in store_text
    assert 'text.startswith("#")' in store_text
    assert "return {tag: counts[tag] for tag in sorted(counts)}" in store_text
    assert "filter_titles(notes, args.tag)" in cli_text
    assert {
        path.relative_to(pack_dir).as_posix(): path.read_text(encoding="utf-8")
        for path in source_files
    } == source_before

    assert len(calls) == 1
    assert calls[0]["request_path"] == "complete-notes-cli.request.json"
    assert "Complete the small Python notes-report project" in calls[0]["prompt"]
    assert "`notes/store.py`" in calls[0]["prompt"]
    assert "`notes/cli.py`" in calls[0]["prompt"]
    assert "Return a complete unified diff" in calls[0]["prompt"]

    record = json.loads((out / "run.jsonl").read_text())
    assert record["pack"] == {
        "id": "mini-project-completion",
        "version": "0.1.0",
    }
    assert record["case"] == "complete-notes-cli"
    assert record["adapter"] == "openai-chat"
    assert record["raw"] == {
        "request_path": "raw/complete-notes-cli.request.json",
        "response_path": "raw/complete-notes-cli.response.json",
    }
    assert record["workspace"] == {
        "path": "workspace/complete-notes-cli/rep-001",
        "source_fixture_id": "repo",
        "source_path": "fixtures/repo",
    }
    assert record["patch"] == {
        "path": "patch/complete-notes-cli/rep-001.diff",
    }
    assert record["task"] == {
        "stdout_path": "task/complete-notes-cli/rep-001.stdout.log",
        "stderr_path": "task/complete-notes-cli/rep-001.stderr.log",
    }
    assert record["verify"] == {
        "path": "verify/complete-notes-cli/rep-001.json",
        "stdout_path": "verify/complete-notes-cli/rep-001.stdout.log",
        "stderr_path": "verify/complete-notes-cli/rep-001.stderr.log",
    }
    assert record["repo_task"] == {"status": "passed", "verify_exit_code": 0}
    assert record["scoring"] == {"mode": "verify-script", "passed": True}
    assert "artifacts" not in record

    patch = (out / record["patch"]["path"]).read_text(encoding="utf-8")
    assert patch
    assert "--- a/notes/store.py" in patch
    assert "--- a/notes/cli.py" in patch
    assert "def _normalized_tags" in patch
    assert (out / record["task"]["stdout_path"]).read_text(encoding="utf-8") == (
        "Applied fenced model patch to workspace.\n"
    )
    assert (out / record["task"]["stderr_path"]).read_text(encoding="utf-8") == ""
    assert (out / record["verify"]["stdout_path"]).read_text(encoding="utf-8") == ""
    assert (out / record["verify"]["stderr_path"]).read_text(encoding="utf-8") == ""

    verify_json = json.loads((out / record["verify"]["path"]).read_text())
    assert verify_json["case"] == "complete-notes-cli"
    assert verify_json["pack_id"] == "mini-project-completion"
    assert verify_json["pack_version"] == "0.1.0"
    assert verify_json["source_fixture_id"] == "repo"
    assert verify_json["patch_exists"] is True
    assert verify_json["patch_bytes"] > 0
    assert verify_json["exit_code"] == 0
    assert verify_json["passed"] is True
    assert {check["name"] for check in verify_json["checks"]} == {
        "visible_parse_notes",
        "visible_summary_report_filter",
        "hidden_edge_parse_summary_filter",
        "cli_summary_and_filter",
        "visible_unittest_suite",
    }
    cli_check = next(
        check
        for check in verify_json["checks"]
        if check["name"] == "cli_summary_and_filter"
    )
    assert cli_check["empty_summary_return_code"] == 0
    assert cli_check["actual_empty_summary_stdout"] == ""
    unittest_check = next(
        check
        for check in verify_json["checks"]
        if check["name"] == "visible_unittest_suite"
    )
    assert unittest_check["test_file_exists"] is True
    assert unittest_check["tests_run"] >= unittest_check["minimum_tests_run"]
    assert all(check["passed"] for check in verify_json["checks"])


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


def test_cli_report_set_prints_markdown_for_manifest_dirs(
    tmp_path: Path,
    capsys,
) -> None:
    run_a = tmp_path / "results" / "run-a"
    run_b = tmp_path / "results" / "run-b"
    _write_compare_run(run_a, wall_s=1.0)
    _write_compare_run(run_b, wall_s=2.0)
    manifest_dir = tmp_path / "sets"
    manifest_dir.mkdir()
    manifest = manifest_dir / "qwen.toml"
    manifest.write_text(
        "\n".join(
            [
                "version = 1",
                "result_dirs = [",
                '  "../results/run-a",',
                '  "../results/run-b",',
                "]",
                "",
            ]
        ),
        encoding="utf-8",
    )

    assert main(["report", "--set", str(manifest)]) == 0

    output = capsys.readouterr().out
    assert "# benchpack report" in output
    assert "## Compare Medians" in output
    assert (
        "| run-a | short | 1 | 1 | 1.000 | 0.100 | — | 40.00 | 30.00 | "
        "60 | 10 | — | 0/1 | cache-missing |"
    ) in output
    assert (
        "| run-b | short | 1 | 1 | 2.000 | 0.100 | — | 40.00 | 30.00 | "
        "60 | 10 | — | 0/1 | cache-missing |"
    ) in output


def test_cli_report_rejects_set_and_positional_dirs(tmp_path: Path) -> None:
    run_a = tmp_path / "run-a"
    _write_compare_run(run_a)
    manifest = tmp_path / "set.toml"
    manifest.write_text('version = 1\nresult_dirs = ["run-a"]\n', encoding="utf-8")

    with pytest.raises(SystemExit, match="either --set or result directories"):
        main(["report", "--set", str(manifest), str(run_a)])


def test_cli_report_rejects_no_inputs() -> None:
    with pytest.raises(SystemExit, match="at least one result directory or --set"):
        main(["report"])


def test_cli_report_rejects_missing_run_jsonl(tmp_path: Path) -> None:
    run_a = tmp_path / "run-a"
    _write_compare_run(run_a)
    run_b = tmp_path / "run-b"
    run_b.mkdir()

    with pytest.raises(SystemExit, match="missing run.jsonl"):
        main(["report", str(run_a), str(run_b)])


def test_cli_report_rejects_malformed_run_metadata_without_traceback(
    tmp_path: Path,
) -> None:
    run_a = tmp_path / "run-a"
    _write_compare_run(run_a)
    (run_a / "run-metadata.json").write_text("{bad json}\n", encoding="utf-8")

    with pytest.raises(SystemExit, match="could not parse run metadata"):
        main(["report", str(run_a)])


def test_cli_report_rejects_malformed_hardware_without_traceback(
    tmp_path: Path,
) -> None:
    run_a = tmp_path / "run-a"
    _write_compare_run(run_a)
    (run_a / "hardware.json").write_text("{bad json}\n", encoding="utf-8")

    with pytest.raises(SystemExit, match="could not parse"):
        main(["report", str(run_a)])


def test_cli_registry_import_indexes_result_dir(
    tmp_path: Path,
    capsys,
) -> None:
    run_a = tmp_path / "run-a"
    _write_compare_run(run_a)
    db_path = tmp_path / "registry.sqlite"

    assert main(["registry", "import", "--db", str(db_path), str(run_a)]) == 0

    output = capsys.readouterr().out
    assert f"imported 1 row from {run_a}" in output
    assert "run_id 1" in output
    assert db_path.is_file()


def test_cli_registry_import_rejects_missing_run_jsonl(tmp_path: Path) -> None:
    run_a = tmp_path / "run-a"
    run_a.mkdir()

    with pytest.raises(SystemExit, match="missing run.jsonl"):
        main(["registry", "import", "--db", str(tmp_path / "registry.sqlite"), str(run_a)])


def test_cli_registry_bundle_create_and_validate(
    tmp_path: Path,
    capsys,
) -> None:
    run_a = tmp_path / "run-a"
    _write_compare_run(run_a)
    bundle_dir = tmp_path / "bundle"

    assert (
        main(
            [
                "registry",
                "bundle",
                "create",
                "--out",
                str(bundle_dir),
                "--provenance",
                "operator-curated",
                str(run_a),
            ]
        )
        == 0
    )
    create_output = capsys.readouterr().out
    assert f"created bundle {bundle_dir}" in create_output
    assert "operator-curated" in create_output

    assert main(["registry", "bundle", "validate", str(bundle_dir)]) == 0
    validate_output = capsys.readouterr().out
    assert f"validated bundle {bundle_dir}" in validate_output
    assert "1 run" in validate_output

    db_path = tmp_path / "registry.sqlite"
    assert (
        main(
            [
                "registry",
                "bundle",
                "import",
                "--db",
                str(db_path),
                str(bundle_dir),
            ]
        )
        == 0
    )
    import_output = capsys.readouterr().out
    assert "imported 1 row from bundled run" in import_output
    assert "run_id 1" in import_output
    assert db_path.is_file()
