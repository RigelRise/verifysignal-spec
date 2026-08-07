from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, NoReturn

from verifysignal_spec.workspace.repository import load_document
from verifysignal_spec.workspace.validation import looks_secret
from verifysignal_spec.workflows.write_safety import resolve_confirmation_signal_placeholders


def prepare_run_request_document(
    run_request: Path,
    runtime_values: dict[str, Any],
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], bool]:
    document = load_document(run_request, default={}) or {}
    if not isinstance(document, dict):
        return None, [], False

    prepared = dict(document)
    changed = False
    parameters = prepared.get("parameters") if isinstance(prepared.get("parameters"), dict) else {}
    merged_parameters = {**parameters, **runtime_values}
    if merged_parameters != parameters:
        prepared["parameters"] = merged_parameters
        changed = True

    policy_key = "sideEffectPolicy" if isinstance(prepared.get("sideEffectPolicy"), dict) else "sideEffects"
    policy = prepared.get(policy_key)
    if not isinstance(policy, dict) or not isinstance(policy.get("confirmationSignals"), list):
        return prepared, [], changed

    resolved_signals, findings = resolve_confirmation_signal_placeholders(
        list(policy["confirmationSignals"]),
        merged_parameters,
        path_prefix=f"{policy_key}.confirmationSignals",
        secret_checker=looks_secret,
    )
    if findings:
        return prepared, findings, changed

    if resolved_signals != policy.get("confirmationSignals"):
        next_policy = dict(policy)
        next_policy["confirmationSignals"] = resolved_signals
        prepared[policy_key] = next_policy
        changed = True
    return prepared, [], changed


def write_prepared_run_request(output_dir: Path, run_id: str, document: dict[str, Any]) -> Path:
    """Write a command-owned stable request, replacing its prior rendering."""

    output_dir.mkdir(parents=True, exist_ok=True)
    prepared = output_dir / f"{run_id}.run-request.json"
    prepared.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return prepared


def _write_exclusive_prepared_run_request(
    output_dir: Path,
    run_id: str,
    document: dict[str, Any],
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    prepared = output_dir / f"{run_id}.run-request.json"
    with prepared.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(document, indent=2) + "\n")
    return prepared


@dataclass(slots=True)
class PreparedRunRequestOwnership:
    path: Path
    createdByThisInvocation: bool
    expectedPath: Path | None = None
    device: int | None = None
    inode: int | None = None
    directoryFd: int | None = None
    fileFd: int | None = None
    cleanupMode: str | None = None
    windowsDirectoryHandles: tuple[int, ...] = ()


def write_owned_prepared_run_request(
    project: Path,
    output_dir: Path,
    run_id: str,
    document: dict[str, Any],
    *,
    writer: Callable[[Path, str, dict[str, Any]], Path] = _write_exclusive_prepared_run_request,
) -> PreparedRunRequestOwnership:
    """Write a collision-free prepared request and report exact ownership."""

    project_root = project.resolve()
    runs_root = project_root / ".verifysignal" / "runs"
    lexical_output = _lexical_absolute(output_dir)
    if (
        not _is_within(lexical_output, runs_root)
        or _has_symlink_component(project_root, lexical_output)
    ):
        return PreparedRunRequestOwnership(path=output_dir, createdByThisInvocation=False)

    candidate_id = run_id
    suffix = 0
    trusted_writer = writer is _write_exclusive_prepared_run_request
    while True:
        expected = lexical_output / f"{candidate_id}.run-request.json"
        if expected.exists() or expected.is_symlink():
            suffix += 1
            candidate_id = f"{run_id}.{suffix}"
            continue
        try:
            if trusted_writer:
                anchored = _write_anchored_exclusive(
                    project_root,
                    lexical_output,
                    expected.name,
                    document,
                )
                if anchored is None:
                    return PreparedRunRequestOwnership(
                        path=expected,
                        createdByThisInvocation=False,
                        expectedPath=expected,
                    )
                (
                    returned,
                    file_stat,
                    directory_fd,
                    file_fd,
                    cleanup_mode,
                    windows_directory_handles,
                ) = anchored
            else:
                returned = Path(writer(lexical_output, candidate_id, document))
                file_stat = None
                directory_fd = None
                file_fd = None
                cleanup_mode = None
                windows_directory_handles = ()
        except FileExistsError:
            suffix += 1
            candidate_id = f"{run_id}.{suffix}"
            continue
        break
    returned_lexical = _lexical_absolute(returned)
    created = bool(
        trusted_writer
        and returned_lexical == expected
        and returned.exists()
        and returned.is_file()
        and not returned.is_symlink()
        and not _has_symlink_component(project_root, returned_lexical)
        and _is_within(returned_lexical, runs_root)
        and file_stat is not None
        and (directory_fd is not None or file_fd is not None)
    )
    if not created:
        _close_descriptor(directory_fd)
        _close_descriptor(file_fd)
        for handle in windows_directory_handles:
            _close_windows_handle(handle)
        directory_fd = None
        file_fd = None
        windows_directory_handles = ()
    return PreparedRunRequestOwnership(
        path=returned_lexical,
        createdByThisInvocation=created,
        expectedPath=expected,
        device=(file_stat.st_dev if created and file_stat is not None else None),
        inode=(file_stat.st_ino if created and file_stat is not None else None),
        directoryFd=directory_fd if created else None,
        fileFd=file_fd if created else None,
        cleanupMode=cleanup_mode if created else None,
        windowsDirectoryHandles=(windows_directory_handles if created else ()),
    )


def prepared_output_dir_is_safe(project: Path, output_dir: Path) -> bool:
    project_root = project.resolve()
    lexical_output = _lexical_absolute(output_dir)
    runs_root = project_root / ".verifysignal" / "runs"
    return bool(
        _is_within(lexical_output, runs_root)
        and not _has_symlink_component(project_root, lexical_output)
    )


def cleanup_owned_prepared_run_request(
    project: Path,
    ownership: PreparedRunRequestOwnership,
) -> bool:
    """Delete only the exact regular file proven created by this invocation."""

    if not ownership.createdByThisInvocation or ownership.expectedPath is None:
        release_prepared_run_request_ownership(ownership)
        return False
    project_root = project.resolve()
    path = _lexical_absolute(ownership.path)
    expected = _lexical_absolute(ownership.expectedPath)
    runs_root = project_root / ".verifysignal" / "runs"
    directory_fd = ownership.directoryFd
    try:
        if (
            path != expected
            or expected.parent != path.parent
            or not _is_within(path, runs_root)
            or ownership.device is None
            or ownership.inode is None
        ):
            return False
        if ownership.cleanupMode == "windows-handle":
            file_fd = ownership.fileFd
            if file_fd is None:
                return False
            observed = os.fstat(file_fd)
            if (
                not stat.S_ISREG(observed.st_mode)
                or observed.st_dev != ownership.device
                or observed.st_ino != ownership.inode
            ):
                return False
            # Windows deletes the exact open file object by handle. A pathname
            # swap cannot redirect this operation to a replacement file.
            return _delete_windows_file_by_handle(file_fd)
        if directory_fd is None:
            return False
        observed = os.stat(expected.name, dir_fd=directory_fd, follow_symlinks=False)
        if (
            not stat.S_ISREG(observed.st_mode)
            or observed.st_dev != ownership.device
            or observed.st_ino != ownership.inode
        ):
            return False
        # The held directory descriptor anchors unlink to the directory in
        # which this invocation created the file, even if its pathname was
        # renamed or replaced while Core was running.
        os.unlink(expected.name, dir_fd=directory_fd)
        return True
    except (FileNotFoundError, NotADirectoryError, OSError):
        return False
    finally:
        release_prepared_run_request_ownership(ownership)


def release_prepared_run_request_ownership(
    ownership: PreparedRunRequestOwnership,
) -> None:
    directory_fd = ownership.directoryFd
    file_fd = ownership.fileFd
    windows_directory_handles = ownership.windowsDirectoryHandles
    ownership.directoryFd = None
    ownership.fileFd = None
    ownership.windowsDirectoryHandles = ()
    _close_descriptor(directory_fd)
    _close_descriptor(file_fd)
    for handle in windows_directory_handles:
        _close_windows_handle(handle)


def _close_descriptor(descriptor: int | None) -> None:
    if descriptor is None:
        return
    try:
        os.close(descriptor)
    except OSError:
        pass


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _lexical_absolute(path: Path) -> Path:
    return Path(os.path.abspath(path))


def _has_symlink_component(project_root: Path, path: Path) -> bool:
    try:
        relative = path.relative_to(project_root)
    except ValueError:
        return True
    current = project_root
    for part in relative.parts:
        current = current / part
        if _is_link_like(current):
            return True
    return False


def _is_link_like(path: Path) -> bool:
    """Treat Windows junctions as redirects alongside symbolic links."""

    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    return bool(callable(is_junction) and is_junction())


def _write_anchored_exclusive(
    project_root: Path,
    output_dir: Path,
    filename: str,
    document: dict[str, Any],
) -> tuple[
    Path,
    os.stat_result,
    int | None,
    int | None,
    str,
    tuple[int, ...],
] | None:
    """Create through no-follow directory descriptors, or fail closed."""

    if not _supports_anchored_file_operations():
        return _write_windows_anchored_exclusive(
            project_root,
            output_dir,
            filename,
            document,
        )
    try:
        relative = output_dir.relative_to(project_root)
    except ValueError:
        return None
    directory_fd: int | None = None
    try:
        directory_fd = _open_anchored_directory(
            project_root,
            relative.parts,
            create=True,
        )
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        file_fd = os.open(filename, flags, 0o600, dir_fd=directory_fd)
        try:
            payload = (json.dumps(document, indent=2) + "\n").encode("utf-8")
            view = memoryview(payload)
            while view:
                written = os.write(file_fd, view)
                view = view[written:]
            file_stat = os.fstat(file_fd)
        finally:
            os.close(file_fd)
        return (
            output_dir / filename,
            file_stat,
            directory_fd,
            None,
            "directory-fd",
            (),
        )
    except FileExistsError:
        if directory_fd is not None:
            os.close(directory_fd)
        raise
    except OSError:
        if directory_fd is not None:
            os.close(directory_fd)
        return None


def _open_anchored_directory(
    project_root: Path,
    parts: tuple[str, ...],
    *,
    create: bool,
) -> int:
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    current_fd = os.open(project_root, flags)
    try:
        for part in parts:
            try:
                next_fd = os.open(part, flags, dir_fd=current_fd)
            except FileNotFoundError:
                if not create:
                    raise
                try:
                    os.mkdir(part, 0o700, dir_fd=current_fd)
                except FileExistsError:
                    pass
                next_fd = os.open(part, flags, dir_fd=current_fd)
            os.close(current_fd)
            current_fd = next_fd
        return current_fd
    except Exception:
        os.close(current_fd)
        raise


def _supports_anchored_file_operations() -> bool:
    return bool(
        hasattr(os, "O_DIRECTORY")
        and hasattr(os, "O_NOFOLLOW")
        and os.open in os.supports_dir_fd
        and os.mkdir in os.supports_dir_fd
        and os.stat in os.supports_dir_fd
        and os.unlink in os.supports_dir_fd
        and os.stat in os.supports_follow_symlinks
    )


def _write_windows_anchored_exclusive(
    project_root: Path,
    output_dir: Path,
    filename: str,
    document: dict[str, Any],
) -> tuple[Path, os.stat_result, None, int, str, tuple[int, ...]] | None:
    """Create safely on Windows while locking every non-reparse ancestor.

    Windows lacks POSIX ``dir_fd``. Holding each validated directory handle
    without ``FILE_SHARE_DELETE`` prevents rename/replacement until Core has
    returned. ``CREATE_NEW`` then creates the file exclusively under that
    locked chain, and the open file handle provides exact cleanup identity.
    """

    if os.name != "nt":
        return None
    try:
        relative = output_dir.relative_to(project_root)
    except ValueError:
        return None

    directory_handles: list[int] = []
    file_fd: int | None = None
    try:
        current = project_root
        root_handle = _windows_open_locked_directory(current, create=False)
        directory_handles.append(root_handle)
        for part in relative.parts:
            current = current / part
            directory_handles.append(
                _windows_open_locked_directory(current, create=True)
            )

        path = output_dir / filename
        file_fd = _windows_create_exclusive_file(path)
        payload = (json.dumps(document, indent=2) + "\n").encode("utf-8")
        view = memoryview(payload)
        while view:
            written = os.write(file_fd, view)
            view = view[written:]
        os.fsync(file_fd)
        observed = os.fstat(file_fd)
        if not stat.S_ISREG(observed.st_mode):
            raise OSError("Prepared request is not a regular file.")
        return (
            path,
            observed,
            None,
            file_fd,
            "windows-handle",
            tuple(directory_handles),
        )
    except FileExistsError:
        _close_descriptor(file_fd)
        for handle in directory_handles:
            _close_windows_handle(handle)
        raise
    except OSError:
        _close_descriptor(file_fd)
        for handle in directory_handles:
            _close_windows_handle(handle)
        return None


def _windows_open_locked_directory(path: Path, *, create: bool) -> int:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    create_file.restype = wintypes.HANDLE
    desired_access = 0x0080  # FILE_READ_ATTRIBUTES
    share_without_delete = 0x00000001 | 0x00000002  # FILE_SHARE_READ | FILE_SHARE_WRITE
    open_existing = 3
    directory_flags = 0x02000000 | 0x00200000  # BACKUP_SEMANTICS | OPEN_REPARSE_POINT

    def open_directory() -> int | None:
        handle = create_file(
            str(path),
            desired_access,
            share_without_delete,
            None,
            open_existing,
            directory_flags,
            None,
        )
        invalid = ctypes.c_void_p(-1).value
        return None if handle in {None, invalid} else int(handle)

    handle = open_directory()
    if handle is None and create:
        create_directory = kernel32.CreateDirectoryW
        create_directory.argtypes = [wintypes.LPCWSTR, wintypes.LPVOID]
        create_directory.restype = wintypes.BOOL
        created = bool(create_directory(str(path), None))
        already_exists = ctypes.get_last_error() in {80, 183}
        if not created and not already_exists:
            raise OSError(f"Could not create locked prepared-request directory: {path.name}")
        handle = open_directory()
    if handle is None or _windows_handle_is_reparse_point(handle):
        _close_windows_handle(handle)
        raise OSError(f"Prepared-request directory is unavailable or a reparse point: {path.name}")
    return handle


def _windows_create_exclusive_file(path: Path) -> int:
    import ctypes
    import msvcrt
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    create_file.restype = wintypes.HANDLE
    desired_access = 0x40000000 | 0x00010000 | 0x0080  # GENERIC_WRITE | DELETE | FILE_READ_ATTRIBUTES
    # Core needs read access to the pathname while this invocation retains
    # the exact file handle. Do not share write/delete: otherwise a concurrent
    # actor could mutate or replace the prepared request before Core reads it.
    share_read_only = 0x00000001
    create_new = 1
    file_flags = 0x00000080 | 0x00200000  # FILE_ATTRIBUTE_NORMAL | OPEN_REPARSE_POINT
    handle = create_file(
        str(path),
        desired_access,
        share_read_only,
        None,
        create_new,
        file_flags,
        None,
    )
    invalid = ctypes.c_void_p(-1).value
    if handle in {None, invalid}:
        _raise_windows_create_error(path, ctypes.get_last_error())
    numeric_handle = int(handle)
    if _windows_handle_is_reparse_point(numeric_handle):
        _close_windows_handle(numeric_handle)
        raise OSError("Prepared request unexpectedly opened a reparse point.")
    try:
        return msvcrt.open_osfhandle(
            numeric_handle,
            os.O_WRONLY | getattr(os, "O_BINARY", 0),
        )
    except OSError:
        _close_windows_handle(numeric_handle)
        raise


def _raise_windows_create_error(path: Path, error: int) -> NoReturn:
    """Map Win32 creation errors without requiring Windows in unit tests."""

    message = f"Could not exclusively create prepared request: {path.name}"
    if error in {80, 183}:  # ERROR_FILE_EXISTS | ERROR_ALREADY_EXISTS
        raise FileExistsError(error, message, str(path))
    raise OSError(error, message, str(path))


def _windows_handle_is_reparse_point(handle: int) -> bool:
    import ctypes
    from ctypes import wintypes

    class FileAttributeTagInfo(ctypes.Structure):
        _fields_ = [
            ("FileAttributes", wintypes.DWORD),
            ("ReparseTag", wintypes.DWORD),
        ]

    info = FileAttributeTagInfo()
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get_file_information = kernel32.GetFileInformationByHandleEx
    get_file_information.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
    ]
    get_file_information.restype = wintypes.BOOL
    result = get_file_information(
        wintypes.HANDLE(handle),
        9,  # FILE_INFO_BY_HANDLE_CLASS.FileAttributeTagInfo
        ctypes.byref(info),
        ctypes.sizeof(info),
    )
    if not result:
        raise OSError("Could not inspect prepared-request handle attributes.")
    return bool(info.FileAttributes & 0x00000400)  # FILE_ATTRIBUTE_REPARSE_POINT


def _delete_windows_file_by_handle(file_fd: int) -> bool:
    if os.name != "nt":
        return False
    try:
        import ctypes
        import msvcrt
        from ctypes import wintypes

        class FileDispositionInfo(ctypes.Structure):
            _fields_ = [("DeleteFile", wintypes.BOOL)]

        handle = wintypes.HANDLE(msvcrt.get_osfhandle(file_fd))
        disposition = FileDispositionInfo(True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        set_file_information = kernel32.SetFileInformationByHandle
        set_file_information.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            wintypes.LPVOID,
            wintypes.DWORD,
        ]
        set_file_information.restype = wintypes.BOOL
        result = set_file_information(
            handle,
            4,  # FILE_INFO_BY_HANDLE_CLASS.FileDispositionInfo
            ctypes.byref(disposition),
            ctypes.sizeof(disposition),
        )
        return bool(result)
    except (ImportError, OSError, ValueError):
        return False


def _close_windows_handle(handle: int | None) -> None:
    if handle is None or os.name != "nt":
        return
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        close_handle = kernel32.CloseHandle
        close_handle.argtypes = [wintypes.HANDLE]
        close_handle.restype = wintypes.BOOL
        close_handle(wintypes.HANDLE(handle))
    except (ImportError, OSError, ValueError):
        pass


def confirmation_placeholder_blockers(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "code": f"runtime.{item.get('code')}",
            "severity": "blocker",
            "category": item.get("category", "side-effect-confirmation"),
            "message": item.get("message"),
            "documentationRef": item.get("path"),
            "recoveryCommand": item.get("recoveryCommand") or "verifysignal workflow check validate --alias <alias> --json",
            "nextAction": item.get("nextAction"),
        }
        for item in findings
    ]
