"""Local-only storage permissions, using native ACLs on Windows (no dependencies)."""
import os
from pathlib import Path


def protect_private(path, *, directory=False):
    """Restrict access to this user; retain Windows SYSTEM/administrator recovery.

    Never silently continue if protection cannot be applied. The caller must
    protect the directory and temporary file before writing any credentials.
    """
    path = Path(path).resolve()
    if os.name == 'nt':
        _windows_private(path, directory)
    else:
        os.chmod(path, 0o700 if directory else 0o600)


def _windows_private(path, directory):
    import ctypes
    from ctypes import wintypes as w

    advapi = ctypes.WinDLL('advapi32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    pointer = ctypes.c_void_p
    advapi.OpenProcessToken.argtypes = [w.HANDLE, w.DWORD, ctypes.POINTER(w.HANDLE)]
    advapi.OpenProcessToken.restype = w.BOOL
    advapi.GetTokenInformation.argtypes = [w.HANDLE, ctypes.c_int, pointer, w.DWORD,
                                          ctypes.POINTER(w.DWORD)]
    advapi.GetTokenInformation.restype = w.BOOL
    advapi.ConvertSidToStringSidW.argtypes = [pointer, ctypes.POINTER(w.LPWSTR)]
    advapi.ConvertSidToStringSidW.restype = w.BOOL
    advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
        w.LPCWSTR, w.DWORD, ctypes.POINTER(pointer), ctypes.POINTER(w.DWORD)]
    advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype = w.BOOL
    advapi.GetSecurityDescriptorDacl.argtypes = [pointer, ctypes.POINTER(w.BOOL),
                                                ctypes.POINTER(pointer), ctypes.POINTER(w.BOOL)]
    advapi.GetSecurityDescriptorDacl.restype = w.BOOL
    advapi.SetNamedSecurityInfoW.argtypes = [w.LPWSTR, ctypes.c_int, w.DWORD,
                                            pointer, pointer, pointer, pointer]
    advapi.SetNamedSecurityInfoW.restype = w.DWORD
    kernel.GetCurrentProcess.argtypes = []
    kernel.GetCurrentProcess.restype = w.HANDLE
    kernel.CloseHandle.argtypes = [w.HANDLE]
    kernel.CloseHandle.restype = w.BOOL
    kernel.LocalFree.argtypes = [pointer]
    kernel.LocalFree.restype = pointer
    kernel.GetVolumePathNameW.argtypes = [w.LPCWSTR, w.LPWSTR, w.DWORD]
    kernel.GetVolumePathNameW.restype = w.BOOL
    kernel.GetVolumeInformationW.argtypes = [w.LPCWSTR, w.LPWSTR, w.DWORD,
                                            ctypes.POINTER(w.DWORD), ctypes.POINTER(w.DWORD),
                                            ctypes.POINTER(w.DWORD), w.LPWSTR, w.DWORD]
    kernel.GetVolumeInformationW.restype = w.BOOL

    def checked(ok):
        if not ok:
            raise ctypes.WinError(ctypes.get_last_error())

    volume = ctypes.create_unicode_buffer(32768)
    checked(kernel.GetVolumePathNameW(str(path), volume, len(volume)))
    filesystem_flags = w.DWORD()
    checked(kernel.GetVolumeInformationW(volume.value, None, 0, None, None,
                                         ctypes.byref(filesystem_flags), None, 0))
    if not filesystem_flags.value & 0x00000008:  # FILE_PERSISTENT_ACLS
        raise PermissionError('Private storage requires a filesystem with persistent Windows ACLs')

    token = w.HANDLE()
    checked(advapi.OpenProcessToken(kernel.GetCurrentProcess(), 0x0008, ctypes.byref(token)))
    try:
        length = w.DWORD()
        # TokenUser: the first field of TOKEN_USER is the user's SID pointer.
        ok = advapi.GetTokenInformation(token, 1, None, 0, ctypes.byref(length))
        if not ok and ctypes.get_last_error() != 122:  # ERROR_INSUFFICIENT_BUFFER
            checked(False)
        buffer = ctypes.create_string_buffer(length.value)
        checked(advapi.GetTokenInformation(token, 1, buffer, length, ctypes.byref(length)))
        sid = w.LPWSTR()
        checked(advapi.ConvertSidToStringSidW(pointer.from_buffer(buffer), ctypes.byref(sid)))
        try:
            user_sid = sid.value
        finally:
            kernel.LocalFree(ctypes.cast(sid, pointer))
    finally:
        kernel.CloseHandle(token)

    # Protected DACL: replace broad inherited/explicit grants. Directory ACEs
    # also propagate to children, so new databases, logs and backups stay private.
    flags = 'OICI' if directory else ''
    sddl = 'D:P' + ''.join(f'(A;{flags};FA;;;{sid})'
                           for sid in dict.fromkeys((user_sid, 'SY', 'BA')))
    descriptor = pointer()
    checked(advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(
        sddl, 1, ctypes.byref(descriptor), None))
    try:
        present, defaulted, dacl = w.BOOL(), w.BOOL(), pointer()
        checked(advapi.GetSecurityDescriptorDacl(descriptor, ctypes.byref(present),
                                                 ctypes.byref(dacl), ctypes.byref(defaulted)))
        if not present.value or not dacl.value:
            raise OSError('A private Windows DACL could not be constructed')
        # SE_FILE_OBJECT, DACL_SECURITY_INFORMATION | PROTECTED_DACL_SECURITY_INFORMATION.
        error = advapi.SetNamedSecurityInfoW(str(path), 1, 0x80000004,
                                             None, None, dacl, None)
        if error:
            raise ctypes.WinError(error)
    finally:
        kernel.LocalFree(descriptor)
