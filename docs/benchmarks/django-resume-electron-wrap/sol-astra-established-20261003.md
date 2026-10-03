# Sol LOW / Astra MEDIUM — established full-access protocol, 2026-10-03

Two fresh sequential one-shot samples passed the original runtime/Node-test
rubric. These are new observations under the recovered original workflow,
not repaired or reclassified earlier samples. No supervising application repair,
score retry, extra generation, publication or deployment occurred.

| Model / effort | Original rubric | Node tests | Agent time | Full runner wall | Native input / cached input / output |
|---|---|---:|---:|---:|---:|
| GPT-6.1 Sol LOW | PASS | 54/54 | 473.3 s | 482.252439 s | 1,658,709 / 1,580,416 / 11,583 |
| GPT-6 Astra MEDIUM | PASS | 56/56 | 911.7 s | 919.065475 s | 2,144,901 / 2,043,264 / 20,005 |

Both wrappers and packaged smokes exited 0. Independent verifier logs show
`/health/` 200, `/` 302 and `/resume/` 200. The original rubric requires serving
and passing generated Node tests; it does not prove every prompt requirement,
complete security correctness or cross-platform packaging.

## Curated evidence

- Sol: [summary](../../../results/agent-wrap-oneshot/gpt61sol-established-low-20261003/summary.txt),
  [Node tests](../../../results/agent-wrap-oneshot/gpt61sol-established-low-20261003/nodetests.log),
  [packaged smoke](../../../results/agent-wrap-oneshot/gpt61sol-established-low-20261003/verify-smoke.log),
  [provenance](../../../results/agent-wrap-oneshot/gpt61sol-established-low-20261003/provenance.json).
- Astra: [summary](../../../results/agent-wrap-oneshot/gpt6astra-established-medium-20261003/summary.txt),
  [Node tests](../../../results/agent-wrap-oneshot/gpt6astra-established-medium-20261003/nodetests.log),
  [packaged smoke](../../../results/agent-wrap-oneshot/gpt6astra-established-medium-20261003/verify-smoke.log),
  [provenance](../../../results/agent-wrap-oneshot/gpt6astra-established-medium-20261003/provenance.json).

The small intentionally committed artifact sets also include npm verifier logs,
diff statistics and changed filenames. Only local absolute paths were replaced;
sidecars record hashes of originals and curated copies. No agent logs, raw
native conversations, session IDs, credentials, generated source trees or CV
contents are committed. Sidecars preserve native record hashes and extracted
model/effort/provider/completion/usage evidence.

## Exact inputs and effective profile

- Django source: `3dc54f85646ace421ddaa164119229f5fc25cef0`.
- Starter: `a0c90a79e6910b2c1547f7eb7398dd6c007cf45c`.
- Prompt: `skills/wrap-existing-django-in-electron/prompt.md`, SHA-256
  `e427efe0072840514238220dbca7d5bebfc41d63e4fc6baca8debb74da7c0512`.
- Harness main at execution: `4680298f4813b1e65fe0d4fd0d078a2b8e9f2f3d`;
  unchanged runner source commit `3ee325fe7ad3e2cf5a2c9d891f1ed0343dbdc7c0`,
  blob `0f38f8a674b210ee9d40bfe0b9f55088b6105b7f`.
- CLI 0.160.0, node v26.10.0, npm 11.19.1, uv 0.12.22, just 1.58.0,
  trusted existing Electron 40.8.5. ChatGPT subscription login was verified;
  both native sessions identify OpenAI, the exact requested model/effort and
  one completed turn. No paid API route or provider fallback was observed.

The unchanged `scripts/run-agent-wrap-oneshot --runner codex-yolo` used explicit
model/effort, fixed source/starter, unique target/results paths and timeout 7200.
It invoked `codex exec --dangerously-bypass-approvals-and-sandbox`. Targets were
outside the harness/results and sibling to a read-only `desktop-django-starter`,
with no enclosing Python project. Verification used ordinary npm install,
Node tests, packaged smoke and target Git diff capture. No custom sandbox-exec,
source-snapshot cap or arbitrary cache exclusions were introduced.

Both cells had separate scratch HOME/Cocoa home/TMP/XDG/uv/npm cache roots,
credential/API-key environment scrubbing and existing subscription CODEX_HOME.
Those environment additions differ from historical inherited-home runs and
provide synthetic-data separation, **not filesystem confinement**. Existing
CLI settings remained inherited. Trusted Electron was selected with
`ELECTRON_OVERRIDE_DIST_PATH` and `ELECTRON_SKIP_BINARY_DOWNLOAD=1`;
Chromium sandboxing remained enabled. Own process-group/descendant sampling
and a final target-cwd check found no live owned processes; no cleanup signals
or unrelated kills were needed. This is bounded observation, not adversarial
containment proof.

## Timing, accounting and comparison limits

Existing normalized `timing.wall_seconds` retains the original runner's **agent
subprocess duration**, rounded to 0.1 s. Both display and notes label it as agent
time. Full monotonic runner time includes clone/diff/verification; post-exit
cleanup observation is excluded. The runner does not separately time its
verifier. Full-minus-agent residuals (approximately 8.952/7.365 s) are not pure
verifier measurements.

Native cumulative totals are 1,670,292/2,164,906. Cached input is a **subset of
input**; reasoning output (1,038/3,574) is a subset of output. Cache-write input
is zero. Do not add cached tokens again or use the shorter CLI `tokens used`
display as the native cumulative total. No billed-price estimate is recorded.

Sol took less time and used fewer cumulative tokens in these observations.
One sample each, different reasoning effort and uncontrolled shared dependency,
service-cache, power/thermal and background conditions do not establish a
model ranking or general economics claim. This full-access profile is distinct
from confined, blocked and supplemental runs. Earlier invalid comparisons,
Astra's incomplete original host run and its separate supplemental verifier PASS
remain unchanged and are not imported as new model PASS/FAIL rows here.

## Registry handoff

Both rows are appended to the existing schema-version-1
[normalized source](../../../data/agent-wrap-oneshot-results.json).
`just registry-site` already supports importing it and rendering a local site;
no code/schema change is required. The registry export projects its supported
columns, so detailed native usage/full-wall/provenance stays in these committed
sidecars and this report, with concise row notes retained in the export.

Local import/render is validation only. Curating these rows does not authorize
merging main, publishing the private site or running staging deployment.
The owner may adopt the commit and regenerate the registry/site from the
committed source before separately authorizing publication.
