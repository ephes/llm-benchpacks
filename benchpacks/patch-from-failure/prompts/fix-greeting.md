Fix the tiny Python repository by editing only the file that needs the bug fix.

Repo path to edit:

- `greeter.py`

Observed failure:

```text
$ python -m unittest discover -s tests
FAIL: test_greets_ada (test_greeter.GreeterTests.test_greets_ada)
AssertionError: 'Hello Ada.' != 'Hello, Ada!'
```

Expected behavior:

- `greet("Ada")` must return exactly `Hello, Ada!`

Return only one fenced code block with info string exactly `diff`.
The first line of your response must be the literal fence marker `` ```diff ``.
Inside that block, return a unified diff that applies from the repository root.
Do not include shell commands, explanations, markdown outside the fenced block,
or extra files unless they are needed.
