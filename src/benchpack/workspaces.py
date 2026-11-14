"""Runner-owned disposable workspace preparation for repo-task cases."""

from __future__ import annotations

import os
import shutil
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Iterator

from .packs import Case, Fixture, Pack
from .safe_files import open_contained_regular


MAX_FIXTURE_COPY_ENTRIES = 20_000
MAX_FIXTURE_COPY_BYTES = 512 * 1024 * 1024


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
    baseline_path: Path | None = None


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


@dataclass
class _CopyBudget:
    entries: int = 0
    bytes: int = 0

    def entry(self) -> None:
        self.entries += 1
        if self.entries > MAX_FIXTURE_COPY_ENTRIES:
            raise WorkspaceError("fixture copy entry limit exceeded")

    def check_bytes(self, count: int) -> None:
        if self.bytes + count > MAX_FIXTURE_COPY_BYTES:
            raise WorkspaceError("fixture copy byte limit exceeded")


def _fixture_entries(root: Path) -> Iterator[tuple[Path, os.stat_result]]:
    """Iterate without following links or materializing a whole directory."""
    pending = [root]
    yield root, root.lstat()
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as children:
            for child in children:
                candidate = Path(child.path)
                info = child.stat(follow_symlinks=False)
                yield candidate, info
                if stat.S_ISDIR(info.st_mode):
                    pending.append(candidate)


def _fixture_link(candidate: Path, root: Path) -> Path:
    target = candidate.readlink()
    if target.is_absolute():
        raise WorkspaceError(f"repo fixture contains absolute symlink {candidate.relative_to(root)}")
    try:
        resolved = (candidate.parent / target).resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise WorkspaceError("repo fixture symlink could not be resolved") from exc
    if not resolved.is_relative_to(root.resolve(strict=True)):
        raise WorkspaceError(f"repo fixture contains symlink {candidate.relative_to(root)} escaping the repo fixture")
    return target


def _reject_escaping_symlinks(source_root: Path, case: Case, fixture: Fixture) -> None:
    """Preflight both generations before allocating output or launching work."""
    budget = _CopyBudget()
    try:
        for candidate, info in _fixture_entries(source_root):
            budget.entry()
            budget.entry()  # workspace plus baseline, including directories/links
            if stat.S_ISLNK(info.st_mode):
                _fixture_link(candidate, source_root)
            elif stat.S_ISREG(info.st_mode):
                budget.check_bytes(info.st_size * 2)
                budget.bytes += info.st_size * 2
            elif not stat.S_ISDIR(info.st_mode):
                raise WorkspaceError("repo fixture must contain regular files, directories or symlinks")
    except WorkspaceError as exc:
        # Pack validation runs this for every case: name the refused case and fixture.
        raise WorkspaceError(f"repo-task case {case.id!r} fixture {fixture.id!r}: {exc}") from exc
    except OSError as exc:
        raise WorkspaceError(f"could not inspect repo-task case {case.id!r} fixture {fixture.id!r}") from exc


def _copy_fixture_tree(source: Path, destination: Path, *, budget: _CopyBudget,
                       dirs_exist_ok: bool = False) -> None:
    """Copy with shared entry/actual-byte ceilings, retaining owned partials."""
    directories = []
    for candidate, info in _fixture_entries(source):
        budget.entry()
        relative = candidate.relative_to(source)
        target = destination / relative
        if stat.S_ISDIR(info.st_mode):
            target.mkdir(exist_ok=dirs_exist_ok and candidate == source)
            directories.append((target, info))
        elif stat.S_ISLNK(info.st_mode):
            target.symlink_to(_fixture_link(candidate, source))
        elif stat.S_ISREG(info.st_mode):
            fd = open_contained_regular(source, relative.as_posix())
            if fd is None:
                raise WorkspaceError("fixture copy source is no longer a regular contained file")
            try:
                opened_info = os.fstat(fd)
                budget.check_bytes(opened_info.st_size)
                with target.open("xb") as out:
                    while True:
                        remaining = MAX_FIXTURE_COPY_BYTES - budget.bytes
                        chunk = os.read(fd, min(65536, remaining + 1))
                        if not chunk:
                            break
                        budget.check_bytes(len(chunk))
                        out.write(chunk)
                        budget.bytes += len(chunk)
                    os.fchmod(out.fileno(), stat.S_IMODE(opened_info.st_mode))
                os.utime(target, ns=(opened_info.st_atime_ns, opened_info.st_mtime_ns))
            finally:
                os.close(fd)
        else:
            raise WorkspaceError("fixture copy source must be regular file, directory or symlink")
    for target, info in reversed(directories):
        target.chmod(stat.S_IMODE(info.st_mode))
        os.utime(target, ns=(info.st_atime_ns, info.st_mtime_ns))


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
    if destination.exists() or destination.is_symlink():
        raise WorkspaceError(
            f"workspace destination already exists for repo-task case "
            f"{case.id!r}: {destination}"
        )

    baseline = Path(output_dir) / "baseline" / case.id / f"rep-{repetition:03d}"
    if baseline.exists() or baseline.is_symlink():
        raise WorkspaceError(f"workspace baseline already exists: {baseline}")

    budget = _CopyBudget()
    staging: Path | None = None
    step = "allocate staging"
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent))
        step = "copy fixture"
        _copy_fixture_tree(source_fixture.path, staging, budget=budget, dirs_exist_ok=True)
        # Exclusive reservation prevents replacing even an empty foreign directory.
        # POSIX publication requires other writers not to rename output directories.
        step = "reserve destination"
        destination.mkdir()
        step = "publish workspace (empty destination reservation retained on failure)"
        staging.rename(destination)
        staging = None
        # Copy the published generation, never reread the live fixture. No model
        # or harness runs until both copies are ready. Only the runner owns this
        # baseline; harnesses may mutate the workspace alone.
        step = "copy prepared baseline"
        baseline.parent.mkdir(parents=True, exist_ok=True)
        _copy_fixture_tree(destination, baseline, budget=budget)
    except (OSError, shutil.Error, WorkspaceError) as exc:
        retained = f"; staging retained at {staging}" if staging is not None else ""
        raise WorkspaceError(
            f"could not prepare workspace for repo-task case {case.id!r} "
            f"from fixture {source_fixture.id!r}: {step}: {exc}"
            f"{retained}; destination: {destination}; baseline: {baseline}"
        ) from exc

    return PreparedWorkspace(source_fixture=source_fixture, path=destination, baseline_path=baseline)
