# Architecture

## Components

`benchpack` should be a small CLI with five internal concepts:

- **Pack**: versioned workload definition.
- **Case**: one request or task inside a pack.
- **Adapter**: runtime-specific request/response bridge.
- **Collector**: hardware, timing, and process/GPU metrics.
- **Reporter**: JSONL artifacts plus human-readable summaries.

## Proposed Layout

```text
benchpacks/
  smoke-chat/
  runtime-sweep/
  desktop-django-wrap/
src/
  benchpack/
    cli.py
    adapters/
      ollama_generate.py
      openai_chat.py
    packs.py
    results.py
    hardware.py
docs/
  specification.md
  architecture.md
  decisions.md
  spec-log.md
  run-log.md
results/
  .gitkeep
```

## Execution Flow

1. Load a benchmark pack and select cases.
2. Load runtime adapter configuration.
3. Capture host metadata.
4. Warm up the endpoint if the pack requests it.
5. Execute cases, streaming when supported.
6. Persist raw requests and responses.
7. Normalize metrics into `run.jsonl`.
8. Run deterministic verifiers if present.
9. Write `summary.md`.

## Adapter Boundary

Adapters should return a normalized record:

```json
{
  "adapter": "ollama-generate",
  "model": "qwen3-coder",
  "ok": true,
  "timing": {
    "wall_s": 4.21,
    "ttft_s": 0.48,
    "prefill_tps": 950.0,
    "decode_tps": 42.0
  },
  "tokens": {
    "prompt": 32768,
    "output": 192
  },
  "raw": {
    "request_path": "raw/case-001.request.json",
    "response_path": "raw/case-001.response.json"
  }
}
```

Adapters may add backend-specific fields under `backend`.

## Hardware Metadata

Host metadata should be best-effort and never block a run unless the user requests
strict mode.

On macOS:

- `sysctl`
- `system_profiler`
- `powermetrics` only when explicitly enabled

On Linux:

- `lscpu`
- `free`
- `nvidia-smi` when available
- `/etc/os-release`

## Spec And Log Management

The repository should use lightweight, reviewable text files rather than a heavy
project-management system:

- `docs/specification.md` is the current contract.
- `docs/decisions.md` records durable architectural decisions.
- `docs/spec-log.md` records dated spec changes and open questions.
- `docs/run-log.md` records curated benchmark runs with links to result folders.
- `results/` is mostly local/generated; commit only curated summaries.

This keeps the spec close to the code while avoiding generated-result churn in
normal commits.
