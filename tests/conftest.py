import json

import pytest


@pytest.fixture
def decoder_nesting_limit(monkeypatch):
    """Make ``json.loads`` reject nested arrays the way an exhausted decoder does.

    The real limit follows the interpreter's C stack, so the depth that raises
    ``RecursionError`` differs between platforms. Readers must map that error
    to their domain error wherever it occurs; this fixture triggers it
    deterministically for any document starting with ``[[``.
    """

    real_loads = json.loads

    def loads(text, *args, **kwargs):
        if isinstance(text, str) and text.startswith("[["):
            raise RecursionError("maximum recursion depth exceeded")
        return real_loads(text, *args, **kwargs)

    monkeypatch.setattr(json, "loads", loads)
