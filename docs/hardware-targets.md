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
size, server command, power mode, thermal state, and cache settings remain run
note responsibilities until a later narrow runtime-metadata slice defines a
reliable collector.

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
