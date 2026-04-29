"""Tests for benchpack.packs (manifest loading)."""

from __future__ import annotations

from pathlib import Path

import pytest

from benchpack.packs import (
    DuplicateCaseIdError,
    InvalidDefaultError,
    InvalidIdError,
    InvalidPromptSourceError,
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


def test_load_pack_loads_prompt_file(tmp_path: Path) -> None:
    pack_dir = write_manifest(
        tmp_path,
        """
[pack]
id = "fileprompt"
version = "0.1.0"

[[cases]]
id = "from-file"
kind = "chat"
prompt_file = "prompts/example.md"
""",
    )
    prompt = "Line one.\nLine two.\n"
    prompt_dir = pack_dir / "prompts"
    prompt_dir.mkdir()
    (prompt_dir / "example.md").write_text(prompt, encoding="utf-8")

    pack = load_pack(pack_dir)

    assert pack.cases[0].prompt == prompt
    assert pack.cases[0].raw["prompt_file"] == "prompts/example.md"


def test_load_pack_keeps_inline_prompt_support(tmp_path: Path) -> None:
    pack_dir = write_manifest(
        tmp_path,
        """
[pack]
id = "inline"
version = "0.1.0"

[[cases]]
id = "inline-case"
kind = "chat"
prompt = "Inline prompt stays supported."
""",
    )

    pack = load_pack(pack_dir)

    assert pack.cases[0].prompt == "Inline prompt stays supported."
    assert pack.cases[0].raw["prompt"] == "Inline prompt stays supported."


def test_load_pack_rejects_absolute_prompt_file(tmp_path: Path) -> None:
    outside = tmp_path / "outside.md"
    outside.write_text("outside\n", encoding="utf-8")
    pack_dir = write_manifest(
        tmp_path,
        f"""
[pack]
id = "absfile"
version = "0.1.0"

[[cases]]
id = "bad"
kind = "chat"
prompt_file = {str(outside)!r}
""",
    )

    with pytest.raises(InvalidPromptSourceError, match="relative"):
        load_pack(pack_dir)


def test_load_pack_rejects_prompt_file_traversal(tmp_path: Path) -> None:
    outside = tmp_path / "outside.md"
    outside.write_text("outside\n", encoding="utf-8")
    pack_dir = write_manifest(
        tmp_path,
        """
[pack]
id = "traversal"
version = "0.1.0"

[[cases]]
id = "bad"
kind = "chat"
prompt_file = "../outside.md"
""",
    )

    with pytest.raises(InvalidPromptSourceError, match="escapes"):
        load_pack(pack_dir)


def test_load_pack_rejects_prompt_file_symlink_escape(tmp_path: Path) -> None:
    outside = tmp_path / "outside.md"
    outside.write_text("outside\n", encoding="utf-8")
    pack_dir = write_manifest(
        tmp_path,
        """
[pack]
id = "symlinkescape"
version = "0.1.0"

[[cases]]
id = "bad"
kind = "chat"
prompt_file = "prompts/escape.md"
""",
    )
    prompts_dir = pack_dir / "prompts"
    prompts_dir.mkdir()
    try:
        (prompts_dir / "escape.md").symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"symlinks cannot be created on this filesystem: {exc}")

    with pytest.raises(InvalidPromptSourceError, match="escapes"):
        load_pack(pack_dir)


def test_load_pack_rejects_non_string_prompt_file(tmp_path: Path) -> None:
    pack_dir = write_manifest(
        tmp_path,
        """
[pack]
id = "badpromptfile"
version = "0.1.0"

[[cases]]
id = "bad"
kind = "chat"
prompt_file = 123
""",
    )

    with pytest.raises(InvalidPromptSourceError, match="must be a string"):
        load_pack(pack_dir)


def test_load_pack_rejects_prompt_and_prompt_file_together(tmp_path: Path) -> None:
    pack_dir = write_manifest(
        tmp_path,
        """
[pack]
id = "both"
version = "0.1.0"

[[cases]]
id = "bad"
kind = "chat"
prompt = "inline"
prompt_file = "prompts/example.md"
""",
    )

    with pytest.raises(InvalidPromptSourceError, match="both"):
        load_pack(pack_dir)


def test_load_pack_rejects_missing_prompt_source(tmp_path: Path) -> None:
    pack_dir = write_manifest(
        tmp_path,
        """
[pack]
id = "noprompt"
version = "0.1.0"

[[cases]]
id = "bad"
kind = "chat"
""",
    )

    with pytest.raises(InvalidPromptSourceError, match="either"):
        load_pack(pack_dir)


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


def test_load_pack_accepts_explicit_zero_warmup(tmp_path: Path) -> None:
    pack_dir = write_manifest(
        tmp_path,
        """
[pack]
id = "p"
version = "0.1.0"

[defaults]
warmup = 0

[[cases]]
id = "c"
kind = "chat"
prompt = "x"
""",
    )

    pack = load_pack(pack_dir)

    assert warmup_from_defaults(pack.defaults) == 0
    assert repetitions_from_defaults(pack.defaults) == 1


def test_bundled_runtime_sweep_pack_contract() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    pack = load_pack(repo_root / "benchpacks" / "runtime-sweep")

    assert pack.id == "runtime-sweep"
    assert pack.version == "0.1.0"
    assert pack.defaults["temperature"] == 0
    assert pack.defaults["max_tokens"] == 128
    assert pack.defaults["stream"] is True
    assert warmup_from_defaults(pack.defaults) == 1
    assert repetitions_from_defaults(pack.defaults) == 3
    assert [case.id for case in pack.cases] == ["short", "medium", "long"]

    prompt_sizes = [len(case.prompt or "") for case in pack.cases]
    assert prompt_sizes == sorted(prompt_sizes)
    assert len(set(prompt_sizes)) == 3

    assert pack.scoring is not None
    assert pack.scoring.mode == "none"


def test_bundled_desktop_django_wrap_pack_contract() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    pack = load_pack(repo_root / "benchpacks" / "desktop-django-wrap")

    assert pack.id == "desktop-django-wrap"
    assert pack.version == "0.1.0"
    assert pack.defaults["temperature"] == 0
    assert pack.defaults["max_tokens"] == 384
    assert pack.defaults["stream"] is True
    assert warmup_from_defaults(pack.defaults) == 0
    assert repetitions_from_defaults(pack.defaults) == 1
    assert [case.id for case in pack.cases] == [
        "wrap-plan-small",
        "wrap-plan-context",
    ]

    assert pack.scoring is not None
    assert pack.scoring.mode == "contains"
    assert pack.scoring.expected == "DDS_WRAP_PLAN"

    forbidden_path_fragments = ("/Users/", "~/", "C:\\")
    for case in pack.cases:
        assert case.kind == "chat"
        assert case.prompt
        assert "DDS_WRAP_PLAN" in case.prompt
        assert "prompt" not in case.raw
        assert "prompt_file" in case.raw
        prompt_file = case.raw["prompt_file"]
        assert isinstance(prompt_file, str)
        assert prompt_file.startswith("prompts/")
        assert not Path(prompt_file).is_absolute()
        for fragment in forbidden_path_fragments:
            assert fragment not in case.prompt
