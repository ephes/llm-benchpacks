# django-dashboard-regression-fix-external-agent

Bundled `repo-task` pack variant that runs the
`django-dashboard-regression-fix` workload through the public `external-agent`
harness.

Pack version: `0.1.0`.

This variant intentionally copies the same fixture, prompt, and verifier as
`django-dashboard-regression-fix`. It differs only by declaring
`harness = { id = "external-agent", timeout_s = 900 }` on the measured
`repo-task` case. The default `django-dashboard-regression-fix` pack remains
the fenced-patch compatibility workload.

## Case

- `fix-dashboard-regressions`: asks the model to patch a stdlib-only dashboard
  fixture so project visibility, archived filtering, row formatting, sorting,
  and input immutability match the included `unittest` cases.

The prompt lives in `prompts/fix-dashboard-regressions.md` and is copied from
the fenced-patch pack. For this variant, the runner still performs the normal
pre-task adapter call, then invokes the configured external-agent subprocess
inside the prepared workspace before capturing
`patch/fix-dashboard-regressions/rep-001.diff` and running the verifier.

## Fixture

The pack declares one `kind = "repo"` fixture:

- `repo`: a small stdlib-only Python repo under `fixtures/repo/`.

The fixture is pack-owned source. The runner copies it to
`workspace/fix-dashboard-regressions/rep-001/` for the measured execution and
must not mutate the source fixture.

The fixture contains intentional regressions across multiple files:

- draft public projects are visible to anonymous users
- private projects are visible to any signed-in user
- archived projects are included even when `include_archived` is false
- dashboard rows are sorted by title instead of due date, priority, then title
- row formatting fills missing values by mutating project dictionaries

## Verification

`verify/check.py` is a deterministic stdlib-only verifier. It imports the
prepared dashboard modules from the workspace, checks permission boundaries,
archived filtering, explicit archived inclusion, deterministic row ordering,
missing-value formatting, and input immutability. It also requires the captured
patch artifact to exist and be non-empty. The verifier writes structured JSON to
the runner-provided `--output` path and uses the process exit code as the
pass/fail authority.

## Runtime Defaults

The pack sets:

- `stream = false`
- `warmup = 0`
- `repetitions = 1`
- `temperature = 0`
- `max_tokens = 1200`
- case scoring `mode = "verify-script"`

## Example Command

```sh
BENCHPACK_EXTERNAL_AGENT_ARGV='["/path/to/agent"]' \
  uv run benchpack run django-dashboard-regression-fix-external-agent --adapter openai-chat --model <model> --endpoint http://localhost:11434/v1 --host-label local-dashboard-regression-external-agent --force
```
