# patch-from-failure-external-agent

Tiny bundled `repo-task` pack variant that runs the `patch-from-failure`
workload through the public `external-agent` harness.

Pack version: `0.1.1`.

This variant uses the same fixture and verifier as `patch-from-failure`, but
its prompt is direct-edit-specific: the external agent is told to modify the
prepared workspace files directly instead of returning a fenced patch. It
declares
`harness = { id = "external-agent", timeout_s = 900 }` on the measured
`repo-task` case. The default `patch-from-failure` pack remains the
fenced-patch compatibility workload, and this pack remains opt-in rather than
part of the default matrix.

## Case

- `fix-greeting`: asks the model to patch a small Python repo so
  `greet("Ada")` returns exactly `Hello, Ada!`.

The prompt lives in `prompts/fix-greeting.md` and tells the external agent that
it is running inside the prepared repository workspace. For this variant, the
runner still performs the normal pre-task adapter call, then invokes the
configured external-agent subprocess inside the prepared workspace. Patch
capture happens after the external-agent task phase at
`patch/fix-greeting/rep-001.diff`, and the verifier remains deterministic.

## Fixture

The pack declares one `kind = "repo"` fixture:

- `repo`: a tiny stdlib-only Python repo under `fixtures/repo/`.

The fixture is pack-owned source. The runner copies it to
`workspace/fix-greeting/rep-001/` for the measured execution and must not mutate
the source fixture.
The `tests/test_greeter.py` file exists to make the prompt's observed failure
concrete for humans and models; the verifier below checks `greeter.py` directly
instead of running that test file.

## Verification

`verify/check.py` is a deterministic stdlib-only verifier. It imports
`greeter.py` from the prepared workspace, calls `greet("Ada")`, checks the exact
expected value, and requires the captured patch artifact to exist and be
non-empty. It writes structured JSON to the runner-provided `--output` path and
uses the process exit code as the pass/fail authority.

## Runtime Defaults

The pack sets:

- `stream = false`
- `warmup = 0`
- `repetitions = 1`
- `temperature = 0`
- `max_tokens = 256`
- case scoring `mode = "verify-script"`

## Example Command

```sh
BENCHPACK_EXTERNAL_AGENT_ARGV='["/path/to/agent"]' \
  uv run benchpack run patch-from-failure-external-agent --adapter openai-chat --model <model> --endpoint http://localhost:11434/v1 --host-label local-patch-external-agent --force
```
