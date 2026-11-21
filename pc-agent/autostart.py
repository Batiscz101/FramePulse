"""Adds or removes FramePulse to/from autostart after login (HKCU\\...\\Run).

Usage:

    .venv\\Scripts\\python.exe autostart.py enable
    .venv\\Scripts\\python.exe autostart.py disable
    .venv\\Scripts\\python.exe autostart.py status
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    import winreg
except ImportError:  # pragma: no cover – jen pro jistotu na ne-Windows
    winreg = None  # type: ignore[assignment]

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "FramePulseAgent"
BASE_DIR = Path(__file__).resolve().parent


def _pythonw() -> Path:
    """Prefers pythonw.exe (no console window) next to the current Python."""
    executable = Path(sys.executable)
    if executable.name.lower() == "pythonw.exe":
        return executable
    candidate = executable.with_name("pythonw.exe")
    return candidate if candidate.exists() else executable


def build_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{Path(sys.executable).resolve()}"'
    launcher = BASE_DIR / "start_agent.pyw"
    return f'"{_pythonw()}" "{launcher}" --silent'


def enable() -> int:
    if winreg is None:
        print("Autostart is supported on Windows only.", file=sys.stderr)
        return 1

    command = build_command()
    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
    ) as key:
        winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, command)

    print("Autostart enabled:")
    print(f"  {command}")
    return 0


def disable() -> int:
    if winreg is None:
        print("Autostart is supported on Windows only.", file=sys.stderr)
        return 1

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.DeleteValue(key, VALUE_NAME)
    except FileNotFoundError:
        print("Autostart was not enabled.")
        return 0

    print("Autostart disabled.")
    return 0


def status() -> int:
    if winreg is None:
        print("Autostart is supported on Windows only.", file=sys.stderr)
        return 1

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _kind = winreg.QueryValueEx(key, VALUE_NAME)
    except FileNotFoundError:
        print("Autostart is disabled.")
        return 1

    print(f"Autostart is enabled:\n  {value}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Autostart for the FramePulse agent.")
    parser.add_argument("action", choices=("enable", "disable", "status"))
    args = parser.parse_args(argv)

    return {"enable": enable, "disable": disable, "status": status}[args.action]()


if __name__ == "__main__":
    raise SystemExit(main())
