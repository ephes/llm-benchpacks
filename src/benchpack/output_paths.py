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
    flags = os.O_RDWR | os.O_CREAT | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    fd = os.open(lock_path, flags, 0o600)
    locked = False
    primary = None
    try:
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
            raise PublicationBusyError(f"publication lock must be a single-link regular file: {lock_path}")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise PublicationBusyError(
                f"output {output} is being published by another process "
                f"(lock {lock_path}); retry when it finishes"
            ) from exc
        locked = True
        held = os.fstat(fd)
        named = lock_path.lstat()
        if (held.st_nlink != 1 or not stat.S_ISREG(named.st_mode)
                or named.st_nlink != 1
                or (held.st_dev, held.st_ino) != (named.st_dev, named.st_ino)):
            raise PublicationBusyError(f"publication lock was exchanged: {lock_path}")
        yield lock_path
    except BaseException as exc:
        primary = exc
        raise
    finally:
        failures = []
        if locked:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except BaseException as exc:
                failures.append(("publication lock unlock failed", exc))
        try:
            os.close(fd)
        except BaseException as exc:
            failures.append(("publication lock close failed", exc))
        if failures:
            if primary is not None:
                for category, _ in failures:
                    primary.add_note(category)
            else:
                category, cause = failures[0]
                if not isinstance(cause, Exception):
                    cause.add_note(category)
                    for category, _ in failures[1:]:
                        cause.add_note(category)
                    raise cause
                error = OSError(category)
                for category, _ in failures[1:]:
                    error.add_note(category)
                raise error from failures[0][1]
