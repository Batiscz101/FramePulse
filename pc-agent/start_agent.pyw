"""Spouštěč agenta bez konzolového okna (dvojklik nebo autostart).

Doporučené spuštění je přes `start_agent.bat`, které použije virtuální
prostředí vytvořené `setup.bat`. Pokud se tento soubor spustí systémovým
Pythonem bez závislostí, zobrazí se srozumitelná hláška.
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
            "Chybí závislosti agenta:\n\n"
            f"{exc}\n\n"
            "Spusťte nejprve setup.bat ve složce pc-agent. Ten vytvoří "
            "virtuální prostředí a nainstaluje vše potřebné."
        )


if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

_check_dependencies()

from framepulse_agent.app import main  # noqa: E402

raise SystemExit(main())
