from __future__ import annotations

from dataclasses import dataclass
import errno
import hashlib
import os
from pathlib import Path
import stat
import tempfile
import threading

from verifysignal_spec.workspace import layout


class RunInvocationLockUnavailable(RuntimeError):
    """Raised when the platform cannot establish a trustworthy run lease."""


_ACTIVE_LOCK = threading.Lock()
_ACTIVE_KEYS: set[tuple[int, str]] = set()


@dataclass(slots=True)
class RunInvocationLease:
    _registry_key: tuple[int, str]
    _backend: str
    _token: int
    _released: bool = False

    def release(self) -> None:
        if self._released:
            return
        self._released = True
        try:
            if self._backend == "windows-mutex":
                _release_windows_mutex(self._token)
            else:
                _release_posix_lock(self._token)
        finally:
            with _ACTIVE_LOCK:
                _ACTIVE_KEYS.discard(self._registry_key)

    def __enter__(self) -> RunInvocationLease:
        return self

    def __exit__(self, *_args: object) -> None:
        self.release()


def acquire_run_invocation_lease(
    project: Path,
    alias: str,
) -> RunInvocationLease | None:
    """Acquire a non-blocking, crash-released lease for one project alias."""

    project = project.resolve()
    alias = layout.ensure_path_safe_alias(alias)
    project_fd: int | None = None
    registry_key: tuple[int, str] | None = None
    try:
        if os.name == "nt":
            digest = hashlib.sha256(
                (
                    f"{os.path.normcase(str(project))}"
                    f"\0{alias.casefold()}"
                ).encode("utf-8")
            ).hexdigest()
        elif os.name == "posix":
            project_fd = _open_posix_project_directory(project)
            metadata = os.fstat(project_fd)
            digest = hashlib.sha256(
                (
                    f"{metadata.st_dev}:{metadata.st_ino}"
                    f"\0{alias.casefold()}"
                ).encode("utf-8")
            ).hexdigest()
        else:
            raise OSError(f"Unsupported run-lock platform: {os.name}")

        registry_key = (os.getpid(), digest)
        with _ACTIVE_LOCK:
            if registry_key in _ACTIVE_KEYS:
                return None
            _ACTIVE_KEYS.add(registry_key)

        if os.name == "nt":
            token = _acquire_windows_mutex(digest)
            backend = "windows-mutex"
        else:
            if project_fd is None:
                raise OSError("The POSIX project identity is unavailable.")
            token = _acquire_posix_lock(project_fd, alias, digest)
            backend = "posix-runtime-file"
        if token is None:
            with _ACTIVE_LOCK:
                _ACTIVE_KEYS.discard(registry_key)
            return None
        return RunInvocationLease(registry_key, backend, token)
    except Exception as exc:
        if registry_key is not None:
            with _ACTIVE_LOCK:
                _ACTIVE_KEYS.discard(registry_key)
        if isinstance(exc, RunInvocationLockUnavailable):
            raise
        raise RunInvocationLockUnavailable(
            "A trustworthy per-use-case run lease could not be established."
        ) from exc
    except BaseException:
        if registry_key is not None:
            with _ACTIVE_LOCK:
                _ACTIVE_KEYS.discard(registry_key)
        raise
    finally:
        if project_fd is not None:
            os.close(project_fd)


def run_invocation_blocker(
    alias: str,
    *,
    unavailable: bool = False,
) -> dict[str, str]:
    code = "runtime.run-lock-unavailable" if unavailable else "runtime.run-in-progress"
    message = (
        "A trustworthy run lock is unavailable; protected execution is blocked."
        if unavailable
        else "Another run for this use case is still in progress."
    )
    return {
        "code": code,
        "severity": "blocker",
        "category": "run-concurrency",
        "message": message,
        "recoveryCommand": (
            f"verifysignal workflow check run --alias {alias} --json"
        ),
    }


def probe_run_invocation_blocker(
    project: Path,
    alias: str,
) -> dict[str, str] | None:
    """Return the current lease blocker without retaining the lease."""

    try:
        lease = acquire_run_invocation_lease(project, alias)
    except RunInvocationLockUnavailable:
        return run_invocation_blocker(alias, unavailable=True)
    if lease is None:
        return run_invocation_blocker(alias)
    lease.release()
    return None


def _acquire_posix_lock(
    project_fd: int,
    alias: str,
    digest: str,
) -> int | None:
    import fcntl

    required = ("O_DIRECTORY", "O_NOFOLLOW")
    if any(not hasattr(os, name) for name in required):
        raise OSError("Anchored no-follow directory locking is unavailable.")
    if os.open not in os.supports_dir_fd or os.mkdir not in os.supports_dir_fd:
        raise OSError("Anchored directory operations are unavailable.")
    runtime_fd = _open_posix_runtime_lock_namespace()
    lock_fd: int | None = None
    try:
        file_flags = os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            file_flags |= os.O_CLOEXEC
        lock_fd = os.open(
            f"{digest}.lock",
            file_flags,
            0o600,
            dir_fd=runtime_fd,
        )
        metadata = os.fstat(lock_fd)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) & 0o077
        ):
            raise OSError("Runtime lock identity is not a private regular file.")
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            if exc.errno in {errno.EACCES, errno.EAGAIN}:
                os.close(lock_fd)
                lock_fd = None
                return None
            raise
        # Retain the project-local identity directory for compatibility and
        # observability only. The actual lease is the runtime fd above, so a
        # alternate path spelling or a worktree rename cannot mint a second
        # lock identity for the same open project directory.
        _ensure_posix_workspace_lock_directory(project_fd, alias)
        return lock_fd
    except BaseException:
        if lock_fd is not None:
            os.close(lock_fd)
        raise
    finally:
        os.close(runtime_fd)


def _open_posix_project_directory(project: Path) -> int:
    required = ("O_DIRECTORY", "O_NOFOLLOW")
    if any(not hasattr(os, name) for name in required):
        raise OSError("No-follow project identity is unavailable.")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    project_fd = os.open(project, flags)
    metadata = os.fstat(project_fd)
    if not stat.S_ISDIR(metadata.st_mode):
        os.close(project_fd)
        raise OSError("The project identity is not a directory.")
    return project_fd


def _open_posix_runtime_lock_namespace() -> int:
    runtime_root = Path(tempfile.gettempdir()).resolve()
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    root_fd = os.open(runtime_root, flags)
    try:
        namespace = f"verifysignal-spec-run-locks-v1-{os.getuid()}"
        try:
            os.mkdir(namespace, 0o700, dir_fd=root_fd)
        except FileExistsError:
            pass
        namespace_fd = os.open(namespace, flags, dir_fd=root_fd)
        metadata = os.fstat(namespace_fd)
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) & 0o077
        ):
            os.close(namespace_fd)
            raise OSError("Runtime lock namespace is not private to this user.")
        return namespace_fd
    finally:
        os.close(root_fd)


def _ensure_posix_workspace_lock_directory(project_fd: int, alias: str) -> None:
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    current_fd = os.dup(project_fd)
    try:
        for part in (layout.WORKSPACE_DIR, ".run-locks", alias):
            try:
                next_fd = os.open(part, flags, dir_fd=current_fd)
            except FileNotFoundError:
                try:
                    os.mkdir(part, 0o700, dir_fd=current_fd)
                except FileExistsError:
                    pass
                next_fd = os.open(part, flags, dir_fd=current_fd)
            os.close(current_fd)
            current_fd = next_fd
    finally:
        os.close(current_fd)


def _release_posix_lock(directory_fd: int) -> None:
    import fcntl

    try:
        fcntl.flock(directory_fd, fcntl.LOCK_UN)
    finally:
        os.close(directory_fd)


def _acquire_windows_mutex(digest: str) -> int | None:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_mutex = kernel32.CreateMutexW
    create_mutex.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    create_mutex.restype = wintypes.HANDLE
    handle = create_mutex(
        None,
        False,
        f"Global\\VerifySignal.Spec.Run.{digest}",
    )
    if not handle:
        raise OSError(ctypes.get_last_error(), "CreateMutexW failed")
    wait = kernel32.WaitForSingleObject
    wait.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    wait.restype = wintypes.DWORD
    result = int(wait(handle, 0))
    if result in {0x00000000, 0x00000080}:  # WAIT_OBJECT_0 | WAIT_ABANDONED
        return int(handle)
    _close_windows_handle(int(handle))
    if result == 0x00000102:  # WAIT_TIMEOUT
        return None
    raise OSError(ctypes.get_last_error(), "WaitForSingleObject failed")


def _release_windows_mutex(handle: int) -> None:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    release = kernel32.ReleaseMutex
    release.argtypes = [wintypes.HANDLE]
    release.restype = wintypes.BOOL
    try:
        if not release(wintypes.HANDLE(handle)):
            raise OSError(ctypes.get_last_error(), "ReleaseMutex failed")
    finally:
        _close_windows_handle(handle)


def _close_windows_handle(handle: int) -> None:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    close = kernel32.CloseHandle
    close.argtypes = [wintypes.HANDLE]
    close.restype = wintypes.BOOL
    close(wintypes.HANDLE(handle))
