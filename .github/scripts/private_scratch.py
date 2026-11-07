"""Descriptor-relative private scratch for isolated, trusted Linux execution."""

import os
import re
import secrets
import stat
import threading


class ScratchError(RuntimeError):
    """The scratch boundary was unavailable or no longer matched its owner."""


_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
_CREATE_FLAGS = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC


def _inode(info):
    return info.st_dev, info.st_ino


def _open_trusted_parent(path):
    if (os.name != "posix" or not all(hasattr(os, name) for name in ("O_DIRECTORY", "O_NOFOLLOW", "O_CLOEXEC"))
            or os.open not in os.supports_dir_fd or os.mkdir not in os.supports_dir_fd
            or os.stat not in os.supports_dir_fd or os.unlink not in os.supports_dir_fd
            or os.rmdir not in os.supports_dir_fd):
        raise ScratchError("Descriptor-relative filesystem operations are unavailable.")
    if not isinstance(path, str) or not path.startswith("/"):
        raise ScratchError("An absolute trusted scratch parent is required.")
    parts = path.split("/")[1:]
    if not parts or any(not part or part in (".", "..") for part in parts):
        raise ScratchError("The scratch parent path is not canonical.")
    current = os.open("/", _DIR_FLAGS)
    uid = os.geteuid()
    try:
        root = os.fstat(current)
        root_mode = stat.S_IMODE(root.st_mode)
        root_sticky_tmp = root.st_uid == 0 and bool(root.st_mode & stat.S_ISVTX)
        if (not stat.S_ISDIR(root.st_mode) or root.st_uid not in (0, uid)
                or (root_mode & 0o022 and not root_sticky_tmp)):
            raise ScratchError("The filesystem root is not trusted.")
        for index, part in enumerate(parts):
            child = None
            try:
                before = os.stat(part, dir_fd=current, follow_symlinks=False)
                if not stat.S_ISDIR(before.st_mode):
                    raise ScratchError("A scratch parent component is not a real directory.")
                child = os.open(part, _DIR_FLAGS, dir_fd=current)
                opened = os.fstat(child)
                after = os.stat(part, dir_fd=current, follow_symlinks=False)
            except OSError:
                if child is not None:
                    os.close(child)
                raise ScratchError("A scratch parent component changed or cannot be opened.") from None
            if (_inode(before) != _inode(opened) or _inode(after) != _inode(opened)
                    or not stat.S_ISDIR(opened.st_mode)):
                os.close(child)
                raise ScratchError("A scratch parent component changed during open.")
            last = index == len(parts) - 1
            mode = stat.S_IMODE(opened.st_mode)
            trusted_sticky_tmp = opened.st_uid == 0 and bool(opened.st_mode & stat.S_ISVTX)
            if opened.st_uid not in (0, uid) or (mode & 0o022 and not trusted_sticky_tmp):
                os.close(child)
                raise ScratchError("A scratch parent component is not trusted.")
            if last and (opened.st_uid != uid or mode & 0o022):
                os.close(child)
                raise ScratchError("The scratch parent must be privately writable by this identity.")
            os.close(current)
            current = child
        return current
    except (OSError, ScratchError):
        os.close(current)
        raise


class PrivateScratch:
    """Own one private directory beneath a trusted parent; never follows links."""

    def __init__(self, parent_fd, fd, name, identity, *, owns_parent, parent_owner=None, lock=None):
        self.name = name
        self._parent_fd = parent_fd
        self._fd = fd
        self._identity = identity
        self._owns_parent = owns_parent
        self._parent_owner = parent_owner
        self._entries = {}
        self._lock = lock or threading.RLock()
        self._removed = False
        self._handles_closed = False

    @classmethod
    def create(cls, parent):
        parent_fd = _open_trusted_parent(os.fspath(parent))
        name = "scratch-" + secrets.token_hex(16)
        if not _NAME.fullmatch(name):
            os.close(parent_fd)
            raise ScratchError("The generated scratch name is invalid.")
        fd = None
        keep = False
        try:
            try:
                os.mkdir(name, 0o700, dir_fd=parent_fd)
            except FileExistsError:
                raise ScratchError("The exclusive scratch name is already in use.") from None
            fd = os.open(name, _DIR_FLAGS, dir_fd=parent_fd)
            os.fchmod(fd, 0o700)
            obj = cls(parent_fd, fd, name, _inode(os.fstat(fd)), owns_parent=True)
            obj._verify_link()
            keep = True
            return obj
        finally:
            if not keep:
                if fd is not None:
                    os.close(fd)
                os.close(parent_fd)

    def __enter__(self):
        self._ensure_open()
        return self

    def __exit__(self, _kind, _value, _traceback):
        try:
            self.cleanup()
        finally:
            self.close_descriptors()

    def _ensure_open(self):
        if self._handles_closed or self._removed:
            raise ScratchError("The scratch directory is no longer open.")

    def _verify_link(self):
        self._ensure_open()
        try:
            named = os.stat(self.name, dir_fd=self._parent_fd, follow_symlinks=False)
            opened = os.fstat(self._fd)
        except OSError:
            raise ScratchError("The owned scratch directory is unavailable.") from None
        if (not stat.S_ISDIR(named.st_mode) or _inode(named) != self._identity
                or _inode(opened) != self._identity or opened.st_uid != os.geteuid()
                or stat.S_IMODE(opened.st_mode) != 0o700):
            raise ScratchError("The owned scratch directory was replaced or changed.")

    def _record_created_file(self, name, fd):
        info = os.fstat(fd)
        identity = _inode(info)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o600):
            raise ScratchError("The created scratch file is not safely owned.")
        owned_fd = os.dup(fd)
        keep = False
        try:
            opened = os.fstat(owned_fd)
            if (_inode(opened) != identity or not stat.S_ISREG(opened.st_mode)
                    or opened.st_uid != os.geteuid() or stat.S_IMODE(opened.st_mode) != 0o600):
                raise ScratchError("The retained scratch file descriptor changed.")
            try:
                named = os.stat(name, dir_fd=self._fd, follow_symlinks=False)
            except OSError:
                raise ScratchError("The created scratch file name is unavailable.") from None
            if (not stat.S_ISREG(named.st_mode) or _inode(named) != identity
                    or named.st_uid != os.geteuid() or stat.S_IMODE(named.st_mode) != 0o600):
                raise ScratchError("The created scratch file name no longer matches its descriptor.")
            self._entries[name] = ("file", identity, owned_fd)
            keep = True
        finally:
            if not keep:
                os.close(owned_fd)
    def _record_created_file_after_error(self, name, fd):
        try:
            self._record_created_file(name, fd)
        except (OSError, ScratchError):
            raise ScratchError("A created scratch file could not be safely recorded and may remain.") from None
    def create_file(self, name, content):
        if not isinstance(name, str) or not _NAME.fullmatch(name):
            raise ScratchError("A single safe file name is required.")
        if not isinstance(content, (bytes, bytearray, memoryview)):
            raise TypeError("Scratch file contents must be bytes-like.")
        source = memoryview(content)
        try:
            if not source.c_contiguous:
                raise TypeError("Scratch file contents must be contiguous.")
            try:
                view = source.cast("B")
            except (TypeError, ValueError):
                raise TypeError("Scratch file contents cannot be viewed as bytes.") from None
            try:
                with self._lock:
                    self._verify_link()
                    if name in self._entries:
                        raise ScratchError("The scratch entry is already owned.")
                    try:
                        fd = os.open(name, _CREATE_FLAGS, 0o600, dir_fd=self._fd)
                    except FileExistsError:
                        raise ScratchError("The scratch file name is already in use.") from None
                    try:
                        try:
                            os.fchmod(fd, 0o600)
                        except OSError:
                            self._record_created_file_after_error(name, fd)
                            raise
                        try:
                            self._record_created_file(name, fd)
                        except OSError:
                            self._record_created_file_after_error(name, fd)
                            raise
                        while view:
                            written = os.write(fd, view)
                            if written <= 0:
                                raise ScratchError("A scratch file write did not make progress.")
                            view = view[written:]
                        os.fsync(fd)
                    finally:
                        os.close(fd)
                return name
            finally:
                view.release()
        finally:
            source.release()

    def create_directory(self, name):
        if not isinstance(name, str) or not _NAME.fullmatch(name):
            raise ScratchError("A single safe directory name is required.")
        with self._lock:
            self._verify_link()
            if name in self._entries:
                raise ScratchError("The scratch entry is already owned.")
            try:
                os.mkdir(name, 0o700, dir_fd=self._fd)
            except FileExistsError:
                raise ScratchError("The scratch directory name is already in use.") from None
            child_fd = os.open(name, _DIR_FLAGS, dir_fd=self._fd)
            keep = False
            try:
                os.fchmod(child_fd, 0o700)
                info = os.fstat(child_fd)
                child = PrivateScratch(self._fd, child_fd, name, _inode(info), owns_parent=False, parent_owner=self, lock=self._lock)
                child._verify_link()
                self._entries[name] = ("directory", _inode(info), child)
                keep = True
                return child
            finally:
                if not keep:
                    os.close(child_fd)

    def _verify_file(self, name, identity, owned_fd):
        if not isinstance(owned_fd, int):
            raise ScratchError("An owned scratch file descriptor is unavailable.")
        try:
            opened = os.fstat(owned_fd)
            if (_inode(opened) != identity or not stat.S_ISREG(opened.st_mode)
                    or opened.st_uid != os.geteuid() or stat.S_IMODE(opened.st_mode) != 0o600):
                raise ScratchError("An owned scratch file descriptor changed.")
            named = os.stat(name, dir_fd=self._fd, follow_symlinks=False)
            if (not stat.S_ISREG(named.st_mode) or _inode(named) != _inode(opened)
                    or named.st_uid != os.geteuid() or stat.S_IMODE(named.st_mode) != 0o600):
                raise ScratchError("An owned scratch file was replaced or changed.")
        except OSError:
            raise ScratchError("An owned scratch file is unavailable.") from None
    def _preflight(self):
        self._verify_link()
        names = os.listdir(self._fd)
        if len(names) != len(self._entries) or set(names) != set(self._entries):
            raise ScratchError("Unexpected scratch contents prevent cleanup.")
        for name, (kind, identity, resource) in self._entries.items():
            if kind == "file":
                self._verify_file(name, identity, resource)
            elif kind == "directory":
                resource._preflight()
            else:
                raise ScratchError("Unknown scratch ownership record.")

    def _remove_contents(self):
        for name, (kind, identity, resource) in tuple(self._entries.items()):
            if kind == "file":
                self._verify_file(name, identity, resource)
                os.unlink(name, dir_fd=self._fd)
                del self._entries[name]
                try:
                    os.close(resource)
                except OSError:
                    raise ScratchError("A removed scratch file descriptor could not be closed.") from None
                continue
            resource._remove_contents()
            resource._verify_link()
            os.rmdir(name, dir_fd=self._fd)
            resource._removed = True
            resource.close_descriptors()
            del self._entries[name]
    def _verify_parent_entry(self):
        if self._owns_parent:
            return None
        parent = self._parent_owner
        if parent is None:
            raise ScratchError("The scratch directory has no recorded owner.")
        parent._verify_link()
        entry = parent._entries.get(self.name)
        if (not isinstance(entry, tuple) or len(entry) != 3
                or entry[0] != "directory" or entry[1] != self._identity or entry[2] is not self):
            raise ScratchError("The parent no longer records this scratch directory.")
        return parent, entry
    def cleanup(self):
        with self._lock:
            if self._removed:
                return
            parent_entry = self._verify_parent_entry()
            self._preflight()
            self._remove_contents()
            self._verify_link()
            os.rmdir(self.name, dir_fd=self._parent_fd)
            if parent_entry is not None:
                parent, entry = parent_entry
                if parent._entries.get(self.name) is not entry:
                    raise ScratchError("The parent scratch ownership record changed during cleanup.")
                del parent._entries[self.name]
            self._removed = True
            self.close_descriptors()

    def close_descriptors(self):
        with self._lock:
            if self._handles_closed:
                return
            close_failed = False
            for name, (kind, identity, resource) in tuple(self._entries.items()):
                if kind == "directory":
                    try:
                        resource.close_descriptors()
                    except ScratchError:
                        close_failed = True
                elif kind == "file" and resource is not None:
                    self._entries[name] = (kind, identity, None)
                    try:
                        os.close(resource)
                    except OSError:
                        close_failed = True
            fd = self._fd
            self._fd = -1
            try:
                os.close(fd)
            except OSError:
                close_failed = True
            if self._owns_parent:
                parent_fd = self._parent_fd
                self._parent_fd = -1
                try:
                    os.close(parent_fd)
                except OSError:
                    close_failed = True
            self._handles_closed = True
            if close_failed:
                raise ScratchError("One or more scratch descriptors could not be closed.")
