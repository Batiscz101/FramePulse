"""Načtení a validace konfigurace agenta.

Konfigurace se čte z `pc-agent/config.json`. Pokud soubor neexistuje, vytvoří se
z výchozích hodnot (včetně připojení k Supabase). Všechny cesty v konfiguraci
jsou relativní ke složce `pc-agent/`.
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
    # Připojení k Supabase – publishable (anon) klíč je veřejný, data chrání RLS.
    # Ukázkové hodnoty nahraďte údaji z vašeho projektu (Project Settings → API).
    "supabase_url": "https://your-project.supabase.co",
    "supabase_key": "your-anon-key",
    # Cesta k PresentMon (relativní ke složce pc-agent).
    "presentmon_path": "tools/PresentMon.exe",
    # Jak často kontrolovat běžící hry (sekundy).
    "poll_interval_seconds": 2.0,
    # Délka jednoho vzorku FPS v grafu (sekundy).
    "sample_interval_seconds": 2.0,
    # Kratší hraní se neukládá.
    "min_session_seconds": 15,
    # Na začátku hraní se zahodí načítání (sekundy).
    "warmup_seconds": 5.0,
    # Když PresentMon za tuto dobu nezachytí ani frame, proces není hra.
    "confirm_frames_seconds": 90,
    # Když hra přestane posílat framy (alt-tab na dlouho), seance se uzavře.
    "stall_seconds": 600,
    # Jak dlouho se po neúspěchu ignoruje stejný proces (sekundy).
    "no_game_cooldown_seconds": 900,
    # Ověřit oprávnění PresentMonu hned při startu.
    "preflight_on_start": True,
    "notifications": True,
    "notify_on_upload": False,
    # Po kolika vzorcích se posílají fps_samples (PostgREST dávka).
    "upload_chunk_size": 500,
    "request_timeout_seconds": 20,
    # Doplňkové seznamy názvů procesů (např. "mygame.exe").
    "ignore_processes": [],
    "force_games": [],
    # Prázdné = %LOCALAPPDATA%\FramePulseAgent
    "data_dir": "",
    "debug": False,
}

_EXE_RE = re.compile(r"[\\/]")


class ConfigError(RuntimeError):
    """Konfiguraci nelze použít (chybí klíč, poškozený JSON…)."""


def normalize_exe(value: str) -> str:
    """`Cyberpunk2077.EXE` -> `cyberpunk2077.exe` (jen název, bez cesty)."""
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
        LOG.warning("Neplatná hodnota %s=%r, používám %s", key, raw.get(key), fallback)
        return fallback
    if not math.isfinite(value):
        LOG.warning("Hodnota %s=%r není konečné číslo, používám %s", key, raw.get(key), fallback)
        return fallback
    if value < minimum:
        LOG.warning("Hodnota %s=%s je příliš malá, používám %s", key, value, minimum)
        return minimum
    return value


def _exe_set(raw: dict[str, Any], key: str) -> frozenset[str]:
    values = raw.get(key) or []
    if not isinstance(values, list):
        raise ConfigError(f"Hodnota '{key}' v config.json musí být seznam názvů procesů.")
    return frozenset(normalize_exe(item) for item in values if str(item).strip())


def load_config(path: Path | None = None) -> Config:
    """Načte config.json; při první startu ho vytvoří s výchozími hodnotami."""
    config_path = path or CONFIG_FILE
    raw: dict[str, Any] = {}

    if config_path.exists():
        try:
            loaded = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ConfigError(
                f"Soubor {config_path.name} není platný JSON (řádek {exc.lineno})."
            ) from exc
        if not isinstance(loaded, dict):
            raise ConfigError(f"Soubor {config_path.name} musí obsahovat JSON objekt.")
        raw = loaded
    else:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps(DEFAULT_CONFIG, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        LOG.info("Vytvořen výchozí config.json: %s", config_path)

    merged: dict[str, Any] = {**DEFAULT_CONFIG, **raw}

    url = str(merged.get("supabase_url") or "").strip().rstrip("/")
    key = str(merged.get("supabase_key") or "").strip()
    warnings: list[str] = []

    if not url.startswith(("https://", "http://")):
        raise ConfigError(
            "V config.json chybí platná 'supabase_url' "
            "(očekávám např. https://<projekt>.supabase.co)."
        )
    if not key:
        raise ConfigError("V config.json chybí 'supabase_key' (publishable/anon klíč).")

    host = url.split("://", 1)[-1].split("/", 1)[0].lower()
    if host in {"supabase.co", "www.supabase.co", "app.supabase.co"}:
        warnings.append(
            "supabase_url míří na obecný web Supabase, ne na projekt. "
            "Použijte adresu https://<project-ref>.supabase.co."
        )
    if key.startswith("eyJ") and len(key) > 200:
        LOG.info("Použit starší anon (JWT) klíč.")
    elif not key.startswith("sb_publishable_"):
        warnings.append("supabase_key nevypadá jako publishable klíč (sb_publishable_…).")

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
        LOG.warning("Konfigurace: %s", warning)

    return config
