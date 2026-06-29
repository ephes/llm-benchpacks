# Legacy DS4 Goal Prompt

Wrap `django-resume` in Electron using Pi backed by local DS4 / DeepSeek V4 Flash, starting from the prepared clean lab workspace at `~/workspaces/ds4-pi-django-resume`.

Done when:
- The run uses `~/workspaces/ds4-pi-django-resume/django-resume` as the target and `~/workspaces/ds4-pi-django-resume/desktop-django-starter` as the starter. Do not use the older dirty `~/workspaces/tmp/django-resume` workspace.
- Pi uses the local DS4 provider/model: `DS4_MODEL_QUANT=q2-imatrix DS4_GGUF_DIR=$HOME/src/ds4/gguf pi --model ds4/deepseek-v4-flash --thinking high ...`. First verify `pi --offline --list-models ds4` shows `ds4/deepseek-v4-flash`; do not switch to OpenAI, Ollama, MLX, or another model unless DS4 is genuinely blocked and the blocker is reported.
- The target starts clean: `git status --short` in `django-resume` is empty. If not, stop and report the dirty paths unless they are known artifacts from this run.
- Stage 1 deterministic scaffold has been run exactly once from the clean target with `../desktop-django-starter/skills/wrap-existing-django-in-electron-staged/scripts/scaffold-target.sh "$PWD"`.
- Stage 2 is run with the staged Electron prompt and keeps writes to `electron/**`; if its verification bundle already passes, it stops with a verification-only result.
- Stage 3 is run with the staged Django prompt and keeps writes to Django-side integration files except for unavoidable tiny Electron compatibility fixes; if its verification bundle already passes, it stops with a verification-only result.
- Stage 4 is used only if a concrete command fails, and receives exact failing output rather than a broad re-review request.
- Final target validation passes from `~/workspaces/ds4-pi-django-resume/django-resume`: `just check`, `just desktop-install`, `just desktop-stage`, and `just desktop-smoke`.
- Packaged smoke reaches the wrapped `/resume/` app without landing on a login page, and detail/CV pages expose a visible route back to the resume list.
- The final status is recorded with model/runtime/setup notes in `llm-benchpacks/docs/run-log.md`; if the staged run completes, also add a concise row to `desktop-django-starter/skills/wrap-existing-django-in-electron-staged/run-log.md`.

Constraints:
- Preserve user work. Do not reset or clean any dirty workspace other than the explicit lab workspace after confirming it belongs to this benchmark run.
- Do not mark the goal complete after setup, scaffold, or docs only. Completion requires the DS4/Pi agent run and the final validation commands.
- Keep generated artifacts such as `.venv`, `.stage`, `node_modules`, logs, and raw benchmark outputs out of committed changes unless explicitly curated.
