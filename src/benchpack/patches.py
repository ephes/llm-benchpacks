"""Deterministic patch artifacts for repo-task workspaces."""

from __future__ import annotations

import difflib
import os
from dataclasses import dataclass
from pathlib import Path

from .packs import Case
from .workspaces import PreparedWorkspace


# Fixed capture ceilings; no partial patch is published when any is exceeded.
MAX_PATCH_FILE_BYTES = 4 * 1024 * 1024
MAX_PATCH_INPUT_BYTES = 32 * 1024 * 1024
MAX_PATCH_OUTPUT_BYTES = 8 * 1024 * 1024
MAX_PATCH_LINES = 4000
MAX_PATCH_DIFF_WORK = 16_000_000
MAX_PATCH_ENTRIES = 10_000


class PatchError(ValueError):
    """Raised when a repo-task patch artifact cannot be captured."""


@dataclass
class _Budget:
    input_bytes: int = 0
    output_bytes: int = 0
    diff_work: int = 0

    def read(self, path: Path) -> bytes:
        limit = min(MAX_PATCH_FILE_BYTES, MAX_PATCH_INPUT_BYTES - self.input_bytes)
        if path.stat().st_size > limit:
            raise PatchError(f"patch input byte budget exceeded at {path}")
        with path.open("rb") as handle:
            raw = handle.read(limit + 1)
        self.consume_input(len(raw), path)
        return raw

    def readlink(self, path: Path) -> str:
        text = os.readlink(path)
        self.consume_input(len(os.fsencode(text)), path)
        return text

    def consume_input(self, size: int, path: Path) -> None:
        self.input_bytes += size
        if size > MAX_PATCH_FILE_BYTES or self.input_bytes > MAX_PATCH_INPUT_BYTES:
            raise PatchError(f"patch input byte budget exceeded at {path}")

    def consume_work(self, old_lines: list[str], new_lines: list[str]) -> None:
        # Conservative bound on SequenceMatcher's worst-case pair comparisons.
        self.diff_work += len(old_lines) * len(new_lines)
        if self.diff_work > MAX_PATCH_DIFF_WORK:
            raise PatchError("patch diff work budget exceeded")


@dataclass(frozen=True)
class _Entry:
    kind: str
    path: Path
    mode: int = 0o100644


def patch_path(output_dir: Path, case: Case, repetition: int) -> Path:
    """Return the deterministic measured patch path for a case repetition."""

    if isinstance(repetition, bool) or not isinstance(repetition, int):
        raise ValueError("repetition must be an integer >= 1")
    if repetition < 1:
        raise ValueError("repetition must be an integer >= 1")
    return Path(output_dir) / "patch" / case.id / f"rep-{repetition:03d}.diff"


def capture_workspace_patch(
    prepared: PreparedWorkspace,
    output_dir: Path,
    case: Case,
    repetition: int,
) -> dict[str, str]:
    """Write the prepared-baseline-vs-workspace patch and return its record."""

    artifact_path = patch_path(output_dir, case, repetition)
    try:
        if prepared.baseline_path is None:
            raise PatchError("prepared workspace has no bound baseline")
        diff = directory_diff(prepared.baseline_path, prepared.path)
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_bytes(diff.encode("utf-8"))
    except (OSError, PatchError) as exc:
        raise PatchError(
            f"could not capture patch for repo-task case {case.id!r} "
            f"at {artifact_path}; workspace retained at {prepared.path}; "
            f"baseline: {prepared.baseline_path}; source: {prepared.source_fixture.path}; {exc}"
        ) from exc
    return patch_record(artifact_path, output_dir)


def patch_record(artifact_path: Path, output_dir: Path) -> dict[str, str]:
    """Return the run.jsonl patch object for a repo-task patch artifact."""

    try:
        relative_path = artifact_path.resolve().relative_to(Path(output_dir).resolve())
    except (OSError, ValueError) as exc:
        raise PatchError(
            f"patch path {artifact_path} is not under run output directory "
            f"{output_dir}"
        ) from exc
    return {"path": relative_path.as_posix()}


def directory_diff(source: Path, workspace: Path) -> str:
    """Return a deterministic unified diff for two directory snapshots."""

    source_entries = _snapshot(source)
    workspace_entries = _snapshot(workspace)
    chunks: list[str] = []
    budget = _Budget()

    for relative_path in sorted(source_entries.keys() | workspace_entries.keys()):
        old = source_entries.get(relative_path)
        new = workspace_entries.get(relative_path)
        if old is None:
            diff = _added_diff(relative_path, new, budget)
        elif new is None:
            diff = _deleted_diff(relative_path, old, budget)
        elif old.kind != new.kind:
            diff = _deleted_diff(relative_path, old, budget) + _added_diff(relative_path, new, budget)
        else:
            diff = _changed_diff(relative_path, old, new, budget)
        if diff and not diff.startswith(("diff --git ", "Binary ")):
            diff = f"diff --git a/{relative_path} b/{relative_path}\n" + diff
        budget.output_bytes += len(diff.encode("utf-8"))
        if budget.output_bytes > MAX_PATCH_OUTPUT_BYTES:
            raise PatchError("patch output byte budget exceeded")
        chunks.append(diff)

    return "".join(chunk for chunk in chunks if chunk)


def _snapshot(root: Path) -> dict[str, _Entry]:
    root = Path(root)
    entries: dict[str, _Entry] = {}

    directories = [root]
    seen = 0
    while directories:
        directory = directories.pop()
        with os.scandir(directory) as children:
            for candidate in children:
                child = Path(candidate.path)
                seen += 1
                if seen > MAX_PATCH_ENTRIES:
                    raise PatchError("patch tree entry budget exceeded")
                relative_path = child.relative_to(root).as_posix()
                if child.is_symlink():
                    entries[relative_path] = _Entry(kind="symlink", path=child, mode=0o120000)
                elif child.is_dir():
                    directories.append(child)
                elif child.is_file():
                    entries[relative_path] = _Entry(kind="file", path=child, mode=0o100755 if child.stat().st_mode & 0o100 else 0o100644)

    return entries


def _added_diff(relative_path: str, entry: _Entry | None, budget: _Budget) -> str:
    if entry is None:
        return ""
    if entry.kind == "symlink":
        return _file_header(relative_path, entry, "new", "") + _text_diff(
            [],
            _text_lines(budget.readlink(entry.path)),
            budget=budget,
            old_label="/dev/null",
            new_label=f"b/{relative_path}",
        )
    text = _decode_bytes(budget.read(entry.path))
    if text is None:
        return f"Binary file added: {relative_path}\n"
    header = _file_header(relative_path, entry, "new", text)
    return header + _text_diff(
        [],
        _text_lines(text),
        budget=budget,
        old_label="/dev/null",
        new_label=f"b/{relative_path}",
        emit_empty_header=True,
    )


def _deleted_diff(relative_path: str, entry: _Entry, budget: _Budget) -> str:
    if entry.kind == "symlink":
        return _file_header(relative_path, entry, "deleted", "") + _text_diff(
            _text_lines(budget.readlink(entry.path)),
            [],
            budget=budget,
            old_label=f"a/{relative_path}",
            new_label="/dev/null",
        )
    text = _decode_bytes(budget.read(entry.path))
    if text is None:
        return f"Binary file deleted: {relative_path}\n"
    header = _file_header(relative_path, entry, "deleted", text)
    return header + _text_diff(
        _text_lines(text),
        [],
        budget=budget,
        old_label=f"a/{relative_path}",
        new_label="/dev/null",
        emit_empty_header=True,
    )


def _file_header(relative_path: str, entry: _Entry, operation: str, text: str) -> str:
    return (f"diff --git a/{relative_path} b/{relative_path}\n"
            f"{operation} file mode {entry.mode:o}\n")


def _changed_diff(relative_path: str, old: _Entry, new: _Entry, budget: _Budget) -> str:
    if old.kind == "symlink":
        old_target = budget.readlink(old.path)
        new_target = budget.readlink(new.path)
        if old_target == new_target:
            return ""
        return (f"diff --git a/{relative_path} b/{relative_path}\n"
                "old mode 120000\nnew mode 120000\n") + _text_diff(
            _text_lines(old_target),
            _text_lines(new_target),
            budget=budget,
            old_label=f"a/{relative_path}",
            new_label=f"b/{relative_path}",
        )

    old_bytes = budget.read(old.path)
    new_bytes = budget.read(new.path)
    mode_diff = ""
    if old.mode != new.mode:
        mode_diff = (f"diff --git a/{relative_path} b/{relative_path}\n"
                     f"old mode {old.mode:o}\nnew mode {new.mode:o}\n")
    if old_bytes == new_bytes:
        return mode_diff

    old_text = _decode_bytes(old_bytes)
    new_text = _decode_bytes(new_bytes)
    if old_text is None or new_text is None:
        return mode_diff + f"Binary files differ: {relative_path}\n"
    return mode_diff + _text_diff(
        _text_lines(old_text),
        _text_lines(new_text),
        budget=budget,
        old_label=f"a/{relative_path}",
        new_label=f"b/{relative_path}",
    )


def _text_diff(
    old_lines: list[str],
    new_lines: list[str],
    *,
    budget: _Budget,
    old_label: str,
    new_label: str,
    emit_empty_header: bool = False,
) -> str:
    budget.consume_work(old_lines, new_lines)
    pieces: list[str] = []
    size = 0
    for line in difflib.unified_diff(old_lines, new_lines, fromfile=old_label,
                                     tofile=new_label, lineterm="\n"):
        if not line.endswith("\n"):
            line += "\n\\ No newline at end of file\n"
        size += len(line.encode("utf-8"))
        if size + budget.output_bytes > MAX_PATCH_OUTPUT_BYTES:
            raise PatchError("patch output byte budget exceeded")
        pieces.append(line)
    if not pieces and emit_empty_header:
        return f"--- {old_label}\n+++ {new_label}\n"
    return "".join(pieces)


def _decode_bytes(raw: bytes) -> str | None:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return text


def _text_lines(text: str) -> list[str]:
    # Git patch lines are delimited by LF only; CR remains content.
    count = text.count("\n") + int(bool(text) and not text.endswith("\n"))
    if count > MAX_PATCH_LINES:
        raise PatchError("patch line budget exceeded")
    lines = text.split("\n")
    return [line + "\n" for line in lines[:-1]] + ([lines[-1]] if lines[-1] else [])
