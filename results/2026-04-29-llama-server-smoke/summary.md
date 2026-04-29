# smoke-chat (0.1.0)

Tiny endpoint smoke test

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
| capital | openai-chat | qwen2.5-0.5b-instruct-q4_k_m | yes | 0.259 | 30.87 | contains: pass |
