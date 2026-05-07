Fix the tiny Python repository by editing only the file that needs the bug fix.

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

Output contract:

- Your entire response must be one fenced code block with info string exactly
  `diff`.
- The first line of your response must be the literal fence marker `` ```diff ``.
- Do not include `<think>`, hidden reasoning, analysis, explanations, shell
  commands, or markdown outside the fenced block.
- Use only exact repo-root paths listed above.
- Do not use placeholder `index` lines or invented paths.
- Inside the block, return a complete unified diff that applies with
  `git apply` from the repository root.
- Close the fenced block.
