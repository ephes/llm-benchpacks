# desktop-django-wrap (0.1.5)

Prompt-only first Phase 3 workload for Django-in-Electron wrapping plans; not a repo-mutating wrap run

Host: `atlas.local` (darwin)
CPU: Apple M5 Max
RAM: 65536 MB
GPU: Apple M5 Max

| case | adapter | model | ok | wall_s | total_tps | scoring |
|------|---------|-------|----|--------|-----------|---------|
| wrap-plan-small | openai-chat | qwen2.5-0.5b-instruct-q4_k_m | yes | 1.228 | 312.83 | regex: fail |
| wrap-plan-context | openai-chat | qwen2.5-0.5b-instruct-q4_k_m | yes | 0.884 | 386.97 | regex: fail |
