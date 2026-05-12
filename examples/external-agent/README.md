# External-Agent Example Harnesses

This directory contains deterministic local examples for the public
`external-agent` repo-task handoff. They are reference harnesses for harness
authors, not production coding agents.

Use it by selecting the public harness in a `repo-task` case:

```toml
[[cases]]
id = "edit-repo"
kind = "repo-task"
fixture_refs = ["repo"]
harness = { id = "external-agent", timeout_s = 120 }
```

Configure the runner-owned subprocess argv with a JSON array, not a shell
command string. The minimal context handoff example does not make model calls:

```sh
BENCHPACK_EXTERNAL_AGENT_ARGV="[\"python3\",\"$PWD/examples/external-agent/reference-agent.py\"]" \
  uv run benchpack run <pack> --adapter openai-chat --model test-model --endpoint http://localhost:11434/v1
```

The runner appends `--workspace`, `--case`, `--output-dir`, `--repetition`, and
`--context`. The example reads the JSON context, checks that the context version,
case id, repetition, output directory, and workspace path match the appended
arguments, writes `external-agent-example.txt` inside the prepared workspace,
and writes one optional model-call telemetry line to the context-provided
`run.model_call_log_path`.

The model-call log line follows the recommended minimal shape:

```json
{"schema_version":1,"sequence":1,"model":"test-model","ok":true}
```

`model-call-agent.py` is a slightly more production-shaped example. It still
stays deterministic and offline when paired with a local fake endpoint, but it
performs one harness-owned HTTP JSON request before mutating the prepared
workspace. Configure it by placing its example-owned `--model-call-url` before
the runner-appended arguments. The URL must be plain HTTP on a loopback host
such as `127.0.0.1`, `::1`, or `localhost`, and must not contain credentials or
a query string:

```sh
BENCHPACK_EXTERNAL_AGENT_ARGV="[\"python3\",\"$PWD/examples/external-agent/model-call-agent.py\",\"--model-call-url\",\"http://127.0.0.1:8000/model-call\"]" \
  uv run benchpack run <pack> --adapter openai-chat --model test-model --endpoint http://localhost:11434/v1
```

The local endpoint is expected to return a tiny deterministic JSON object such
as:

```json
{"ok":true,"workspace_file":"external-agent-model-call.txt","content":"deterministic text\n","model":"test-model","prompt_tokens":3,"output_tokens":5}
```

The example sends only `case`, `repetition`, and `model` to that endpoint. It
does not call a live model service by itself and does not send full prompts,
adapter responses, raw artifact paths, headers, environment variables, API
keys, bearer tokens, or credentials. From the validated response, it writes only
`external-agent-model-call.txt` inside the prepared workspace and one JSONL line
at `run.model_call_log_path` with the recommended core fields plus safe
example-owned fields such as `adapter`, `endpoint`, `duration_s`,
`prompt_tokens`, and `output_tokens`. `duration_s` is measured telemetry and
can vary between runs; the deterministic boundary is the local request shape,
validated response shape, workspace mutation, and artifact ownership.

The runner treats that file as optional, harness-owned, and opaque: it does not
pre-create, require, validate, parse, summarize, report, or add it to
`run.jsonl`. Default harness telemetry should not include full prompts, full
responses, request bodies beyond a tiny safe local payload, headers,
environment variables, API keys, bearer tokens, or credentials.

`codex-oss-agent.py` is a local live-evidence wrapper for Codex CLI when Codex
is run in OSS/local-provider mode, for example against local Ollama. It reads
the benchpack context, asks Codex to edit the prepared workspace directly, and
writes one safe model-call telemetry line. Use it only when `codex exec --oss`
and the selected local provider/model are already available locally:

```sh
BENCHPACK_EXTERNAL_AGENT_ARGV="[\"python3\",\"$PWD/examples/external-agent/codex-oss-agent.py\",\"--codex-model\",\"qwen3-coder:latest\",\"--local-provider\",\"ollama\"]" \
  uv run benchpack run patch-from-failure-external-agent --adapter ollama-generate --model qwen3-coder:latest
```

Use an absolute script path in `BENCHPACK_EXTERNAL_AGENT_ARGV`. Repo-task
harnesses launch the external process with the prepared workspace as its
current directory, so repo-relative argv paths resolve inside that workspace.

The wrapper passes `--sandbox workspace-write`, `--skip-git-repo-check`, and
`--ephemeral` to `codex exec`. It is intended for local OSS/provider evidence,
not for cloud-backed runs or runs that require secrets.

`openai-direct-edit-agent.py` is an opt-in live wrapper for authenticated
OpenAI-compatible chat endpoints. It reads the public context, calls
`/chat/completions`, expects the assistant to return JSON full-file
replacements, applies only files listed in the prompt's allowed edit paths, and
writes one safe telemetry line. That line includes the safe request-shape
labels `response_format` and `token_budget_field`, plus `finish_reason` when
the endpoint reports it. By default it sends a portable plain non-streaming
chat-completion request. When the target endpoint supports
OpenAI-style JSON-object response formatting, add
`--response-format json_object` to the wrapper argv to request a stricter JSON
assistant payload for the harness-owned task call. When the endpoint supports
OpenAI-style structured outputs, use `--response-format json_schema` instead;
that mode sends a strict schema for the full-file replacement payload and
constrains `files[].path` to the prompt-derived allowed path list. The wrapper
validates the complete `files` array before writing any replacement content,
rejects duplicate or disallowed paths, and restores original file contents if a
write fails during application. It defaults to `--max-tokens 4096`; pass a
larger value such as `--max-tokens 8192` when direct-edit payloads need more
completion room. The budget is sent as `max_tokens` by default for local
OpenAI-compatible servers; add `--token-budget-field max_completion_tokens`
only for endpoints or models that require the newer OpenAI-style field. An
empty `files` array is a valid
no-op wrapper response; the benchmark verifier still decides whether that
no-op passes. Use it from the operator machine when the endpoint and token are
already configured locally:

```sh
BENCHPACK_EXTERNAL_AGENT_ARGV="[\"python3\",\"$PWD/examples/external-agent/openai-direct-edit-agent.py\",\"--endpoint\",\"https://llm.django-cast.com/v1\",\"--model\",\"Qwen/Qwen2.5-1.5B-Instruct\",\"--api-key-env\",\"BENCHPACK_HETZNER_OPENAI_TOKEN\"]" \
  uv run benchpack run patch-from-failure-external-agent \
    --adapter openai-chat \
    --model Qwen/Qwen2.5-1.5B-Instruct \
    --endpoint https://llm.django-cast.com/v1 \
    --openai-api-key-env BENCHPACK_HETZNER_OPENAI_TOKEN
```

For a JSON-mode experiment, add
`"--response-format","json_object"` to `BENCHPACK_EXTERNAL_AGENT_ARGV` anywhere
after the wrapper script path. For a structured-output experiment, use
`"--response-format","json_schema"` instead. For a larger-budget
structured-output experiment against an endpoint that expects the newer token
budget field, add
`"--max-tokens","8192","--token-budget-field","max_completion_tokens"` as well.

The wrapper records only the environment variable name in commands and context;
the token value must stay in the local environment or secret store. For the
Hetzner service path, the server is reached through the public TLS/Django
Bearer-auth proxy. Do not install or expect Codex, Claude, Ollama, or this
repository on the server for this wrapper.
