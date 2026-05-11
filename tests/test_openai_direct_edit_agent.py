from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest


def _load_agent_module() -> Any:
    path = (
        Path(__file__).resolve().parents[1]
        / "examples"
        / "external-agent"
        / "openai-direct-edit-agent.py"
    )
    spec = importlib.util.spec_from_file_location("openai_direct_edit_agent", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_chat_completions_url_appends_expected_path() -> None:
    agent = _load_agent_module()

    assert (
        agent._chat_completions_url("https://llm.example.test/v1")
        == "https://llm.example.test/v1/chat/completions"
    )
    assert (
        agent._chat_completions_url(
            "https://llm.example.test/v1/chat/completions"
        )
        == "https://llm.example.test/v1/chat/completions"
    )


def test_chat_completions_url_rejects_unsafe_endpoints() -> None:
    agent = _load_agent_module()

    for endpoint in (
        "ftp://llm.example.test/v1",
        "https://user:pass@llm.example.test/v1",
        "https://llm.example.test/v1?token=bad",
        "https://llm.example.test/v1#fragment",
        "/v1",
    ):
        with pytest.raises(ValueError):
            agent._chat_completions_url(endpoint)


def test_allowed_paths_match_prompt_bullets() -> None:
    agent = _load_agent_module()

    assert agent._allowed_paths(
        "Allowed repo-root paths to edit:\n\n"
        "- `dashboard/permissions.py`\n"
        "- `dashboard/formatting.py`\n"
        "- `dashboard/views.py`\n\n"
        "Workspace editing contract:\n"
        "- Edit only the allowed repo-root paths listed above.\n"
    ) == (
        "dashboard/permissions.py",
        "dashboard/formatting.py",
        "dashboard/views.py",
    )


def test_allowed_paths_ignore_later_backticked_bullets() -> None:
    agent = _load_agent_module()

    assert agent._allowed_paths(
        "Allowed repo-root path to edit:\n\n"
        "- `greeter.py`\n\n"
        "Useful files:\n\n"
        "- `tests/test_greeter.py`\n"
    ) == ("greeter.py",)


def test_allowed_paths_allow_blank_lines_between_bullets() -> None:
    agent = _load_agent_module()

    assert agent._allowed_paths(
        "Allowed repo-root paths to edit:\n\n"
        "- `dashboard/permissions.py`\n\n"
        "- `dashboard/formatting.py`\n\n"
        "- `dashboard/views.py`\n\n"
        "Current file: `dashboard/permissions.py`\n"
    ) == (
        "dashboard/permissions.py",
        "dashboard/formatting.py",
        "dashboard/views.py",
    )


def test_allowed_paths_require_section_heading() -> None:
    agent = _load_agent_module()

    with pytest.raises(ValueError):
        agent._allowed_paths(
            "The Allowed repo-root path wording appears in prose.\n\n"
            "- `tests/test_greeter.py`\n"
        )


def test_apply_edits_rejects_disallowed_paths(tmp_path: Path) -> None:
    agent = _load_agent_module()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "greeter.py").write_text("old\n", encoding="utf-8")

    try:
        agent._apply_edits(
            workspace,
            {"files": [{"path": "tests/test_greeter.py", "content": "bad\n"}]},
            ("greeter.py",),
        )
    except ValueError as exc:
        assert "disallowed path" in str(exc)
    else:
        raise AssertionError("expected disallowed path rejection")

    assert (workspace / "greeter.py").read_text(encoding="utf-8") == "old\n"


def test_workspace_path_rejects_unsafe_paths(tmp_path: Path) -> None:
    agent = _load_agent_module()
    workspace = (tmp_path / "workspace").resolve()
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (workspace / "link").symlink_to(outside)

    for relative_path in (
        "/tmp/file.py",
        "../file.py",
        "dir/../file.py",
        "bad\x00path.py",
        "link/escaped.py",
    ):
        with pytest.raises(ValueError):
            agent._workspace_path(workspace, relative_path)


def test_apply_edits_writes_allowed_file(tmp_path: Path) -> None:
    agent = _load_agent_module()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "greeter.py"
    target.write_text("old\n", encoding="utf-8")

    changed, summary = agent._apply_edits(
        workspace,
        {
            "files": [{"path": "greeter.py", "content": "new\n"}],
            "summary": "fixed greeting",
        },
        ("greeter.py",),
    )

    assert changed == 1
    assert summary == "fixed greeting"
    assert target.read_text(encoding="utf-8") == "new\n"


def test_call_chat_completion_omits_response_format_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = _load_agent_module()
    requests: list[Any] = []

    class FakeResponse:
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(
                {"choices": [{"message": {"content": "{\"files\":[]}"}}]}
            ).encode("utf-8")

    def fake_urlopen(request: Any, timeout: float) -> FakeResponse:
        requests.append((request, timeout))
        return FakeResponse()

    monkeypatch.setattr(agent.urllib.request, "urlopen", fake_urlopen)

    response, _ = agent._call_chat_completion(
        endpoint="https://llm.example.test/v1",
        api_key="secret",
        model="test-model",
        prompt="Fix it.",
        allowed_paths=("greeter.py",),
        timeout_s=12.5,
        temperature=0.0,
        max_tokens=1024,
        response_format="default",
    )

    assert response["choices"][0]["message"]["content"] == '{"files":[]}'
    request, timeout = requests[0]
    assert timeout == 12.5
    assert request.full_url == "https://llm.example.test/v1/chat/completions"
    body = json.loads(request.data.decode("utf-8"))
    assert "response_format" not in body


def test_call_chat_completion_sends_json_object_response_format(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = _load_agent_module()
    requests: list[Any] = []

    class FakeResponse:
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(
                {"choices": [{"message": {"content": "{\"files\":[]}"}}]}
            ).encode("utf-8")

    def fake_urlopen(request: Any, timeout: float) -> FakeResponse:
        requests.append((request, timeout))
        return FakeResponse()

    monkeypatch.setattr(agent.urllib.request, "urlopen", fake_urlopen)

    agent._call_chat_completion(
        endpoint="https://llm.example.test/v1",
        api_key="secret",
        model="test-model",
        prompt="Fix it.",
        allowed_paths=("greeter.py",),
        timeout_s=12.5,
        temperature=0.0,
        max_tokens=1024,
        response_format="json_object",
    )

    request, _ = requests[0]
    body = json.loads(request.data.decode("utf-8"))
    assert body["response_format"] == {"type": "json_object"}


def test_call_chat_completion_rejects_unknown_response_format() -> None:
    agent = _load_agent_module()

    with pytest.raises(ValueError, match="unsupported response format"):
        agent._call_chat_completion(
            endpoint="https://llm.example.test/v1",
            api_key="secret",
            model="test-model",
            prompt="Fix it.",
            allowed_paths=("greeter.py",),
            timeout_s=12.5,
            temperature=0.0,
            max_tokens=1024,
            response_format="xml",
        )


def test_parse_edit_payload_strips_json_fence() -> None:
    agent = _load_agent_module()

    assert agent._parse_edit_payload(
        '```json\n{"files":[],"summary":"none"}\n```'
    ) == {"files": [], "summary": "none"}


def test_parse_edit_payload_reports_finish_reason() -> None:
    agent = _load_agent_module()

    with pytest.raises(ValueError, match="finish_reason=length"):
        agent._parse_edit_payload("not json", finish_reason="length")


def test_safe_endpoint_label_has_no_url_or_credential_markers() -> None:
    agent = _load_agent_module()

    label = agent._safe_endpoint_label("https://llm.example.test/v1")

    assert label == "llm.example.test"
    assert "://" not in label
    assert "?" not in label
    assert "@" not in label


def test_load_context_rejects_model_call_log_under_raw(tmp_path: Path) -> None:
    agent = _load_agent_module()
    workspace = tmp_path / "workspace"
    output = tmp_path / "out"
    workspace.mkdir()
    (output / "raw").mkdir(parents=True)
    context_path = output / "task" / "case" / "rep-001.context.json"
    context_path.parent.mkdir(parents=True)
    context_path.write_text(
        json.dumps(
            {
                "version": 1,
                "case": {"id": "case", "prompt": "- `greeter.py`\n"},
                "run": {
                    "output_dir": str(output.resolve()),
                    "repetition": 1,
                    "model_call_log_path": str(
                        (output / "raw" / "rep-001.model-calls.jsonl").resolve()
                    ),
                },
                "workspace": {"path": str(workspace.resolve())},
            }
        ),
        encoding="utf-8",
    )

    args = argparse.Namespace(
        workspace=str(workspace),
        case="case",
        output_dir=str(output),
        repetition="1",
        context=str(context_path),
    )

    try:
        agent._load_and_validate_context(args)
    except ValueError as exc:
        assert "must not be under raw" in str(exc)
    else:
        raise AssertionError("expected raw model-call log rejection")
