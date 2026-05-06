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

Candidate order:

- Candidate, unverified Hugging Face ID `google/gemma-4-E2B-it`: primary small
  tri-host smoke/runtime target once the exact Hugging Face, GGUF/Ollama, MLX,
  and vLLM artifacts are confirmed.
- Candidate, unverified Hugging Face ID `google/gemma-4-E4B-it`: secondary
  target if it fits comfortably on the RTX 4000 SFF Ada 20 GB class host and
  has matching local runtime support.
- Gemma 4 26B MoE and 31B dense variants: larger investigation targets, not
  the first Hetzner GEX44-class benchmark until runtime support, quantization,
  and memory fit are proven.

Sources:

- <https://blog.google/innovation-and-ai/technology/developers-tools/gemma-4/>
- <https://blog.google/innovation-and-ai/technology/developers-tools/multi-token-prediction-gemma-4/>

Tri-host comparison modes:

- Strict parity: use the same GGUF artifact through `llama-server` on M4, M5,
  and the Linux CUDA host. This is the cleanest hardware/runtime comparison if
  the CUDA host has a suitable llama.cpp build and the selected quantization
  fits.
- Service-shaped comparison: use MLX or GGUF on Apple Silicon and Hugging Face
  weights through vLLM on Hetzner. This is useful operational evidence, but
  must be labeled as runtime-and-format rather than strict artifact parity.

Current blockers:

- Authenticated OpenAI-compatible endpoint calls now use
  `benchpack run --adapter openai-chat --openai-api-key-env <ENV_NAME>`, which
  reads the bearer token from the named environment variable and sends the
  Authorization header without writing token values to result artifacts. Token
  provisioning for the public Hetzner `/v1` surface remains an operational
  prerequisite for live runs.
- Live Hetzner SSH/inventory access is not confirmed, so exact RAM, GPU model,
  driver version, and runtime state still need read-only verification.
- The sibling deployment repo's deployed vLLM stack has not been re-validated
  against Gemma 4. Gemma 4 serving must be validated before changing the
  deployed model.

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

- Add a tested Gemma 4 artifact table after exact MLX/GGUF/Ollama/vLLM model
  IDs and revisions are verified.
- Add a tiny metadata example for a Gemma 4 tri-host run, including whether the
  run is strict parity or runtime-and-format.
- Revisit the catalog when Hetzner token provisioning, live host inventory, and
  Gemma 4 serving readiness are confirmed.
