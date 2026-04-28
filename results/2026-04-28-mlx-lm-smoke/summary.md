# smoke-chat (0.1.0)

Tiny endpoint smoke test

Host: `atlas.local` (darwin)
CPU: Apple M5 Max
RAM: 65536 MB
GPU: Apple M5 Max
Runtime: `mlx_lm.server` via `uvx --from mlx-lm` (`mlx-lm==0.31.3`, `mlx==0.31.2`, `mlx-metal==0.31.2`)
Server command: `uvx --from mlx-lm mlx_lm.server --model mlx-community/Qwen2.5-0.5B-Instruct-4bit --host 127.0.0.1 --port 8080`
Endpoint: `http://localhost:8080/v1`

| case | adapter | model | ok | wall_s | total_tps | scoring |
|------|---------|-------|----|--------|-----------|---------|
| capital | openai-chat | mlx-community/Qwen2.5-0.5B-Instruct-4bit | yes | 0.685 | 11.68 | contains: pass |
