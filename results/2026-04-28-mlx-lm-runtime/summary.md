# runtime-sweep (0.1.0)

Fixed-size prompt sweep for repeated local runtime measurements

Host: `atlas.local` (darwin)
CPU: Apple M5 Max
RAM: 65536 MB
GPU: Apple M5 Max
Runtime: `mlx_lm.server` via `uvx --from mlx-lm` (`mlx-lm==0.31.3`, `mlx==0.31.2`, `mlx-metal==0.31.2`)
Server command: `uvx --from mlx-lm mlx_lm.server --model mlx-community/Qwen2.5-0.5B-Instruct-4bit --host 127.0.0.1 --port 8080`
Endpoint: `http://localhost:8080/v1`

| case | adapter | model | ok | wall_s | total_tps | scoring |
|------|---------|-------|----|--------|-----------|---------|
| short#1 | openai-chat | mlx-community/Qwen2.5-0.5B-Instruct-4bit | yes | 0.257 | 299.11 | — |
| short#2 | openai-chat | mlx-community/Qwen2.5-0.5B-Instruct-4bit | yes | 0.231 | 333.23 | — |
| short#3 | openai-chat | mlx-community/Qwen2.5-0.5B-Instruct-4bit | yes | 0.324 | 237.52 | — |
| medium#1 | openai-chat | mlx-community/Qwen2.5-0.5B-Instruct-4bit | yes | 0.364 | 329.76 | — |
| medium#2 | openai-chat | mlx-community/Qwen2.5-0.5B-Instruct-4bit | yes | 0.346 | 347.09 | — |
| medium#3 | openai-chat | mlx-community/Qwen2.5-0.5B-Instruct-4bit | yes | 0.341 | 351.61 | — |
| long#1 | openai-chat | mlx-community/Qwen2.5-0.5B-Instruct-4bit | yes | 0.371 | 345.01 | — |
| long#2 | openai-chat | mlx-community/Qwen2.5-0.5B-Instruct-4bit | yes | 0.369 | 346.93 | — |
| long#3 | openai-chat | mlx-community/Qwen2.5-0.5B-Instruct-4bit | yes | 0.380 | 336.60 | — |
