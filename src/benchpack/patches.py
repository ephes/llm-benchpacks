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
    """Write the source-vs-workspace patch artifact and return its record."""

    artifact_path = patch_path(output_dir, case, repetition)
    try:
        diff = directory_diff(prepared.source_fixture.path, prepared.path)
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_bytes(diff.encode("utf-8"))
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
            diff = _added_diff(relative_path, new)
        elif new is None:
            diff = _deleted_diff(relative_path, old)
        elif old.kind != new.kind:
            diff = _deleted_diff(relative_path, old) + _added_diff(relative_path, new)
        else:
            diff = _changed_diff(relative_path, old, new)
        if diff and not diff.startswith(("diff --git ", "Binary ")):
            diff = f"diff --git a/{relative_path} b/{relative_path}\n" + diff
        chunks.append(diff)

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
                entries[relative_path] = _Entry(kind="file", path=child, mode=0o100755 if child.stat().st_mode & 0o100 else 0o100644)

    walk(root)
    return entries


def _added_diff(relative_path: str, entry: _Entry | None) -> str:
    if entry is None:
        return ""
    if entry.kind == "symlink":
        return _text_diff(
            [],
            [_readlink_text(entry.path) + "\n"],
            old_label="/dev/null",
            new_label=f"b/{relative_path}",
        )
    text = _decode_text(entry.path)
    if text is None:
        return f"Binary file added: {relative_path}\n"
    header = _file_header(relative_path, entry, "new", text)
    return header + _text_diff(
        [],
        _text_lines(text),
        old_label="/dev/null",
        new_label=f"b/{relative_path}",
        emit_empty_header=True,
    )


def _deleted_diff(relative_path: str, entry: _Entry) -> str:
    if entry.kind == "symlink":
        return _text_diff(
            [_readlink_text(entry.path) + "\n"],
            [],
            old_label=f"a/{relative_path}",
            new_label="/dev/null",
        )
    text = _decode_text(entry.path)
    if text is None:
        return f"Binary file deleted: {relative_path}\n"
    header = _file_header(relative_path, entry, "deleted", text)
    return header + _text_diff(
        _text_lines(text),
        [],
        old_label=f"a/{relative_path}",
        new_label="/dev/null",
        emit_empty_header=True,
    )


def _file_header(relative_path: str, entry: _Entry, operation: str, text: str) -> str:
    return (f"diff --git a/{relative_path} b/{relative_path}\n"
            f"{operation} file mode {entry.mode:o}\n")


def _changed_diff(relative_path: str, old: _Entry, new: _Entry) -> str:
    if old.kind == "symlink":
        old_target = _readlink_text(old.path)
        new_target = _readlink_text(new.path)
        if old_target == new_target:
            return ""
        return _text_diff(
            [old_target + "\n"],
            [new_target + "\n"],
            old_label=f"a/{relative_path}",
            new_label=f"b/{relative_path}",
        )

    old_bytes = old.path.read_bytes()
    new_bytes = new.path.read_bytes()
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
            lineterm="\n",
        )
    )
    if not diff_lines and emit_empty_header:
        diff_lines = [f"--- {old_label}\n", f"+++ {new_label}\n"]
    if not diff_lines:
        return ""
    return "".join(
        line if line.endswith("\n") else line + "\n\\ No newline at end of file\n"
        for line in diff_lines
    )


def _decode_text(path: Path) -> str | None:
    return _decode_bytes(path.read_bytes())


def _decode_bytes(raw: bytes) -> str | None:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return text


def _text_lines(text: str) -> list[str]:
    # Git patch lines are delimited by LF only; CR remains content.
    lines = text.split("\n")
    return [line + "\n" for line in lines[:-1]] + ([lines[-1]] if lines[-1] else [])


def _readlink_text(path: Path) -> str:
    return path.readlink().as_posix()
