"""Logging to file – the agent runs under pythonw, no console is available."""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def setup_logging(log_dir: Path, debug: bool = False) -> Path:
    """Sets the rotating log to `log_dir/agent.log` and returns the file path."""
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "agent.log"

    root = logging.getLogger()
    root.setLevel(logging.DEBUG if debug else logging.INFO)

    for handler in list(root.handlers):
        root.removeHandler(handler)

    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    root.addHandler(file_handler)

    # When started from the console (development), log there too. Under pythonw, stderr is None.
    if sys.stderr is not None and sys.stderr.isatty():
        console = logging.StreamHandler(sys.stderr)
        console.setFormatter(logging.Formatter(LOG_FORMAT))
        root.addHandler(console)

    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("PIL").setLevel(logging.WARNING)

    return log_file


def write_fatal(message: str, data_dir: Path | None = None) -> None:
    """Writes an error that happened before logging could be set up."""
    if data_dir is None:
        return
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        with (data_dir / "fatal.log").open("a", encoding="utf-8") as handle:
            handle.write(message.rstrip() + "\n\n")
    except OSError:
        pass
