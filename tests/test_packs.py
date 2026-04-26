"""Tests for benchpack.packs (manifest loading)."""

from __future__ import annotations

from pathlib import Path

import pytest

from benchpack.packs import (
    DuplicateCaseIdError,
    InvalidDefaultError,
    InvalidIdError,
    load_pack,
    repetitions_from_defaults,
    warmup_from_defaults,
)


def write_manifest(tmp_path: Path, body: str) -> Path:
    pack_dir = tmp_path / "examplepack"
    pack_dir.mkdir()
    (pack_dir / "benchpack.toml").write_text(body)
    return pack_dir


def test_load_pack_minimal(tmp_path: Path) -> None:
    pack_dir = write_manifest(
        tmp_path,
        """
[pack]
id = "smoke-chat"
version = "0.1.0"
description = "Tiny endpoint smoke test"

[defaults]
temperature = 0
max_tokens = 64
stream = false

[[cases]]
id = "capital"
kind = "chat"
prompt = "What is the capital of France?"

[scoring]
mode = "contains"
expected = "Paris"
""",
    )

    pack = load_pack(pack_dir)

    assert pack.id == "smoke-chat"
    assert pack.version == "0.1.0"
    assert pack.description == "Tiny endpoint smoke test"
    assert pack.defaults["temperature"] == 0
    assert pack.defaults["max_tokens"] == 64
    assert pack.defaults["stream"] is False
    assert repetitions_from_defaults(pack.defaults) == 1
    assert warmup_from_defaults(pack.defaults) == 0
    assert len(pack.cases) == 1
    assert pack.cases[0].id == "capital"
    assert pack.cases[0].kind == "chat"
    assert pack.cases[0].prompt == "What is the capital of France?"
    assert pack.scoring is not None
    assert pack.scoring.mode == "contains"
    assert pack.scoring.expected == "Paris"
    assert pack.path == pack_dir


def test_load_pack_rejects_duplicate_case_ids(tmp_path: Path) -> None:
    pack_dir = write_manifest(
        tmp_path,
        """
[pack]
id = "dup"
version = "0.1.0"

[[cases]]
id = "a"
kind = "chat"
prompt = "x"

[[cases]]
id = "a"
kind = "chat"
prompt = "y"
""",
    )

    with pytest.raises(DuplicateCaseIdError):
        load_pack(pack_dir)


def test_load_pack_no_scoring(tmp_path: Path) -> None:
    pack_dir = write_manifest(
        tmp_path,
        """
[pack]
id = "noscore"
version = "0.1.0"

[[cases]]
id = "only"
kind = "chat"
prompt = "hi"
""",
    )

    pack = load_pack(pack_dir)

    assert pack.scoring is None
    assert pack.cases[0].scoring is None


def test_load_pack_per_case_scoring_override(tmp_path: Path) -> None:
    pack_dir = write_manifest(
        tmp_path,
        """
[pack]
id = "mix"
version = "0.1.0"

[scoring]
mode = "contains"
expected = "default"

[[cases]]
id = "uses-default"
kind = "chat"
prompt = "x"

[[cases]]
id = "overrides"
kind = "chat"
prompt = "y"
scoring = { mode = "none" }
""",
    )

    pack = load_pack(pack_dir)

    assert pack.scoring is not None
    assert pack.scoring.mode == "contains"
    assert pack.cases[0].scoring is None
    assert pack.cases[1].scoring is not None
    assert pack.cases[1].scoring.mode == "none"


def test_load_pack_rejects_path_unsafe_case_id(tmp_path: Path) -> None:
    for bad in ("foo/bar", "..", "../escape", "has space", ".hidden", ""):
        pack_dir = tmp_path / f"bad-{abs(hash(bad))}"
        pack_dir.mkdir()
        (pack_dir / "benchpack.toml").write_text(
            f"""
[pack]
id = "p"
version = "0.1.0"

[[cases]]
id = {bad!r}
kind = "chat"
prompt = "x"
"""
        )
        with pytest.raises((InvalidIdError, Exception)):
            load_pack(pack_dir)


def test_load_pack_rejects_path_unsafe_pack_id(tmp_path: Path) -> None:
    pack_dir = write_manifest(
        tmp_path,
        """
[pack]
id = "../escape"
version = "0.1.0"

[[cases]]
id = "ok"
kind = "chat"
prompt = "x"
""",
    )
    with pytest.raises(InvalidIdError):
        load_pack(pack_dir)


def test_load_pack_accepts_documented_id_styles(tmp_path: Path) -> None:
    for good in ("capital", "json-output", "case_001", "Case1", "smoke-chat-2"):
        pack_dir = tmp_path / f"good-{good}"
        pack_dir.mkdir()
        (pack_dir / "benchpack.toml").write_text(
            f"""
[pack]
id = "p"
version = "0.1.0"

[[cases]]
id = "{good}"
kind = "chat"
prompt = "x"
"""
        )
        pack = load_pack(pack_dir)
        assert pack.cases[0].id == good


def test_load_pack_resolves_string_arg(tmp_path: Path) -> None:
    pack_dir = write_manifest(
        tmp_path,
        """
[pack]
id = "p"
version = "0.1.0"

[[cases]]
id = "c"
kind = "chat"
prompt = "x"
""",
    )

    pack = load_pack(str(pack_dir))

    assert pack.id == "p"


@pytest.mark.parametrize(
    "defaults_body",
    [
        "repetitions = 0",
        "repetitions = -1",
        'repetitions = "2"',
        "warmup = -1",
        'warmup = "1"',
    ],
)
def test_load_pack_rejects_invalid_runtime_defaults(
    tmp_path: Path,
    defaults_body: str,
) -> None:
    pack_dir = write_manifest(
        tmp_path,
        f"""
[pack]
id = "p"
version = "0.1.0"

[defaults]
{defaults_body}

[[cases]]
id = "c"
kind = "chat"
prompt = "x"
""",
    )

    with pytest.raises(InvalidDefaultError):
        load_pack(pack_dir)


def test_load_pack_reads_warmup_and_repetition_defaults(tmp_path: Path) -> None:
    pack_dir = write_manifest(
        tmp_path,
        """
[pack]
id = "p"
version = "0.1.0"

[defaults]
warmup = 1
repetitions = 2

[[cases]]
id = "c"
kind = "chat"
prompt = "x"
""",
    )

    pack = load_pack(pack_dir)

    assert warmup_from_defaults(pack.defaults) == 1
    assert repetitions_from_defaults(pack.defaults) == 2
