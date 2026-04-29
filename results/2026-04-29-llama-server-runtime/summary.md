# runtime-sweep (0.1.0)

Fixed-size prompt sweep for repeated local runtime measurements

Host: `atlas.local` (darwin)
CPU: Apple M5 Max
RAM: 65536 MB
GPU: Apple M5 Max
Runtime: `llama-server` from Homebrew `llama.cpp` (`version: 8960 (19821178b)`)
Server command: `llama-server --model /Users/jochen/models/gguf/Qwen2.5-0.5B-Instruct-Q4_K_M.gguf --alias qwen2.5-0.5b-instruct-q4_k_m --host 127.0.0.1 --port 8081 --ctx-size 4096 --gpu-layers auto`
Endpoint: `http://127.0.0.1:8081/v1`
Model file: `/Users/jochen/models/gguf/Qwen2.5-0.5B-Instruct-Q4_K_M.gguf`
Model SHA256: `6eb923e7d26e9cea28811e1a8e852009b21242fb157b26149d3b188f3a8c8653`
Quantization: `Q4_K_M` (`llama-server` reported file type `Q4_K - Medium`)
Context: `4096`

| case | adapter | model | ok | wall_s | total_tps | scoring |
|------|---------|-------|----|--------|-----------|---------|
| short#1 | openai-chat | qwen2.5-0.5b-instruct-q4_k_m | yes | 0.289 | 395.07 | — |
| short#2 | openai-chat | qwen2.5-0.5b-instruct-q4_k_m | yes | 0.282 | 403.76 | — |
| short#3 | openai-chat | qwen2.5-0.5b-instruct-q4_k_m | yes | 0.281 | 405.91 | — |
| medium#1 | openai-chat | qwen2.5-0.5b-instruct-q4_k_m | yes | 0.289 | 411.27 | — |
| medium#2 | openai-chat | qwen2.5-0.5b-instruct-q4_k_m | yes | 0.296 | 402.01 | — |
| medium#3 | openai-chat | qwen2.5-0.5b-instruct-q4_k_m | yes | 0.302 | 393.53 | — |
| long#1 | openai-chat | qwen2.5-0.5b-instruct-q4_k_m | yes | 0.203 | 398.54 | — |
| long#2 | openai-chat | qwen2.5-0.5b-instruct-q4_k_m | yes | 0.201 | 402.01 | — |
| long#3 | openai-chat | qwen2.5-0.5b-instruct-q4_k_m | yes | 0.204 | 397.34 | — |
