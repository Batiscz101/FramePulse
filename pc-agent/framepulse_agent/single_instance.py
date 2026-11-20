"""Safety against two running instances of the agent (two icons in the tray)."""

from __future__ import annotations

import ctypes
import logging

LOG = logging.getLogger(__name__)

ERROR_ALREADY_EXISTS = 183
MUTEX_NAME = "Local\\FramePulseAgent.SingleInstance"

# The handle must stay alive for the whole process runtime.
_mutex_handle: int | None = None


def acquire_instance_lock(name: str = MUTEX_NAME) -> bool:
    """Returns True if this instance is first; otherwise False."""
    global _mutex_handle

    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    handle = kernel32.CreateMutexW(None, False, name)
    if not handle:
        LOG.warning("CreateMutexW failed, continuing without the lock.")
        return True

    last_error = kernel32.GetLastError()
    if last_error == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(ctypes.c_void_p(handle))
        return False

    _mutex_handle = handle
    return True
