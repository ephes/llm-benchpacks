# Qwen3.8-27B One-Shot Wrap Campaign - 2026-08-31

This campaign is the first hard one-shot `django-resume` Electron wrap run for
a local open-weight Qwen3.8 artifact. It has four cells, all through
`scripts/run-agent-wrap-oneshot` with the `pi` runner against a local
`llama-server`:

| Cell | Label | Reasoning | Outcome |
| --- | --- | --- | --- |
| A | `qwen38-pi-llamacpp-256k-off` | thinking off | FAIL, timeout |
| B | `qwen38-pi-llamacpp-256k-high` | `xhigh` (default, unset) | FAIL, timeout |
| C | `qwen38-pi-llamacpp-256k-off-prewarmed` | thinking off | FAIL, timeout |
| D | `qwen38-pi-llamacpp-256k-medium` | `medium` (explicit) | **PASS** |

**Run D is the first PASS by a local open-weight model on this benchmark.**
Every prior pass in the curated table is a hosted frontier model. It exited
cleanly in 92.8 minutes rather than hitting the cap, passed 53/53 Node tests,
and served the packaged app with `app_served=1`.

Two findings carry the campaign.

- **`reasoning_effort` is the decisive variable.** Runs C and D are identical
  in every respect except the reasoning level, and it flipped the outcome. The
  model's own uncontrolled default, `xhigh`, was actively harmful; `medium`,
  the only level that injects no reasoning instruction, passed. See
  [Reasoning Effort Is The Decisive Variable](#reasoning-effort-is-the-decisive-variable).
- **Every failure is one pathology.** In all four defects across Runs A, B, and
  C the model wrote two components that disagree about an interface, on a code
  path it never executed. See
  [One Pathology, Four Defects](#one-pathology-four-defects).

A post-hoc counterfactual on Run B, in
[Counterfactual: Distance To Pass](#counterfactual-distance-to-pass), showed
that even the xhigh cell was a single two-line defect away from serving. The
recorded outcome for Runs A, B, and C remains FAIL.

The PASS is **one unreplicated run**. A confirmation run of the same medium
configuration, `qwen38-pi-llamacpp-256k-medium-rerun1`, was in progress when
this report was written and its result is not yet known. Runs A and B also
predate the Electron environment fix, so they are not strictly comparable to
Runs C and D.

**Addendum 2026-09-01: the confirmation cell FAILED — the PASS did not
replicate.** `qwen38-pi-llamacpp-256k-medium-rerun1` completed 2026-08-31
21:07: `pi_exit=0` in 3567.3s (59.5 min, a clean self-termination 33 minutes
faster than Run D), 53/53 Node tests, 33 files changed (+7537/-136), but the
packaged smoke exited 1 with all HTTP counters 0. `stage-backend` staged the
backend, and Django died booting packaged mode on `ModuleNotFoundError: No
module named 'example.packaged_settings'` — the launcher names a settings
module the staging step never ships, the same one-pathology signature as
every other failure in this campaign. The transcript shows two
`just desktop-dev-smoke` (dev-mode) runs and no packaged-smoke execution, so
the defect survived to the verifier. The medium lane is therefore **1-for-2**:
`reasoning_effort=medium` remains decisive for avoiding the xhigh/off failure
modes, but is not sufficient for a reliable pass. See the rerun1 row in
`docs/run-log.md`.

## Setup

Host and runtime:

- Host: studio (Apple M4 Max, 128 GB, Mac Studio `Mac16,9`, macOS 26.6.2).
- llama.cpp build 10621 (`c1d0e7a00`), `llama-server` on `127.0.0.1:18084`.
- Model: `ggml-org/Qwen3.8-27B-GGUF`, file `Qwen3.8-27B-Q4_K_M.gguf`,
  18,973,870,432 bytes, stored at `/Users/jochen/models/gguf/qwen3.8-27b/`.
  Pinned after the runs, on 2026-08-31: repo revision
  `0669b98607d47046c7c2b3f801011d54a08cfccf`, SHA-256
  `31629f53165ab6a7dad8c9847dcfd1fdf55829dac1e6e748f4a68581b0033d34`,
  matching the upstream Hugging Face LFS `oid`. The pin was taken after both
  cells ran, so these rows are runtime-and-format evidence, not
  artifact-parity evidence.
  Qwen3.8-27B is a dense Apache 2.0 model released around 2026-08-13.

Server flags, identical in both cells except for the reasoning switch:

```sh
llama-server \
  --ctx-size 262144 --batch-size 2048 --ubatch-size 512 \
  --cache-type-k q8_0 --cache-type-v q8_0 \
  --gpu-layers 999 --parallel 1 --cache-prompt \
  --no-webui --jinja --timeout 3600
```

Run A added `--chat-template-kwargs '{"enable_thinking":false}'`. Run B used
`--reasoning-budget -1`.

Gotcha worth recording: `--reasoning-budget 0` did **not** disable thinking on
this chat template. Only the `--chat-template-kwargs '{"enable_thinking":false}'`
route produced a genuine thinking-off lane. Verify the thinking state on the
template rather than assuming the reasoning-budget flag applies.

Second gotcha, found on 2026-08-31 after both cells had run, and material to
how Run B should be read: the reasoning level is a `reasoning_effort` template
variable, not a llama.cpp flag. `Qwen/Qwen3.8-27B/chat_template.jinja` accepts
only `xhigh`, `medium`, and `low` — there is no `high` — and raises on any
other value. With thinking enabled and `reasoning_effort` unset it resolves to
`xhigh`, which injects "Reasoning effort is set to xhigh. Please think
carefully through the task, validate key assumptions, consider plausible
alternatives, and prioritize correctness, consistency, and clarity in the
final answer." `medium` injects no reasoning instruction at all.

Run B passed pi `--thinking high` and the server `--reasoning-budget -1` but
never set `reasoning_effort`, so **Run B is an `xhigh` cell**, run at the
model's maximum deliberation setting with an explicit deliberate-more
instruction in its system prompt — not the intermediate level its label
suggests. Read its 34.5-minute write-free reconnaissance phase and its two
consecutive ~8-minute thinking-only turns in that light. Later Qwen3.8 cells
should set `reasoning_effort` explicitly and label the cell by the resolved
value.

Harness:

- Runner `scripts/run-agent-wrap-oneshot`, `--runner pi`, pi 0.84.4.
- Provider extension
  `/Users/jochen/projects/desktop-django-starter/.bench-qwen38/pi-llamacpp38-256k-provider.ts`
  registering provider id `llamacpp38`, model id `qwen3.8-27b`,
  `contextWindow=262144`, `maxTokens=16384`.
- Source checkout `/Users/jochen/projects/django-resume-bench-main` at
  `3dc54f8` (`Release 0.3.0`), the same checkout as the current GPT-5.5,
  Opus 4.8, and GLM-5.2 rows.
- Timeout 7200s in both cells.

## Runtime Compatibility

Qwen3.8 needed no runtime upgrade. Its Hugging Face config declares
`model_type: "qwen3_5"` and `Qwen3_5ForConditionalGeneration`, with 64 layers,
hidden size 5120, 24 attention heads, 4 KV heads, and
`max_position_embeddings` 262144. That is the same architecture string and the
same geometry as Qwen3.6-27B, so existing llama.cpp and `mlx-lm` builds load
the artifact directly.

The internals are not the same, which is a confound for any Qwen3.6 comparison:
48 of the 64 layers are GatedDeltaNet linear attention with no KV cache, and
only 16 are full attention. KV cost at 262k context is therefore far below a
conventional 27B, so the two generations are not serving the same memory
profile even at identical flags and quantization.

## Run A - `qwen38-pi-llamacpp-256k-off`

Thinking off. `pi_exit=124` at 7200.0s (timeout).

| Check | Result |
| --- | --- |
| `electron/package.json` exists | yes |
| `npm install` | ok |
| Node tests | pass, 53/53 |
| `smoke:packaged` | exit 2, all HTTP counters 0, `app_served=0` |
| Diff | 38 files changed, +7749 / -3 |
| Outcome | FAIL |

Smoke failed inside `npm run stage-backend`:

```text
error: /Users/jochen/projects/django-resume-oneshot-qwen38-pi-llamacpp-256k-off/.stage/backend/src
does not appear to be a Python project, as neither `pyproject.toml` nor
`setup.py` are present in the directory
```

A separate Electron dialog reported
`ModuleNotFoundError: No module named 'example.desktop_dev_settings'`.

Server-side: peak context 209,440 tokens, 234 slot launches.

No transcript was captured for this cell. `--pi-mode` was not set, and pi's
buffered output flushes nothing on `SIGTERM`, so the timeout kill left
`pi.log` at 33 bytes. This is a recorded methodology error, not a property of
the model; see D-039.

## Run B - `qwen38-pi-llamacpp-256k-high`

Thinking high, `--pi-mode json`. `pi_exit=124` at 7200.0s (timeout).

| Check | Result |
| --- | --- |
| `electron/package.json` exists | yes |
| `npm install` | ok |
| Node tests | pass, 53/53 |
| `smoke:packaged` | exit 1, all HTTP counters 0, `app_served=0` |
| Diff | 37 files changed, +7708 / -136 |
| Outcome | FAIL |

Smoke failed with a `TypeError` in the model's own generated
`electron/scripts/stage-backend.cjs`:

```text
TypeError: Cannot read properties of undefined (reading 'endsWith')
    at Object.isStalePythonArtifact [as filter] (.../electron/scripts/stage-backend.cjs:29:50)
    at cpSyncFn (node:internal/fs/cp/cp-sync:49:29)
    at Object.cpSync (node:fs:3823:3)
    at copyRequiredFiles (.../electron/scripts/stage-backend.cjs:47:6)
```

The cause is a single wrong API assumption. The model invented a helper
`isStalePythonArtifact(_sourcePath, entry)` and wrote it as if `fs.cpSync`'s
`filter` callback receives a `Dirent`. Node passes `(src, dest)` strings, so
`entry.name` is `undefined`. `isStalePythonArtifact` does not exist anywhere in
the starter or the reference shell; the model authored it at tool call 64,
turn 42, `t=3121s`.

Server-side: peak context 148,591 tokens, 100 slot launches. Transcript:
19.8 MB JSONL, 64,425 lines.

## Run B Transcript Forensics

The Run B transcript is the substantive artifact of this campaign, so it is
summarized here in detail.

Shape: 125 tool calls across 99 assistant turns. Tool mix was bash 93,
write 13, read 11, edit 8, for 21 write-or-edit calls. Most reconnaissance ran
through bash, so the read count understates how much file inspection happened.

Phase structure:

| Phase | Turns | Calls | Wall clock | Writes/edits |
| --- | --- | --- | --- | --- |
| Recon | 1-28 | 1-46 | 0-2071s (34.5 min) | 0 |
| Build | 29-53 | 47-77 | 2071-3505s (24.0 min) | all 21 |
| Blocked side-quest | 54-99 | 78-125 | 3505-7200s (61.5 min) | 0 |

The first write landed at `t=2071s`, 28.8% of the budget. Two thinking-only
turns preceded it: turn 27 (28,236 chars, 482s) and turn 28 (29,202 chars,
494s), so 16 straight minutes of deliberation before the first file appeared.

Nothing was written after `t=3505s`, with 51% of the budget still unspent. The
7200s cap was therefore not the binding constraint on this run. Adding time
would not have changed the outcome.

The final 48 calls were a single blocked side-quest: getting the Electron
binary into `node_modules/electron/dist`. Its root cause was self-inflicted. At
call 88, `@electron/get` printed the true cache path containing the 64-hex hash

```text
2fab1e37ba37d5443819b4991a9a9da5d4e5ccffe61916abec89be380121b50f
```

The model re-typed that hash by hand and dropped the `d4`, producing a 62-char
string. It then used the wrong hash in 17 subsequent commands and the correct
hash in zero. Every `ENOENT` it chased was hunting a file that had existed all
along. Alongside that, `ls node_modules/electron/dist` returned the identical
three lines (`LICENSE`, `LICENSES.chromium.html`, `version`) eleven times
across calls 81 through 124 without the model changing approach; `install.js`
was re-run 10 times and hand-rolled extraction attempted 14 times.

Underneath the side-quest there is a real host defect. At call 95 a traced
`install.js` reported extracting the correct-hash zip and exited `rc=0`, yet
`dist/` still held only the same three files. That symptom has since been
reproduced on this host with no model involved; see
[The Host Electron Install Defect](#the-host-electron-install-defect). The
model did not imagine its blocker. What it added on top was the mistyped hash
and the progressive corruption of its own `node_modules/electron` state, which
turned a workaround-able environment problem into an unwinnable hour. Run A is
the control: the same model, same host, same day, ended with a healthy 275 MB
`dist/` containing `Electron.app` and a packaged app that actually launched.

The run ended by deadlocking itself. The model wrote a stall watchdog using a
bare `setInterval(..., 5000)` with no `.unref()`, which kept Node's event loop
alive indefinitely. Its own anti-hang code held the process for the final
1420s, about 20% of the budget, until the harness killed it.
`tool_execution_start #125` has no matching end. There was no final
verification, no summary, and no `git status`.

The critical finding: the model **never executed its own acceptance criterion,
not once**. Of its 93 bash commands, none contains `smoke` or
`--runtime=packaged`, and the only two that mention `stage-backend` at all are
a `cp` copying the starter's script into `electron/scripts/` and a Python
heredoc rewriting `electron-builder-config.test.cjs` whose replacement text
happens to include the string. Neither runs anything. It never ran `npm test`
or `node --test` either; the 53/53 result came from the benchmark harness
afterwards. `npm run stage-backend` requires no Electron binary at all - it is
pure Node `fs` work - so running it once during those 61 blocked minutes would
have surfaced the `TypeError` in under a second.

What the model got right is not trivial:

- correct `repoRoot` depth fix for `electron/scripts/`;
- `settingsModule` remapped to `example.packaged_settings`;
- flat settings files
  `example/example/{base_settings,desktop_dev_settings,packaged_settings}.py`;
- a correct `smoke:packaged` script authored in `electron/package.json`.

Context pressure was not a factor. There was no compaction, roughly 153k tokens
against the 262k window. Six tool outputs were truncated at the 51,200-byte
cap, which is ordinary bash clipping.

## The Host Electron Install Defect

The Electron binary never lands in `node_modules/electron/dist` on this host by
the normal path. Three findings, all reproduced without any model in the loop:

1. `npm --prefix electron install` does not run Electron's postinstall. npm
   11.19.0 gates install scripts and warns:

   ```text
   npm warn install-scripts 2 packages have install scripts not yet covered by
   allowScripts: electron@40.8.5 (postinstall: node install.js)
   ```

   npm still exits 0, which is why the verifier records `npm_install_ok=1`
   while `dist/` is empty.
2. Running `node install.js` by hand exits silently with no error and produces
   only `LICENSE`, `LICENSES.chromium.html`, and `version` - 15 MB, no
   `Electron.app`. This is exactly the symptom the model reported at Run B call
   95.
3. The cached zip is intact. `unzip -t` on
   `~/Library/Caches/electron/2fab1e37.../electron-v40.8.5-darwin-arm64.zip`
   (114,274,304 bytes) is clean, and a plain `unzip` produces the correct
   275 MB `dist/` including `Electron.app`.

So the defect is inside Electron's own `install.js` / extract-zip path on this
host (electron 40.8.5, node v26.8.1), not in the cache and not in the model.

Pinned exactly on 2026-08-31 and reproduced in a bare `npm i electron@40.8.5`
scratch project with no model and no benchmark involved:

- `npm install-scripts approve electron` writes `allowScripts` into
  `package.json` and still yields nothing.
- `node install.js` run directly, and `npm rebuild electron
  --foreground-scripts`, both print nothing, exit 0, and produce no
  `Electron.app` and no `path.txt`. The `@electron/get` download promise never
  settles, so Node's event loop empties and the process exits clean.
- The three files in `dist/` ship inside the npm tarball. They are not a
  partial extraction, which is why re-running the installer never changed the
  listing.

### The Fix

Implemented on 2026-08-31 as environment plumbing only; no model code and no
verifier logic changed. A canonical dist was built once at
`/Users/jochen/.cache/benchpack-electron/40.8.5/` by unzipping the cached zip,
plus a symlink inside it:

```text
electron -> Electron.app/Contents/MacOS/Electron
```

The symlink is load-bearing. `electron/index.js` resolves
`path.join(ELECTRON_OVERRIDE_DIST_PATH, executablePath || 'electron')`, and
`executablePath` comes from `path.txt`, which does not exist when the download
is skipped, so the fallback branch needs a file literally named `electron` in
the dist root. Runs then export:

```sh
ELECTRON_OVERRIDE_DIST_PATH=/Users/jochen/.cache/benchpack-electron/40.8.5
ELECTRON_SKIP_BINARY_DOWNLOAD=1
```

Validated by deleting `dist/` and `path.txt` outright and still reaching
`smoke_exit=0 / health200=1 / root302=1 / resume200=1`. `install.js` now exits
in 0.04s instead of hanging. This is the D-040 precondition, implemented.

Runs A and B predate the fix; Runs C and D ran with it. That is a real
difference in operating conditions, so A/B and C/D are not strictly comparable
cells.

The two cells diverged on it. Run A's clone ended with a healthy 275 MB `dist/`
and a packaged app that launched far enough to show an Electron dialog with a
Django `ModuleNotFoundError`, so that model worked around the defect. Run B's
clone ended with an empty `dist/` plus a model-created `.electron-cache/`
directory from its hand-rolled extraction attempts.

Benchmark-validity consequence: until this host defect is fixed, this benchmark
is partly measuring "can the agent work around a broken Electron install"
rather than "can the agent author a correct Electron wrapper". That is a
scoring hazard for every future cell on this host, not a Qwen3.8 property.
D-040 records the resulting preflight requirement.

## Counterfactual: Distance To Pass

This is a post-hoc diagnostic, not a benchmark result. The official outcome for
both cells stays FAIL.

Run B's clone was copied to
`/Users/jochen/projects/django-resume-oneshot-qwen38-counterfactual` and two
changes were applied:

- **Model code, two lines.** The model's invented
  `isStalePythonArtifact(_sourcePath, entry)` was rewritten to
  `isStalePythonArtifact(sourcePath)` using `path.basename(sourcePath)` instead
  of a `Dirent` `.name`. Nothing else in the model's output was touched.
- **Host plumbing, no model code.** The host Electron install was repaired by
  unzipping the cached zip manually and writing
  `node_modules/electron/path.txt`, working around the defect above.

With only that, `npm run smoke:packaged` ran end to end:

- `stage-backend` fully succeeded: built the `django_resume-0.3.0` wheel,
  installed 5 packages, ran migrations, `collectstatic` copied 144 static
  files, and staged the bundle.
- The packaged Electron app launched and served. `smoke_exit=0`,
  `health200=1`, `root200=0`, `root302=1`, `resume200=1`, and zero error or
  traceback lines.
- Django 6.1 came up under settings `example.packaged_settings`, `/resume/`
  returned 19,898 bytes, and packaged static files (CSS, fonts, PNGs) served
  200.

The verifier's own gate is `smoke_exit == 0 and health200 >= 1 and (root200 >= 1
or (root302 >= 1 and resume200 >= 1))`, at
`scripts/run-agent-wrap-oneshot:272-283`, with the pass requiring
`app_served == 1` and `node_tests == "pass"` at line 288. The counterfactual
run satisfies `app_served=1`, and the recorded Run B `node_tests` was already
53/53. **Qwen3.8-27B's Run B output therefore satisfies this benchmark's pass
criteria once one hallucinated function signature is corrected.**

Two things follow.

- The distance to pass for this artifact is a single defect, not a class of
  missing capability. Everything else the wrap needs - settings split, wheel
  build, migrations, staticfiles, packaged-runtime paths, the `smoke:packaged`
  script itself - was already correct in the model's output.
- The defect is an execution slip, not a knowledge gap. Asked directly about
  `fs.cpSync`'s `filter` callback, the model answers correctly, that it
  receives two string arguments, source and destination. It knew the API and
  still wrote against a `Dirent` at tool call 64, turn 42, under long-horizon
  load - and then never ran the one command that would have caught it.

## Run C - `qwen38-pi-llamacpp-256k-off-prewarmed`

Thinking off, `--pi-mode json`, first cell with the Electron fix in place.
`pi_exit=124` at 7200.0s (timeout).

| Check | Result |
| --- | --- |
| `electron/package.json` exists | yes |
| `npm install` | ok |
| Node tests | pass, 53/53 |
| `smoke:packaged` | exit 124 (200s cap), all HTTP counters 0, `app_served=0` |
| Diff | 46 files changed, +7608 / -138 |
| Outcome | FAIL |

Real progress against A and B: **`stage-backend` succeeded for the first time
in this campaign.** It built `django_resume-0.3.0-py3-none-any.whl`, installed
5 packages (django 6.1, asgiref, nh3, sqlparse, django-resume), copied 143
static files, and printed `Staged backend bundle at ...`. That is the exact
step that killed both A and B.

It then died two different ways, on two independent model-authored defects.

**C(a), the dev-smoke deadlock.** Unlike Run B, this cell did try to verify its
own work - 10 of its 108 bash commands invoke a smoke - and its attempt
deadlocked it. Its invented justfile target reads:

```make
desktop-dev-smoke:
    DESKTOP_DJANGO_SMOKE_TEST=1 node ./electron/scripts/launch-electron.cjs
```

It passes the smoke flag as an **environment variable**, while its own
`launch-electron.cjs` parses `if (argument === "--smoke-test")` from **argv**
and sets that env var itself. So the target launches a normal windowed app that
never exits. The starter has no `desktop-dev-smoke` target; the model invented
it. The live process tree was captured mid-hang - `python3` runner -> `pi` ->
`bash` -> `just` -> `node launch-electron.cjs` -> `electron` - with the Electron
process idle for 27+ minutes and `pi.log` completely stalled. GPU utilisation
sat at 0 for about 30 minutes, which is how it was noticed.

**C(b), the packaged smoke has no failure path.** Independently, the verifier's
own packaged smoke also hung, `smoke_exit=124` at the 200s cap. Here the argv
*is* wired correctly:

```json
"smoke:packaged": "npm run stage-backend && node ./scripts/launch-electron.cjs --runtime=packaged --smoke-test"
```

It hung because `electron/main.js:547-550` binds the smoke exit solely to the
success event:

```js
win.webContents.once("did-finish-load", () => {
  if (process.env.DESKTOP_DJANGO_SMOKE_TEST === "1") {
    setTimeout(() => app.quit(), 750);
  }
});
```

There is no timeout fallback and no failure path, so when the page never loads
the app hangs forever. `verify-smoke.log` contains **zero `[django]` lines** -
Django never booted in packaged mode - so `did-finish-load` never fired, and
the log's last line is the harness's `[benchpack] timeout after 200s`.

The run was allowed to time out rather than being unblocked by hand, so the row
stays clean.

## Run D - `qwen38-pi-llamacpp-256k-medium` - first PASS

Configuration identical to Run C - same model and Q4_K_M artifact, 262144
context, q8_0 KV, same harness, same Electron fix - with exactly one change:
the reasoning level. The server was started with
`--chat-template-kwargs '{"reasoning_effort":"medium"}'` and pi ran
`--thinking medium`. The setting was verified active before launch: thinking
present but terse, 144 characters, correct answer.

`pi_exit=0`. The run **completed cleanly; it was not a timeout.**

| Check | Result |
| --- | --- |
| Wall clock | 5570.0s (92.8 min), exited on its own |
| `electron/package.json` exists | yes |
| `npm install` | ok |
| Node tests | pass, 53/53 |
| `smoke:packaged` | exit 0, `health200=1`, `root200=0`, `root302=1`, `resume200=1` |
| `app_served` | 1 |
| Diff | 36 files changed, +7622 / -120 |
| Outcome | **PASS** |

The result was checked rather than read off `summary.txt`: the HTTP counters
were recounted directly from `verify-smoke.log` and match, `GET /resume/`
returned 19,898 bytes of real content, packaged static assets all served 200,
and the artifact's mtime confirms freshness. Django's log timestamps are UTC
(18:01) against CEST local (20:01), which is consistent rather than stale.

**It self-verified.** From its own transcript, 119 tool calls (bash 81, write
15, edit 15, read 8), of which 15 bash commands actually run a smoke: 12
direct `node ./scripts/launch-electron.cjs --smoke-test` invocations, three
`just desktop-dev-smoke` runs, and one `node --test`. Run B ran none.

It also authored a `desktop-dev-smoke` target - the same invention that
deadlocked Run C - but wired it correctly, by delegating instead of
re-implementing:

```make
desktop-dev-smoke:
    npm --prefix electron run smoke:dev
```

where `smoke:dev` is
`node ./scripts/launch-electron.cjs --smoke-test`, so the flag reaches argv.

This is the **first PASS by a local open-weight model on this benchmark.**
Every prior pass in `data/agent-wrap-oneshot-results.json` is a hosted frontier
model - GPT-5.5, Opus 4.8, Sonnet 4.6, GLM-5.2 - and all eight legacy Qwen3.6
cells plus Qwen3.8 Runs A, B, and C failed.

One honest qualification: Run D carries the **same** latent C(b) defect. Its
`main.js:576-580` binds the smoke exit to `did-finish-load` with no timeout
fallback, exactly like Run C. Its checks terminated because they succeeded, not
because it wrote a failure path. Had its page failed to load, its own smoke
would have hung the same way.

## Reasoning Effort Is The Decisive Variable

Runs C and D are a clean A/B. Same model, same quantization, same context and
KV settings, same harness, same Electron fix, same source checkout, same
timeout. The only difference is the reasoning level, and it decided the
outcome.

| Cell | `reasoning_effort` | How set | Result |
| --- | --- | --- | --- |
| Run A | n/a, thinking disabled | `enable_thinking:false` | FAIL, timeout |
| Run B | `xhigh` | **unset**, resolved to the model default | FAIL, timeout |
| Run C | n/a, thinking disabled | `enable_thinking:false` | FAIL, timeout |
| Run D | `medium` | set explicitly | **PASS**, exited cleanly |

The finding is that the decisive variable is `reasoning_effort`, not the model
and not the quant. `xhigh` - the model's own uncontrolled default, and the
setting that injects an explicit "think carefully, validate key assumptions,
consider plausible alternatives" instruction - never validated its work. Both
thinking-off cells failed. `medium`, the one level that injects **no** reasoning
instruction at all, passed. The harness had never controlled this parameter
before Run D.

## One Pathology, Four Defects

Every failure in this campaign is the same shape: **the model writes two
components that disagree about an interface, on a code path it never
executes.**

| Cell | The two components | The disagreement |
| --- | --- | --- |
| A | staging vs the staged tree | staging expects `.stage/backend/src` to be a Python project; nothing ever places a `pyproject.toml` or `setup.py` there |
| B | `isStalePythonArtifact` vs `fs.cpSync` | the filter assumes it receives a `Dirent`; Node passes `(src, dest)` strings |
| C(a) | justfile vs `launch-electron.cjs` | the target passes the smoke flag as an env var; the launcher reads argv |
| C(b) | smoke exit vs failure | exit bound solely to `did-finish-load`, so a load failure hangs instead of failing |

C(b) is the sharpest of the four. Run C did the thing Run B failed to do - it
tried to verify its own work - and its verification harness had no failure
path, so the attempt itself deadlocked it. Writing a check is not the same as
writing a check that can fail. Run D both self-verified and, on the path it
actually took, terminated.

## Qwen3.6 And Qwen3.8 Comparison

The Qwen3.6-27B baseline ran the legacy harness
`~/projects/desktop-django-starter/.bench-qwen36/run-oneshot-wrap.sh` with a
byte-identical verifier policy to the current runner, so the verdicts are
comparable. Eight dense cells, all FAIL, best characterized as PARTIAL.
Summaries are at `.bench-qwen36/results-oneshot-*/summary.txt` and the
narrative is `.bench-qwen36/RUNTIME-COMPARISON.md:178-187`.

| Generation | Cell | Thinking | Wall clock | End state | Files | Node tests | Smoke failure |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 3.6 Q4_K_M | `qwen256k` | off | 79.0 min | completed | 30 | 45 | `ModuleNotFoundError: No module named 'core'` |
| 3.6 Q4_K_M | `qwen256k-med` | medium (budget 2048) | 114.2 min | completed | 32 | 38 | `KeyError: 'collectstatic'` + `ModuleNotFoundError: example` |
| 3.6 Q4_K_M | `qwen-q4-low` | low (budget 512) | 66.3 min | completed | 29 | 18 | smoke timeout (`smoke_exit=124`) |
| 3.6 Q4_K_M | `qwen256k-think` | high | 20.0 min | completed | 0 | n/a | no `electron/` authored |
| 3.6 Q8_0 | `qwen-q8-q8` | off | 67.7 min | completed | 32 | 51 | smoke timeout, self-inconsistent `manage.py` path |
| 3.6 Q8_0 | `qwen-q8-low` | low (budget 512) | 120.8 min | completed | 178 | 53 | smoke exit 0 but `/` never requested, `app_served=0` |
| 3.6 MLX 4-bit | `qwen-mlx` | off | 41.8 min | completed | 32 | 49 | missing `.stage/backend/manage.py` |
| 3.6 MLX 4-bit | `qwen-mlx-high` | high | 16.5 min | completed | 0 | n/a | no `electron/` authored |
| 3.8 Q4_K_M (A) | `qwen38-pi-llamacpp-256k-off` | off | 120.0 min | timeout | 38 | 53 | `.stage/backend/src` not a Python project |
| 3.8 Q4_K_M (B) | `qwen38-pi-llamacpp-256k-high` | `xhigh` (default, unset) | 120.0 min | timeout | 37 | 53 | `TypeError` in its own `stage-backend.cjs` |
| 3.8 Q4_K_M (C) | `qwen38-pi-llamacpp-256k-off-prewarmed` | off | 120.0 min | timeout | 46 | 53 | staging OK; dev smoke deadlocked, packaged smoke hung at 200s |
| 3.8 Q4_K_M (D) | `qwen38-pi-llamacpp-256k-medium` | `medium` (explicit) | 92.8 min | **exited 0** | 36 | 53 | **none - `app_served=1`, PASS** |

Reading of that table:

- The Qwen3.6 analysis-paralysis failure mode is gone. Both 3.6 high-thinking
  cells, on two different runtimes, produced zero files. Qwen3.8 high produced
  37 files and a complete harness. That is the single largest generational
  change here.
- Output completeness is at frontier level. All four 3.8 cells passed 53/53
  Node tests. Among the 3.6 cells only `qwen-q8-low` matched that, and it did so
  at Q8_0 with 178 changed paths including committed staticfiles and
  package-lock material. No 3.6 Q4_K_M cell got past 51.
- The failure moved one step later in the pipeline, and then stopped being a
  failure. Qwen3.6's problem was producing the artifact at all. Qwen3.8 Runs A
  and B produced near-correct artifacts and never validated them; the
  counterfactual shows Run B was one defect from serving, which is not true of
  any Qwen3.6 cell. Run C got staging working and died on its own verification
  harness. Run D self-verified and passed.
- Wall clock is no longer a straight regression. Runs A, B, and C all burned the
  120-minute cap without terminating, but Run D finished on its own in 92.8
  minutes. That is slower than the best Qwen3.6 cell's 79.0 minutes, and it is
  the only cell in either generation that actually passed.
- Reasoning effort, not generation and not quantization, separates the Qwen3.8
  cells from each other. Three of the four failed and the fourth passed on a
  single changed parameter.

## Conclusions

1. **Qwen3.8-27B passes this benchmark, at `reasoning_effort=medium`.** Run D
   is the first PASS by a local open-weight model here. The campaign record is
   1 pass in 4 cells; the three failures are Runs A, B, and C.
2. **`reasoning_effort` is the decisive variable, not the model or the quant.**
   Runs C and D differ in that parameter alone and differ in outcome. The
   model's uncontrolled default resolves to `xhigh`, which was actively
   harmful, and the harness had never controlled it before Run D. Any future
   Qwen3.8 agentic cell must set it explicitly and label by the resolved value
   (D-041).
3. The Qwen3.6 analysis-paralysis collapse is resolved. Both Qwen3.6
   high-thinking cells produced zero files; every Qwen3.8 cell produced a
   complete wrapper.
4. Generated-artifact completeness is at hosted-frontier level across the
   board: 53/53 Node tests in all four cells, on 36-46 file wrappers.
5. The failure mode of the three failing cells is "produces a near-complete,
   nearly-correct artifact and never successfully validates it". The
   counterfactual puts Run B one two-line defect from serving.
6. **The decisive gap is self-verification, not code generation.** Run B ran no
   smoke at all. Run C ran one and deadlocked on it because its check had no
   failure path. Run D ran 15 and passed. Writing a check and writing a check
   that can fail are different capabilities, and only Run D's page-load path
   exercised the difference - Run D carries the same latent no-timeout defect
   as Run C.
7. Every defect in this campaign is one pathology: two model-authored
   components disagreeing about an interface on a path the model never
   executed. That is a self-verification failure expressed four different ways,
   not four unrelated bugs.
8. The host's broken Electron install was a confirmed scoring hazard and is now
   fixed (D-040). Runs A and B predate the fix, which is why they are not
   strictly comparable to Runs C and D.
9. Wall clock is no longer a straight regression against Qwen3.6, but it is not
   an improvement either: the passing cell took 92.8 minutes against the best
   Qwen3.6 cell's 79.0 minutes, and that Qwen3.6 cell did not pass.

## Methodology Caveats

- **Run A has no transcript.** `--pi-mode` was unset and pi's buffered output
  flushes nothing on `SIGTERM`, so nothing survived the timeout kill. All
  behavioural claims in this report come from Run B. Recorded as D-039; new
  local-model one-shot wrap runs must pass `--pi-mode json`.
- **Source-repo difference against the legacy 3.6 cells.** The 3.8 runs used
  `django-resume-bench-main` at `3dc54f8` (0.3.0). The legacy Qwen3.6 cells
  cloned `~/projects/django-resume`. The verifier policy is byte-identical, so
  verdicts compare, but this is not a byte-identical replication and small
  target differences cannot be excluded.
- **KV-cache confound.** 48 of Qwen3.8's 64 layers are GatedDeltaNet linear
  attention with no KV cache. At identical `--ctx-size 262144` and identical
  q8_0 KV flags, the two generations are not under the same memory pressure.
  Any 3.6-vs-3.8 claim about long-context behaviour is confounded by this.
- **The counterfactual is a diagnostic, not a result.** It required repairing
  the host Electron install by hand, which the benchmark contract expects the
  agent to handle. It measures distance-to-pass; it does not convert either
  cell into a pass, and neither cell's recorded outcome changes.
- **The PASS did not replicate.** Run D is a single observation, and the
  confirmation run `qwen38-pi-llamacpp-256k-medium-rerun1` has since FAILED
  its packaged smoke (see the 2026-09-01 addendum above), putting the medium
  lane at 1-for-2. Do not treat Qwen3.8-27B as a reliable pass on this
  benchmark.
- **Runs A and B predate the Electron fix.** They ran against a host where the
  Electron binary never installed; Runs C and D ran with the fix in place. A/B
  and C/D are therefore not strictly comparable, and part of the A-B-to-C-D
  improvement is environmental rather than model behaviour.
- **Single run per cell.** No repeats, no seed control, and no thermal or
  power control. Treat every cell as one observation.
- **Runtime-and-format scope.** These are llama.cpp Q4_K_M rows. They are not
  artifact-parity comparisons against the MLX or Q8_0 Qwen3.6 lanes.

## Artifacts

Generated and gitignored:

```text
results/agent-wrap-oneshot/qwen38-pi-llamacpp-256k-off/
results/agent-wrap-oneshot/qwen38-pi-llamacpp-256k-high/
results/agent-wrap-oneshot/qwen38-pi-llamacpp-256k-off-prewarmed/
results/agent-wrap-oneshot/qwen38-pi-llamacpp-256k-medium/
```

Each contains `summary.txt`, `diff-stat.txt`, `files-changed.txt`, `npm.log`,
`nodetests.log`, `verify-smoke.log`, and `pi.log`. Every cell except Run A
holds a usable JSONL transcript; Run A's was lost to the timeout kill.

The counterfactual clone is kept for reproducibility at:

```text
/Users/jochen/projects/django-resume-oneshot-qwen38-counterfactual
```

Its only divergence from Run B's model output is the
`isStalePythonArtifact` signature in `electron/scripts/stage-backend.cjs`; the
rest of the difference is the repaired host Electron install under
`electron/node_modules/electron/`.

Normalized rows for both cells are in
`data/agent-wrap-oneshot-results.json`.
