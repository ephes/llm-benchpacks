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
  implementation-plan.md
  benchpack-format.md
  hardware-targets.md
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
7. Run deterministic verifiers if present.
8. Normalize metrics, resources, and scoring into `run.jsonl`.
9. Write `summary.md`.

## Result Record Envelope

Each line of `run.jsonl` is a result record. The record is the union of three
contributions — adapter, collector, and reporter — with a clear split of
responsibility so that adapter code never needs to read the pack manifest,
sample host resources, or compute derived metrics.

### Adapter return payload

The runtime adapter returns only fields the backend can supply directly:

- `adapter`, `model`, `ok`
- `timing.wall_s`, `timing.ttft_s`, `timing.prefill_tps`, `timing.decode_tps`
- `tokens.prompt`, `tokens.output`
- `raw.request_path`, `raw.response_path`
- optional `backend` table for backend-specific fields the adapter wants to
  preserve verbatim

### Collector sample

The collector samples host and process resources during the run. All fields
are best-effort: missing values are written as `null` rather than blocking the
run.

- `resources.memory_mb` — peak RSS of the runtime process when observable
- `resources.gpu_memory_mb` — peak GPU memory in MB when a GPU is present
- optional `resources.backend` for backend-specific samples (powermetrics on
  macOS, `nvidia-smi` on Linux)

### Reporter additions

The reporter wraps the adapter payload and collector sample before writing them
to `run.jsonl`:

- `pack.id`, `pack.version` — copied from the loaded manifest
- `case` — the case id from the manifest
- `timing.total_tps` — derived as `tokens.output / timing.wall_s`
- `scoring` — the result of the configured scoring mode (see
  `docs/benchpack-format.md`); `null` when mode is `none` or absent

Adapters do not produce or read these fields. The reporter is also where pack
id/version get attached for cross-run comparison.

### Combined record

```json
{
  "pack": { "id": "smoke-chat", "version": "0.1.0" },
  "case": "capital",
  "adapter": "ollama-generate",
  "model": "qwen3-coder",
  "ok": true,
  "timing": {
    "wall_s": 4.21,
    "ttft_s": 0.48,
    "prefill_tps": 950.0,
    "decode_tps": 42.0,
    "total_tps": 45.6
  },
  "tokens": { "prompt": 32768, "output": 192 },
  "resources": {
    "memory_mb": 6234,
    "gpu_memory_mb": 14820
  },
  "scoring": {
    "mode": "contains",
    "passed": true
  },
  "raw": {
    "request_path": "raw/case-001.request.json",
    "response_path": "raw/case-001.response.json"
  }
}
```

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
- `results/*/raw/` is generated and ignored by default; curated `summary.md`,
  `hardware.json`, and small `run.jsonl` files under `results/` may be
  committed.

This keeps the spec close to the code while avoiding generated-result churn in
normal commits.
