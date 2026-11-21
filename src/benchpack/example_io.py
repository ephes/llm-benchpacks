"""Small file-publication helpers for the shipped external-agent examples.

Held no-follow parents and atomic replacement avoid following substituted links.
Generation checks detect concurrent writers; these examples are not an isolation
boundary against a malicious process with the same user identity.
"""
from __future__ import annotations

import json
import os
import stat
import sys
import uuid
from contextlib import ExitStack, contextmanager, suppress
from pathlib import Path

from benchpack.safe_files import admitted_directory, contained_parts, read_opened_regular

EXAMPLE_FILE_BYTES = 16 * 1024 * 1024
_DIR = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
_READ = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK


def _generation(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _cleanup_callback(stack, callback, *args, note):
    """Attempt owned cleanup without replacing the active publication verdict.

    The verdict is the exception unwinding this ExitStack, never an unrelated
    exception a caller happens to be handling around the helper.
    """
    def cleanup(exc_type, primary, traceback):
        try:
            callback(*args)
        except OSError:
            if primary is not None:
                if note in getattr(primary, '__notes__', ()):
                    return False
                primary.add_note(note)
            # Example callers print only str(exc), so residue is also reported
            # on stderr. Cleanup residue is separate from the edit verdict.
            # Fixed text keeps file contents and OS error payloads private.
            try:
                print(f'example cleanup warning: {note}', file=sys.stderr)
            except (OSError, ValueError):
                pass
        return False
    stack.push(cleanup)


def _close_callback(stack, fd):
    _cleanup_callback(stack, os.close, fd,
                      note='example descriptor close failed; publication verdict unchanged')


class _Target:
    def __init__(self, stack, root, relative, *, missing=False):
        parts = contained_parts(relative)
        if parts is None:
            raise ValueError('unsafe workspace path')
        absolute = Path(os.path.abspath(root))
        fd = os.open(absolute.parent, _DIR)
        _close_callback(stack, fd)
        self.edges = []
        for part in (absolute.name, *parts[:-1]):
            child = os.open(part, _DIR, dir_fd=fd)
            _close_callback(stack, child)
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
            _close_callback(stack, source)
            self.info = os.fstat(source)
            if not stat.S_ISREG(self.info.st_mode) or self.info.st_nlink != 1:
                raise OSError('example target must be a regular file with one link')
            snapshot = read_opened_regular(source, EXAMPLE_FILE_BYTES)
            if snapshot.data is None:
                raise ValueError('example file exceeds byte limit')
            self.original = snapshot.data
        self.published = None
        self.staged_fds = {}
        self.retained = set()

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

    def stage(self, data, stack, *, private=False):
        name = f'.benchpack-example-{uuid.uuid4().hex}.tmp'
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=self.parent)
        def discard():
            if name in self.retained:
                return
            try:
                os.unlink(name, dir_fd=self.parent)
            except FileNotFoundError:
                pass
        _cleanup_callback(stack, discard,
                          note='example temporary cleanup failed; .benchpack-example-*.tmp residue may remain; publication verdict unchanged')
        with ExitStack() as writing:
            _close_callback(writing, fd)
            stream = os.fdopen(fd, 'wb', closefd=False)
            _cleanup_callback(writing, stream.close,
                              note='example descriptor close failed; publication verdict unchanged')
            if stream.write(data) != len(data):
                raise OSError('short example stage write')
            stream.flush()
            if self.info is not None and not private:
                os.fchmod(stream.fileno(), stat.S_IMODE(self.info.st_mode))
            os.fsync(stream.fileno())
            held = os.dup(stream.fileno())
            self.staged_fds[name] = held
            _close_callback(stack, held)
        return name


def replace_workspace_files(root: Path, replacements: list[tuple[str, bytes]], *, missing=False):
    """Stage workspace bytes before publication; roll back only owned generations."""
    replace_example_files([(root, relative, data) for relative, data in replacements], missing=missing)


def _sync_parents(targets):
    """Acknowledge each held directory once, attempting all after an I/O error."""
    seen = set()
    failure = None
    for target in targets:
        try:
            info = os.fstat(target.parent)
        except OSError as exc:
            # Still attempt the acknowledgement, but never report it as certain.
            if failure is None:
                failure = exc
            identity = ('fd', target.parent)
        else:
            identity = (info.st_dev, info.st_ino)
        if identity in seen:
            continue
        seen.add(identity)
        try:
            os.fsync(target.parent)
        except OSError as exc:
            if failure is None:
                failure = exc
    return failure


def replace_example_files(replacements: list[tuple[Path, str, bytes]], *, missing=False):
    """Publish an admitted set across example roots with owned rollback.

    Existing targets must be single-link regular files; missing leaves are
    opt-in. New files use mode 0600 and existing permissions are preserved.
    Sync distinct held parents after publication and compensation. A publication
    sync failure retains complete visible edits with explicitly uncertain durability.
    This is compensation for reported errors, not a crash-atomic transaction.
    """
    with ExitStack() as stack:
        entries = []
        try:
            for root, relative, data in replacements:
                target = _Target(stack, root, relative, missing=missing)
                stage = target.stage(data, stack)
                backup = target.stage(target.original, stack) if target.original is not None else None
                entries.append((target, stage, backup))
        except OSError as exc:
            # Nothing is published yet; admission/staging failures are edit
            # failures, not transport failures of the external agent.
            raise ValueError('could not stage assistant edit payload') from exc
        try:
            for target, stage, _ in entries:
                target.check(target.info)
                # Keep the actual staged inode, even if a concurrent writer
                # substitutes the destination immediately after replacement.
                os.replace(stage, target.name, src_dir_fd=target.parent, dst_dir_fd=target.parent)
                target.published = os.fstat(target.staged_fds[stage])
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
                    if backup is not None:
                        target.retained.add(backup)
            rollback = 'edit publication failed'
            if failed:
                rollback += '; rollback failed; original .benchpack-example-*.tmp backups retained'
            uncertain = '; rollback directory durability uncertain; inspect visible files before retrying'
            try:
                sync_failure = _sync_parents(target for target, _, _ in entries if target.published is not None)
            except BaseException as interrupt:
                # A later interrupt or exit wins, but still reports the
                # rollback outcome and the original failure as context.
                if not isinstance(interrupt, Exception):
                    interrupt.add_note(rollback + uncertain)
                raise
            if sync_failure is not None:
                rollback += uncertain
            if not isinstance(exc, Exception):
                # Keep interrupts and exits (for example signal SystemExit) intact.
                if failed or sync_failure is not None:
                    exc.add_note(rollback)
                raise
            if failed or sync_failure is not None:
                raise ValueError(rollback) from exc
            raise ValueError('could not apply assistant edit payload') from exc
        # All complete new bytes are visible. A failed acknowledgement cannot
        # safely turn that outcome into rollback or an automatic retry.
        uncertain = 'edits published; directory durability uncertain; inspect visible files before retrying'
        try:
            failure = _sync_parents(target for target, _, _ in entries)
        except BaseException as exc:
            # An interrupt or exit during acknowledgement keeps its identity,
            # but must not hide that every new file is already visible.
            if not isinstance(exc, Exception):
                exc.add_note(uncertain)
            raise
        if failure is not None:
            raise ValueError(uncertain) from failure


def control_json(text):
    """Decode example control JSON with one interpretation and bounded errors."""
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate JSON member')
            result[key] = value
        return result
    try:
        return json.loads(text, object_pairs_hook=unique)
    except json.JSONDecodeError as exc:
        raise json.JSONDecodeError('invalid control JSON', '', 0) from exc
    except (ValueError, RecursionError) as exc:
        raise ValueError('invalid or ambiguous control JSON') from exc


class TelemetryDestination:
    """Hold sidecar directory and expected leaf generation across an agent call."""
    def __init__(self, resources, root: Path, path: Path):
        relative = path.relative_to(root).as_posix()
        self.target = _Target(resources, root, relative, missing=True)
        self.resources = resources

    def write(self, data: bytes):
        target = self.target
        stage = target.stage(data, self.resources, private=True)
        target.check(target.info)
        os.replace(stage, target.name, src_dir_fd=target.parent, dst_dir_fd=target.parent)
        target.info = os.fstat(target.staged_fds[stage])
        target.check(target.info)
        # Complete bytes are already published if directory sync fails.
        try:
            os.fsync(target.parent)
        except OSError as exc:
            raise OSError('telemetry published; directory durability uncertain') from exc


def publish_telemetry(destination, text: str):
    data = text.encode('utf-8')
    if isinstance(destination, TelemetryDestination):
        destination.write(data)
    else:
        # Direct helper calls admit their destination here; CLI calls admit it
        # before executing the external agent/HTTP call.
        with ExitStack() as resources:
            TelemetryDestination(resources, destination.parent, destination).write(data)


MAX_CONTEXT_BYTES = 16 * 1024 * 1024


def read_context_text(path: Path) -> str:
    """Admit an opened regular UTF-8 context before decoding control JSON."""
    try:
        fd = os.open(path, _READ)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise ValueError('context must be a regular file')
            snapshot = read_opened_regular(fd, MAX_CONTEXT_BYTES)
            if snapshot.data is None:
                raise ValueError('context exceeds byte limit')
            text = snapshot.data.decode('utf-8')
        except BaseException:
            # Preserve the admission failure. The descriptor number may already
            # be reusable if close raises.
            with suppress(OSError):
                os.close(fd)
            raise
        os.close(fd)
        return text
    except (OSError, UnicodeError) as exc:
        raise ValueError('could not read stable UTF-8 context') from exc


@contextmanager
def workspace_input(root: Path, relative: str, *, optional=False):
    """Open contained regular inputs nonblocking, refusing links at every step."""
    if contained_parts(relative) is None:
        raise ValueError('unsafe workspace input path')
    path = root / relative
    with ExitStack() as resources:
        try:
            parent = resources.enter_context(admitted_directory(path.parent, base=root.parent))
            fd = os.open(path.name, _READ, dir_fd=parent)
        except FileNotFoundError:
            if optional:
                yield None
                return
            raise ValueError('workspace input missing') from None
        resources.callback(os.close, fd)
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError('workspace input must be regular')
        yield fd


def workspace_text(root: Path, relative: str, limit: int) -> str:
    with workspace_input(root, relative) as fd:
        snapshot = read_opened_regular(fd, limit)
        if snapshot.data is None:
            raise ValueError('workspace context exceeds byte limit')
        try:
            return snapshot.data.decode('utf-8')
        except UnicodeError as exc:
            raise ValueError('workspace context must be UTF-8') from exc
