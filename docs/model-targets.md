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

## Priority Targets As Of 2026-05-06

### Gemma 4

Use Gemma 4 as the preferred current small-model target for the next
M4/M5/Hetzner planning slice, subject to artifact and runtime validation.
Google announced Gemma 4 on 2026-04-02 with E2B, E4B, 26B MoE, and 31B dense
variants, and described Multi-Token Prediction drafter support on 2026-05-05.

Verified artifact state as of 2026-05-06, based on primary Google, Hugging
Face, vLLM, Transformers, MLX conversion, and GGUF repository metadata. No
models were downloaded, no endpoints were called, and no benchmarks were run.

The previous candidate IDs are real public Hugging Face model repos:

- `google/gemma-4-E2B-it`: public, not gated in Hugging Face API metadata,
  Apache 2.0, Transformers architecture `Gemma4ForConditionalGeneration`,
  source revision `6b7e72c67d3c4556f42b56d5a68b4b8e864c63b4`.
- `google/gemma-4-E4B-it`: public, not gated in Hugging Face API metadata,
  Apache 2.0, Transformers architecture `Gemma4ForConditionalGeneration`,
  source revision `c53e9d33178b12afbad4a48334d21e19b8c29761`.
- Gemma 4 26B MoE and 31B dense variants remain larger investigation targets,
  not the first Hetzner GEX44-class benchmark until runtime support,
  quantization, and memory fit are proven.

#### Verified Small Gemma 4 Artifacts

Use immutable Hugging Face repo commit SHAs in metadata and local operator
notes. Artifact checksums and actual memory fit still need preflight capture
after any download; do not invent them from filenames or sizes.

| Target role | Verified status | Source type | Model/repo ID and artifact | Revision/pin guidance | Format/quantization | License/auth gate | Runtime support notes | Source links |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Hetzner vLLM / Transformers E2B | Verified public HF model | Google HF weights | `google/gemma-4-E2B-it` | Pin `6b7e72c67d3c4556f42b56d5a68b4b8e864c63b4` | Safetensors BF16, `Gemma4ForConditionalGeneration` | HF API card license `apache-2.0`; gated/private false | Transformers docs include Gemma4 examples with this ID. vLLM latest supported-models docs list `Gemma4ForConditionalGeneration`; live vLLM serving on the target Hetzner host remains a preflight. | [HF model](https://huggingface.co/google/gemma-4-E2B-it), [Transformers Gemma4](https://huggingface.co/docs/transformers/model_doc/gemma4), [vLLM supported models](https://docs.vllm.ai/en/latest/models/supported_models/) |
| Hetzner vLLM / Transformers E4B | Verified public HF model | Google HF weights | `google/gemma-4-E4B-it` | Pin `c53e9d33178b12afbad4a48334d21e19b8c29761` | Safetensors BF16, `Gemma4ForConditionalGeneration` | HF API card license `apache-2.0`; gated/private false | vLLM Gemma 4 recipe uses this ID in examples; live vLLM serving on the target Hetzner host remains a preflight. | [HF model](https://huggingface.co/google/gemma-4-E4B-it), [vLLM Gemma 4 recipe](https://docs.vllm.ai/projects/recipes/en/latest/Google/Gemma4.html) |
| Primary strict same-GGUF candidate | Verified GGUF repo and file | HF GGUF conversion | `bartowski/google_gemma-4-E2B-it-GGUF`, file `google_gemma-4-E2B-it-Q4_K_M.gguf` | Pin `b5e99bd964eaacc27ba484bb2eb3e9f6160b9143` | GGUF Q4_K_M, 3.46 GB in model card; optional multimodal projectors `mmproj-google_gemma-4-E2B-it-f16.gguf` or `mmproj-google_gemma-4-E2B-it-bf16.gguf` | Apache 2.0, not gated in HF metadata | Best first strict-GGUF dry-run candidate because it is the smallest verified Q4_K_M instruct artifact among the listed sources. llama.cpp load and memory fit on M4, M5, and Hetzner remain local preflights. | [GGUF repo](https://huggingface.co/bartowski/google_gemma-4-E2B-it-GGUF), [Q4_K_M file](https://huggingface.co/bartowski/google_gemma-4-E2B-it-GGUF/blob/main/google_gemma-4-E2B-it-Q4_K_M.gguf) |
| Upstream ggml-org E2B GGUF | Verified GGUF repo, no Q4_K_M in repo | ggml-org HF GGUF | `ggml-org/gemma-4-E2B-it-GGUF`, files `gemma-4-E2B-it-Q8_0.gguf`, `gemma-4-E2B-it-bf16.gguf`, plus matching `mmproj-*` files | Pin `a1dac71d3ab220618f5a7573a52acdc4baf3ae3b` | GGUF Q8_0 or BF16, no Q4_K_M listed in this repo on 2026-05-06 | Not gated in HF metadata; repo card does not declare a license field, base model is Apache 2.0 | Repo README recommends `llama-server -hf ggml-org/gemma-4-E2B-it-GGUF`; use only after local load and fit preflight. | [GGUF repo](https://huggingface.co/ggml-org/gemma-4-E2B-it-GGUF), [tree](https://huggingface.co/ggml-org/gemma-4-E2B-it-GGUF/tree/main) |
| Upstream ggml-org E4B GGUF | Verified GGUF repo and file | ggml-org HF GGUF | `ggml-org/gemma-4-E4B-it-GGUF`, file `gemma-4-E4B-it-Q4_K_M.gguf` | Pin `2714b5519c6c3516b1000e7c5e1eba998dfe1fe8` | GGUF Q4_K_M, Q8_0, or BF16; Q4_K_M file is 5.34 GB in HF tree metadata | Not gated in HF metadata; repo card does not declare a license field, base model is Apache 2.0 | Repo README recommends `llama-server -hf ggml-org/gemma-4-E4B-it-GGUF`; use as a stricter upstream-org alternative to the E2B Q4_K_M candidate after fit preflight. | [GGUF repo](https://huggingface.co/ggml-org/gemma-4-E4B-it-GGUF), [Q4_K_M file](https://huggingface.co/ggml-org/gemma-4-E4B-it-GGUF/blob/main/gemma-4-E4B-it-Q4_K_M.gguf) |
| Alternative GGUF conversion set | Verified GGUF repos and files | Unsloth HF GGUF conversions | `unsloth/gemma-4-E2B-it-GGUF` and `unsloth/gemma-4-E4B-it-GGUF`, including `*-Q4_K_M.gguf` and `*-UD-Q4_K_XL.gguf` files | Pin E2B `90f9618340396838ee7ff5b0ba2da27da62953d3`; E4B `653803f092503c04a65164346f3208a36e707693` | GGUF standard and Unsloth dynamic quant files | Apache 2.0, not gated in HF metadata | Candidate alternatives if the operator wants Unsloth dynamic quants; still not artifact parity with bartowski or ggml-org files. | [E2B GGUF](https://huggingface.co/unsloth/gemma-4-E2B-it-GGUF), [E4B GGUF](https://huggingface.co/unsloth/gemma-4-E4B-it-GGUF) |
| Optional Ollama local adapter targets | Verified official Ollama tags | Ollama library | `gemma4:e2b-it-q4_K_M` digest `7fbdbf8f5e45`; `gemma4:e4b-it-q4_K_M` digest `c6eb396dbd59` | Pin by tag and digest, and capture `ollama show` output in local notes before any run | Ollama Q4_K_M tags, 128K context, text/image input | Apache 2.0 shown on tag pages; no repo credential gate in public page | Useful for `ollama-generate` runs, but not strict same-GGUF parity unless the Ollama model is created from the same downloaded GGUF file used by `llama-server`. | [Ollama tags](https://ollama.com/library/gemma4/tags), [E2B Q4_K_M](https://ollama.com/library/gemma4:e2b-it-q4_K_M), [E4B Q4_K_M](https://ollama.com/library/gemma4:e4b-it-q4_K_M) |
| Apple MLX E2B service-shaped candidate | Verified MLX conversion | MLX Community HF conversion | `mlx-community/gemma-4-e2b-it-4bit`, file `model.safetensors` | Pin `99d9a53ff828d365a8ecae538e45f80a08d612cd` | MLX Safetensors, 4-bit, converted from source-card base `google/gemma-4-e2b-it`; canonical Google repo is `google/gemma-4-E2B-it`; conversion used `mlx-vlm` 0.4.3 | Apache 2.0, not gated in HF metadata | Model card documents `mlx-vlm` usage, not `mlx_lm.server`; OpenAI-compatible MLX serving remains unresolved until local preflight. This is runtime-and-format evidence, not strict GGUF parity. | [MLX repo](https://huggingface.co/mlx-community/gemma-4-e2b-it-4bit) |
| Apple MLX E4B service-shaped candidate | Verified MLX conversion | MLX Community HF conversion | `mlx-community/gemma-4-e4b-it-4bit`, file `model.safetensors` | Pin `cc3b666c01c20395e0dcebd53854504c7d9821f9` | MLX Safetensors, 4-bit, converted from source-card base `google/gemma-4-e4b-it`; canonical Google repo is `google/gemma-4-E4B-it`; conversion used `mlx-vlm` 0.4.3 | Apache 2.0, not gated in HF metadata | Model card documents `mlx-vlm` usage, not `mlx_lm.server`; OpenAI-compatible MLX serving remains unresolved until local preflight. This is runtime-and-format evidence, not strict GGUF parity. | [MLX repo](https://huggingface.co/mlx-community/gemma-4-e4b-it-4bit) |

Tri-host comparison modes:

- Primary strict parity: use the same GGUF artifact through `llama-server` on
  M4, M5, and the Linux CUDA host. This is the first campaign mode documented
  in `docs/gemma4-tri-host-runbook.md` and is the cleanest hardware/runtime
  comparison if the CUDA host has a suitable llama.cpp build and the selected
  quantization fits.
- Service-shaped comparison: use MLX or GGUF on Apple Silicon and Hugging Face
  weights through vLLM on Hetzner. This secondary/fallback mode is useful
  operational evidence, but must be labeled as runtime-and-format rather than
  strict artifact parity.

Current blockers:

- Exact small Gemma 4 IDs and first candidate GGUF/MLX/vLLM artifacts are now
  verified above. For the selected strict same-GGUF E2B Q4_K_M artifact, local
  M5 and M4 checksum, `llama-server --reasoning off` load behavior,
  tokenizer/chat-template behavior, context/cache settings, and same-commit
  four-pack Apple matrices are captured. Equivalent strict-GGUF llama.cpp
  support and memory fit remain unverified on Hetzner.
- Authenticated OpenAI-compatible endpoint calls now use
  `benchpack run --adapter openai-chat --openai-api-key-env <ENV_NAME>`, which
  reads the bearer token from the named environment variable and sends the
  Authorization header without writing token values to result artifacts. Token
  provisioning for the public Hetzner `/v1` surface remains an operational
  prerequisite for live runs. The tmux helper can pass the same option through
  in dry-run matrices without reading the token value.
- Live Hetzner SSH/inventory, GPU-driver recovery, Qwen2.5 baseline
  restoration, Gemma-4-capable vLLM role support, and a local-only full-card
  idle-load preflight for pinned `google/gemma-4-E2B-it` are now recorded as
  landed in the sibling deployment repo's backlog. The proven service-shaped
  Hetzner path is vLLM `0.20.1+cu129` with Torch `2.11.0+cu129`, BF16 Hugging
  Face weights, 8K context, one sequence, `--gpu-memory-utilization 0.85`,
  text-only multimodal limits, and `--enforce-eager`. That is not strict
  same-GGUF parity with the Apple `llama-server` runs.
- Hetzner strict same-GGUF `llama-server`/llama.cpp support, checksum parity,
  comparable runtime options, and memory fit remain separate unverified
  blockers. Use the vLLM route only as runtime-and-format evidence unless a
  later strict-GGUF preflight lands.
- Token provisioning for authenticated public Hetzner `/v1` benchmark access
  remains the next operational prerequisite before remote `benchpack` runs.
  The sibling LNB-005 contract has landed: use public TLS `/v1` through the
  Django Bearer-auth proxy with token env var
  `BENCHPACK_HETZNER_OPENAI_TOKEN`. What remains is operator token
  provisioning plus an authenticated live smoke before benchmark scheduling.
  On Hetzner, follow the sibling readiness notes for the isolated Hugging Face
  cache layout because the complete pinned E2B weights are in the alternate
  `models--google--gemma-4-E2B-it/snapshots/...` directory.

Sources:

- <https://blog.google/innovation-and-ai/technology/developers-tools/gemma-4/>
- <https://blog.google/innovation-and-ai/technology/developers-tools/multi-token-prediction-gemma-4/>
- <https://deepmind.google/models/gemma/gemma-4/>
- <https://huggingface.co/google/gemma-4-E2B-it>
- <https://huggingface.co/google/gemma-4-E4B-it>
- <https://huggingface.co/docs/transformers/model_doc/gemma4>
- <https://docs.vllm.ai/en/latest/models/supported_models/>
- <https://docs.vllm.ai/projects/recipes/en/latest/Google/Gemma4.html>
- <https://huggingface.co/bartowski/google_gemma-4-E2B-it-GGUF>
- <https://huggingface.co/bartowski/google_gemma-4-E4B-it-GGUF>
- <https://huggingface.co/ggml-org/gemma-4-E2B-it-GGUF>
- <https://huggingface.co/ggml-org/gemma-4-E4B-it-GGUF>
- <https://huggingface.co/unsloth/gemma-4-E2B-it-GGUF>
- <https://huggingface.co/unsloth/gemma-4-E4B-it-GGUF>
- <https://ollama.com/library/gemma4/tags>
- <https://huggingface.co/mlx-community/gemma-4-e2b-it-4bit>
- <https://huggingface.co/mlx-community/gemma-4-e4b-it-4bit>

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
default answer to every new “current preferred model” question.

## Next Catalog Work

- Capture post-download checksums, runtime versions, load commands, local
  tokenizer/chat-template behavior, and memory fit for any selected Gemma 4
  Hetzner mode before live benchmark matrices. The sibling repo has current
  vLLM E2B readiness evidence; strict same-GGUF llama.cpp evidence is still
  absent.
- Use `docs/gemma4-tri-host-runbook.md` as the operational checklist for the
  first tri-host campaign and keep its placeholder metadata examples aligned
  with verified artifacts when they are known.
- Revisit the catalog when an authenticated public Hetzner `/v1` benchmark
  smoke succeeds or when a strict same-GGUF Hetzner `llama-server` preflight
  lands.
