# DeepSeek V4.1 Flash One-Shot Wrap Campaign - 2026-09-10

Status: complete, four cells, four passes.

This campaign adds the first DeepSeek evidence to the hard one-shot
`django-resume` Electron wrap and the first hosted-model sweep on this
benchmark in which **every thinking level passed**.

## Summary

Four Pi/OpenRouter cells at thinking off/low/medium/high, all on the same
source commit, same prompt, and same runner lane:

| Cell | Thinking | Wall | Files | Insertions | Deletions | Node tests | Outcome |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| `...-030-off` | off | 1371.0s (22m51s) | 33 | 7000 | 136 | 37 | PASS |
| `...-030-low` | low | 560.0s (9m20s) | 33 | 7009 | 139 | 40 | PASS |
| `...-030-medium` | medium | 760.2s (12m40s) | 34 | 7549 | 136 | 53 | PASS |
| `...-030-high` | high | 576.0s (9m36s) | 34 | 7576 | 138 | 53 | PASS |

Every label is prefixed
`deepseek-v41-flash-pi-openrouter-django-resume-030-`.

The thinking levels were genuinely distinct, not a collapsed on/off flag:
reasoning-token counts were 0 / 28,303 / 30,806 / 34,487 for
off/low/medium/high. Total OpenRouter spend for the four cells was about
$0.82.

The thinking-off lane was the **slowest** cell at 1371.0s despite emitting no
reasoning tokens. It spent 96 turns and 108 tool calls exploring, and it did
run `just desktop-dev-smoke` four times and `npm --prefix electron test` five
times. On this workload, wall time tracked exploration and self-verification
behaviour, not reasoning volume.

## Setup

- Model: `deepseek/deepseek-v4.1-flash` via OpenRouter (1.0M context, 384K max
  output, thinking and image support).
- Runner: `scripts/run-agent-wrap-oneshot --runner pi --provider openrouter
  --model deepseek/deepseek-v4.1-flash --pi-mode json --thinking <level>`.
- Host: studio, Apple M4 Max, 128 GB, Mac Studio `Mac16,9`.
- Target: clean checkout `/Users/jochen/projects/django-resume-bench-main` at
  `3dc54f8` (`Release 0.3.0`), cloned per cell into
  `~/projects/django-resume-oneshot-<label>`.
- Pack: one-shot `django-resume` Electron wrap with no deterministic Stage 1
  scaffold.
- Timeout: runner default 7200s; no cell came close.

## Per-Cell Notes

### off - 1371.0s, PASS

96 turns, 108 tool calls (bash 83, write 14, edit 7, read 4), 13.5 MB
transcript, $0.2265. 37 Node tests, the fewest of the four. Did not boot its
own packaged smoke; the verifier's independent packaged smoke passed.

### low - 560.0s, PASS

Fastest and cheapest cell ($0.1838). 57 turns, 78 tool calls (bash 51, write
14, edit 8, read 5), 18.0 MB transcript. 40 Node tests. Three dev smokes and
two Node test runs; no self-booted packaged smoke.

### medium - 760.2s, PASS

65 turns, 108 tool calls (read 49, bash 38, write 10, edit 11), 17.5 MB
transcript, $0.2116. 53 Node tests, matching the GPT-5.5 Pi count. The only
cell that ran its own `smoke:packaged`, plus three dev smokes and three Node
test runs.

### high - 576.0s, PASS

Second-fastest cell, with the most reasoning of the four (34,487 tokens). 75
turns, 95 tool calls (bash 76, write 14, edit 4, read 1), 21.1 MB transcript,
$0.1986. 53 Node tests. Three dev smokes and two Node test runs.

## Comparison

Wall time is only comparable within a harness. This campaign used the neutral
Pi lane, so the fair same-harness reference rows are:

| Row | Harness | Thinking | Wall | Outcome |
| --- | --- | --- | ---: | --- |
| GPT-5.6 Sol | Pi / OpenAI Codex | off | 362.9s | PASS |
| GPT-5.5 | Pi / OpenAI Codex | off | 431.7s | PASS |
| DeepSeek V4.1 Flash | Pi / OpenRouter | low | 560.0s | PASS |
| DeepSeek V4.1 Flash | Pi / OpenRouter | high | 576.0s | PASS |
| Opus 4.8 | Pi / OpenRouter | off | 612.4s | PASS |
| DeepSeek V4.1 Flash | Pi / OpenRouter | medium | 760.2s | PASS |
| Opus 4.8 | Pi / OpenRouter | high | 734.3s | FAIL |
| DeepSeek V4.1 Flash | Pi / OpenRouter | off | 1371.0s | PASS |

The Opus 5 and GPT-5.6 Sol Codex rows in the curated dataset ran through
Claude Code and Codex CLI respectively, so their wall times are **not**
directly comparable to these cells; only outcomes and structural metrics are.
DeepSeek V4.1 Flash is the only model in the dataset with a full four-level
thinking sweep on a single harness.

## Host Electron Install Defect (D-040)

The host Electron install defect is still active, and this campaign
deliberately did **not** set `ELECTRON_OVERRIDE_DIST_PATH` or
`ELECTRON_SKIP_BINARY_DOWNLOAD`. Each cell therefore had to recover a working
`electron/node_modules/electron/dist/` on its own, and all four did:

- `off`: unzipped the cached Electron zip under `~/Library/Caches/electron/`.
- `low`: removed `node_modules/electron` and reinstalled until `dist/` appeared.
- `medium`: copied `dist/` from
  `desktop-django-starter/shells/electron/node_modules/electron/`.
- `high`: unzipped the cached Electron zip into `dist/`.

This is a meaningful difference from the 2026-09-01/02 cells that ran behind
the D-040 override. These DeepSeek cells measure wrapping **plus** workaround
ability, and the pass is not attributable to a pre-fixed host environment.

## Caveats

- One cell per thinking level, one workload, one host. Four passes are four
  samples, not a reliability claim.
- Runtime-and-format comparison only in the sense that this is a hosted API
  model with no local artifact; there is no strict-GGUF or MLX parity lane.
- No Codex CLI or Claude Code route for `deepseek/deepseek-v4.1-flash` was
  verified, so a fully harness-matched comparison against the GPT-5.6 Sol and
  Opus 5 rows is still outstanding.
- Wall times are single observations and were not repeated on a quiet host.

## Artifacts

Generated, ignored result directories:

- `results/agent-wrap-oneshot/deepseek-v41-flash-pi-openrouter-django-resume-030-off/`
- `results/agent-wrap-oneshot/deepseek-v41-flash-pi-openrouter-django-resume-030-low/`
- `results/agent-wrap-oneshot/deepseek-v41-flash-pi-openrouter-django-resume-030-medium/`
- `results/agent-wrap-oneshot/deepseek-v41-flash-pi-openrouter-django-resume-030-high/`

Curated rows: `data/agent-wrap-oneshot-results.json`.
Published at <https://benchmarks.staging.django-cast.com/>.
