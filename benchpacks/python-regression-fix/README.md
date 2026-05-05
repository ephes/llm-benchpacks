# python-regression-fix

Bundled `repo-task` pack that exercises the current fenced unified-diff
model-output contract with a small Python regression fix.

Pack version: `0.1.0`.

## Case

- `fix-task-summary`: asks the model to patch a stdlib-only Python module so
  task summary and overdue-title behavior match the included `unittest` cases.

The prompt lives in `prompts/fix-task-summary.md` and tells the model to return
only a fenced code block with info string `diff`. The runner extracts the first
fenced `diff` or `patch` block, applies it inside the run-owned workspace, then
captures `patch/fix-task-summary/rep-001.diff` and runs the verifier.

## Fixture

The pack declares one `kind = "repo"` fixture:

- `repo`: a small stdlib-only Python repo under `fixtures/repo/`.

The fixture is pack-owned source. The runner copies it to
`workspace/fix-task-summary/rep-001/` for the measured execution and must not
mutate the source fixture.

The fixture contains intentional regressions in `task_summary.py`:

- missing owners are normalized by mutating task dictionaries
- completed tasks are excluded from owner counts
- completed tasks can appear in overdue output
- overdue output is sorted by title instead of due date then title

## Verification

`verify/check.py` is a deterministic stdlib-only verifier. It imports
`task_summary.py` from the prepared workspace, checks the expected summary,
checks that input task dictionaries were not mutated, checks overdue title
filtering and ordering, and requires the captured patch artifact to exist and be
non-empty. It writes structured JSON to the runner-provided `--output` path and
uses the process exit code as the pass/fail authority.

## Runtime Defaults

The pack sets:

- `stream = false`
- `warmup = 0`
- `repetitions = 1`
- `temperature = 0`
- `max_tokens = 768`
- case scoring `mode = "verify-script"`

## Example Command

```sh
uv run benchpack run python-regression-fix --adapter openai-chat --model <model> --endpoint http://localhost:11434/v1 --host-label local-python-regression --force
```
