"""Reading and validation of the agent configuration.

The configuration is read from `pc-agent/config.json` when running from source.
In a PyInstaller build it is looked up next to `FramePulseAgent.exe` and then in
`%LOCALAPPDATA%\\FramePulseAgent\\` – never inside the temporary `_MEIPASS`
folder. If the file does not exist, it is created from `config.example.json`
(or the built-in defaults). All relative paths are resolved against the folder
with the executable (frozen) or the `pc-agent/` folder (source).
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import shutil
import sys
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


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _frozen_exe_dir() -> Path:
    return Path(sys.executable).resolve().parent


def _bundle_dir() -> Path | None:
    """Read-only folder PyInstaller extracted the one-file build into."""
    meipass = getattr(sys, "_MEIPASS", None)
    return Path(meipass) if meipass else None


def app_dir() -> Path:
    """Folder with config.json: next to the exe (frozen) or pc-agent/ (source)."""
    return _frozen_exe_dir() if is_frozen() else BASE_DIR


def _is_writable_dir(directory: Path) -> bool:
    try:
        directory.mkdir(parents=True, exist_ok=True)
        probe = directory / ".framepulse-write-test"
        probe.write_text("", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def config_file() -> Path:
    """Path of config.json: next to the exe, then %LOCALAPPDATA%, then source."""
    if not is_frozen():
        return CONFIG_FILE

    exe_config = _frozen_exe_dir() / "config.json"
    user_config = default_data_dir() / "config.json"
    for candidate in (exe_config, user_config):
        if candidate.exists():
            return candidate
    # First run: prefer a portable config next to the exe, but fall back to the
    # user profile when the exe lives in a read-only folder (e.g. Program Files).
    return exe_config if _is_writable_dir(exe_config.parent) else user_config


def _example_config_file(config_path: Path) -> Path | None:
    """Look for config.example.json next to the exe/data dir; bundled copy last."""
    if not is_frozen():
        return None

    candidates = [
        _frozen_exe_dir() / "config.example.json",
        default_data_dir() / "config.example.json",
        config_path.parent / "config.example.json",
    ]
    bundle = _bundle_dir()
    if bundle is not None:
        # Bundled example is read-only and only used when no editable copy exists.
        candidates.append(bundle / "config.example.json")

    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if candidate.exists():
            return candidate
    return None


def _download_presentmon(target: Path) -> None:
    """Downloads the official PresentMon (2.x, x64) to `target` (GitHub latest)."""
    import urllib.request

    api_request = urllib.request.Request(
        "https://api.github.com/repos/GameTechDev/PresentMon/releases/latest",
        headers={
            "User-Agent": "FramePulseAgent/1.0",
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(api_request, timeout=30) as response:
        release = json.loads(response.read().decode("utf-8"))

    url = next(
        (
            str(asset["browser_download_url"])
            for asset in release.get("assets", [])
            if re.match(
                r"^PresentMon-[\d.]+-x64\.exe$", str(asset.get("name", "")), re.IGNORECASE
            )
        ),
        None,
    )
    if not url:
        raise RuntimeError("No x64 console application in the latest PresentMon release.")

    tmp = target.with_suffix(".exe.tmp")
    request = urllib.request.Request(url, headers={"User-Agent": "FramePulseAgent/1.0"})
    with urllib.request.urlopen(request, timeout=120) as response, tmp.open("wb") as handle:
        shutil.copyfileobj(response, handle, length=64 * 1024)
    with tmp.open("rb") as handle:
        is_executable = handle.read(2) == b"MZ"
    if tmp.stat().st_size < 200_000 or not is_executable:
        tmp.unlink(missing_ok=True)
        raise RuntimeError("Downloaded PresentMon is not a valid Windows executable.")
    tmp.replace(target)


def _resolve_presentmon_frozen(data_dir: Path) -> Path:
    """Locate PresentMon when frozen: bundled, next to the exe, or auto-download."""
    # An updated copy next to the exe or in the user profile wins over the bundle.
    search_roots = [_frozen_exe_dir(), data_dir]
    bundle = _bundle_dir()
    if bundle is not None:
        search_roots.append(bundle)

    for root in search_roots:
        for candidate in (root / "PresentMon.exe", root / "tools" / "PresentMon.exe"):
            if candidate.exists():
                return candidate

    # Nothing next to the exe or bundled – fetch it into the user profile.
    target = data_dir / "tools" / "PresentMon.exe"
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        _download_presentmon(target)
    except Exception as exc:
        LOG.warning("Could not download PresentMon to %s: %s", target, exc)
    return target


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
    if path is not None and is_frozen() and not path.is_absolute():
        # A relative --config is resolved next to the exe, not the current directory.
        path = _frozen_exe_dir() / path
    config_path = path or config_file()
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
        source = _example_config_file(config_path)
        if source is not None:
            try:
                loaded = json.loads(source.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                loaded = None
            if isinstance(loaded, dict) and loaded:
                raw = loaded
                try:
                    config_path.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
                    LOG.info("Created config.json from %s: %s", source.name, config_path)
                except OSError:
                    pass
        if not raw:
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

    data_dir_raw = str(merged.get("data_dir") or "").strip()
    data_dir = Path(data_dir_raw) if data_dir_raw else default_data_dir()
    if not data_dir.is_absolute():
        data_dir = (app_dir() / data_dir).resolve()

    presentmon = Path(str(merged.get("presentmon_path") or "tools/PresentMon.exe"))
    if not presentmon.is_absolute():
        presentmon = (app_dir() / presentmon).resolve()
    if is_frozen() and not presentmon.exists():
        presentmon = _resolve_presentmon_frozen(data_dir)

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
