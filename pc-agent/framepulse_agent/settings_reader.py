"""Automatic reading of key graphics settings from game configuration files.

Scans `%LOCALAPPDATA%` and `Documents\\My Games` for Unreal Engine
`GameUserSettings.ini` and common game `.ini` / `.cfg` / `.json` files, and
extracts the key graphics settings (quality preset, DLSS/FSR, ray tracing,
V-Sync, FPS limit) into a small canonical dict.

Everything is best effort: files that cannot be read, sections that do not
apply, or values that cannot be interpreted are ignored, never raising.
"""

from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

LOG = logging.getLogger(__name__)

# Keys the returned settings dictionary may contain.
CANONICAL_KEYS = ("quality", "dlss", "fsr", "ray_tracing", "vsync", "fps_limit")

# Limits for the directory walk (a corrupted/huge tree must not hang the agent).
_MAX_DEPTH = 8
_MAX_FILES = 250
_PRUNED_DIRS = {"node_modules", ".git", "__pycache__", "logs", "crashdumps", "cache"}

# Canonical value of the quality preset (LOW →ultra-high quality).
_QUALITY_STRINGS = {
    "low": "Low",
    "medium": "Medium",
    "high": "High",
    "ultra": "Ultra",
    "epic": "Ultra",
    "ultrahigh": "Ultra",
}

# Unreal Engine scalability levels: 0..3 (3 is the top).
_QUALITY_BY_NUMBER = {0: "Low", 1: "Medium", 2: "High", 3: "Ultra", 4: "Ultra"}

_QUALITY_KEY_TOKENS = (
    "quality",
    "scalability",
    "graphicsquality",
    "renderquality",
    "qualitylevel",
    "graphicpreset",
    "preset",
    "visualquality",
)
_DLSS_KEY_TOKENS = ("dlss",)
_FSR_KEY_TOKENS = ("fsr", "fidelityfx")
_RAY_TRACING_KEY_TOKENS = ("raytracing", "raytrace", "rtx")
_VSYNC_KEY_TOKENS = ("vsync", "verticalsync", "vblanksync")
_FPS_LIMIT_KEY_TOKENS = (
    "frameratelimit",
    "frameratecap",
    "fpslimit",
    "maxfps",
    "cappfps",
    "fpscap",
    "maxframerate",
)


def _default_roots() -> list[Path]:
    roots: list[Path] = []
    local = os.environ.get("LOCALAPPDATA")
    if local:
        roots.append(Path(local))
    else:
        roots.append(Path.home() / "AppData" / "Local")
    docs = Path.home() / "Documents" / "My Games"
    if docs.is_dir():
        roots.append(docs)
    return roots


def _canonical_key(key: str) -> str:
    """Normalizes a config key for matching (e.g. `bUseVsync` → `busevsync`)."""
    return re.sub(r"[^a-z0-9]", "", str(key).lower())


def _strip_quotes(text: str) -> str:
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    return text


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if not text:
        return None
    if text in ("1", "true", "yes", "on", "enabled", "enable", "y"):
        return True
    if text in ("0", "false", "no", "off", "disabled", "disable", "n"):
        return False
    return None


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return int(float(text))
    except ValueError:
        return None


def _quality_from_value(value: Any) -> str | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = int(value)
        return _QUALITY_BY_NUMBER.get(number)
    text = str(value).strip()
    if not text:
        return None
    return _QUALITY_STRINGS.get(text.lower())


# ---------------------------------------------------------------------------
# INI parsing
# ---------------------------------------------------------------------------


def parse_ini_text(text: str) -> dict[str, Any]:
    """Parses an INI-like file into a flat `{key: value}` dict.

    Sections are folded into the key name (`[Video]\\nDLSSEnabled=true`
    becomes `videodlssenabled`). Comments (`;`/`#` at line start) and lines
    without a value separator are ignored. Unreal Engine's
    `GameUserSettings.ini` uses the same `key=value` layout.
    """
    data: dict[str, Any] = {}
    section = ""
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line[0] in ";#":
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
            continue
        separator = "=" if "=" in line else ":" if ":" in line else None
        if separator is None:
            continue
        key_raw, value_raw = line.split(separator, 1)
        key = _strip_quotes((section + "::" + key_raw.strip()) if section else key_raw.strip())
        key = _canonical_key(key)
        if not key or key in data:
            continue
        data[key] = _strip_quotes(value_raw.strip())
    return data


def parse_ini_file(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    return parse_ini_text(text)


# ---------------------------------------------------------------------------
# JSON parsing
# ---------------------------------------------------------------------------


def _flatten_json(data: Mapping[str, Any], prefix: str = "") -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in data.items():
        flat_key = f"{prefix}{key}".lower()
        if isinstance(value, Mapping):
            result.update(_flatten_json(value, flat_key + "."))
        elif isinstance(value, (str, bool, int, float)):
            result[flat_key] = value
    return result


def parse_json_file(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, Mapping):
        return {}
    return _flatten_json(data)


# ---------------------------------------------------------------------------
# file discovery and the main entry point
# ---------------------------------------------------------------------------


def discover_config_files(roots: Sequence[Path] | None = None) -> list[Path]:
    """Finds game config files in the standard game locations.

    Returns Unreal Engine `GameUserSettings.ini` files and the common game
    `.ini` / `.cfg` / `.json` files, walking the roots (default:
    `%LOCALAPPDATA%` and `Documents\\My Games`) with a depth/size limit.
    """
    root_paths = [Path(root) for root in roots] if roots is not None else _default_roots()
    files: list[Path] = []
    for root in root_paths:
        if not root.is_dir():
            continue
        try:
            root_resolved = root.resolve()
        except OSError:
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(name for name in dirnames if name not in _PRUNED_DIRS)
            try:
                depth = len(Path(dirpath).resolve().relative_to(root_resolved).parts)
            except ValueError:
                depth = _MAX_DEPTH + 1
            if depth > _MAX_DEPTH or len(files) >= _MAX_FILES:
                dirnames[:] = []
                continue
            for name in sorted(filenames):
                if len(files) >= _MAX_FILES:
                    break
                lowered = name.lower()
                suffix = Path(name).suffix.lower()
                if lowered == "gameusersettings.ini" or suffix in (".ini", ".cfg", ".json"):
                    files.append(Path(dirpath) / name)
    return files


def parse_file(path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    if suffix in (".ini", ".cfg"):
        return parse_ini_file(path)
    if suffix == ".json":
        return parse_json_file(path)
    return {}


def normalize_settings(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Extracts the canonical settings dictionary from parsed config values."""
    settings: dict[str, Any] = {}
    for key, value in raw.items():
        canonical = _canonical_key(key)
        if not canonical:
            continue
        if any(token in canonical for token in _QUALITY_KEY_TOKENS):
            quality = _quality_from_value(value)
            if quality is not None:
                settings["quality"] = quality
        if any(token in canonical for token in _DLSS_KEY_TOKENS):
            flag = _as_bool(value)
            if flag is not None:
                settings["dlss"] = flag
        if any(token in canonical for token in _FSR_KEY_TOKENS):
            flag = _as_bool(value)
            if flag is not None:
                settings["fsr"] = flag
        if any(token in canonical for token in _RAY_TRACING_KEY_TOKENS):
            flag = _as_bool(value)
            if flag is not None:
                settings["ray_tracing"] = flag
        if any(token in canonical for token in _VSYNC_KEY_TOKENS):
            flag = _as_bool(value)
            if flag is not None:
                settings["vsync"] = flag
        if any(token in canonical for token in _FPS_LIMIT_KEY_TOKENS):
            limit = _as_int(value)
            if limit is not None and limit > 0:
                settings["fps_limit"] = limit
    return settings


def read_game_settings(
    *,
    files: Iterable[Path] | None = None,
    roots: Sequence[Path] | None = None,
) -> dict[str, Any]:
    """Returns the key graphics settings of the game, read from config files.

    With `files` an explicit list is parsed; otherwise the standard game
    locations are discovered (or `roots` is walked when given).
    """
    if files is not None:
        paths = [Path(path) for path in files]
    else:
        paths = discover_config_files(roots=roots)

    raw: dict[str, Any] = {}
    for path in paths:
        raw.update(parse_file(path))
    return normalize_settings(raw)
