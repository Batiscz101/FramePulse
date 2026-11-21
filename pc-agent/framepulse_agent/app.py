"""Entry point of the agent – environment preparation and tray startup.

Called from `framepulse_agent/__main__.py` (python -m) and `start_agent.pyw`
(pythonw, without console).
"""

from __future__ import annotations

import argparse
import ctypes
import logging
import os
import sys
from pathlib import Path

from framepulse_agent import __version__
from framepulse_agent.capture import CaptureFailure, preflight
from framepulse_agent.config import ConfigError, default_data_dir, load_config
from framepulse_agent.logging_setup import setup_logging, write_fatal
from framepulse_agent.single_instance import acquire_instance_lock
from framepulse_agent.supabase import SupabaseClient
from framepulse_agent.tray import TrayApp
from framepulse_agent.upload import Uploader

LOG = logging.getLogger(__name__)

APP_TITLE = "FramePulse"
MB_ICONERROR = 0x00000010
MB_ICONINFORMATION = 0x00000040
MB_SETFOREGROUND = 0x00010000
MB_TOPMOST = 0x00040000


def _ensure_streams() -> None:
    """Under pythonw, sys.stdout/stderr are None – redirect them to devnull."""
    devnull = None
    for name in ("stdout", "stderr"):
        if getattr(sys, name) is None:
            if devnull is None:
                devnull = open(os.devnull, "w", encoding="utf-8")
            setattr(sys, name, devnull)


def _attach_parent_console() -> None:
    """Shows --autostart output in cmd/PowerShell (the exe is a GUI subsystem app)."""
    if os.name != "nt":
        return
    try:
        if not ctypes.windll.kernel32.AttachConsole(-1):
            return
        for name in ("stdout", "stderr"):
            try:
                setattr(sys, name, open("CONOUT$", "w", encoding="utf-8", buffering=1))
            except OSError:
                pass
    except Exception:
        # No parent console (double-click) – registry changes still work.
        pass


def _message_box(message: str, *, title: str = APP_TITLE, error: bool = True) -> None:
    if os.name != "nt":
        return
    flags = (MB_ICONERROR if error else MB_ICONINFORMATION) | MB_SETFOREGROUND | MB_TOPMOST
    try:
        ctypes.windll.user32.MessageBoxW(None, message, title, flags)
    except Exception:
        pass


def _fatal(message: str, *, interactive: bool, data_dir: Path | None = None) -> None:
    write_fatal(message, data_dir or default_data_dir())
    if interactive:
        _message_box(message)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="framepulse-agent",
        description="FramePulse PC agent – measures FPS of games and sends them to Supabase.",
    )
    parser.add_argument("--config", type=Path, default=None, help="path to config.json")
    parser.add_argument("--debug", action="store_true", help="verbose log")
    parser.add_argument(
        "--silent",
        action="store_true",
        help="never show error dialogs (used at autostart)",
    )
    parser.add_argument(
        "--autostart",
        choices=("enable", "disable", "status"),
        default=None,
        help="manage Windows autostart for this agent",
    )
    return parser.parse_args(argv)


RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "FramePulseAgent"


def _autostart_value() -> str:
    """Command line written to the Run registry value (frozen or source mode)."""
    if getattr(sys, "frozen", False):
        return f'"{Path(sys.executable).resolve()}"'
    executable = Path(sys.executable)
    if executable.name.lower() != "pythonw.exe":
        alternative = executable.with_name("pythonw.exe")
        if alternative.exists():
            executable = alternative
    launcher = Path(__file__).resolve().parent.parent / "start_agent.pyw"
    return f'"{executable.resolve()}" "{launcher}" --silent'


def _run_autostart(action: str) -> int:
    """Manages the Windows Run autostart entry (`--autostart`)."""
    try:
        import winreg
    except ImportError:  # pragma: no cover – only on non-Windows
        print("Autostart is supported on Windows only.", file=sys.stderr)
        return 1

    value = _autostart_value()
    if action == "enable":
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, RUN_VALUE, 0, winreg.REG_SZ, value)
        print(f"Autostart is enabled:\n  {value}")
        return 0
    if action == "disable":
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
            ) as key:
                winreg.DeleteValue(key, RUN_VALUE)
        except FileNotFoundError:
            print("Autostart is not enabled.")
            return 1
        print("Autostart is disabled.")
        return 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _kind = winreg.QueryValueEx(key, RUN_VALUE)
    except FileNotFoundError:
        print("Autostart is disabled.")
        return 1
    print(f"Autostart is enabled:\n  {value}")
    return 0


def main(argv: list[str] | None = None) -> int:
    raw_args = list(sys.argv[1:] if argv is None else argv)
    if any(arg == "--autostart" or arg.startswith("--autostart=") for arg in raw_args):
        _attach_parent_console()
    _ensure_streams()
    args = _parse_args(raw_args)
    if args.autostart:
        return _run_autostart(args.autostart)
    interactive = not args.silent

    if not acquire_instance_lock():
        LOG.info("Agent already running – second instance not started.")
        if interactive:
            _message_box(
                "The FramePulse agent is already running. Find it as the pulse icon "
                "in the notification area next to the clock.",
                error=False,
            )
        return 0

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        _fatal(str(exc), interactive=interactive)
        return 2

    log_file = setup_logging(config.log_dir, debug=config.debug or args.debug)
    LOG.info("FramePulse agent %s starting.", __version__)
    LOG.info("Data: %s", config.data_dir)
    LOG.info("Log: %s", log_file)
    LOG.info("PresentMon: %s", config.presentmon_path)

    client = SupabaseClient(
        config.supabase_url,
        config.supabase_key,
        timeout=config.request_timeout,
    )
    uploader = Uploader(client, config.outbox_dir, config.upload_chunk_size)

    issue: CaptureFailure | None = None
    if config.preflight_on_start:
        issue = preflight(config.presentmon_path)
        if issue is not None:
            LOG.error("PresentMon check: %s", issue.message)

    try:
        TrayApp(
            config,
            uploader,
            startup_issue_message=issue.message if issue else None,
        ).run()
    except Exception as exc:
        LOG.exception("Agent spadl")
        _fatal(
            f"The agent exited unexpectedly:\n\n{exc}\n\nDetails are in the log:\n{log_file}",
            interactive=interactive,
            data_dir=config.data_dir,
        )
        return 1
    finally:
        client.close()

    LOG.info("Agent exited.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
