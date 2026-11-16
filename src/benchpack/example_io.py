"""Small file-publication helpers for the shipped external-agent examples.

Held no-follow parents and atomic replacement avoid following substituted links.
Generation checks detect concurrent writers; these examples are not an isolation
boundary against a malicious process with the same user identity.
"""
from __future__ import annotations

import os
import stat
import uuid
from contextlib import ExitStack
from pathlib import Path

from benchpack.safe_files import contained_parts, read_opened_regular

EXAMPLE_FILE_BYTES = 16 * 1024 * 1024
_DIR = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
_READ = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK


def _generation(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


class _Target:
    def __init__(self, stack, root, relative, *, missing=False):
        parts = contained_parts(relative)
        if parts is None:
            raise ValueError('unsafe workspace path')
        absolute = Path(os.path.abspath(root))
        fd = os.open(absolute.parent, _DIR)
        stack.callback(os.close, fd)
        self.edges = []
        for part in (absolute.name, *parts[:-1]):
            child = os.open(part, _DIR, dir_fd=fd)
            stack.callback(os.close, child)
            self.edges.append((fd, part, child))
            fd = child
        self.parent, self.name = fd, parts[-1]
        try:
            source = os.open(self.name, _READ, dir_fd=fd)
        except FileNotFoundError:
            if not missing:
                raise
            self.info, self.original = None, None
        else:
            stack.callback(os.close, source)
            self.info = os.fstat(source)
            if not stat.S_ISREG(self.info.st_mode) or self.info.st_nlink != 1:
                raise OSError('edit target must be an unlinked regular file (one link)')
            snapshot = read_opened_regular(source, EXAMPLE_FILE_BYTES)
            if snapshot.data is None:
                raise ValueError('example file exceeds byte limit')
            self.original = snapshot.data
        self.published = None

    def check(self, expected):
        for parent, name, child in self.edges:
            current = os.stat(name, dir_fd=parent, follow_symlinks=False)
            held = os.fstat(child)
            if (current.st_dev, current.st_ino) != (held.st_dev, held.st_ino):
                raise OSError('workspace directory changed')
        try:
            current = os.stat(self.name, dir_fd=self.parent, follow_symlinks=False)
        except FileNotFoundError:
            current = None
        if ((current is None) != (expected is None)
                or current is not None and _generation(current) != _generation(expected)):
            raise OSError('workspace target changed')

    def stage(self, data, stack):
        name = f'.benchpack-example-{uuid.uuid4().hex}.tmp'
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=self.parent)
        def discard():
            try:
                os.unlink(name, dir_fd=self.parent)
            except FileNotFoundError:
                pass
        stack.callback(discard)
        with os.fdopen(fd, 'wb') as stream:
            if stream.write(data) != len(data):
                raise OSError('short example stage write')
            stream.flush()
            if self.info is not None:
                os.fchmod(stream.fileno(), stat.S_IMODE(self.info.st_mode))
            os.fsync(stream.fileno())
        return name


def replace_workspace_files(root: Path, replacements: list[tuple[str, bytes]], *, missing=False):
    """Stage every byte before publication; roll back only owned generations."""
    with ExitStack() as stack:
        entries = []
        for relative, data in replacements:
            target = _Target(stack, root, relative, missing=missing)
            stage = target.stage(data, stack)
            backup = target.stage(target.original, stack) if target.original is not None else None
            entries.append((target, stage, backup))
        try:
            for target, stage, _ in entries:
                target.check(target.info)
                # Remember the stage identity before rename (ctime changes on rename).
                os.replace(stage, target.name, src_dir_fd=target.parent, dst_dir_fd=target.parent)
                target.published = os.stat(target.name, dir_fd=target.parent, follow_symlinks=False)
            for target, _, _ in entries:
                target.check(target.published)
        except BaseException as exc:
            failed = False
            for target, _, backup in reversed(entries):
                if target.published is None:
                    continue
                try:
                    target.check(target.published)
                    if backup is None:
                        os.unlink(target.name, dir_fd=target.parent)
                    else:
                        os.replace(backup, target.name, src_dir_fd=target.parent, dst_dir_fd=target.parent)
                except OSError:
                    failed = True
            if failed:
                raise ValueError('edit publication failed; rollback failed; inspect workspace') from exc
            raise ValueError('could not apply assistant edit payload') from exc
