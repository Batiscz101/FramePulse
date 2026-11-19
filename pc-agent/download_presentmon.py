"""Stáhne oficiální PresentMon (2.x, x64) z GitHubu do `tools/PresentMon.exe`.

PresentMon je nástroj Intelu pro měření frame times přes ETW. Agent používá
konzolovou aplikaci 2.x – novější verze se poznají podle názvu assetu
`PresentMon-<verze>-x64.exe`.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path

API_URL = "https://api.github.com/repos/GameTechDev/PresentMon/releases/latest"
ASSET_PATTERN = re.compile(r"^PresentMon-[\d.]+-x64\.exe$", re.IGNORECASE)
DEFAULT_TARGET = Path(__file__).resolve().parent / "tools" / "PresentMon.exe"
USER_AGENT = "FramePulseAgent-Setup/1.0"
MIN_SIZE = 200_000


def _get_json(url: str) -> dict:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def _pick_asset(release: dict) -> dict:
    for asset in release.get("assets", []):
        if ASSET_PATTERN.match(str(asset.get("name", ""))):
            return asset
    raise RuntimeError(
        "V nejnovějším vydání PresentMonu není x64 konzolová aplikace "
        f"({release.get('tag_name', '?')})."
    )


def _download(url: str, target: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response, target.open("wb") as handle:
        shutil.copyfileobj(response, handle, length=64 * 1024)


def _verify(path: Path) -> None:
    size = path.stat().st_size
    if size < MIN_SIZE:
        raise RuntimeError(f"Stažený soubor je podezřele malý ({size} B).")
    with path.open("rb") as handle:
        if handle.read(2) != b"MZ":
            raise RuntimeError("Stažený soubor není spustitelný soubor Windows (chybí MZ).")


def install(target: Path, force: bool = False) -> int:
    if target.exists() and not force:
        print(f"PresentMon už existuje: {target}")
        print("Pro novou verzi spusťte: python download_presentmon.py --force")
        return 0

    print("Hledám nejnovější PresentMon na GitHubu…")
    try:
        release = _get_json(API_URL)
    except urllib.error.HTTPError as exc:
        print(f"GitHub API vrátilo HTTP {exc.code}. Zkuste to později.", file=sys.stderr)
        return 1
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        print(f"Nepodařilo se spojit s GitHubem: {exc}", file=sys.stderr)
        return 1

    tag = str(release.get("tag_name") or "?")
    asset = _pick_asset(release)
    print(f"Stahuji {asset['name']} ({tag})…")

    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(".exe.tmp")

    try:
        _download(str(asset["browser_download_url"]), temp)
        _verify(temp)
        temp.replace(target)
    except (urllib.error.URLError, OSError, RuntimeError, TimeoutError) as exc:
        temp.unlink(missing_ok=True)
        print(f"Stažení selhalo: {exc}", file=sys.stderr)
        return 1

    print(f"Hotovo: {target} ({target.stat().st_size // 1024} KB, {tag})")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stáhne PresentMon do složky tools/.")
    parser.add_argument(
        "--target",
        type=Path,
        default=DEFAULT_TARGET,
        help=f"cílová cesta (výchozí: {DEFAULT_TARGET})",
    )
    parser.add_argument("--force", action="store_true", help="stáhnout i když soubor existuje")
    args = parser.parse_args(argv)
    return install(args.target, args.force)


if __name__ == "__main__":
    raise SystemExit(main())
