"""Tests for benchpack.packs (manifest loading)."""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from benchpack.packs import (
    DuplicateCaseIdError,
    DuplicateFixtureIdError,
    InvalidDefaultError,
    InvalidFixtureError,
    InvalidFixtureRefError,
    InvalidIdError,
    InvalidPromptSourceError,
    PackError,
    load_pack,
    repetitions_from_defaults,
    warmup_from_defaults,
)
from benchpack.workspaces import validate_repo_task_case


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
    assert pack.cases[0].fixture_refs == []
    assert pack.scoring is not None
    assert pack.scoring.mode == "contains"
    assert pack.scoring.expected == "Paris"
    assert pack.path == pack_dir
    assert pack.fixtures == []


def test_load_pack_loads_case_fixture_refs(tmp_path: Path) -> None:
    pack_dir = write_manifest(
        tmp_path,
        """
[pack]
id = "fixturepack"
version = "0.1.0"

[[fixtures]]
id = "synthetic-fixture"
kind = "context"
path = "fixtures/context.md"

[[cases]]
id = "c"
kind = "chat"
prompt = "x"
fixture_refs = ["synthetic-fixture"]
""",
    )
    fixture_dir = pack_dir / "fixtures"
    fixture_dir.mkdir()
    (fixture_dir / "context.md").write_text("portable context\n", encoding="utf-8")

    pack = load_pack(pack_dir)

    assert pack.cases[0].fixture_refs == ["synthetic-fixture"]
    assert pack.cases[0].raw["fixture_refs"] == ["synthetic-fixture"]


def test_load_pack_appends_referenced_file_fixture_to_prompt(tmp_path: Path) -> None:
    pack_dir = write_manifest(
        tmp_path,
        """
[pack]
id = "fixtureprompt"
version = "0.1.0"

[[fixtures]]
id = "context"
kind = "context"
path = "fixtures/context.md"

[[cases]]
id = "c"
kind = "chat"
prompt = "Base prompt."
fixture_refs = ["context"]
""",
    )
    fixture_dir = pack_dir / "fixtures"
    fixture_dir.mkdir()
    (fixture_dir / "context.md").write_text("fixture context\n", encoding="utf-8")

    pack = load_pack(pack_dir)

    assert pack.cases[0].prompt == (
        "Base prompt.\n\n"
        "--- BEGIN FIXTURE context (context, fixtures/context.md) ---\n"
        "fixture context\n"
        "--- END FIXTURE context ---"
    )
    assert pack.cases[0].fixture_refs == ["context"]
    assert pack.cases[0].raw["prompt"] == "Base prompt."


def test_load_pack_keeps_fixture_footer_on_own_line_without_trailing_newline(
    tmp_path: Path,
) -> None:
    pack_dir = write_manifest(
        tmp_path,
        """
[pack]
id = "fixturepromptfile"
version = "0.1.0"

[[fixtures]]
id = "context"
kind = "context"
path = "fixtures/context.md"

[[cases]]
id = "c"
kind = "chat"
prompt_file = "prompts/base.md"
fixture_refs = ["context"]
""",
    )
    prompt_dir = pack_dir / "prompts"
    prompt_dir.mkdir()
    prompt_dir.joinpath("base.md").write_text("Base prompt.\n", encoding="utf-8")
    fixture_dir = pack_dir / "fixtures"
    fixture_dir.mkdir()
    fixture_dir.joinpath("context.md").write_text(
        "fixture without trailing newline",
        encoding="utf-8",
    )

    pack = load_pack(pack_dir)

    assert pack.cases[0].prompt == (
        "Base prompt.\n\n"
        "--- BEGIN FIXTURE context (context, fixtures/context.md) ---\n"
        "fixture without trailing newline\n"
        "--- END FIXTURE context ---"
    )


def test_load_pack_appends_multiple_file_fixtures_in_ref_order(
    tmp_path: Path,
) -> None:
    pack_dir = write_manifest(
        tmp_path,
        """
[pack]
id = "fixtureorder"
version = "0.1.0"

[[fixtures]]
id = "first"
kind = "context"
path = "fixtures/first.md"

[[fixtures]]
id = "second"
kind = "context"
path = "fixtures/second.md"

[[cases]]
id = "c"
kind = "chat"
prompt = "Base"
fixture_refs = ["second", "first"]
""",
    )
    fixture_dir = pack_dir / "fixtures"
    fixture_dir.mkdir()
    (fixture_dir / "first.md").write_text("first contents\n", encoding="utf-8")
    (fixture_dir / "second.md").write_text("second contents\n", encoding="utf-8")

    prompt = load_pack(pack_dir).cases[0].prompt

    assert prompt is not None
    assert prompt.index("--- BEGIN FIXTURE second") < prompt.index(
        "--- BEGIN FIXTURE first"
    )
    assert "second contents\n--- END FIXTURE second ---" in prompt
    assert "first contents\n--- END FIXTURE first ---" in prompt


def test_load_pack_keeps_directory_fixture_refs_metadata_only(
    tmp_path: Path,
) -> None:
    pack_dir = write_manifest(
        tmp_path,
        """
[pack]
id = "fixturedirref"
version = "0.1.0"

[[fixtures]]
id = "repo-snapshot"
kind = "repo"
path = "fixtures/repo"

[[cases]]
id = "c"
kind = "chat"
prompt = "Base prompt."
fixture_refs = ["repo-snapshot"]
""",
    )
    fixture_dir = pack_dir / "fixtures" / "repo"
    fixture_dir.mkdir(parents=True)
    (fixture_dir / "README.md").write_text("directory fixture text\n", encoding="utf-8")

    pack = load_pack(pack_dir)

    assert pack.cases[0].prompt == "Base prompt."
    assert pack.cases[0].fixture_refs == ["repo-snapshot"]
    assert pack.fixtures[0].path.is_dir()


def test_load_pack_loads_case_fixture_refs_when_fixtures_appear_after_cases(
    tmp_path: Path,
) -> None:
    pack_dir = write_manifest(
        tmp_path,
        """
[pack]
id = "fixtureorder"
version = "0.1.0"

[[cases]]
id = "c"
kind = "chat"
prompt = "x"
fixture_refs = ["late-fixture"]

[[fixtures]]
id = "late-fixture"
kind = "context"
path = "fixtures/context.md"
""",
    )
    fixture_dir = pack_dir / "fixtures"
    fixture_dir.mkdir()
    (fixture_dir / "context.md").write_text("portable context\n", encoding="utf-8")

    pack = load_pack(pack_dir)

    assert pack.cases[0].fixture_refs == ["late-fixture"]


def test_load_pack_without_fixtures_or_refs_still_loads(tmp_path: Path) -> None:
    pack_dir = write_manifest(
        tmp_path,
        """
[pack]
id = "plainpack"
version = "0.1.0"

[[cases]]
id = "c"
kind = "chat"
prompt = "x"
""",
    )

    pack = load_pack(pack_dir)

    assert pack.fixtures == []
    assert pack.cases[0].fixture_refs == []


def test_load_pack_rejects_non_list_fixture_refs(tmp_path: Path) -> None:
    pack_dir = write_manifest(
        tmp_path,
        """
[pack]
id = "badrefs"
version = "0.1.0"

[[fixtures]]
id = "context"
kind = "context"
path = "fixtures/context.md"

[[cases]]
id = "c"
kind = "chat"
prompt = "x"
fixture_refs = "context"
""",
    )
    (pack_dir / "fixtures").mkdir()
    (pack_dir / "fixtures" / "context.md").write_text("x", encoding="utf-8")

    with pytest.raises(InvalidFixtureRefError, match="must be a list"):
        load_pack(pack_dir)


def test_load_pack_rejects_non_string_fixture_refs(tmp_path: Path) -> None:
    pack_dir = write_manifest(
        tmp_path,
        """
[pack]
id = "badrefentries"
version = "0.1.0"

[[fixtures]]
id = "context"
kind = "context"
path = "fixtures/context.md"

[[cases]]
id = "c"
kind = "chat"
prompt = "x"
fixture_refs = [123]
""",
    )
    (pack_dir / "fixtures").mkdir()
    (pack_dir / "fixtures" / "context.md").write_text("x", encoding="utf-8")

    with pytest.raises(InvalidFixtureRefError, match="entries must be strings"):
        load_pack(pack_dir)


def test_load_pack_rejects_invalid_fixture_ref_id(tmp_path: Path) -> None:
    pack_dir = write_manifest(
        tmp_path,
        """
[pack]
id = "badrefid"
version = "0.1.0"

[[fixtures]]
id = "context"
kind = "context"
path = "fixtures/context.md"

[[cases]]
id = "c"
kind = "chat"
prompt = "x"
fixture_refs = ["../context"]
""",
    )
    (pack_dir / "fixtures").mkdir()
    (pack_dir / "fixtures" / "context.md").write_text("x", encoding="utf-8")

    with pytest.raises(InvalidIdError):
        load_pack(pack_dir)


def test_load_pack_rejects_duplicate_fixture_refs(tmp_path: Path) -> None:
    pack_dir = write_manifest(
        tmp_path,
        """
[pack]
id = "duprefs"
version = "0.1.0"

[[fixtures]]
id = "context"
kind = "context"
path = "fixtures/context.md"

[[cases]]
id = "c"
kind = "chat"
prompt = "x"
fixture_refs = ["context", "context"]
""",
    )
    (pack_dir / "fixtures").mkdir()
    (pack_dir / "fixtures" / "context.md").write_text("x", encoding="utf-8")

    with pytest.raises(InvalidFixtureRefError, match="more than once"):
        load_pack(pack_dir)


def test_load_pack_rejects_missing_fixture_refs(tmp_path: Path) -> None:
    pack_dir = write_manifest(
        tmp_path,
        """
[pack]
id = "missingrefs"
version = "0.1.0"

[[fixtures]]
id = "context"
kind = "context"
path = "fixtures/context.md"

[[cases]]
id = "c"
kind = "chat"
prompt = "x"
fixture_refs = ["missing"]
""",
    )
    (pack_dir / "fixtures").mkdir()
    (pack_dir / "fixtures" / "context.md").write_text("x", encoding="utf-8")

    with pytest.raises(InvalidFixtureRefError, match="unknown fixture"):
        load_pack(pack_dir)


def test_load_pack_loads_fixture_file_metadata(tmp_path: Path) -> None:
    pack_dir = write_manifest(
        tmp_path,
        """
[pack]
id = "fixturepack"
version = "0.1.0"

[[fixtures]]
id = "synthetic-fixture"
kind = "context"
path = "fixtures/context.md"
description = "Synthetic context"

[[cases]]
id = "c"
kind = "chat"
prompt = "x"
""",
    )
    fixture_dir = pack_dir / "fixtures"
    fixture_dir.mkdir()
    fixture_file = fixture_dir / "context.md"
    fixture_file.write_text("portable context\n", encoding="utf-8")

    pack = load_pack(pack_dir)

    assert len(pack.fixtures) == 1
    fixture = pack.fixtures[0]
    assert fixture.id == "synthetic-fixture"
    assert fixture.kind == "context"
    assert fixture.path == fixture_file.resolve()
    assert fixture.description == "Synthetic context"
    assert fixture.raw == {
        "id": "synthetic-fixture",
        "kind": "context",
        "path": "fixtures/context.md",
        "description": "Synthetic context",
    }
    assert pack.cases[0].fixture_refs == []


def test_load_pack_accepts_fixture_directory(tmp_path: Path) -> None:
    pack_dir = write_manifest(
        tmp_path,
        """
[pack]
id = "fixturedir"
version = "0.1.0"

[[fixtures]]
id = "repo-snapshot"
kind = "repo"
path = "fixtures/repo"

[[cases]]
id = "c"
kind = "chat"
prompt = "x"
""",
    )
    fixture_dir = pack_dir / "fixtures" / "repo"
    fixture_dir.mkdir(parents=True)

    pack = load_pack(pack_dir)

    assert pack.fixtures[0].path == fixture_dir.resolve()
    assert pack.fixtures[0].path.is_dir()


def test_load_pack_rejects_invalid_fixture_id(tmp_path: Path) -> None:
    pack_dir = write_manifest(
        tmp_path,
        """
[pack]
id = "badfixtureid"
version = "0.1.0"

[[fixtures]]
id = "../escape"
kind = "context"
path = "fixtures/context.md"

[[cases]]
id = "c"
kind = "chat"
prompt = "x"
""",
    )
    (pack_dir / "fixtures").mkdir()
    (pack_dir / "fixtures" / "context.md").write_text("x", encoding="utf-8")

    with pytest.raises(InvalidIdError):
        load_pack(pack_dir)


def test_load_pack_rejects_duplicate_fixture_ids(tmp_path: Path) -> None:
    pack_dir = write_manifest(
        tmp_path,
        """
[pack]
id = "dupfixtures"
version = "0.1.0"

[[fixtures]]
id = "same"
kind = "context"
path = "fixtures/a.md"

[[fixtures]]
id = "same"
kind = "context"
path = "fixtures/b.md"

[[cases]]
id = "c"
kind = "chat"
prompt = "x"
""",
    )
    fixtures_dir = pack_dir / "fixtures"
    fixtures_dir.mkdir()
    (fixtures_dir / "a.md").write_text("a", encoding="utf-8")
    (fixtures_dir / "b.md").write_text("b", encoding="utf-8")

    with pytest.raises(DuplicateFixtureIdError):
        load_pack(pack_dir)


def test_load_pack_rejects_non_table_fixture_entries(tmp_path: Path) -> None:
    pack_dir = write_manifest(
        tmp_path,
        """
fixtures = ["not-a-table"]

[pack]
id = "badfixtureshape"
version = "0.1.0"

[[cases]]
id = "c"
kind = "chat"
prompt = "x"
""",
    )

    with pytest.raises(InvalidFixtureError, match="tables"):
        load_pack(pack_dir)


def test_load_pack_rejects_non_string_fixture_path(tmp_path: Path) -> None:
    pack_dir = write_manifest(
        tmp_path,
        """
[pack]
id = "badfixturepath"
version = "0.1.0"

[[fixtures]]
id = "context"
kind = "context"
path = 123

[[cases]]
id = "c"
kind = "chat"
prompt = "x"
""",
    )

    with pytest.raises(InvalidFixtureError, match="path must be a string"):
        load_pack(pack_dir)


def test_load_pack_rejects_non_string_fixture_kind(tmp_path: Path) -> None:
    pack_dir = write_manifest(
        tmp_path,
        """
[pack]
id = "badfixturekind"
version = "0.1.0"

[[fixtures]]
id = "context"
kind = 123
path = "fixtures/context.md"

[[cases]]
id = "c"
kind = "chat"
prompt = "x"
""",
    )
    (pack_dir / "fixtures").mkdir()
    (pack_dir / "fixtures" / "context.md").write_text("x", encoding="utf-8")

    with pytest.raises(InvalidFixtureError, match="kind must be a non-empty string"):
        load_pack(pack_dir)


@pytest.mark.parametrize("kind", ['""', '"   "'])
def test_load_pack_rejects_empty_fixture_kind(tmp_path: Path, kind: str) -> None:
    pack_dir = write_manifest(
        tmp_path,
        f"""
[pack]
id = "emptyfixturekind"
version = "0.1.0"

[[fixtures]]
id = "context"
kind = {kind}
path = "fixtures/context.md"

[[cases]]
id = "c"
kind = "chat"
prompt = "x"
""",
    )
    (pack_dir / "fixtures").mkdir()
    (pack_dir / "fixtures" / "context.md").write_text("x", encoding="utf-8")

    with pytest.raises(InvalidFixtureError, match="kind must be a non-empty string"):
        load_pack(pack_dir)


def test_load_pack_rejects_absolute_fixture_path(tmp_path: Path) -> None:
    outside = tmp_path / "outside.md"
    outside.write_text("outside\n", encoding="utf-8")
    pack_dir = write_manifest(
        tmp_path,
        f"""
[pack]
id = "absfixture"
version = "0.1.0"

[[fixtures]]
id = "bad"
kind = "context"
path = {str(outside)!r}

[[cases]]
id = "c"
kind = "chat"
prompt = "x"
""",
    )

    with pytest.raises(InvalidFixtureError, match="relative"):
        load_pack(pack_dir)


def test_load_pack_rejects_fixture_path_traversal(tmp_path: Path) -> None:
    outside = tmp_path / "outside.md"
    outside.write_text("outside\n", encoding="utf-8")
    pack_dir = write_manifest(
        tmp_path,
        """
[pack]
id = "fixturetraversal"
version = "0.1.0"

[[fixtures]]
id = "bad"
kind = "context"
path = "../outside.md"

[[cases]]
id = "c"
kind = "chat"
prompt = "x"
""",
    )

    with pytest.raises(InvalidFixtureError, match="escapes"):
        load_pack(pack_dir)


def test_load_pack_rejects_missing_fixture_traversal_as_escape(
    tmp_path: Path,
) -> None:
    pack_dir = write_manifest(
        tmp_path,
        """
[pack]
id = "missingfixturetraversal"
version = "0.1.0"

[[fixtures]]
id = "bad"
kind = "context"
path = "../missing.md"

[[cases]]
id = "c"
kind = "chat"
prompt = "x"
""",
    )

    with pytest.raises(InvalidFixtureError, match="escapes"):
        load_pack(pack_dir)


@pytest.mark.parametrize("fixture_path", ['""', '"."'])
def test_load_pack_rejects_fixture_path_resolving_to_pack_root(
    tmp_path: Path,
    fixture_path: str,
) -> None:
    pack_dir = write_manifest(
        tmp_path,
        f"""
[pack]
id = "fixturepackroot"
version = "0.1.0"

[[fixtures]]
id = "bad"
kind = "context"
path = {fixture_path}

[[cases]]
id = "c"
kind = "chat"
prompt = "x"
""",
    )

    with pytest.raises(InvalidFixtureError, match="pack directory"):
        load_pack(pack_dir)


def test_load_pack_rejects_fixture_symlink_escape(tmp_path: Path) -> None:
    outside = tmp_path / "outside.md"
    outside.write_text("outside\n", encoding="utf-8")
    pack_dir = write_manifest(
        tmp_path,
        """
[pack]
id = "fixturesymlinkescape"
version = "0.1.0"

[[fixtures]]
id = "bad"
kind = "context"
path = "fixtures/escape.md"

[[cases]]
id = "c"
kind = "chat"
prompt = "x"
""",
    )
    fixtures_dir = pack_dir / "fixtures"
    fixtures_dir.mkdir()
    try:
        (fixtures_dir / "escape.md").symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"symlinks cannot be created on this filesystem: {exc}")

    with pytest.raises(InvalidFixtureError, match="escapes"):
        load_pack(pack_dir)


def test_load_pack_rejects_missing_fixture_path(tmp_path: Path) -> None:
    pack_dir = write_manifest(
        tmp_path,
        """
[pack]
id = "missingfixture"
version = "0.1.0"

[[fixtures]]
id = "bad"
kind = "context"
path = "fixtures/missing.md"

[[cases]]
id = "c"
kind = "chat"
prompt = "x"
""",
    )

    with pytest.raises(InvalidFixtureError, match="does not exist"):
        load_pack(pack_dir)


def test_load_pack_rejects_fixture_path_that_is_not_file_or_directory(
    tmp_path: Path,
) -> None:
    if not hasattr(os, "mkfifo"):
        pytest.skip("mkfifo is not available on this platform")
    pack_dir = write_manifest(
        tmp_path,
        """
[pack]
id = "specialfixture"
version = "0.1.0"

[[fixtures]]
id = "special"
kind = "context"
path = "fixtures/special"

[[cases]]
id = "c"
kind = "chat"
prompt = "x"
""",
    )
    fixtures_dir = pack_dir / "fixtures"
    fixtures_dir.mkdir()
    try:
        os.mkfifo(fixtures_dir / "special")
    except OSError as exc:
        pytest.skip(f"fifo cannot be created on this filesystem: {exc}")

    with pytest.raises(InvalidFixtureError, match="file or directory"):
        load_pack(pack_dir)


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


def test_load_pack_rejects_missing_prompt_file_traversal_as_escape(
    tmp_path: Path,
) -> None:
    pack_dir = write_manifest(
        tmp_path,
        """
[pack]
id = "missingtraversal"
version = "0.1.0"

[[cases]]
id = "bad"
kind = "chat"
prompt_file = "../missing.md"
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


def test_load_pack_rejects_missing_prompt_file(tmp_path: Path) -> None:
    pack_dir = write_manifest(
        tmp_path,
        """
[pack]
id = "missingpromptfile"
version = "0.1.0"

[[cases]]
id = "bad"
kind = "chat"
prompt_file = "prompts/missing.md"
""",
    )

    with pytest.raises(InvalidPromptSourceError, match="could not be read"):
        load_pack(pack_dir)


def test_load_pack_rejects_directory_prompt_file(tmp_path: Path) -> None:
    pack_dir = write_manifest(
        tmp_path,
        """
[pack]
id = "directorypromptfile"
version = "0.1.0"

[[cases]]
id = "bad"
kind = "chat"
prompt_file = "prompts"
""",
    )
    (pack_dir / "prompts").mkdir()

    with pytest.raises(InvalidPromptSourceError, match="could not be read"):
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


def test_load_pack_scoring_timeout_int_is_first_class_field(
    tmp_path: Path,
) -> None:
    pack_dir = write_manifest(
        tmp_path,
        """
[pack]
id = "timeoutpack"
version = "0.1.0"

[[cases]]
id = "c"
kind = "chat"
prompt = "x"

[scoring]
mode = "verify-script"
script = "verify/check.py"
timeout_s = 30
custom_key = "kept"
""",
    )

    scoring = load_pack(pack_dir).scoring

    assert scoring is not None
    assert scoring.timeout_s == 30.0
    assert isinstance(scoring.timeout_s, float)
    assert scoring.extra == {"custom_key": "kept"}


def test_load_pack_case_scoring_timeout_float_is_first_class_field(
    tmp_path: Path,
) -> None:
    pack_dir = write_manifest(
        tmp_path,
        """
[pack]
id = "timeoutpack"
version = "0.1.0"

[[cases]]
id = "c"
kind = "chat"
prompt = "x"
scoring = { mode = "verify-script", script = "verify/check.py", timeout_s = 2.5 }
""",
    )

    scoring = load_pack(pack_dir).cases[0].scoring

    assert scoring is not None
    assert scoring.timeout_s == 2.5
    assert "timeout_s" not in scoring.extra


@pytest.mark.parametrize(
    "timeout_s",
    ["0", "0.0", "-1", "true", "false", '"30"'],
)
def test_load_pack_rejects_invalid_scoring_timeout(
    tmp_path: Path,
    timeout_s: str,
) -> None:
    pack_dir = write_manifest(
        tmp_path,
        f"""
[pack]
id = "badtimeout"
version = "0.1.0"

[[cases]]
id = "c"
kind = "chat"
prompt = "x"

[scoring]
mode = "verify-script"
script = "verify/check.py"
timeout_s = {timeout_s}
""",
    )

    with pytest.raises(PackError, match="scoring.timeout_s"):
        load_pack(pack_dir)


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
    assert [case.fixture_refs for case in pack.cases] == [[], [], []]

    prompt_sizes = [len(case.prompt or "") for case in pack.cases]
    assert prompt_sizes == sorted(prompt_sizes)
    assert len(set(prompt_sizes)) == 3

    assert pack.scoring is not None
    assert pack.scoring.mode == "none"
    assert pack.fixtures == []


def test_bundled_smoke_chat_pack_has_no_fixtures() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    pack = load_pack(repo_root / "benchpacks" / "smoke-chat")

    assert pack.id == "smoke-chat"
    assert pack.fixtures == []
    assert [case.fixture_refs for case in pack.cases] == [[]]


def test_bundled_desktop_django_wrap_pack_contract() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    pack = load_pack(repo_root / "benchpacks" / "desktop-django-wrap")
    pack_dir = repo_root / "benchpacks" / "desktop-django-wrap"

    assert pack.id == "desktop-django-wrap"
    assert pack.version == "0.1.5"
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
    assert pack.scoring.mode == "regex"
    assert pack.scoring.pattern is not None
    assert pack.scoring.expected is None
    assert re.search(
        pack.scoring.pattern,
        (
            "DDS_WRAP_PLAN\n"
            "Inspect: check settings and entrypoints.\n"
            "Electron shell: start Django on 127.0.0.1.\n"
            "Django runtime: move state under app data.\n"
            "Packaging: split dev and packaged launch.\n"
            "Verification: run a smoke command."
        ),
    )
    assert not re.search(
        pack.scoring.pattern,
        (
            "DDS_WRAP_PLAN\n"
            "Inspect: check settings and entrypoints.\n"
            "Django runtime: move state under app data.\n"
            "Electron shell: start Django on 127.0.0.1.\n"
            "Packaging: split dev and packaged launch.\n"
            "Verification: run a smoke command."
        ),
    )
    output_labels = [
        "DDS_WRAP_PLAN",
        "Inspect:",
        "Electron shell:",
        "Django runtime:",
        "Packaging:",
        "Verification:",
    ]

    forbidden_path_fragments = ("/Users/", "~/", "C:\\")
    for case in pack.cases:
        assert case.kind == "chat"
        assert case.fixture_refs == ["synthetic-django-app", "synthetic-django-repo"]
        assert case.prompt
        for label in output_labels:
            assert label in case.prompt
        assert "Use exactly" in case.prompt
        assert "output skeleton" in case.prompt
        assert "prompt" not in case.raw
        assert "prompt_file" in case.raw
        assert case.raw["fixture_refs"] == [
            "synthetic-django-app",
            "synthetic-django-repo",
        ]
        assert (
            "--- BEGIN FIXTURE synthetic-django-app "
            "(context, fixtures/synthetic-django-app.md) ---"
        ) in case.prompt
        assert "--- END FIXTURE synthetic-django-app ---" in case.prompt
        assert "fixtures/synthetic-django-repo" not in case.prompt
        assert "--- BEGIN FIXTURE synthetic-django-repo" not in case.prompt
        assert "Synthetic Django Repo Snapshot" not in case.prompt
        assert "class StockItem" not in case.prompt
        assert "Inventory Dashboard" not in case.prompt
        assert "## Application Shape" in case.prompt
        assert "Django project with a `manage.py` entrypoint" in case.prompt
        prompt_file = case.raw["prompt_file"]
        assert isinstance(prompt_file, str)
        assert prompt_file.startswith("prompts/")
        assert not Path(prompt_file).is_absolute()
        for fragment in forbidden_path_fragments:
            assert fragment not in case.prompt

    assert [fixture.id for fixture in pack.fixtures] == [
        "synthetic-django-app",
        "synthetic-django-repo",
    ]
    fixtures_by_id = {fixture.id: fixture for fixture in pack.fixtures}

    app_fixture = fixtures_by_id["synthetic-django-app"]
    assert app_fixture.kind == "context"
    assert app_fixture.raw["path"] == "fixtures/synthetic-django-app.md"
    assert app_fixture.raw["path"].startswith("fixtures/")
    assert app_fixture.path.is_relative_to(pack_dir.resolve())
    assert app_fixture.path.is_file()
    app_fixture_contents = app_fixture.path.read_text(encoding="utf-8")
    for fragment in forbidden_path_fragments:
        assert fragment not in app_fixture_contents

    repo_fixture = fixtures_by_id["synthetic-django-repo"]
    assert repo_fixture.kind == "repo"
    assert repo_fixture.raw["path"] == "fixtures/synthetic-django-repo"
    assert repo_fixture.raw["path"].startswith("fixtures/")
    assert repo_fixture.path.is_relative_to(pack_dir.resolve())
    assert repo_fixture.path.is_dir()
    expected_repo_files = {
        "README.md",
        "manage.py",
        "pyproject.toml",
        "config/__init__.py",
        "config/settings.py",
        "config/urls.py",
        "config/wsgi.py",
        "inventory/__init__.py",
        "inventory/models.py",
        "inventory/views.py",
        "inventory/urls.py",
        "inventory/templates/inventory/dashboard.html",
        "inventory/static/inventory/app.css",
    }
    actual_repo_files = {
        path.relative_to(repo_fixture.path).as_posix()
        for path in repo_fixture.path.rglob("*")
        if path.is_file()
    }
    assert actual_repo_files == expected_repo_files
    actual_repo_parts = {
        part for path in actual_repo_files for part in path.split("/")
    }
    assert "__pycache__" not in actual_repo_parts
    for fixture_file in repo_fixture.path.rglob("*"):
        resolved_fixture_file = fixture_file.resolve()
        assert resolved_fixture_file.is_relative_to(pack_dir.resolve())
        if fixture_file.is_file():
            fixture_contents = fixture_file.read_text(encoding="utf-8")
            for fragment in forbidden_path_fragments:
                assert fragment not in fixture_contents


def test_bundled_patch_from_failure_pack_contract() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    pack = load_pack(repo_root / "benchpacks" / "patch-from-failure")
    pack_dir = repo_root / "benchpacks" / "patch-from-failure"

    assert pack.id == "patch-from-failure"
    assert pack.version == "0.1.0"
    assert pack.defaults["temperature"] == 0
    assert pack.defaults["max_tokens"] == 256
    assert pack.defaults["stream"] is False
    assert warmup_from_defaults(pack.defaults) == 0
    assert repetitions_from_defaults(pack.defaults) == 1
    assert pack.scoring is None

    assert [fixture.id for fixture in pack.fixtures] == ["repo"]
    fixture = pack.fixtures[0]
    assert fixture.kind == "repo"
    assert fixture.raw["path"] == "fixtures/repo"
    assert fixture.path.is_relative_to(pack_dir.resolve())
    assert fixture.path.is_dir()

    assert len(pack.cases) == 1
    case = pack.cases[0]
    assert case.id == "fix-greeting"
    assert case.kind == "repo-task"
    assert case.fixture_refs == ["repo"]
    assert case.raw["prompt_file"] == "prompts/fix-greeting.md"
    assert "prompt" not in case.raw
    assert case.prompt is not None
    assert "```diff" in case.prompt
    assert "info string exactly `diff`" in case.prompt
    assert "`greeter.py`" in case.prompt
    assert "Hello, Ada!" in case.prompt
    assert "Do not include shell commands" in case.prompt

    assert case.scoring is not None
    assert case.scoring.mode == "verify-script"
    assert case.scoring.script == "verify/check.py"
    assert validate_repo_task_case(pack, case).id == "repo"

    fixture_files = {
        path.relative_to(fixture.path).as_posix()
        for path in fixture.path.rglob("*")
        if path.is_file()
    }
    assert fixture_files == {"greeter.py", "tests/test_greeter.py"}
    assert (
        fixture.path.joinpath("greeter.py").read_text(encoding="utf-8")
        == 'def greet(name: str) -> str:\n    return f"Hello {name}."\n'
    )
    assert pack_dir.joinpath("verify/check.py").is_file()
