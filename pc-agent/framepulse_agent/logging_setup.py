"""Logování do souboru – agent běží pod pythonw, konzole není k dispozici."""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def setup_logging(log_dir: Path, debug: bool = False) -> Path:
    """Nastaví rotující log do `log_dir/agent.log` a vrátí cestu k souboru."""
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

    # Při spuštění z konzole (vývoj) logujeme i tam. Pod pythonw je stderr None.
    if sys.stderr is not None and sys.stderr.isatty():
        console = logging.StreamHandler(sys.stderr)
        console.setFormatter(logging.Formatter(LOG_FORMAT))
        root.addHandler(console)

    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("PIL").setLevel(logging.WARNING)

    return log_file


def write_fatal(message: str, data_dir: Path | None = None) -> None:
    """Zapíše chybu, která nastala dřív než šlo nastavit logging."""
    if data_dir is None:
        return
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        with (data_dir / "fatal.log").open("a", encoding="utf-8") as handle:
            handle.write(message.rstrip() + "\n\n")
    except OSError:
        pass
