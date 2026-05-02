"""Deterministic patch artifacts for repo-task workspaces."""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from pathlib import Path

from .packs import Case
from .workspaces import PreparedWorkspace


class PatchError(ValueError):
    """Raised when a repo-task patch artifact cannot be captured."""


@dataclass(frozen=True)
class _Entry:
    kind: str
    path: Path


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
    """Write the source-vs-workspace patch artifact and return its record."""

    artifact_path = patch_path(output_dir, case, repetition)
    try:
        diff = directory_diff(prepared.source_fixture.path, prepared.path)
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(diff, encoding="utf-8")
    except OSError as exc:
        raise PatchError(
            f"could not capture patch for repo-task case {case.id!r} "
            f"at {artifact_path}"
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

    for relative_path in sorted(source_entries.keys() | workspace_entries.keys()):
        old = source_entries.get(relative_path)
        new = workspace_entries.get(relative_path)
        if old is None:
            chunks.append(_added_diff(relative_path, new))
            continue
        if new is None:
            chunks.append(_deleted_diff(relative_path, old))
            continue
        if old.kind != new.kind:
            chunks.append(_deleted_diff(relative_path, old))
            chunks.append(_added_diff(relative_path, new))
            continue
        chunks.append(_changed_diff(relative_path, old, new))

    return "".join(chunk for chunk in chunks if chunk)


def _snapshot(root: Path) -> dict[str, _Entry]:
    root = Path(root)
    entries: dict[str, _Entry] = {}

    def walk(directory: Path) -> None:
        for child in directory.iterdir():
            relative_path = child.relative_to(root).as_posix()
            if child.is_symlink():
                entries[relative_path] = _Entry(kind="symlink", path=child)
            elif child.is_dir():
                walk(child)
            elif child.is_file():
                entries[relative_path] = _Entry(kind="file", path=child)

    walk(root)
    return entries


def _added_diff(relative_path: str, entry: _Entry | None) -> str:
    if entry is None:
        return ""
    if entry.kind == "symlink":
        return _text_diff(
            [],
            [_readlink_text(entry.path)],
            old_label="/dev/null",
            new_label=f"b/{relative_path}",
        )
    text = _decode_text(entry.path)
    if text is None:
        return f"Binary file added: {relative_path}\n"
    return _text_diff(
        [],
        _text_lines(text),
        old_label="/dev/null",
        new_label=f"b/{relative_path}",
        emit_empty_header=True,
    )


def _deleted_diff(relative_path: str, entry: _Entry) -> str:
    if entry.kind == "symlink":
        return _text_diff(
            [_readlink_text(entry.path)],
            [],
            old_label=f"a/{relative_path}",
            new_label="/dev/null",
        )
    text = _decode_text(entry.path)
    if text is None:
        return f"Binary file deleted: {relative_path}\n"
    return _text_diff(
        _text_lines(text),
        [],
        old_label=f"a/{relative_path}",
        new_label="/dev/null",
        emit_empty_header=True,
    )


def _changed_diff(relative_path: str, old: _Entry, new: _Entry) -> str:
    if old.kind == "symlink":
        old_target = _readlink_text(old.path)
        new_target = _readlink_text(new.path)
        if old_target == new_target:
            return ""
        return _text_diff(
            [old_target],
            [new_target],
            old_label=f"a/{relative_path}",
            new_label=f"b/{relative_path}",
        )

    old_bytes = old.path.read_bytes()
    new_bytes = new.path.read_bytes()
    if old_bytes == new_bytes:
        return ""

    old_text = _decode_bytes(old_bytes)
    new_text = _decode_bytes(new_bytes)
    if old_text is None or new_text is None:
        return f"Binary files differ: {relative_path}\n"
    return _text_diff(
        _text_lines(old_text),
        _text_lines(new_text),
        old_label=f"a/{relative_path}",
        new_label=f"b/{relative_path}",
    )


def _text_diff(
    old_lines: list[str],
    new_lines: list[str],
    *,
    old_label: str,
    new_label: str,
    emit_empty_header: bool = False,
) -> str:
    diff_lines = list(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=old_label,
            tofile=new_label,
            lineterm="",
        )
    )
    if not diff_lines and emit_empty_header:
        diff_lines = [f"--- {old_label}", f"+++ {new_label}"]
    if not diff_lines:
        return ""
    return "\n".join(diff_lines) + "\n"


def _decode_text(path: Path) -> str | None:
    return _decode_bytes(path.read_bytes())


def _decode_bytes(raw: bytes) -> str | None:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _text_lines(text: str) -> list[str]:
    return text.splitlines()


def _readlink_text(path: Path) -> str:
    return path.readlink().as_posix()
