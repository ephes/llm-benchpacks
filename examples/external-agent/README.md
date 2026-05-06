# External-Agent Reference Harness

This directory contains a deterministic local example for the public
`external-agent` repo-task handoff. It is a reference harness for harness
authors, not a production coding agent, and it does not make live model calls.

Use it by selecting the public harness in a `repo-task` case:

```toml
[[cases]]
id = "edit-repo"
kind = "repo-task"
fixture_refs = ["repo"]
harness = { id = "external-agent", timeout_s = 120 }
```

Configure the runner-owned subprocess argv with a JSON array, not a shell
command string:

```sh
BENCHPACK_EXTERNAL_AGENT_ARGV='["python3","examples/external-agent/reference-agent.py"]' \
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

The runner treats that file as optional, harness-owned, and opaque: it does not
pre-create, require, validate, parse, summarize, report, or add it to
`run.jsonl`. The example also keeps the telemetry intentionally small. Default
harness telemetry should not include full prompts, full responses, request
bodies, headers, environment variables, API keys, bearer tokens, or credentials.
