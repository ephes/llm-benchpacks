You are running inside the prepared repository workspace for this benchmark
case. Fix the tiny Python repository by editing the workspace files directly.

Allowed repo-root path to edit:

- `greeter.py`

Current file: `greeter.py`

```python
def greet(name: str) -> str:
    return f"Hello {name}."
```

Relevant test: `tests/test_greeter.py`

```python
import unittest

from greeter import greet


class GreeterTests(unittest.TestCase):
    def test_greets_ada(self) -> None:
        self.assertEqual(greet("Ada"), "Hello, Ada!")


if __name__ == "__main__":
    unittest.main()
```

Observed failure:

```text
$ python -m unittest discover -s tests
FAIL: test_greets_ada (test_greeter.GreeterTests.test_greets_ada)
AssertionError: 'Hello Ada.' != 'Hello, Ada!'
```

Expected behavior:

- `greet("Ada")` must return exactly `Hello, Ada!`

Workspace editing contract:

- Edit only the allowed repo-root path listed above.
- Do not write outside the prepared workspace.
- Do not edit tests, verifier files, prompts, README files, generated result
  artifacts, task logs, raw payloads, patch artifacts, or metadata files.
- Make the smallest source change needed for the stated verifier expectation.
- No patch needs to be printed. The runner captures workspace changes after the
  external-agent task phase exits.
- A short stdout summary is fine, but scoring depends on workspace state and the
  deterministic verifier, not prose.
