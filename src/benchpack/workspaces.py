"""Runner-owned disposable workspace preparation for repo-task cases."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from .packs import Case, Fixture, Pack


class WorkspaceError(ValueError):
    """Raised when a repo-task workspace cannot be prepared safely."""


@dataclass(frozen=True)
class PreparedWorkspace:
    """Metadata for a prepared workspace.

    The runner owns this object; result rows receive only the narrow serialized
    metadata needed to locate the prepared workspace for this measured record.
    """

    source_fixture: Fixture
    path: Path


def validate_repo_task_case(pack: Pack, case: Case) -> Fixture:
    """Return the one repo fixture for a repo-task case or raise clearly."""

    fixtures_by_id = {fixture.id: fixture for fixture in pack.fixtures}
    repo_fixtures: list[Fixture] = []

    for fixture_id in case.fixture_refs:
        fixture = fixtures_by_id.get(fixture_id)
        if fixture is None:
            raise WorkspaceError(
                f"repo-task case {case.id!r} references unknown fixture "
                f"{fixture_id!r}"
            )
        if fixture.kind == "repo":
            if not fixture.path.is_dir():
                raise WorkspaceError(
                    f"repo-task case {case.id!r} fixture {fixture.id!r} has "
                    f"kind 'repo' but is not a directory"
                )
            repo_fixtures.append(fixture)
            continue

        if fixture.path.is_dir():
            raise WorkspaceError(
                f"repo-task case {case.id!r} references non-repo directory "
                f"fixture {fixture.id!r} (kind {fixture.kind!r})"
            )

    if len(repo_fixtures) != 1:
        raise WorkspaceError(
            f"repo-task case {case.id!r} must reference exactly one "
            f"kind='repo' directory fixture; found {len(repo_fixtures)}"
        )

    return repo_fixtures[0]


def validate_repo_task_cases(pack: Pack) -> None:
    """Validate repo-task fixture shape for all cases in a loaded pack."""

    for case in pack.cases:
        if case.kind == "repo-task":
            source_fixture = validate_repo_task_case(pack, case)
            _reject_escaping_symlinks(source_fixture.path, case, source_fixture)


def workspace_path(output_dir: Path, case: Case, repetition: int) -> Path:
    """Return the deterministic measured workspace path for a case repetition."""

    if isinstance(repetition, bool) or not isinstance(repetition, int):
        raise ValueError("repetition must be an integer >= 1")
    if repetition < 1:
        raise ValueError("repetition must be an integer >= 1")
    # Case ids are path-component-safe because the pack loader enforces ID_PATTERN.
    return Path(output_dir) / "workspace" / case.id / f"rep-{repetition:03d}"


def workspace_record(prepared: PreparedWorkspace, output_dir: Path) -> dict[str, str]:
    """Return the run.jsonl workspace object for a prepared repo-task workspace."""

    try:
        relative_path = prepared.path.resolve().relative_to(Path(output_dir).resolve())
    except (OSError, ValueError) as exc:
        raise WorkspaceError(
            f"workspace path {prepared.path} is not under run output directory "
            f"{output_dir}"
        ) from exc

    return {
        "path": relative_path.as_posix(),
        "source_fixture_id": prepared.source_fixture.id,
        "source_path": str(prepared.source_fixture.raw["path"]),
    }


def _reject_escaping_symlinks(source_root: Path, case: Case, fixture: Fixture) -> None:
    """Reject symlinks that would let future workspace writes escape isolation."""

    resolved_source_root = source_root.resolve(strict=True)

    def walk(directory: Path) -> None:
        try:
            children = list(directory.iterdir())
        except OSError as exc:
            raise WorkspaceError(
                f"could not inspect directory {directory} in repo-task case "
                f"{case.id!r} fixture {fixture.id!r}"
            ) from exc

        for candidate in children:
            if candidate.is_symlink():
                _validate_symlink(candidate)
                continue
            if candidate.is_dir():
                walk(candidate)

    def _validate_symlink(candidate: Path) -> None:
        try:
            target = candidate.readlink()
        except OSError as exc:
            raise WorkspaceError(
                f"could not inspect symlink {candidate} in repo-task case "
                f"{case.id!r} fixture {fixture.id!r}"
            ) from exc

        if target.is_absolute():
            raise WorkspaceError(
                f"repo-task case {case.id!r} fixture {fixture.id!r} contains "
                f"absolute symlink {candidate.relative_to(source_root)}"
            )

        resolved_target = (candidate.parent / target).resolve(strict=False)
        if not resolved_target.is_relative_to(resolved_source_root):
            raise WorkspaceError(
                f"repo-task case {case.id!r} fixture {fixture.id!r} contains "
                f"symlink {candidate.relative_to(source_root)} escaping the "
                "repo fixture"
            )

    walk(source_root)


def prepare_repo_task_workspace(
    pack: Pack,
    case: Case,
    output_dir: Path,
    repetition: int,
) -> PreparedWorkspace:
    """Copy a repo-task's source fixture into a fresh run-owned workspace."""

    # Re-check at copy time so this helper remains safe when called directly.
    source_fixture = validate_repo_task_case(pack, case)
    _reject_escaping_symlinks(source_fixture.path, case, source_fixture)
    destination = workspace_path(output_dir, case, repetition)
    if destination.exists():
        raise WorkspaceError(
            f"workspace destination already exists for repo-task case "
            f"{case.id!r}: {destination}"
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copytree(source_fixture.path, destination, symlinks=True)
    except (OSError, shutil.Error) as exc:
        raise WorkspaceError(
            f"could not prepare workspace for repo-task case {case.id!r} "
            f"from fixture {source_fixture.id!r}"
        ) from exc

    return PreparedWorkspace(source_fixture=source_fixture, path=destination)
