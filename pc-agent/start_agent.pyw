"""Launcher for the agent without a console window (double-click or autostart).

The recommended launch is via `start_agent.bat`, which uses the virtual
environment created by `setup.bat`. If this file runs with the system Python
without dependencies, a readable message is shown.
"""

from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

SILENT = "--silent" in sys.argv[1:]


def _fatal_log(message: str) -> None:
    local = os.environ.get("LOCALAPPDATA")
    data_dir = Path(local) / "FramePulseAgent" if local else Path.home() / ".framepulse"
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        with (data_dir / "fatal.log").open("a", encoding="utf-8") as handle:
            handle.write(message.rstrip() + "\n\n")
    except OSError:
        pass


def _message_box(message: str) -> None:
    if os.name != "nt":
        return
    try:
        ctypes.windll.user32.MessageBoxW(
            None, message, "FramePulse", 0x00000010 | 0x00010000
        )
    except Exception:
        pass


def _fail(message: str) -> None:
    _fatal_log(message)
    if not SILENT:
        _message_box(message)
    raise SystemExit(1)


def _check_dependencies() -> None:
    try:
        import PIL  # noqa: F401
        import psutil  # noqa: F401
        import pystray  # noqa: F401
        import requests  # noqa: F401
    except ImportError as exc:
        _fail(
            "Missing agent dependencies:\n\n"
            f"{exc}\n\n"
            "First run setup.bat in the pc-agent folder. It creates "
            "the virtual environment and installs everything needed."
        )


if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

_check_dependencies()

from framepulse_agent.app import main  # noqa: E402

raise SystemExit(main())
