"""Pojistka proti dvěma běžícím instancím agenta (dvě ikony v trayi)."""

from __future__ import annotations

import ctypes
import logging

LOG = logging.getLogger(__name__)

ERROR_ALREADY_EXISTS = 183
MUTEX_NAME = "Local\\FramePulseAgent.SingleInstance"

# Handle musí zůstat živý po celou dobu běhu procesu.
_mutex_handle: int | None = None


def acquire_instance_lock(name: str = MUTEX_NAME) -> bool:
    """Vrátí True, pokud je tato instance první; jinak False."""
    global _mutex_handle

    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    handle = kernel32.CreateMutexW(None, False, name)
    if not handle:
        LOG.warning("CreateMutexW selhal, pokračuji bez zámku.")
        return True

    last_error = kernel32.GetLastError()
    if last_error == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(ctypes.c_void_p(handle))
        return False

    _mutex_handle = handle
    return True
