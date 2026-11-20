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
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

_DIR_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
_FILE_FLAGS = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
_CHUNK_BYTES = 1024 * 1024


class UnstableFileError(OSError):
    """An opened evidence file changed while its bytes were being admitted."""


class PublishedDurabilityError(OSError):
    """Complete new bytes are visible, but directory sync did not confirm durability."""

    def __init__(self, name: str) -> None:
        self.published_name = name
        super().__init__(f"artifact {name!r} published; directory durability uncertain; "
                         "retain visible evidence and retry on the same directory")


def require_stable_file(fd: int, initial: os.stat_result) -> None:
    """Fence content reads, allowing an unlink-only atomic path replacement.

    Unlinking the opened inode changes ctime/link count without changing its
    contents. Size and mtime must still match in that case. This is a metadata
    fence for accidental concurrent writers, not same-user filesystem isolation.
    """
    final = os.fstat(fd)
    fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns")
    if (any(getattr(initial, key) != getattr(final, key) for key in fields)
            or (initial.st_ctime_ns != final.st_ctime_ns
                and final.st_nlink >= initial.st_nlink)):
        raise UnstableFileError("opened result file changed during read")


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


@contextmanager
def open_result_directory(path: Path) -> Iterator[int]:
    """Hold the resolved directory descriptor, allowing directory aliases."""
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        yield fd
    finally:
        os.close(fd)


def open_regular_at(directory: int, name: str) -> int | None:
    """Open one no-follow regular file relative to an admitted directory.

    A special file returns None. Open and inspection errors propagate.
    """
    if contained_parts(name) != (name,):
        raise ValueError("expected a single filename")
    fd = os.open(name, _FILE_FLAGS, dir_fd=directory)
    try:
        if stat.S_ISREG(os.fstat(fd).st_mode):
            os.set_blocking(fd, True)
            return fd
    except BaseException:
        os.close(fd)
        raise
    os.close(fd)
    return None


def open_contained_regular(root: Path | int, relative_path: str) -> int | None:
    """Open ``root/relative_path`` as a regular file without following links.

    Returns an open read-only descriptor, or ``None`` when the path is unsafe,
    missing, traverses a symlink, or does not name a regular file. The root
    directory itself may be reached through a symlink; nothing below it may.
    An integer root is an already admitted directory descriptor, duplicated here.
    """

    parts = contained_parts(relative_path)
    if parts is None:
        return None
    try:
        current = (os.dup(root) if isinstance(root, int) else
                   os.open(root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)))
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
            return open_regular_at(current, parts[-1])
        except OSError:
            return None
    finally:
        os.close(current)


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
        return read_opened_regular(fd, limit)
    except UnstableFileError:
        raise
    except OSError:
        return None
    finally:
        os.close(fd)


def read_opened_regular(fd: int, limit: int) -> FileSnapshot:
    """Read an admitted regular descriptor, leaving its lifetime to the caller."""
    initial = os.fstat(fd)
    if initial.st_size > limit:
        return FileSnapshot(size=initial.st_size, data=None)
    chunks: list[bytes] = []
    total = 0
    while total <= limit:
        chunk = os.read(fd, min(_CHUNK_BYTES, limit + 1 - total))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
    if total > limit:
        return FileSnapshot(size=max(initial.st_size, total), data=None)
    require_stable_file(fd, initial)
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
        initial = os.fstat(fd)
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
                require_stable_file(fd, initial)
            except BaseException:
                out.close()
                destination.unlink(missing_ok=True)
                raise
    finally:
        os.close(fd)
    return total


# Mutations use the same no-follow directory walk as reads. Keep every ancestor
# open so an exchanged directory can be detected before returning to the caller.
def trusted_root(path: Path) -> Path:
    """Absolute ``path`` with its ancestors resolved but ``path`` itself kept.

    Ancestors such as macOS ``/tmp`` -> ``/private/tmp`` or a symlinked home are
    trusted; the final component stays literal so a symlinked root is still
    refused by a no-follow walk from its parent.
    """
    absolute = Path(os.path.abspath(path))
    if absolute == Path(absolute.anchor):
        return absolute
    return Path(os.path.realpath(absolute.parent)) / absolute.name


@contextmanager
def admitted_directory(path: Path, *, base: Path | None = None, create: bool = False):
    """Yield a directory fd; reject links below ``base`` and detect exchanges.

    ``base`` (default: the parent of ``path``) is trusted and opened normally,
    so links among its ancestors are followed. Every component of ``path``
    below it is opened with ``O_NOFOLLOW`` (and created when ``create``).
    """
    absolute = Path(os.path.abspath(path))
    trusted = Path(os.path.abspath(base)) if base is not None else absolute.parent
    try:
        relative = absolute.relative_to(trusted)
    except ValueError:
        raise OSError('admitted directory escapes its trusted base') from None
    if any(part in {'', '.', '..'} for part in relative.parts):
        raise OSError('admitted directory escapes its trusted base')
    if create:
        os.makedirs(trusted, exist_ok=True)
    fds = [os.open(trusted, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))]
    edges = []
    try:
        for part in relative.parts:
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

    Existing regular-file permissions survive replacement; new files follow the
    process umask. Links and special
    destinations are refused. Pre-replace failures remove only the owned
    temporary. Post-replace sync failure retains the complete visible file and
    raises PublishedDurabilityError; it must never trigger rollback.
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
    # 0o666 lets the kernel apply the process umask, as a plain open() would.
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                 0o666, dir_fd=directory)
    try:
        with os.fdopen(fd, 'wb') as stream:
            if stream.write(data) != len(data):
                raise OSError('short file write')
            stream.flush()
            if previous is not None:
                os.fchmod(stream.fileno(), stat.S_IMODE(previous.st_mode))

            os.fsync(stream.fileno())
        os.replace(temporary, name, src_dir_fd=directory, dst_dir_fd=directory)
    except BaseException:
        try:
            os.unlink(temporary, dir_fd=directory)
        except FileNotFoundError:
            pass
        raise

    try:
        os.fsync(directory)
    except OSError as exc:
        raise PublishedDurabilityError(name) from exc
