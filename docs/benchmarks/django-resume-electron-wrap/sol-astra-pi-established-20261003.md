# Sol LOW / Astra MEDIUM through Pi — 2026-10-03

One fresh original-protocol sample per model; both **PASS**, with no operator app repair or score retry. Pi0.99.2 selected provider **openai**, authenticated through its supported **OpenAI (ChatGPT subscription)** OAuth route. No OpenRouter, paid API-key, Anthropic or local-provider calls. This is separate from [the established Codex pair](sol-astra-established-20261003.md), not a retroactive replacement.

| Cell | Node tests / packaged smoke | Agent / full runner seconds | Inclusive input / cached subset / output |
|---|---|---|---|
| gpt61sol-pi-openai-sub-low-20261003 | 54 PASS / HTTP OK | 359.9 /369.246124 | 914,801 /868,992 /6,295 |
| gpt6astra-pi-openai-sub-medium-20261003 | 54 PASS / HTTP OK | 667.5 /674.916760 | 1,970,456 /1,899,776 /11,857 |

Both npm installs succeeded; original independent packaged smoke exit0 served health200 and root302→resume200. Native JSON final assistant messages confirm exact requested models/provider/API, nonzero generation/tools, final stopReason stop and no error. Wrapper exit0 alone is not evidence. Registry `wall_seconds` remains the original rounded agent duration, not full runner or verifier. Verifier was not separately timed.

Pi native `usage.input` means **uncached**:45,809/70,680. Add cacheRead868,992/1,899,776 and cacheWrite0 to obtain inclusive input above. Native totals921,096/1,982,313 equal inclusive input+output. Reasoning108/688 is an output subset. Pricing fields are excluded; tokens cannot be converted directly to subscription allowance or list-price billing.

## Fixed provenance and reproducible invocation

Original runner source commit3ee325fe7ad3e2cf5a2c9d891f1ed0343dbdc7c0, blob0f38f8a674b210ee9d40bfe0b9f55088b6105b7f, SHA25682f01df17656f5e22584e1e92cb170d065a7c15126aea97c4dd57f2c31aa5285. Source3dc54f85646ace421ddaa164119229f5fc25cef0; sibling desktop-django-starter a0c90a79e6910b2c1547f7eb7398dd6c007cf45c. Prompt skills/wrap-existing-django-in-electron/prompt.md SHA256e427efe0072840514238220dbca7d5bebfc41d63e4fc6baca8debb74da7c0512. All match the Codex pair; ordinary original Git diff/npm/Node/packaged verifier, no custom source-cap/cache-accounting admission.

Use a fresh root outside harness and enclosing Python projects, with a fixed clean starter sibling and distinct target/results/scratch for each cell. Original runner commands (replace fixture paths explicitly; never force over old evidence):

```sh
scripts/run-agent-wrap-oneshot --runner pi --provider openai \
 --model gpt-6.1-sol --thinking low --pi-mode json --pi-extension none \
 --label gpt61sol-pi-openai-sub-low-20261003 --source <fixed-synthetic-source> \
 --starter <fresh-root>/desktop-django-starter \
 --prompt <fresh-root>/desktop-django-starter/skills/wrap-existing-django-in-electron/prompt.md \
 --target <fresh-root>/django-resume-oneshot-gpt61sol-pi-openai-sub-low-20261003 \
 --results-root <fresh-root>/results --timeout 7200
scripts/run-agent-wrap-oneshot --runner pi --provider openai \
 --model gpt-6-astra --thinking medium --pi-mode json --pi-extension none \
 --label gpt6astra-pi-openai-sub-medium-20261003 --source <fixed-synthetic-source> \
 --starter <fresh-root>/desktop-django-starter \
 --prompt <fresh-root>/desktop-django-starter/skills/wrap-existing-django-in-electron/prompt.md \
 --target <fresh-root>/django-resume-oneshot-gpt6astra-pi-openai-sub-medium-20261003 \
 --results-root <fresh-root>/results --timeout 7200
```

The existing runner uses --no-session/-nc/-ns/-np; JSON output preserves local native traces. Explicit LOW/MEDIUM override the owner's unrelated screenshot HIGH. Effort is evidenced by exact observed argv and supported installed mapping; JSON does not independently expose server request effort. Isolated config copied only renewed openai subscription OAuth, mode0600; no global settings/extensions or other provider credentials. Per-cell scratch HOME/Cocoa/TMP/XDG/uv/npm caches, API-key/foreign-provider environment scrubbed. Credential copies removed after completion; raw trace is never committed. Reuse trusted Electron40.8.5 override/skip-download; Chromium sandbox enabled. Node26.10.0/npm11.19.1/uv0.12.22/just1.58.0.

Owned group/descendant PID+start-identity observation and final target-cwd scan found no survivors; no signals or unrelated kills. Sol74/Astra78 observed process identities. Generated main: contextIsolation true/nodeIntegration false, Sol enabled Electron40 default sandbox, Astra explicit sandboxtrue. No sandbox-disable commands observed. Sequential run/cleanup window released13:17:23.297087UTC; no extra samples.

## Failed authentication remains separate

Earlier label gpt61sol-pi-established-low-20261003 used stale **openai-codex** OAuth: refresh401 refresh_token_invalidated before inference, zero tokens/edits, agent0.4s/full0.964954s. Original wrapperexit0/strictFAIL is preserved in [summary](../../../results/agent-wrap-oneshot/gpt61sol-pi-established-low-20261003/summary.txt) and [aggregate provenance](../../../results/agent-wrap-oneshot/gpt61sol-pi-established-low-20261003/provenance.json). **Infrastructure-invalid, not a model-quality FAIL**, no normalized performance row. Astra never launched on that failed route. Owner renewed the distinct supported openai ChatGPT subscription route; fresh labels/trees preserve failed attempt, not a score-improving retry. OpenRouter screenshot was diagnosis evidence only, never benchmark provider authorization.

## Curated evidence and limits

Per-cell [Sol provenance](../../../results/agent-wrap-oneshot/gpt61sol-pi-openai-sub-low-20261003/provenance.json) / [Astra provenance](../../../results/agent-wrap-oneshot/gpt6astra-pi-openai-sub-medium-20261003/provenance.json) retain native trace hash, exact source/prompt/runner/model/effort/Pi provenance, usage and clean-log original/curated hashes. Only summary, npm/Node/packaged logs, diff statistics and changed filenames committed, with local absolute paths sanitized. No raw native conversations, session IDs, auth data, generated app/CV source or pricing. Detailed sidecars are source evidence, not additional static-site metric columns.

Earlier50 normalized rows remain unchanged; append exactly two Pi PASS rows (52 total). Old confined/invalid/incomplete/supplemental outcomes remain separate. Existing static exporter shows supported notes/columns; do not claim raw logs/sidecars are publicly served.

One sample per model and different efforts permit no general ranking. Versus Codex, fixed workload/inputs/rubric/full-access synthetic policy match, but system prompts/tool implementations/backend subscription serving route/cache histories differ. Pi catalog context272K does not prove context parity with Codex. No pure-model isolation/economics claim. Original rubric checks authored tests/runtime/endpoints, not exhaustive security/prompt/platform quality. No human generated-app repair; owner login was infrastructure preparation.

Prepared for owner adoption/import only; no main merge, push or Pi staging publication. Already-published Codex pair is unchanged. Regenerate supported registry import/static export after adoption; do not ship stale output.
