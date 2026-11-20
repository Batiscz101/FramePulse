"""Reading and validation of the agent configuration.

The configuration is read from `pc-agent/config.json`. If the file does not
exist, it is created with default values (including the Supabase connection).
All paths in the configuration are relative to the `pc-agent/` folder.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

LOG = logging.getLogger(__name__)

PACKAGE_DIR = Path(__file__).resolve().parent
BASE_DIR = PACKAGE_DIR.parent

AGENT_VERSION = "1.0.0"

CONFIG_FILE = BASE_DIR / "config.json"

APP_DATA_FOLDER = "FramePulseAgent"

DEFAULT_CONFIG: dict[str, Any] = {
    # Supabase connection – the publishable (anon) key is public; data is protected by RLS.
    # Replace the sample values with data from your project (Project Settings → API).
    "supabase_url": "https://your-project.supabase.co",
    "supabase_key": "your-anon-key",
    # Path to PresentMon (relative to the pc-agent folder).
    "presentmon_path": "tools/PresentMon.exe",
    # How often visible games are checked (seconds).
    "poll_interval_seconds": 2.0,
    # Length of one FPS graph point (seconds).
    "sample_interval_seconds": 2.0,
    # Shorter plays are not saved.
    "min_session_seconds": 15,
    # At the start of a play, loading is discarded (seconds).
    "warmup_seconds": 5.0,
    # When PresentMon captures no frame within this time, the process is not a game.
    "confirm_frames_seconds": 90,
    # When the game stops sending frames (alt-tab for a long time), the session is closed.
    "stall_seconds": 600,
    # How long the same process is ignored after a failure (seconds).
    "no_game_cooldown_seconds": 900,
    # Verify PresentMon permissions right at startup.
    "preflight_on_start": True,
    "notifications": True,
    "notify_on_upload": False,
    # After how many samples fps_samples are sent (PostgREST batch).
    "upload_chunk_size": 500,
    "request_timeout_seconds": 20,
    # Additional process name lists (e.g. "mygame.exe").
    "ignore_processes": [],
    "force_games": [],
    # Empty = %LOCALAPPDATA%\FramePulseAgent
    "data_dir": "",
    "debug": False,
}

_EXE_RE = re.compile(r"[\\/]")


class ConfigError(RuntimeError):
    """The configuration cannot be used (missing key, corrupted JSON…)."""


def normalize_exe(value: str) -> str:
    """`Cyberpunk2077.EXE` -> `cyberpunk2077.exe` (just the name, without the path)."""
    name = _EXE_RE.split(str(value).strip())[-1].lower()
    if name and not name.endswith(".exe"):
        name += ".exe"
    return name


def default_data_dir() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / APP_DATA_FOLDER
    return Path.home() / "AppData" / "Local" / APP_DATA_FOLDER


@dataclass(frozen=True)
class Config:
    supabase_url: str
    supabase_key: str
    presentmon_path: Path
    data_dir: Path
    poll_interval: float
    sample_interval: float
    min_session_seconds: float
    warmup_seconds: float
    confirm_frames_seconds: float
    stall_seconds: float
    no_game_cooldown_seconds: float
    preflight_on_start: bool
    notifications: bool
    notify_on_upload: bool
    upload_chunk_size: int
    request_timeout: float
    ignore_processes: frozenset[str] = frozenset()
    force_games: frozenset[str] = frozenset()
    debug: bool = False
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def outbox_dir(self) -> Path:
        return self.data_dir / "outbox"

    @property
    def log_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def capture_dir(self) -> Path:
        return self.data_dir / "captures"


def _number(raw: dict[str, Any], key: str, fallback: float, minimum: float) -> float:
    try:
        value = float(raw.get(key, fallback))
    except (TypeError, ValueError):
        LOG.warning("Invalid value %s=%r, using %s", key, raw.get(key), fallback)
        return fallback
    if not math.isfinite(value):
        LOG.warning("Value %s=%r is not a finite number, using %s", key, raw.get(key), fallback)
        return fallback
    if value < minimum:
        LOG.warning("Value %s=%s is too small, using %s", key, value, minimum)
        return minimum
    return value


def _exe_set(raw: dict[str, Any], key: str) -> frozenset[str]:
    values = raw.get(key) or []
    if not isinstance(values, list):
        raise ConfigError(f"Value '{key}' in config.json must be a list of process names.")
    return frozenset(normalize_exe(item) for item in values if str(item).strip())


def load_config(path: Path | None = None) -> Config:
    """Reads config.json; on first start, creates it with default values."""
    config_path = path or CONFIG_FILE
    raw: dict[str, Any] = {}

    if config_path.exists():
        try:
            loaded = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ConfigError(
                f"File {config_path.name} is not valid JSON (line {exc.lineno})."
            ) from exc
        if not isinstance(loaded, dict):
            raise ConfigError(f"File {config_path.name} must contain a JSON object.")
        raw = loaded
    else:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps(DEFAULT_CONFIG, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        LOG.info("Created default config.json: %s", config_path)

    merged: dict[str, Any] = {**DEFAULT_CONFIG, **raw}

    url = str(merged.get("supabase_url") or "").strip().rstrip("/")
    key = str(merged.get("supabase_key") or "").strip()
    warnings: list[str] = []

    if not url.startswith(("https://", "http://")):
        raise ConfigError(
            "config.json is missing a valid 'supabase_url' "
            "(expected e.g. https://<project>.supabase.co)."
        )
    if not key:
        raise ConfigError("config.json is missing 'supabase_key' (publishable/anon key).")

    host = url.split("://", 1)[-1].split("/", 1)[0].lower()
    if host in {"supabase.co", "www.supabase.co", "app.supabase.co"}:
        warnings.append(
            "supabase_url points to the generic Supabase web, not to a project. "
            "Use the address https://<project-ref>.supabase.co."
        )
    if key.startswith("eyJ") and len(key) > 200:
        LOG.info("Using the older anon (JWT) key.")
    elif not key.startswith("sb_publishable_"):
        warnings.append("supabase_key does not look like a publishable key (sb_publishable_…).")

    presentmon = Path(str(merged.get("presentmon_path") or "tools/PresentMon.exe"))
    if not presentmon.is_absolute():
        presentmon = (BASE_DIR / presentmon).resolve()

    data_dir_raw = str(merged.get("data_dir") or "").strip()
    data_dir = Path(data_dir_raw) if data_dir_raw else default_data_dir()
    if not data_dir.is_absolute():
        data_dir = (BASE_DIR / data_dir).resolve()

    chunk = int(max(1.0, _number(merged, "upload_chunk_size", 500, 1)))
    config = Config(
        supabase_url=url,
        supabase_key=key,
        presentmon_path=presentmon,
        data_dir=data_dir,
        poll_interval=_number(merged, "poll_interval_seconds", 2.0, 0.5),
        sample_interval=_number(merged, "sample_interval_seconds", 2.0, 0.5),
        min_session_seconds=_number(merged, "min_session_seconds", 15, 1),
        warmup_seconds=_number(merged, "warmup_seconds", 5.0, 0.0),
        confirm_frames_seconds=_number(merged, "confirm_frames_seconds", 90, 10),
        stall_seconds=_number(merged, "stall_seconds", 600, 30),
        no_game_cooldown_seconds=_number(merged, "no_game_cooldown_seconds", 900, 30),
        preflight_on_start=bool(merged.get("preflight_on_start", True)),
        notifications=bool(merged.get("notifications", True)),
        notify_on_upload=bool(merged.get("notify_on_upload", False)),
        upload_chunk_size=chunk,
        request_timeout=_number(merged, "request_timeout_seconds", 20, 3),
        ignore_processes=_exe_set(merged, "ignore_processes"),
        force_games=_exe_set(merged, "force_games"),
        debug=bool(merged.get("debug", False)),
        warnings=tuple(warnings),
    )

    for warning in warnings:
        LOG.warning("Configuration: %s", warning)

    return config
