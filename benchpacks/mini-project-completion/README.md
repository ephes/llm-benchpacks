# mini-project-completion

Bundled opt-in `repo-task` pack for a small deterministic project-completion
task. It asks the model to finish a stdlib-only notes reporting CLI and uses
the default fenced unified-diff executor.

Pack version: `0.1.0`.

## Case

- `complete-notes-cli`: completes parsing, tag summaries, tag filtering, and
  CLI output for a tiny notes project.

The prompt lives in `prompts/complete-notes-cli.md` and tells the model to
return only a fenced code block with info string `diff`. The expected response
is a unified diff over the allowed project files. The runner extracts the first
fenced `diff` or `patch` block, applies it inside the run-owned workspace,
captures `patch/complete-notes-cli/rep-001.diff`, and runs the verifier.

## Fixture

The pack declares one `kind = "repo"` fixture:

- `repo`: a tiny stdlib-only Python project under `fixtures/repo/`.

The fixture is pack-owned source. The runner copies it to
`workspace/complete-notes-cli/rep-001/` for the measured execution and must not
mutate the source fixture.

The fixture contains incomplete behavior in:

- `notes/store.py`: parsing, tag normalization, summary ordering, and tag
  filtering are incomplete.
- `notes/cli.py`: the CLI parses notes but ignores `--tag`.

## Verification

`verify/check.py` is a deterministic stdlib-only verifier. It imports the
workspace project, runs visible and hidden parser/report/filter checks, runs
the CLI through its public `main()` entry point, requires the source-vs-
workspace patch artifact to exist and be non-empty, writes structured JSON to
the runner-provided `--output` path, and uses the process exit code as the
pass/fail authority.

## Runtime Defaults

The pack sets:

- `stream = false`
- `warmup = 0`
- `repetitions = 1`
- `temperature = 0`
- `max_tokens = 1400`
- case scoring `mode = "verify-script"`

## Example Command

```sh
uv run benchpack run mini-project-completion --adapter openai-chat --model <model> --endpoint http://localhost:11434/v1 --host-label local-mini-project --force
```
