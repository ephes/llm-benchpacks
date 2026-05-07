# python-regression-fix-external-agent

Bundled `repo-task` pack variant that runs the `python-regression-fix` workload
through the public `external-agent` harness.

Pack version: `0.1.1`.

This variant uses the same fixture and verifier as `python-regression-fix`, but
its prompt is direct-edit-specific: the external agent is told to modify the
prepared workspace files directly instead of returning a fenced patch. It
declares
`harness = { id = "external-agent", timeout_s = 900 }` on the measured
`repo-task` case. The default `python-regression-fix` pack remains the
fenced-patch compatibility workload, and this pack remains opt-in rather than
part of the default matrix.

## Case

- `fix-task-summary`: asks the model to patch a stdlib-only Python module so
  task summary and overdue-title behavior match the included `unittest` cases.

The prompt lives in `prompts/fix-task-summary.md` and tells the external agent
that it is running inside the prepared repository workspace. For this variant,
the runner still performs the normal pre-task adapter call, then invokes the
configured external-agent subprocess inside the prepared workspace. Patch
capture happens after the external-agent task phase at
`patch/fix-task-summary/rep-001.diff`, and the verifier remains deterministic.

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
BENCHPACK_EXTERNAL_AGENT_ARGV='["/path/to/agent"]' \
  uv run benchpack run python-regression-fix-external-agent --adapter openai-chat --model <model> --endpoint http://localhost:11434/v1 --host-label local-python-regression-external-agent --force
```
