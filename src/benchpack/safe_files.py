"""Descriptor-bound access to files contained in a result directory.

Path checks followed by a separate ``open`` race with concurrent replacement of
the file or of one of its ancestors. These helpers walk the relative path one
component at a time from a directory descriptor, refuse symlinks at every step
(``O_NOFOLLOW``), and hand out a descriptor that has been verified to be a
regular file. Everything derived from the file (size, contents, digest) is then
read from that one descriptor.
"""

from __future__ import annotations

import os
import stat
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

_DIR_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
_FILE_FLAGS = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
_CHUNK_BYTES = 1024 * 1024


@dataclass(frozen=True)
class FileSnapshot:
    """Bytes read from one verified regular-file descriptor.

    ``size`` is the descriptor's ``st_size`` when the file was opened.
    ``data`` is ``None`` when the file is larger than the requested limit; the
    caller must then treat the contents as unknown.
    """

    size: int
    data: bytes | None


def contained_parts(relative_path: str) -> tuple[str, ...] | None:
    """Return the components of a safe relative path, or ``None``."""

    if not relative_path or "\x00" in relative_path or "\\" in relative_path:
        return None
    pure = PurePosixPath(relative_path)
    if pure.is_absolute() or Path(relative_path).is_absolute():
        return None
    parts = tuple(relative_path.split("/"))
    if any(part in ("", ".", "..") for part in parts):
        return None
    return parts


def open_contained_regular(root: Path, relative_path: str) -> int | None:
    """Open ``root/relative_path`` as a regular file without following links.

    Returns an open read-only descriptor, or ``None`` when the path is unsafe,
    missing, traverses a symlink, or does not name a regular file. The root
    directory itself may be reached through a symlink; nothing below it may.
    """

    parts = contained_parts(relative_path)
    if parts is None:
        return None
    try:
        current = os.open(root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    except OSError:
        return None
    try:
        for part in parts[:-1]:
            try:
                child = os.open(part, _DIR_FLAGS, dir_fd=current)
            except OSError:
                return None
            os.close(current)
            current = child
        try:
            fd = os.open(parts[-1], _FILE_FLAGS, dir_fd=current)
        except OSError:
            return None
    finally:
        os.close(current)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            os.close(fd)
            return None
        os.set_blocking(fd, True)
    except OSError:
        os.close(fd)
        return None
    return fd


def read_contained_regular(
    root: Path,
    relative_path: str,
    limit: int,
) -> FileSnapshot | None:
    """Read a contained regular file through one descriptor, up to ``limit``."""

    fd = open_contained_regular(root, relative_path)
    if fd is None:
        return None
    try:
        size = os.fstat(fd).st_size
        chunks: list[bytes] = []
        total = 0
        while total <= limit:
            chunk = os.read(fd, min(_CHUNK_BYTES, limit + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
    except OSError:
        return None
    finally:
        os.close(fd)
    if total > limit:
        return FileSnapshot(size=max(size, total), data=None)
    return FileSnapshot(size=total, data=b"".join(chunks))


def copy_contained_regular(
    root: Path,
    relative_path: str,
    destination: Path,
    limit: int,
) -> int | None:
    """Copy a contained regular file into a new ``destination`` file.

    The source is opened once through :func:`open_contained_regular` and copied
    from that descriptor. Returns the number of bytes copied, ``None`` when the
    source is unsafe or unavailable. Raises ``ValueError`` when the source grows
    beyond ``limit`` bytes; the partial destination is removed.
    """

    fd = open_contained_regular(root, relative_path)
    if fd is None:
        return None
    total = 0
    try:
        with open(destination, "xb") as out:
            try:
                while True:
                    chunk = os.read(fd, _CHUNK_BYTES)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > limit:
                        raise ValueError(
                            f"source file exceeds {limit} bytes: {relative_path}"
                        )
                    out.write(chunk)
            except BaseException:
                out.close()
                destination.unlink(missing_ok=True)
                raise
    finally:
        os.close(fd)
    return total


# Mutations use the same no-follow directory walk as reads. Keep every ancestor
# open so an exchanged directory can be detected before returning to the caller.
@contextmanager
def admitted_directory(path: Path, *, create: bool = False):
    """Yield a directory fd; reject links and detect exchanged ancestors."""
    absolute = Path(os.path.abspath(path))
    fds = [os.open(absolute.anchor, _DIR_FLAGS)]
    edges = []
    try:
        for part in absolute.parts[1:]:
            parent = fds[-1]
            if create:
                try:
                    os.mkdir(part, dir_fd=parent)
                except FileExistsError:
                    pass
            child = os.open(part, _DIR_FLAGS, dir_fd=parent)
            fds.append(child)
            edges.append((parent, part, child))
        yield fds[-1]
        for parent, part, child in edges:
            current = os.stat(part, dir_fd=parent, follow_symlinks=False)
            opened = os.fstat(child)
            if (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino):
                raise OSError('admitted directory was exchanged')
    finally:
        for fd in reversed(fds):
            os.close(fd)


def atomic_write_at(directory: int, name: str, data: bytes) -> None:
    """Publish a complete regular file relative to an admitted directory fd.

    Existing regular-file permissions survive replacement. Links and special
    destinations are refused; the owned temporary is removed on every failure.
    """
    if contained_parts(name) != (name,):
        raise ValueError('expected one filename')
    try:
        previous = os.stat(name, dir_fd=directory, follow_symlinks=False)
    except FileNotFoundError:
        previous = None
    if previous is not None and not stat.S_ISREG(previous.st_mode):
        raise OSError('destination must be a regular file')
    temporary = f'.benchpack-{uuid.uuid4().hex}.tmp'
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                 0o600, dir_fd=directory)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            if previous is not None:
                os.fchmod(stream.fileno(), stat.S_IMODE(previous.st_mode))
            os.fsync(stream.fileno())
        os.replace(temporary, name, src_dir_fd=directory, dst_dir_fd=directory)
    finally:
        try:
            os.unlink(temporary, dir_fd=directory)
        except FileNotFoundError:
            pass
