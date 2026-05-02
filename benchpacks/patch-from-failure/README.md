# patch-from-failure

Tiny bundled `repo-task` pack that exercises the current fenced unified-diff
model-output contract.

Pack version: `0.1.0`.

## Case

- `fix-greeting`: asks the model to patch a small Python repo so
  `greet("Ada")` returns exactly `Hello, Ada!`.

The prompt lives in `prompts/fix-greeting.md` and tells the model to return only
a fenced code block with info string `diff`. The runner extracts the first
fenced `diff` or `patch` block, applies it inside the run-owned workspace, then
captures `patch/fix-greeting/rep-001.diff` and runs the verifier.
The runner accepts either `diff` or `patch`; this pack asks for `diff` to keep
model outputs uniform across runs.

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
uv run benchpack run patch-from-failure --adapter openai-chat --model <model> --endpoint http://localhost:11434/v1 --host-label local-patch --force
```
