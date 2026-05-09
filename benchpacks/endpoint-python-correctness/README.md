# endpoint-python-correctness

Bundled endpoint-only `repo-task` pack for a small deterministic Python
correctness fix. It uses the normal chat adapter path and the default fenced
unified-diff executor; it does not require `external-agent`.

Pack version: `0.2.0`.

## Case

- `fix-inventory-aggregation`: asks the model to patch a stdlib-only inventory
  module so SKU aggregation and reorder behavior match deterministic checks.

The prompt lives in `prompts/fix-inventory-aggregation.md` and tells the model
to return only a fenced code block with info string `diff`. The preferred
response remains a unified diff. If the model cannot produce one, the prompt
allows a full-file replacement block for `inventory.py` using exact
`*** Begin File: inventory.py` and `*** End File` markers inside the same
`diff` fence. The runner extracts the first fenced `diff` or `patch` block,
applies either the unified diff or the explicit replacement block inside the
run-owned workspace, then captures
`patch/fix-inventory-aggregation/rep-001.diff` and runs the verifier.
The generic executor validates workspace-relative paths; this pack's prompt and
verifier constrain the useful replacement target to `inventory.py`.

## Fixture

The pack declares one `kind = "repo"` fixture:

- `repo`: a tiny stdlib-only Python repo under `fixtures/repo/`.

The fixture is pack-owned source. The runner copies it to
`workspace/fix-inventory-aggregation/rep-001/` for the measured execution and
must not mutate the source fixture.

The fixture contains intentional regressions in `inventory.py`:

- duplicate SKUs overwrite instead of summing
- SKU normalization is missing
- blank SKUs are not ignored
- reorder selection uses `<= minimum` and sorts only by SKU

## Verification

`verify/check.py` is a deterministic stdlib-only verifier. It imports
`inventory.py` from the prepared workspace, checks visible aggregation and
reorder cases, checks a second edge dataset with numeric-string quantities,
blank SKUs, and strict threshold behavior, requires input rows to remain
unchanged, and requires the captured patch artifact to exist and be non-empty.
It writes structured JSON to the runner-provided `--output` path and uses the
process exit code as the pass/fail authority.

## Runtime Defaults

The pack sets:

- `stream = false`
- `warmup = 0`
- `repetitions = 1`
- `temperature = 0`
- `max_tokens = 640`
- case scoring `mode = "verify-script"`

## Example Command

```sh
uv run benchpack run endpoint-python-correctness --adapter openai-chat --model <model> --endpoint http://localhost:11434/v1 --host-label local-endpoint-correctness --force
```
