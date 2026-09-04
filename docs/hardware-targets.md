# Hardware Targets

## Apple Silicon

Primary local target:

- M-series MacBook Pro or Mac Studio
- unified memory
- MLX, Ollama, llama.cpp/Metal, and OpenAI-compatible local servers

Apple Silicon runs should capture:

- chip name
- hardware model identity, such as `hardware_model`,
  `hardware_model_identifier`, and `hardware_model_name` when macOS reports
  them
- total unified memory
- macOS version
- GPU model name
- runtime versions
- model format: MLX, GGUF, Ollama tag, or server-specific
- requested context size

The runner records Apple Silicon host metadata in `hardware.json` on a
best-effort basis. Current Darwin-specific optional fields include `chip`,
`hardware_model` from `sysctl hw.model`, and `hardware_model_name` /
`hardware_model_identifier` from `system_profiler SPHardwareDataType` when that
tool is available. Runtime versions, model checksums, quantization, context
size, server command, power mode, thermal state, and cache settings are not
autodiscovered; capture them explicitly with `benchpack run --run-metadata`
when a result should be interpretable later.

For stable registry browsing, optional run metadata may set `host.identity`
and `host.display`. When they are absent, registry schema version `4` derives a
browse-only host identity and readable label from captured chip, hardware model
name, and memory instead of exposing Bonjour hostnames or the `darwin`
kernel-family value as primary labels. Raw hostname, platform, and hardware
fields remain stored as provenance; `darwin` is displayed as `macOS` in
human-facing static snapshots.

## Hetzner Small GPU

Initial hosted Linux target:

- Hetzner GEX44-class dedicated GPU server
- NVIDIA RTX 4000 SFF Ada Generation
- 20 GB GDDR6 ECC VRAM
- 64 GB DDR4 system RAM
- Intel Core i5-13500

This target is useful because it represents a small, rented CUDA host with a hard
VRAM ceiling. It should force the benchmark to handle:

- CUDA runtime setup
- GGUF or Ollama models that fit in 20 GB VRAM
- possible CPU/RAM spillover
- Linux service orchestration
- remote result capture

Larger Hetzner GEX131-class machines can be added later, but they are not the
initial "small GPU" target.

Verified Qwen3.8 fit boundary (2026-09-02): the pinned 18.97 GB
`Qwen3.8-27B-Q4_K_M.gguf` loads all 64 layers on this card and completes the 4K
`runtime-sweep` at about 13.1 median decode tok/s. It leaves little headroom:
the long-context agent configuration peaked at 19,418 MiB used out of 20,021
MiB available to `llama-server`. A 262,144-token q8_0 KV cache adds 8,704 MiB
and therefore had to remain in system RAM; decode declined to about 2.1 tok/s
near 92K prompt tokens, and the one-shot Django/Electron wrap timed out at two
hours without editing. Treat this host as a proven short-context Q4 serving
target, not as a proven 256K agent target. The inference server was remote;
the benchmark harness and verifier ran on the M4 Studio over an SSH loopback
forward.

## Generic CUDA

The design should keep generic CUDA hosts in scope:

- consumer RTX cards
- rented GPU marketplace machines
- workstations with one GPU

No benchmark pack should hard-code provider-specific paths.

## Hardware Profiles

Every run should write a `hardware.json` file with:

- hostname
- OS and kernel
- CPU model and core count
- RAM
- GPU model(s)
- GPU VRAM
- platform-specific host model identifiers when available
- driver/runtime versions when available
- storage path for model cache when known

Profiles should be data, not assumptions. The pack decides what matters, but the
runner records what the host actually reports.
