"""Vstupní bod agenta – příprava prostředí a spuštění traye.

Volá se z `framepulse_agent/__main__.py` (python -m) i ze `start_agent.pyw`
(pythonw, bez konzole).
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
    """Pod pythonw jsou sys.stdout/stderr None – přesměrujeme je do devnull."""
    devnull = None
    for name in ("stdout", "stderr"):
        if getattr(sys, name) is None:
            if devnull is None:
                devnull = open(os.devnull, "w", encoding="utf-8")
            setattr(sys, name, devnull)


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
        description="FramePulse PC agent – měří FPS her a posílá je do Supabase.",
    )
    parser.add_argument("--config", type=Path, default=None, help="cesta k config.json")
    parser.add_argument("--debug", action="store_true", help="podrobný log")
    parser.add_argument(
        "--silent",
        action="store_true",
        help="nikdy nezobrazovat chybová okna (používá se při autostartu)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    _ensure_streams()
    args = _parse_args(list(sys.argv[1:] if argv is None else argv))
    interactive = not args.silent

    if not acquire_instance_lock():
        LOG.info("Agent už běží – druhá instance se nespouští.")
        if interactive:
            _message_box(
                "FramePulse agent už běží. Najdete ho jako ikonu pulzu "
                "v oznamovací oblasti vedle hodin.",
                error=False,
            )
        return 0

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        _fatal(str(exc), interactive=interactive)
        return 2

    log_file = setup_logging(config.log_dir, debug=config.debug or args.debug)
    LOG.info("FramePulse agent %s startuje.", __version__)
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
            LOG.error("Kontrola PresentMonu: %s", issue.message)

    try:
        TrayApp(
            config,
            uploader,
            startup_issue_message=issue.message if issue else None,
        ).run()
    except Exception as exc:
        LOG.exception("Agent spadl")
        _fatal(
            f"Agent neočekávaně skončil:\n\n{exc}\n\nPodrobnosti jsou v logu:\n{log_file}",
            interactive=interactive,
            data_dir=config.data_dir,
        )
        return 1
    finally:
        client.close()

    LOG.info("Agent ukončen.")
    return 0
