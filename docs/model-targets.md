# Model Target Catalog

This catalog tracks preferred and interesting model targets for repeatable
benchmarks. It is source-controlled planning metadata, not a live benchmark
result. Update it before substantial benchmark campaigns and whenever a model,
runtime, quantization, license gate, or deployment target changes enough to
affect comparisons.

Selection rules:

- Prefer current models for new generic questions, while keeping older targets
  only when they provide continuity with already curated results.
- Record exact model IDs, artifact files, quantization, revisions, and runtime
  support before launching live benchmark matrices.
- Treat authentication-gated downloads as explicit prerequisites. Do not hide
  Hugging Face tokens, API keys, bearer tokens, or endpoint credentials in
  metadata or result artifacts.
- Separate strict artifact-parity comparisons from runtime-and-format
  comparisons. MLX, GGUF, and hosted vLLM artifacts can answer useful
  questions, but they are not bit-identical unless documented as such.
- Revisit this file at least before each new benchmark campaign and preferably
  monthly while the model/runtime landscape is moving quickly.

## Priority Targets As Of 2026-05-12

### Gemma 4

Use Gemma 4 as the preferred current small/medium-model target for tri-host
planning. The strict same-GGUF E2B Q4_K_M lane now has M4, M5, and Hetzner
evidence, and the larger `gemma-4-26B-A4B-it-Q4_K_M.gguf` strict-GGUF lane
now also has M5, M4, and Hetzner `llama-server` evidence.
Google announced Gemma 4 on 2026-04-02 with E2B, E4B, 26B MoE, and 31B dense
variants, and described Multi-Token Prediction drafter support on 2026-05-05.

Initial artifact state was verified on 2026-05-06 from primary Google,
Hugging Face, vLLM, Transformers, MLX conversion, and GGUF repository metadata.
The 26B A4B campaign candidate was refreshed on 2026-05-12 from Hugging Face
API metadata before local preflight. Later preflight and benchmark evidence
for selected strict-GGUF artifacts is summarized below.

The previous candidate IDs are real public Hugging Face model repos:

- `google/gemma-4-E2B-it`: public, not gated in Hugging Face API metadata,
  Apache 2.0, Transformers architecture `Gemma4ForConditionalGeneration`,
  source revision `6b7e72c67d3c4556f42b56d5a68b4b8e864c63b4`.
- `google/gemma-4-E4B-it`: public, not gated in Hugging Face API metadata,
  Apache 2.0, Transformers architecture `Gemma4ForConditionalGeneration`,
  source revision `c53e9d33178b12afbad4a48334d21e19b8c29761`.
- `google/gemma-4-26B-A4B-it`: public, not gated in Hugging Face API metadata,
  Apache 2.0, Transformers architecture `Gemma4ForConditionalGeneration`,
  source revision `462a98a12e28e2cbcfccaf78fe41e3e50235e6ae`.
- Gemma 4 31B dense remains a larger investigation target, not a GEX44-class
  benchmark candidate until runtime support, quantization, and memory fit are
  proven.

#### Verified Small Gemma 4 Artifacts

Use immutable Hugging Face repo commit SHAs in metadata and local operator
notes. Artifact checksums and actual memory fit still need preflight capture
after any download; do not invent them from filenames or sizes.

| Target role | Verified status | Source type | Model/repo ID and artifact | Revision/pin guidance | Format/quantization | License/auth gate | Runtime support notes | Source links |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Hetzner vLLM / Transformers E2B | Verified public HF model | Google HF weights | `google/gemma-4-E2B-it` | Pin `6b7e72c67d3c4556f42b56d5a68b4b8e864c63b4` | Safetensors BF16, `Gemma4ForConditionalGeneration` | HF API card license `apache-2.0`; gated/private false | Transformers docs include Gemma4 examples with this ID. vLLM latest supported-models docs list `Gemma4ForConditionalGeneration`; live vLLM serving on the target Hetzner host remains a preflight. | [HF model](https://huggingface.co/google/gemma-4-E2B-it), [Transformers Gemma4](https://huggingface.co/docs/transformers/model_doc/gemma4), [vLLM supported models](https://docs.vllm.ai/en/latest/models/supported_models/) |
| Hetzner vLLM / Transformers E4B | Verified public HF model | Google HF weights | `google/gemma-4-E4B-it` | Pin `c53e9d33178b12afbad4a48334d21e19b8c29761` | Safetensors BF16, `Gemma4ForConditionalGeneration` | HF API card license `apache-2.0`; gated/private false | vLLM Gemma 4 recipe uses this ID in examples; live vLLM serving on the target Hetzner host remains a preflight. | [HF model](https://huggingface.co/google/gemma-4-E4B-it), [vLLM Gemma 4 recipe](https://docs.vllm.ai/projects/recipes/en/latest/Google/Gemma4.html) |
| Selected strict same-GGUF artifact | Verified GGUF repo and file | HF GGUF conversion | `bartowski/google_gemma-4-E2B-it-GGUF`, file `google_gemma-4-E2B-it-Q4_K_M.gguf` | Pin `b5e99bd964eaacc27ba484bb2eb3e9f6160b9143` | GGUF Q4_K_M, 3.46 GB in model card; optional multimodal projectors `mmproj-google_gemma-4-E2B-it-f16.gguf` or `mmproj-google_gemma-4-E2B-it-bf16.gguf` | Apache 2.0, not gated in HF metadata | Selected because it was the smallest verified Q4_K_M instruct artifact among the listed sources. Checksum, conservative load behavior, memory fit, and four-pack benchmark evidence are now captured on M4, M5, and Hetzner. | [GGUF repo](https://huggingface.co/bartowski/google_gemma-4-E2B-it-GGUF), [Q4_K_M file](https://huggingface.co/bartowski/google_gemma-4-E2B-it-GGUF/blob/main/google_gemma-4-E2B-it-Q4_K_M.gguf) |
| Upstream ggml-org E2B GGUF | Verified GGUF repo, no Q4_K_M in repo | ggml-org HF GGUF | `ggml-org/gemma-4-E2B-it-GGUF`, files `gemma-4-E2B-it-Q8_0.gguf`, `gemma-4-E2B-it-bf16.gguf`, plus matching `mmproj-*` files | Pin `a1dac71d3ab220618f5a7573a52acdc4baf3ae3b` | GGUF Q8_0 or BF16, no Q4_K_M listed in this repo on 2026-05-06 | Not gated in HF metadata; repo card does not declare a license field, base model is Apache 2.0 | Repo README recommends `llama-server -hf ggml-org/gemma-4-E2B-it-GGUF`; use only after local load and fit preflight. | [GGUF repo](https://huggingface.co/ggml-org/gemma-4-E2B-it-GGUF), [tree](https://huggingface.co/ggml-org/gemma-4-E2B-it-GGUF/tree/main) |
| Upstream ggml-org E4B GGUF | Verified GGUF repo and file | ggml-org HF GGUF | `ggml-org/gemma-4-E4B-it-GGUF`, file `gemma-4-E4B-it-Q4_K_M.gguf` | Pin `2714b5519c6c3516b1000e7c5e1eba998dfe1fe8` | GGUF Q4_K_M, Q8_0, or BF16; Q4_K_M file is 5.34 GB in HF tree metadata | Not gated in HF metadata; repo card does not declare a license field, base model is Apache 2.0 | Repo README recommends `llama-server -hf ggml-org/gemma-4-E4B-it-GGUF`; use as a stricter upstream-org alternative to the E2B Q4_K_M candidate after fit preflight. | [GGUF repo](https://huggingface.co/ggml-org/gemma-4-E4B-it-GGUF), [Q4_K_M file](https://huggingface.co/ggml-org/gemma-4-E4B-it-GGUF/blob/main/gemma-4-E4B-it-Q4_K_M.gguf) |
| Completed 26B A4B strict same-GGUF campaign | Verified public HF model plus GGUF repo and Q4_K_M file; preflight and default-matrix evidence on M5, M4, and Hetzner | Google HF weights plus ggml-org HF GGUF | Base `google/gemma-4-26B-A4B-it`; GGUF `ggml-org/gemma-4-26B-A4B-it-GGUF`, file `gemma-4-26B-A4B-it-Q4_K_M.gguf` | Pin base `462a98a12e28e2cbcfccaf78fe41e3e50235e6ae`; pin GGUF repo `ae4d537a6345467d1c86bb5cc0d4505ff3ebe0f3` | GGUF Q4_K_M, 16,796,015,136 bytes; LFS SHA-256 `88f4a13b0bb95f031a7fad973e10854122fb67ebc34d214d39a2f65053046abc` | Base HF card license `apache-2.0`; base and GGUF repos are not gated/private in HF API metadata | Completed 2026-05-12 strict same-GGUF `llama-server --reasoning off` campaign at 4K context. M5, M4, and Hetzner all passed direct smoke and default four-pack evidence. Hetzner CUDA memory fit was measured directly: 16,915 MiB projected device use against 19,850 MiB free after stopping production. Stronger repo-task evidence remains opt-in because local M5 broader repo-task outcomes and M4 `endpoint-python-correctness` were mixed. | [Base HF model](https://huggingface.co/google/gemma-4-26B-A4B-it), [GGUF repo](https://huggingface.co/ggml-org/gemma-4-26B-A4B-it-GGUF), [Q4_K_M file](https://huggingface.co/ggml-org/gemma-4-26B-A4B-it-GGUF/blob/main/gemma-4-26B-A4B-it-Q4_K_M.gguf) |
| Alternative GGUF conversion set | Verified GGUF repos and files | Unsloth HF GGUF conversions | `unsloth/gemma-4-E2B-it-GGUF` and `unsloth/gemma-4-E4B-it-GGUF`, including `*-Q4_K_M.gguf` and `*-UD-Q4_K_XL.gguf` files | Pin E2B `90f9618340396838ee7ff5b0ba2da27da62953d3`; E4B `653803f092503c04a65164346f3208a36e707693` | GGUF standard and Unsloth dynamic quant files | Apache 2.0, not gated in HF metadata | Candidate alternatives if the operator wants Unsloth dynamic quants; still not artifact parity with bartowski or ggml-org files. | [E2B GGUF](https://huggingface.co/unsloth/gemma-4-E2B-it-GGUF), [E4B GGUF](https://huggingface.co/unsloth/gemma-4-E4B-it-GGUF) |
| Optional Ollama local adapter targets | Verified official Ollama tags | Ollama library | `gemma4:e2b-it-q4_K_M` digest `7fbdbf8f5e45`; `gemma4:e4b-it-q4_K_M` digest `c6eb396dbd59` | Pin by tag and digest, and capture `ollama show` output in local notes before any run | Ollama Q4_K_M tags, 128K context, text/image input | Apache 2.0 shown on tag pages; no repo credential gate in public page | Useful for `ollama-generate` runs, but not strict same-GGUF parity unless the Ollama model is created from the same downloaded GGUF file used by `llama-server`. | [Ollama tags](https://ollama.com/library/gemma4/tags), [E2B Q4_K_M](https://ollama.com/library/gemma4:e2b-it-q4_K_M), [E4B Q4_K_M](https://ollama.com/library/gemma4:e4b-it-q4_K_M) |
| Apple MLX E2B service-shaped candidate | Verified MLX conversion | MLX Community HF conversion | `mlx-community/gemma-4-e2b-it-4bit`, file `model.safetensors` | Pin `99d9a53ff828d365a8ecae538e45f80a08d612cd` | MLX Safetensors, 4-bit, converted from source-card base `google/gemma-4-e2b-it`; canonical Google repo is `google/gemma-4-E2B-it`; conversion used `mlx-vlm` 0.4.3 | Apache 2.0, not gated in HF metadata | Model card documents `mlx-vlm` usage, not `mlx_lm.server`; OpenAI-compatible MLX serving remains unresolved until local preflight. This is runtime-and-format evidence, not strict GGUF parity. | [MLX repo](https://huggingface.co/mlx-community/gemma-4-e2b-it-4bit) |
| Apple MLX E4B service-shaped candidate | Verified MLX conversion | MLX Community HF conversion | `mlx-community/gemma-4-e4b-it-4bit`, file `model.safetensors` | Pin `cc3b666c01c20395e0dcebd53854504c7d9821f9` | MLX Safetensors, 4-bit, converted from source-card base `google/gemma-4-e4b-it`; canonical Google repo is `google/gemma-4-E4B-it`; conversion used `mlx-vlm` 0.4.3 | Apache 2.0, not gated in HF metadata | Model card documents `mlx-vlm` usage, not `mlx_lm.server`; OpenAI-compatible MLX serving remains unresolved until local preflight. This is runtime-and-format evidence, not strict GGUF parity. | [MLX repo](https://huggingface.co/mlx-community/gemma-4-e4b-it-4bit) |

Tri-host comparison modes:

- Primary strict parity: use the same GGUF artifact through `llama-server` on
  M4, M5, and the Linux CUDA host. This is the completed first campaign mode
  documented in `docs/gemma4-tri-host-runbook.md` and remains the cleanest
  hardware/runtime comparison when the CUDA host has a suitable llama.cpp build
  and the selected quantization fits.
- Service-shaped comparison: use MLX or GGUF on Apple Silicon and Hugging Face
  weights through vLLM on Hetzner. This secondary/fallback mode is useful
  operational evidence, but must be labeled as runtime-and-format rather than
  strict artifact parity.

Current status and boundaries:

- Exact small Gemma 4 IDs and candidate GGUF/MLX/vLLM artifacts are now
  verified above. For the selected strict same-GGUF E2B Q4_K_M artifact, local
  M5 and M4 checksum, `llama-server --reasoning off` load behavior,
  tokenizer/chat-template behavior, context/cache settings, same-commit
  four-pack Apple matrices, and Hetzner CUDA `llama-server` checksum/load/
  memory-fit preflight are captured. The Hetzner strict same-GGUF evidence now
  covers the full four-pack set across two narrow 2026-05-07 exclusive-GPU
  windows: local-only `smoke-chat` passed, `runtime-sweep` wrote 9/9
  `ok=true` measured rows with comparable prompt/cache metadata,
  `desktop-django-wrap` passed both regex cases, and `patch-from-failure`
  reached the endpoint with adapter `ok=true` but failed deterministic
  `verify-script` scoring. That patch outcome matches the Apple M4/M5
  strict-GGUF behavior for this artifact.
- Authenticated OpenAI-compatible endpoint calls now use
  `benchpack run --adapter openai-chat --openai-api-key-env <ENV_NAME>`, which
  reads the bearer token from the named environment variable and sends the
  Authorization header without writing token values to result artifacts. The
  public Hetzner `/v1` token has been provisioned and a single authenticated
  `smoke-chat` passed on 2026-05-07 through the Django Bearer-auth proxy. The
  tmux helper can pass the same option through in dry-run matrices without
  reading the token value.
- Live Hetzner SSH/inventory, GPU-driver recovery, Qwen2.5 baseline
  restoration, authenticated benchmark access, Gemma-4-capable vLLM role
  support, and a local-only full-card idle-load preflight for pinned
  `google/gemma-4-E2B-it` are now recorded as landed in the sibling deployment
  repo's backlog. The proven service-shaped Hetzner path is vLLM
  `0.20.1+cu129` with Torch `2.11.0+cu129`, BF16 Hugging Face weights, 8K
  context, one sequence, `--gpu-memory-utilization 0.85`, text-only multimodal
  limits, and `--enforce-eager`. That is not strict same-GGUF parity with the
  Apple `llama-server` runs.
- Hetzner strict same-GGUF `llama-server`/llama.cpp support, checksum parity,
  conservative 8K load behavior, memory fit, and four-pack benchmark evidence
  are now captured. Use the vLLM route only as runtime-and-format evidence
  unless the planned run explicitly targets the strict same-GGUF
  `llama-server` lane.
- The sibling LNB-010 smoke has landed: authenticated public Hetzner `/v1`
  benchmark access works through the Django Bearer-auth proxy with token env
  var `BENCHPACK_HETZNER_OPENAI_TOKEN`. Treat that as smoke-only access
  readiness, not benchmark campaign approval.
  On Hetzner, follow the sibling readiness notes for the isolated Hugging Face
  cache layout because the complete pinned E2B weights are in the alternate
  `models--google--gemma-4-E2B-it/snapshots/...` directory.
- The 26B A4B strict-GGUF campaign has M5, M4, and Hetzner evidence as of
  2026-05-12. The exact Q4_K_M artifact checksum matched on all three hosts,
  `llama-server --reasoning off` loaded at 4K context, direct smoke passed,
  and the default four-pack passed on all three hosts. M4
  `endpoint-python-correctness` reached the endpoint with adapter `ok=true` but
  failed verifier after a source mutation; local M5 broader repo-task evidence
  was also mixed. Treat this as viable serving/runtime/default-matrix evidence,
  not broad coding-task quality proof. Runtime-sweep compare reported
  `prefill parity=comparable` for short, medium, and long, with median total
  TPS M5 vs M4 vs Hetzner of 106.99 vs 87.58 vs 72.51 short, 108.70 vs 89.08
  vs 71.93 medium, and 107.65 vs 87.25 vs 68.91 long.
  The compact summary is
  `docs/gemma4-26b-strict-gguf-trihost-summary.md`.

Sources:

- <https://blog.google/innovation-and-ai/technology/developers-tools/gemma-4/>
- <https://blog.google/innovation-and-ai/technology/developers-tools/multi-token-prediction-gemma-4/>
- <https://deepmind.google/models/gemma/gemma-4/>
- <https://huggingface.co/google/gemma-4-E2B-it>
- <https://huggingface.co/google/gemma-4-E4B-it>
- <https://huggingface.co/google/gemma-4-26B-A4B-it>
- <https://huggingface.co/docs/transformers/model_doc/gemma4>
- <https://docs.vllm.ai/en/latest/models/supported_models/>
- <https://docs.vllm.ai/projects/recipes/en/latest/Google/Gemma4.html>
- <https://huggingface.co/bartowski/google_gemma-4-E2B-it-GGUF>
- <https://huggingface.co/bartowski/google_gemma-4-E4B-it-GGUF>
- <https://huggingface.co/ggml-org/gemma-4-E2B-it-GGUF>
- <https://huggingface.co/ggml-org/gemma-4-E4B-it-GGUF>
- <https://huggingface.co/ggml-org/gemma-4-26B-A4B-it-GGUF>
- <https://huggingface.co/unsloth/gemma-4-E2B-it-GGUF>
- <https://huggingface.co/unsloth/gemma-4-E4B-it-GGUF>
- <https://ollama.com/library/gemma4/tags>
- <https://huggingface.co/mlx-community/gemma-4-e2b-it-4bit>
- <https://huggingface.co/mlx-community/gemma-4-e4b-it-4bit>

### Qwen3.8

Qwen3.8-27B dense is the current local open-weight Qwen target for
agent-shaped coding workloads. It was released around 2026-08-13 under
Apache 2.0 and first benchmarked in this repo on 2026-08-31.

- Dense target: `Qwen/Qwen3.8-27B`.
- llama.cpp/Ollama GGUF default: `ggml-org/Qwen3.8-27B-GGUF`, file
  `Qwen3.8-27B-Q4_K_M.gguf`.

Runtime compatibility, verified on 2026-08-31:

- Qwen3.8 declares `model_type: "qwen3_5"` and
  `Qwen3_5ForConditionalGeneration` with 64 layers, hidden size 5120, 24
  attention heads, 4 KV heads, and `max_position_embeddings` 262144. That is
  the same architecture string and the same geometry as Qwen3.6-27B, so the
  existing local `llama.cpp` and `mlx-lm` builds load it with no runtime
  upgrade. Plan Qwen3.8 campaigns as drop-in on hosts that already serve
  Qwen3.6-27B.
- Throughput equivalence measured on 2026-09-01: `runtime-sweep` at 4-bit,
  thinking off, puts every Qwen3.8-27B cell within ~4% of the matching
  Qwen3.6-27B dense cell on both hosts and both runtimes — llama.cpp ~21
  (M4 Max) / ~23-24 (M5 Max) median total tok/s, MLX ~25 (M4) / ~30 (M5).
  MLX wins decode by ~20-25%; llama.cpp wins prefill and TTFT. So the
  drop-in claim holds for short-context throughput, not just loading. See
  the 2026-09-01 `docs/run-log.md` row for flags, caveats, and the
  long-context qualifier.
- The internals are not the same. 48 of the 64 layers are GatedDeltaNet linear
  attention and carry no KV cache; only 16 are full attention. KV cost at 262k
  context is therefore far below a conventional 27B. Treat any Qwen3.6-vs-3.8
  long-context or memory-pressure comparison as confounded by this even when
  `--ctx-size` and KV quantization flags are identical.
- Variant landscape, researched 2026-08-31: the Qwen org publishes exactly three
  distinct Qwen3.8 base models - `Qwen3.8-27B` (dense VLM, apache-2.0),
  `Qwen3.8-2.4T-A95B` (MoE, the Max open release, license `qwen3.8-max`, not
  locally runnable), and `Qwen3.8-Flash-Next` (MoE VLM, `model_type
  qwen4_exp`, ~180B total / ~6B active, license `qwen-community-1.0`). **There
  is no Qwen3.8-Coder** and none has been announced; anything under that name
  on Hugging Face is a community quant.
- Flash-Next needs a newer llama.cpp than the 27B does. Homebrew's llama.cpp
  (0.3.0, build 10621, `c1d0e7a00`) lacks the `qwen4exp` arch - verified by
  `strings libllama.dylib | grep -c qwen4exp` returning 0 - and Homebrew has
  nothing newer. A source build at commit `774ee0e` (build 200) contains both
  ggml-org/llama.cpp#27742 "model: add Qwen3.8-Flash-Next (qwen4exp)" (merged
  2026-08-27, `6c84c7d`) and the follow-up #27880 "qwen4exp: reduce number of
  graph splits" (`6fe7498`), and the new binary was verified to contain
  `qwen4exp`. The Homebrew install is untouched and the source build is for
  Flash-Next only. All 27B cells so far used the Homebrew binary; keep later
  27B cells on it for parity.

Verified artifact state:

- `ggml-org/Qwen3.8-27B-GGUF`, file `Qwen3.8-27B-Q4_K_M.gguf`,
  18,973,870,432 bytes, downloaded to
  `/Users/jochen/models/gguf/qwen3.8-27b/` and served successfully by
  `llama-server` build 10621 (`c1d0e7a00`) at `--ctx-size 262144` with q8_0
  KV cache on the M4 Studio.
- Pinned on 2026-08-31: Hugging Face repo revision
  `0669b98607d47046c7c2b3f801011d54a08cfccf` (repo last modified
  2026-08-14), local SHA-256
  `31629f53165ab6a7dad8c9847dcfd1fdf55829dac1e6e748f4a68581b0033d34`. The
  local digest matches the Hugging Face LFS `oid` for the same path and size,
  so this pin is upstream-verified rather than self-reported.
- MLX conversions of the 27B do exist, correcting an earlier note in this repo
  that none was found: `mlx-community/Qwen3.8-27B-{4bit,8bit,bf16}` run through
  `mlx-vlm` because the 27B is a VLM, plus
  `lukaskremla/Qwen3.8-27B-*-MLX-TextOnly` for plain `mlx-lm`. None has been
  loaded or benchmarked here yet, so treat them as candidates pending
  preflight. No Ollama Qwen3.8 tag has been verified.
- Also staged locally and checksum-verified against upstream Hugging Face LFS
  oids: `ggml-org` `Qwen3.8-27B-Q8_0.gguf` (28,595,763,552 bytes, SHA-256
  `f5c702d8820d36fb55985bb238fc83ee3a313e920f4b752a437c3a6a9e14e4c8`) and the
  three `unsloth` `Qwen3.8-Flash-Next-UD-IQ4_XS` shards (10,946,624 /
  49,835,229,856 / 43,836,407,744 bytes, 93.7 GB). Both now have one-shot wrap
  evidence; see below.
- The `qwen4exp` `llama-server` for Flash-Next lives in two byte-identical
  durable copies of the same build 200 (`774ee0e`): `~/src/llama.cpp-774ee0e/bin/`
  (also used by the Laguna cells; its rpath still points into a reapable
  session scratchpad) and `~/opt/llama.cpp-qwen4exp/bin/` (rpath rewritten to
  `@executable_path`, ad-hoc re-signed, verified to load without the scratchpad
  and to contain `qwen4exp`). Use the `~/opt` copy for Flash-Next.
- Flash-Next memory profile on the 128 GB M4 Max, measured 2026-09-01 with the
  exact benchmark flags (`--ctx-size 131072`, q8_0 KV, `-ot "ple_ngram_embd=CPU"`):
  loading wires **96.5 GB** system-wide (from 6.7 GB idle), because
  Metal-resident weights are wired rather than evictable page cache; free drops
  from 89% to 11% and the compressor grows from 6.7 GB to 16 GB. Load takes
  40-54 s. Sustained generation holds ~30 tok/s at short context. Budget the
  remaining ~30 GB for the OS, the agent, and the benchmark's own Django,
  Electron, npm and node processes; see the 2026-09-01 run-log rows for the
  sustained-load and colima numbers.

Chat-template gotchas:

- On this GGUF and llama.cpp build, `--reasoning-budget 0` did **not** disable
  thinking. Only
  `--chat-template-kwargs '{"enable_thinking":false}'` produced a genuine
  thinking-off lane. Verify the thinking state against the template before
  labelling a Qwen3.8 cell as thinking-off.
- The reasoning level is controlled by a `reasoning_effort` template variable,
  not by a llama.cpp flag. Read from `Qwen/Qwen3.8-27B/chat_template.jinja` on
  2026-08-31, the accepted values are `xhigh`, `medium`, and `low`; there is
  no `high`, and the template raises on any other value. When thinking is
  enabled and `reasoning_effort` is unset it resolves to **`xhigh`**, which
  injects an explicit "think carefully ... validate key assumptions, consider
  plausible alternatives" instruction. `medium` injects no reasoning
  instruction at all.
- Consequence for the 2026-08-31 rows: the cell labelled thinking-high ran at
  the model's `xhigh` default because the harness never set `reasoning_effort`.
  Set `--chat-template-kwargs '{"reasoning_effort":"medium"}'` (or `low`)
  explicitly for any intermediate lane, and treat an uncontrolled thinking-on
  Qwen3.8 cell as an `xhigh` cell.

Benchmark evidence:

- **Qwen3.8 passes the hard one-shot `django-resume` Electron wrap at
  `reasoning_effort=medium`, the first passes by a local open-weight model on
  that benchmark.** Nine valid cells ran on 2026-08-31 and 2026-09-01/02: 27B
  Q4_K_M at thinking-off, at the model's uncontrolled `xhigh` default,
  thinking-off again after the Electron environment fix, `medium`, and a
  `medium` confirmation rerun; 27B Q8_0 at `medium`; and Flash-Next UD-IQ4_XS
  at `medium` three times. The three off/xhigh cells failed at the 7200s
  timeout; of the six `medium` cells, five passed: Q4_K_M in 92.8 min (53/53
  tests), Q8_0 in 61.7 min (40/40), Flash-Next in 41.5 min (34/34), at the
  120-min cap (53/53, verified after the timeout), and in 62.3 min (34/34).
  The Q4_K_M `medium` rerun failed. Every cell passed every Node test it
  wrote, so output
  completeness is at hosted-frontier level throughout, and the Qwen3.6
  high-thinking zero-file analysis-paralysis mode did not reproduce in any
  cell. Details and caveats are in
  `docs/benchmarks/django-resume-electron-wrap/qwen38-oneshot-20260831.md`.
- **`reasoning_effort` is the decisive variable for this target, not the model
  or the quantization.** The two cells that differ only in reasoning level
  differ in outcome. Set it explicitly on every Qwen3.8 agentic cell and label
  by the resolved value (D-041); an uncontrolled thinking-on cell runs at
  `xhigh`, which was actively harmful here.
- The limiting factor is self-verification, not code generation. The failing
  `xhigh` cell never ran its own `smoke:packaged` script, and a post-hoc
  counterfactual correcting only its invented `isStalePythonArtifact`
  signature - two lines - made its packaged app build, launch, and serve. The
  failing prewarmed cell did attempt self-verification and deadlocked because
  its own check had no failure path. The passing cell ran 15 smokes.
- The 27B Q4_K_M PASS **did not replicate on its first confirmation**: the
  cell `qwen38-pi-llamacpp-256k-medium-rerun1` failed its packaged smoke
  (`ModuleNotFoundError: example.packaged_settings`, recorded 2026-09-01), so
  that lane is 1-for-2. The Q8_0 pass is a single run. Two of the original
  cells also predate the D-040 Electron environment fix. Do not promote
  Qwen3.8-27B to "reliably passes" on this evidence.
- **Flash-Next at `reasoning_effort=medium` is 3-for-3 and is the recommended
  local Qwen3.8 target for this workload on a 128 GB host.** The original cell
  passed in 41.5 min; the two detached replication cells
  (`qwen38-flashnext-pi-llamacpp-128k-medium-rerun1`, `-rerun2`, 2026-09-01/02)
  passed at the 120-min cap and in 62.3 min. It is the only local open-weight
  lane whose pass has replicated. Caveats that stay attached to the
  recommendation: it is a different model, not a different quant, and its
  numbers carry four confounds against the 27B rows (source-built binary,
  131072 context, UD-IQ4_XS quant family, separate port and provider); the
  cap-hitting rerun lost 30 minutes to `electron-builder --dir` auto-signing
  the app with the host's Developer ID certificate (set
  `CSC_IDENTITY_AUTO_DISCOVERY=false` for benchmark hosts; not applied
  mid-campaign, so rows stay comparable); it wires ~96 GB
  and needs the memory discipline above (stop colima, launch detached per
  D-042); and three runs on one host, one quant, one benchmark is still thin.
  Two earlier attempts of the original cell were terminated by the agent
  harness at ~29.5 minutes and are discarded, not recorded (D-042).
- This is agent-workflow evidence on one workload from single runs per cell. It
  is not a runtime throughput result and not a replacement for the Qwen3.6
  strict-GGUF preflight lane.

Sources:

- <https://huggingface.co/Qwen/Qwen3.8-27B>
- <https://huggingface.co/ggml-org/Qwen3.8-27B-GGUF>

### Laguna XS 2.1

Laguna XS 2.1 (poolside) is the first non-Qwen local coding-specialist target,
added 2026-09-01. It is a 33B-total / ~3B-active MoE (`model_type: laguna`,
40 layers, 256 experts, 8 active per token, 262,144 max positions) under the
permissive OpenMDW-1.1 license, trained specifically for agentic coding and
long-horizon work.

- Official GGUF: `poolside/Laguna-XS-2.1-GGUF`, file
  `Laguna-XS-2.1-Q4_K_M.gguf`, 20,274,300,032 bytes, SHA-256
  `1ac7079101fca5a6df8c5a7523a3c30ea7d1c0e4b1258090e7d6d4039287f6cb`, local
  copies at `~/models/gguf/laguna-xs-2.1/` on studio and atlas.
- Throughput measured 2026-09-01 (`runtime-sweep`, thinking off): **~113-121
  tok/s decode on the M4 Max**, ~5.5x Qwen3.8-27B at the same ~20 GB Q4_K_M
  footprint; prefill up to ~46k tok/s. Atlas (M5) totals were noisier
  (89-129 tok/s) and at/below studio on the long case — unresolved, repeat
  before trusting M5 Laguna numbers. See the 2026-09-01 run-log rows.

Runtime requirements and sharp edges, all verified 2026-09-01:

- **Homebrew llama.cpp build 10621 is not usable for chat** with this model:
  it loads the `laguna` arch and raw `/completion` works, but the chat-mode
  response parser silently swallows all output (empty `content`, tokens still
  billed). Use the source build at `~/src/llama.cpp-774ee0e/bin/` (0.3.0-dev
  build 200, commit `774ee0e`), which carries an explicit Laguna patch in its
  chat auto-parser. The atlas copy is rpath-fixed
  (`install_name_tool -add_rpath @executable_path` + ad-hoc codesign);
  `DYLD_LIBRARY_PATH` does not survive `nohup` under SIP.
- Thinking is a **binary** `enable_thinking` chat-template toggle (default
  false), no effort levels. `--reasoning on/off` does not control it; only
  `--chat-template-kwargs '{"enable_thinking":...}'` does.
- **Degenerate default-system-message loop**: with the template's built-in
  Poolside default system message and thinking off, a user-only prompt at
  temp 0 makes the model emit `〈|SPECIAL_12|〉` (token 31) forever. Any custom
  system message avoids it. For system-message-less harnesses (e.g.
  `runtime-sweep`) serve with the one-line-patched template
  `~/models/gguf/laguna-xs-2.1/laguna-chat-template-neutral-sys.jinja`;
  agent harnesses that always send a system prompt (Pi) can use the stock
  template.
- Native OpenAI `tool_calls` work out of the box on build 200 (GLM-style
  `<tool_call>` wire format, parsed server-side).
- One-shot wrap evidence: **0-for-2** (2026-09-01). Thinking-on FAILED with
  zero self-verification and an `app.exit(0)` that masks startup failure as
  success; thinking-off FAILED despite genuinely self-verifying (ran staging,
  its own packaged smoke, 45 Node + 182 Django tests) because it rationalized
  past its one red end-to-end check and the verifier's smoke then hung. The
  thinking toggle flips verification *behavior* but neither lane passes. See
  the run-log rows before planning follow-up cells.

Sources:

- <https://huggingface.co/poolside/Laguna-XS-2.1>
- <https://huggingface.co/poolside/Laguna-XS-2.1-GGUF>
- <https://poolside.ai/blog/introducing-laguna-s-2-1>

### Qwen3.6

Keep Qwen3.6 as the continuity target for the completed M4/M5 sweep and for
explicit Qwen comparison requests:

- MoE target: `Qwen/Qwen3.6-35B-A3B`.
- Dense target: `Qwen/Qwen3.6-27B`.
- llama.cpp/Ollama GGUF defaults:
  - `unsloth/Qwen3.6-35B-A3B-GGUF`,
    `Qwen3.6-35B-A3B-UD-Q4_K_M.gguf`.
  - `unsloth/Qwen3.6-27B-GGUF`, `Qwen3.6-27B-Q4_K_M.gguf`.
- MLX defaults:
  - `majentik/Qwen3.6-35B-A3B-MLX-MXFP4`.
  - `mlx-community/Qwen3.6-27B-4bit`.

Qwen3.6 remains useful for trend continuity and for the documented Apple
Silicon MLX-vs-llama.cpp-vs-Ollama workflow. It should not be treated as the
default answer to every new “current preferred model” question. For new local
Qwen work prefer Qwen3.8-27B above; keep Qwen3.6 as the baseline the Qwen3.8
rows are read against, and keep it as the only Qwen generation with verified
MLX, Ollama, and strict same-GGUF tri-host artifacts.

Latest strict-GGUF preflight note:

- On 2026-05-09/10, the narrow dense `Qwen3.6-27B-Q4_K_M.gguf` strict-GGUF
  preflight reached all three target hosts: local M5, remote M4 Studio, and
  Hetzner CUDA. All three hosts used SHA256
  `5ed60d0af4650a854b1755bd392f9aef4872643dc25a254bc68043fa638392a0`,
  alias `qwen36-27b-q4km`, `llama-server`, 4K context, f16 KV cache,
  prompt cache, `--parallel 1`, and `--reasoning off`. `smoke-chat` and
  `endpoint-python-correctness` both passed on M4 and Hetzner after the local
  M5 recount-capable runner fix, so the lane now has same-artifact load,
  endpoint-smoke, and one deterministic endpoint-coding pass on all three
  hosts. This is still a narrow preflight, not a full four-pack default matrix
  promotion.

### Hosted Agent/Coding Models

As of 2026-06-23, the most relevant new targets for hosted agent-workflow
experiments are API-served models rather than local strict-GGUF replacements.
Keep them separate from Apple/Hetzner local-runtime comparisons.

| Target role | Model/provider ID | Status | Benchmark use | Notes |
| --- | --- | --- | --- | --- |
| Current-target OpenAI Codex frontier reference | Pi/OpenAI Codex `gpt-5.5`, Codex CLI/yolo `gpt-5.5`, and Pipy/openai-codex `gpt-5.5`; older one-shot control used the same model on the prior `django-resume` 0.2.0 baseline | Pi model metadata available locally on 2026-06-22: context 272,000, max output 128,000, thinking supported; high/off Pi tool probes passed. Codex CLI 0.142.0 accepted `model_reasoning_effort="none"` on 2026-06-23; literal `off` was rejected, and `minimal` was rejected with the active Codex tool set. Codex CLI also accepted `low`, `medium`, and `high`. Pipy's model catalog listed `openai-codex/gpt-5.5` with 400K context, 128K max output, thinking support, and image support on 2026-06-24 | Use as the OpenAI Codex hosted frontier comparison for current `django-resume` 0.3.0 one-shot wrap runs, keeping Pi, direct Codex CLI/yolo, and Pipy native-tool-loop rows separate | Fresh neutral-runner Pi `thinking off` retry on 2026-06-23 passed in 431.7s with a 35-file wrapper, 53 passing Node tests, and packaged smoke (`/health/` 200, `/` 302, `/resume/` 200); this supersedes the earlier interrupted Pi/off evidence for the same current target. The direct-Codex no-reasoning comparison is `model_reasoning_effort="none"`, not `low`: that row failed packaged smoke after 471.4s because Electron reported an install-integrity error before HTTP checks. A fresh neutral-runner Codex CLI/yolo low-reasoning retry passed in 438.3s with a 37-file wrapper, 53 passing Node tests, and packaged smoke, making it the fastest direct Codex CLI current-target pass so far, but it is not the same lane as Pi `thinking off`. A Codex CLI/yolo medium-reasoning row passed in 741.9s with a 39-file wrapper, 55 passing Node tests, and packaged smoke; it was slower than the low rerun and Pi/off rows, slightly slower than the legacy high row, and faster than the neutral-runner high row. A Pipy native tool-loop run with `openai-codex/gpt-5.5` and `--thinking off` passed on 2026-06-24 in 1003.5s with a 35-file wrapper, 53 passing Node tests, and packaged smoke; this is Pipy harness evidence and should not be merged with Pi or Codex CLI timings. Current-target hard one-shot `django-resume` run on 2026-06-22 passed through Pi with `--thinking high`: Pi exited 0 in 701.2s, authored a 35-file Electron wrapper from scratch, passed 53 Node tests, and passed packaged smoke; parsed unique-turn usage estimate was about $4.92. The earlier current-target Pi `thinking off` run was interrupted after 1240.1s due 8.7 GB raw log growth; keep it as a failure-mode artifact, not the representative off-thinking result. Legacy Codex CLI/yolo runs on 2026-06-23 passed in both reasoning modes tested: low passed in 669.9s with a 39-file wrapper, and high passed in 730.2s with a 39-file wrapper. The older 2026-06-03 GPT-5.5 control passed in 432.5s, but used the older 0.2.0 target baseline. |
| Direct Claude Code frontier reference | Claude Code alias `opus` through `scripts/run-agent-wrap-oneshot --runner claude-yolo`; interpreted as Claude Opus 4.8 in this local Claude Code installation | Claude CLI accepted non-interactive `-p --model opus --effort low|medium|high --permission-mode bypassPermissions --tools default` on 2026-06-23 | Use as direct Claude Code/yolo agent-workflow evidence, separate from Pi/OpenRouter Opus rows because runner, auth path, telemetry, and cost accounting differ | Fresh neutral-runner one-shot `django-resume` rows on 2026-06-23 all passed. Low effort exited 0 in 1053.0s with a 38-file wrapper, passed Node tests, and passed packaged smoke (`/health/` 200, `/` 302, `/resume/` 200). Medium effort exited 0 in 871.0s with a 34-file wrapper, 53 passing Node tests, and packaged smoke after one transient Claude API 500 launch failure before edits; it is the fastest direct Claude Code/yolo row so far. High effort exited 0 in 1131.3s with a 34-file wrapper and also passed packaged smoke. Claude Code does not expose a literal thinking-off switch in this CLI path; `--effort low` is the closest no/low-thinking lane. Direct Claude Code rows remain slower than the fastest Pi/OpenRouter Opus 4.8 thinking-off pass. |
| Direct Claude Code Sonnet comparison | Claude Code alias `sonnet` through `scripts/run-agent-wrap-oneshot --runner claude-yolo`; interpreted as Claude Sonnet 4.6 in this local Claude Code installation | Claude CLI accepted non-interactive `-p --model sonnet --effort low|medium|high --permission-mode bypassPermissions --tools default` on 2026-06-23. One initial low-effort launch hit a transient 529 overload before edits and was retried with a fresh forced run | Use as the direct Claude Code/yolo Sonnet comparison against Opus 4.8 and GPT-5.5 one-shot rows on the same `django-resume` 0.3.0 target | Fresh neutral-runner one-shot `django-resume` rows on 2026-06-23 all passed independent smoke. Low effort exited 0 in 1136.1s with a 35-file wrapper, 53 passing Node tests, and packaged smoke. Medium effort exited 0 in 1554.8s with a 33-file wrapper, 47 passing Node tests, and packaged smoke; it is the slowest successful current-target pass in the curated table so far. High effort exited 0 in 1276.6s with a 34-file wrapper, 53 passing Node tests, and packaged smoke. On this slice, Sonnet low was fastest, high was second, and medium was slowest; all three were slower than Opus 4.8 medium and the fastest GPT-5.5 direct/Pi rows. |
| Fast hosted frontier one-shot reference | OpenRouter `anthropic/claude-opus-4.8`; Pi built-in Anthropic ID `claude-opus-4-8` exists but direct Anthropic access was blocked by third-party extra-usage billing on 2026-06-22 | OpenRouter model metadata verified 2026-06-22: text/image model, context length 1,000,000, max completion tokens 128,000; OpenRouter route accepted Pi probes for off and high thinking | Use as a hosted Pi/OpenRouter frontier comparison for one-shot wrap quality and wall-clock, with cost recorded separately from GLM-style hosted runs | First hard one-shot `django-resume` run on 2026-06-22 passed via OpenRouter with thinking off: Pi exited 0 in 612.4s, authored a 36-file Electron wrapper from scratch, passed 53 Node tests, and passed packaged smoke (`/health/` 200, `/` 302, `/resume/` 200). The high-thinking variant failed after 734.3s: it passed 53 Node tests, but packaged smoke failed before HTTP checks with `ModuleNotFoundError: No module named 'desktop_django_starter'`. Parsed unique-turn OpenRouter usage estimates were about $6.22 off and $4.82 high. |
| Long-horizon hosted agent candidate | OpenRouter `z-ai/glm-5.2`, resolved as `z-ai/glm-5.2-20260616`; upstream HF `zai-org/GLM-5.2` | OpenRouter model metadata verified 2026-06-22: text-only, context length 1,048,576, max completion tokens 32,768, supports tools and reasoning parameters | Use for hosted Pi/OpenRouter one-shot wrap experiments, especially when the question is agent workflow/tool reliability rather than local tokens/sec | First hard one-shot `django-resume` runs on 2026-06-22 passed in both thinking modes tested. Thinking off exited 0 in 1126.4s, authored a 31-file Electron wrapper from scratch, passed Node tests, and passed packaged smoke (`/health/` 200, `/` 302, `/resume/` 200). Thinking high also passed, exiting 0 in 1014.0s with a 27-file wrapper and 40 passing Node tests. A staged run the same day also completed Stage 2/3, but its final Electron wrapper smoke hit a host spawn caveat, so the one-shot rows are the stronger benchmark signal. See `docs/run-log.md`. |
| Small/free hosted coding model probe | OpenRouter `cohere/north-mini-code:free`; upstream HF `CohereLabs/North-Mini-Code-1.0` | OpenRouter model metadata verified 2026-06-22: text-only, context length 256,000, advertised free pricing, supports tools | Use as a cheap hosted Pi/OpenRouter sanity or efficiency comparison, not as the strongest quality target | Pi tool-call connectivity probe passed on 2026-06-22. No wrap benchmark has been run yet. |
| Proprietary Qwen hosted agent targets | `qwen3.7-max` and `qwen3.7-plus` through Alibaba Cloud/DashScope-compatible hosted routes when credentials and data policy are acceptable | Not local open-weight replacements. No official Qwen3.7 GGUF/MLX local artifact was verified in this repo on 2026-06-22, and that remains true for the 3.7 line | Use only for hosted API comparison lanes, not for the existing Qwen3.6 M4/M5 MLX-vs-llama.cpp-vs-Ollama workflow | `qwen3.7-max` is the text/agent target; `qwen3.7-plus` is the multimodal agent target. Add exact provider, model ID, pricing, context, and credential path before any live run. Superseded as the answer to “is there a current local Qwen?”: the Qwen3.8 section above records a verified local open-weight Q4_K_M GGUF that loads on existing llama.cpp builds, so a hosted 3.7 route is no longer the only way to get past Qwen3.6 locally. |

Sources:

- <https://openrouter.ai/z-ai/glm-5.2>
- <https://openrouter.ai/anthropic/claude-opus-4.8>
- <https://huggingface.co/blog/zai-org/glm-52-blog>
- <https://openrouter.ai/cohere/north-mini-code%3Afree>
- <https://cohere.com/blog/north-mini-code>
- <https://www.alibabacloud.com/blog/qwen3-7-the-agent-frontier_603154>
- <https://www.alibabacloud.com/blog/qwen3-7-plus-multimodal-agent-intelligence_603206>

## Next Catalog Work

- Keep the strict-GGUF tri-host summary current if the selected Gemma 4
  artifact, llama.cpp revision, context/cache settings, or production Hetzner
  baseline changes. The sibling repo now has both vLLM E2B readiness evidence
  and strict same-GGUF llama.cpp E2B Q4_K_M checksum/load/memory-fit evidence;
  this repo now has strict-GGUF four-pack evidence for the same artifact on M5,
  M4, and Hetzner, summarized in
  `docs/gemma4-strict-gguf-trihost-summary.md`.
- Keep the Gemma 4 26B A4B strict-GGUF summary current if the selected
  artifact, checksum, llama.cpp builds, context/cache settings, or Hetzner
  production baseline changes. Stronger repo-task packs remain opt-in for this
  lane because deterministic verifier quality was mixed outside the default
  four-pack. The completed 2026-05-12 lane is summarized in
  `docs/gemma4-26b-strict-gguf-trihost-summary.md`.
- Keep `docs/qwen36-27b-strict-gguf-trihost-summary.md` current if the narrow
  Qwen3.6 27B strict-GGUF preflight is expanded into a full four-pack matrix
  or if the selected artifact, checksum, llama.cpp builds, context/cache
  settings, or Hetzner production baseline changes.
- Use `docs/gemma4-tri-host-runbook.md` as the archived checklist and template
  for future tri-host campaigns, keeping placeholder metadata examples aligned
  with verified artifacts when they are known.
- The Qwen3.8 GGUF revision pin and SHA-256 were captured on 2026-08-31 and
  are recorded in the Qwen3.8 section above. The 2026-08-31 one-shot wrap rows
  themselves ran before the pin was taken, so treat them as
  runtime-and-format evidence; any strict same-GGUF or tri-host campaign
  should re-verify the digest against the pinned revision at preflight.
- Preflight the identified Qwen3.8-27B MLX conversions (`mlx-community` via
  `mlx-vlm`, `lukaskremla` TextOnly via `mlx-lm`) and find or build an Ollama
  tag before Qwen3.8 can replace Qwen3.6 in the Apple Silicon
  MLX-vs-llama.cpp-vs-Ollama workflow. Only the llama.cpp lane has run.
- Decide whether to promote `Qwen3.8-Flash-Next` to a benchmark target. Its
  artifacts are staged and checksum-verified and a `qwen4exp`-capable llama.cpp
  is built, but it needs the source build rather than the Homebrew binary the
  27B cells use, so it cannot share their parity lane.
- Revisit the catalog before scheduling the next authenticated remote or
  service-shaped benchmark matrix.
