"""Filesystem containment checks for generated output and protected inputs."""

from __future__ import annotations

import fcntl
import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


def paths_overlap(output: Path, source: Path) -> bool:
    """Check containment, including existing case, symlink, and hardlink aliases."""
    output = output.resolve()
    source = source.resolve()
    if source.is_relative_to(output) or output.is_relative_to(source):
        return True
    for path, ancestors in (
        (output, (source, *source.parents)),
        (source, (output, *output.parents)),
    ):
        for ancestor in ancestors:
            try:
                if path.samefile(ancestor):
                    return True
            except (FileNotFoundError, NotADirectoryError):
                continue
    return False


class PublicationBusyError(RuntimeError):
    """Raised when another process holds the publication lock for an output."""


def publication_lock_path(output: Path) -> Path:
    """Return the lock file guarding publication of ``output``.

    The lock is keyed by the canonical output location (resolved parent plus
    final name) and lives next to it as ``.<name>.benchpack-publish.lock``. The
    parent directory is created when missing. The lock file is never removed:
    deleting it would let two publishers lock different inodes.
    """

    absolute = Path(os.path.abspath(output))
    if absolute.name in ("", ".", ".."):
        absolute = absolute.resolve()
    absolute.parent.mkdir(parents=True, exist_ok=True)
    parent = absolute.parent.resolve()
    return parent / f".{absolute.name}.benchpack-publish.lock"


@contextmanager
def publication_lock(output: Path) -> Iterator[Path]:
    """Hold a nonblocking exclusive OS lock for publishing ``output``.

    Preflight, staging swap, rollback and backup cleanup of one output run
    under this lock, so concurrent ``--force`` publishers cannot rename or
    delete each other's generations. A second publisher fails immediately with
    :class:`PublicationBusyError` instead of waiting. The kernel drops the lock
    when the holder exits, including when it is killed.
    """

    lock_path = publication_lock_path(output)
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    fd = os.open(lock_path, flags, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise PublicationBusyError(f"publication lock is not a regular file: {lock_path}")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise PublicationBusyError(
                f"output {output} is being published by another process "
                f"(lock {lock_path}); retry when it finishes"
            ) from exc
        try:
            yield lock_path
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)
