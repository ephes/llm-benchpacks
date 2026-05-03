# Apple Silicon M4/M5 Runbook

This runbook makes the first Apple Silicon operational comparison repeatable:
run the same benchmark packs on the local M5 Max machine and on an M4 Max Studio
over SSH, pull the selected result directories back, and compare existing
`run.jsonl` artifacts.

The goal is a first-pass operational and performance comparison, not final proof
of coding-agent quality. Do not commit generated benchmark artifacts from this
workflow unless a later curated run-log entry explicitly calls for a small
summary artifact. Raw responses under `results/*/raw/` remain local generated
output.

## Prerequisites

Both machines should have:

- This repository checked out at the same commit or intentionally documented
  commits.
- Dependencies installed with `uv sync`.
- The same model installed and addressable by the runtime.
- The same model tag, quantization, file, or adapter-visible model id.
- The same runtime path where possible, such as both using `mlx_lm.server`,
  both using `llama-server` through the OpenAI-compatible adapter, or both
  using Ollama through the same adapter shape.
- The same endpoint shape: OpenAI-compatible `/v1` base URL for `openai-chat`,
  or Ollama-native endpoint/defaults for `ollama-generate`.
- Enough disk space for result directories, including `raw/`, `workspace/`,
  `patch/`, `task/`, and `verify/` artifacts for repo-task packs.

The local M5 machine also needs SSH access to the M4 Studio:

```sh
ssh <m4-studio-host> 'uname -a'
```

Use placeholders for private details in notes and handoffs:
`<m4-studio-host>`, `<remote-repo>`, `<model>`, and `<endpoint>`.

## Runtime Setup

Start the same runtime/server shape on both machines before running packs. For
OpenAI-compatible servers, use an endpoint base URL such as:

```text
http://127.0.0.1:8080/v1
http://127.0.0.1:8081/v1
```

For Ollama-native runs, the adapter can use its default local endpoint or an
explicit endpoint if needed:

```sh
uv run benchpack run smoke-chat --adapter ollama-generate --model <model> --host-label m5-max-smoke
```

For `openai-chat` streaming packs, the default sends
`stream_options.include_usage` so supporting endpoints can report token usage.
If a local OpenAI-compatible server rejects that option, rerun the same command
with:

```sh
--openai-stream-usage omit
```

That compatibility mode preserves streamed output and TTFT, but usage-derived
token counts and token-rate fields may stay null unless the server reports
usage another way.

## Recommended Matrix

Run these packs first:

- `smoke-chat`: endpoint sanity.
- `runtime-sweep`: TTFT, decode throughput, total throughput, prompt-token,
  cached-token, and gated prefill-parity comparison.
- `desktop-django-wrap`: prompt-only coding-agent-shaped behavior.
- `patch-from-failure`: tiny repo-mutating, verifier-backed smoke benchmark
  using the current fenced unified-diff contract.

Use result labels that encode the host and pack. The default output directory is
`results/<YYYY-MM-DD>-<host-label>/`, so labels such as `m5-max-runtime` and
`m4-max-runtime` produce distinguishable directories.

## Local M5 Run

From the repo on the local M5 machine:

```sh
uv sync

uv run benchpack run smoke-chat \
  --adapter openai-chat \
  --model <model> \
  --endpoint <endpoint> \
  --host-label <host-label-prefix>-smoke \
  --force

uv run benchpack run runtime-sweep \
  --adapter openai-chat \
  --model <model> \
  --endpoint <endpoint> \
  --host-label <host-label-prefix>-runtime \
  --force

uv run benchpack run desktop-django-wrap \
  --adapter openai-chat \
  --model <model> \
  --endpoint <endpoint> \
  --host-label <host-label-prefix>-wrap \
  --force

uv run benchpack run patch-from-failure \
  --adapter openai-chat \
  --model <model> \
  --endpoint <endpoint> \
  --host-label <host-label-prefix>-patch \
  --force
```

Example label choices:

```text
<host-label-prefix> = m5-max
results/<date>-m5-max-runtime/
results/<date>-m5-max-wrap/
```

If the OpenAI-compatible server rejects streaming usage options, add
`--openai-stream-usage omit` to the streaming packs that need it, especially
`runtime-sweep` and `desktop-django-wrap`.

## SSH M4 Run

Run the same commands on the M4 Studio through SSH. Keep the remote repo path as
a placeholder in docs and handoffs:

```sh
ssh <m4-studio-host> '
  set -eu
  cd <remote-repo>
  uv sync

  uv run benchpack run smoke-chat \
    --adapter openai-chat \
    --model <model> \
    --endpoint <endpoint> \
    --host-label m4-max-smoke \
    --force

  uv run benchpack run runtime-sweep \
    --adapter openai-chat \
    --model <model> \
    --endpoint <endpoint> \
    --host-label m4-max-runtime \
    --force

  uv run benchpack run desktop-django-wrap \
    --adapter openai-chat \
    --model <model> \
    --endpoint <endpoint> \
    --host-label m4-max-wrap \
    --force

  uv run benchpack run patch-from-failure \
    --adapter openai-chat \
    --model <model> \
    --endpoint <endpoint> \
    --host-label m4-max-patch \
    --force
'
```

If the remote endpoint is bound to the M4 Studio loopback interface, the
`<endpoint>` value in the SSH command should usually be a loopback URL from the
remote machine's point of view, for example `http://127.0.0.1:8080/v1`.

For Ollama-native comparisons, keep the same host-label pattern and switch the
adapter shape consistently on both machines:

```sh
uv run benchpack run runtime-sweep \
  --adapter ollama-generate \
  --model <model> \
  --host-label m4-max-runtime \
  --force
```

## Result Pullback

After the remote run, pull back only the result directories needed for the
comparison. For compare-only work, `run.jsonl` is the required file; pulling
`summary.md` and `hardware.json` alongside it keeps the directory inspectable
without copying large generated payloads.

```sh
mkdir -p results/<date>-m4-max-smoke
mkdir -p results/<date>-m4-max-runtime
mkdir -p results/<date>-m4-max-wrap

rsync -a \
  --include '/run.jsonl' \
  --include '/summary.md' \
  --include '/hardware.json' \
  --exclude '*' \
  <m4-studio-host>:<remote-repo>/results/<date>-m4-max-smoke/ \
  results/<date>-m4-max-smoke/

rsync -a \
  --include '/run.jsonl' \
  --include '/summary.md' \
  --include '/hardware.json' \
  --exclude '*' \
  <m4-studio-host>:<remote-repo>/results/<date>-m4-max-runtime/ \
  results/<date>-m4-max-runtime/

rsync -a \
  --include '/run.jsonl' \
  --include '/summary.md' \
  --include '/hardware.json' \
  --exclude '*' \
  <m4-studio-host>:<remote-repo>/results/<date>-m4-max-wrap/ \
  results/<date>-m4-max-wrap/
```

`scp` is also acceptable for the small compare files:

```sh
mkdir -p results/<date>-m4-max-patch

scp \
  <m4-studio-host>:<remote-repo>/results/<date>-m4-max-patch/run.jsonl \
  <m4-studio-host>:<remote-repo>/results/<date>-m4-max-patch/summary.md \
  <m4-studio-host>:<remote-repo>/results/<date>-m4-max-patch/hardware.json \
  results/<date>-m4-max-patch/
```

Do not pull or add `raw/`, `workspace/`, `patch/`, `task/`, `verify/`, or other
generated payloads for this slice. If a later run-log entry needs durable
evidence, curate only the small artifacts called out in `docs/run-log.md`.

## Compare Workflow

`benchpack compare` reads existing result directories that contain `run.jsonl`
and writes only a textual comparison to stdout. Compare matching packs with
matching result labels:

```sh
uv run benchpack compare \
  results/<date>-m5-max-smoke \
  results/<date>-m4-max-smoke

uv run benchpack compare \
  results/<date>-m5-max-runtime \
  results/<date>-m4-max-runtime

uv run benchpack compare \
  results/<date>-m5-max-wrap \
  results/<date>-m4-max-wrap

uv run benchpack compare \
  results/<date>-m5-max-patch \
  results/<date>-m4-max-patch
```

Compare warnings are part of the result interpretation:

- `prompt-diff` means the prompt-token medians differ, so cache and prefill
  conclusions are not comparable for that case.
- `cache-missing` means at least one side did not report complete
  `tokens.cached_prompt` metadata.
- `cache-diff` means prompt metadata matches, but cached prompt-token medians
  differ.
- `prefill_tps med` is rendered only when prompt and cache parity are
  `comparable`.

## Hardware Metadata Check

Before interpreting M4/M5 results, inspect each pulled `hardware.json`. For
Apple Silicon comparisons it should identify the host through `chip`,
`hardware_model`, `hardware_model_name`, `hardware_model_identifier`, `ram_mb`,
`os`, and `gpus` when macOS reports those values.

These fields distinguish host class, for example an M5 Max MacBook Pro from an
M4 Max Mac Studio. They do not prove runtime parity. Continue recording runtime
version, server command, model id, quantization, model checksum, context size,
power mode, thermal state, and cache settings in run notes or curated
`docs/run-log.md` entries when a result is meant to be interpreted later.

## Fairness Checklist

Before interpreting M4-vs-M5 numbers, record or align:

- Same model id, model file, or model tag.
- Same quantization, such as the same MLX quant or GGUF quant.
- Same runtime/server and version where possible.
- Same adapter path, such as `openai-chat` on both machines or
  `ollama-generate` on both machines.
- Same endpoint options, context size, GPU layer settings, batch settings, and
  prompt-cache settings.
- Same `--openai-stream-usage` mode for OpenAI-compatible streaming packs.
- Similar power mode and no intentional low-power throttling on one side only.
- Thermal state before the run, especially whether either machine is already
  heat-soaked.
- Background load, including other inference servers, indexing, builds, or
  backups.
- Runtime version output and model checksum when practical.

Treat M4-vs-M5 conclusions as invalid or exploratory when these items are not
aligned or documented.

## Interpretation Boundaries

`runtime-sweep` is the pack to use for performance comparison now. Its output is
still only as fair as the model/runtime/cache alignment above.

`desktop-django-wrap` is prompt-only. It is useful for coding-agent-shaped
prompt behavior and streaming metrics, but it does not mutate a repository or
prove a real wrap task.

`patch-from-failure` is a tiny repo-task smoke benchmark. It exercises the
current fenced patch, workspace, patch artifact, task log, and verifier path,
but it is not enough for broad coding-agent conclusions.

Larger coding-agent claims should wait for production external harness support,
larger repo-task packs, and curated reporting around those runs.

## Troubleshooting

Endpoint smoke failure:
: Run `smoke-chat` first and confirm the server is reachable from the machine
  executing `benchpack`. For SSH runs, `127.0.0.1` means the remote M4 Studio,
  not the local M5 machine.

Server rejects `stream_options.include_usage`:
: Add `--openai-stream-usage omit` to OpenAI-compatible streaming commands and
  note that usage-derived token counts and token-rate fields may be null.

SSH quoting or path issues:
: Keep `<remote-repo>` free of shell-specific shortcuts in copied runbooks. If
  quoting becomes fragile, SSH into `<m4-studio-host>` interactively and run the
  same commands directly from `<remote-repo>`.

Missing result directories:
: Check the command's printed output path. `--host-label` controls only the
  default output directory name; `--out` overrides it entirely. A repeated label
  on the same date requires `--force` or a unique `--out`.

Compare warnings:
: `benchpack compare` uses existing `run.jsonl` rows only. Prompt, cache, and
  prefill warnings mean the compared rows are not equivalent enough for the
  affected conclusion, even when wall time or decode throughput numbers are
  still visible.
