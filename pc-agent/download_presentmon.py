"""Downloads the official PresentMon (2.x, x64) from GitHub to `tools/PresentMon.exe`.

PresentMon is Intel's tool for measuring frame times over ETW. The agent uses
the 2.x console app; newer versions are recognized by the asset name
`PresentMon-<version>-x64.exe`.
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
        "The latest PresentMon release has no x64 console app "
        f"({release.get('tag_name', '?')})."
    )


def _download(url: str, target: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response, target.open("wb") as handle:
        shutil.copyfileobj(response, handle, length=64 * 1024)


def _verify(path: Path) -> None:
    size = path.stat().st_size
    if size < MIN_SIZE:
        raise RuntimeError(f"The downloaded file is suspiciously small ({size} B).")
    with path.open("rb") as handle:
        if handle.read(2) != b"MZ":
            raise RuntimeError("The downloaded file is not a Windows executable (MZ missing).")


def install(target: Path, force: bool = False) -> int:
    if target.exists() and not force:
        print(f"PresentMon already exists: {target}")
        print("For a new version, run: python download_presentmon.py --force")
        return 0

    print("Looking for the latest PresentMon on GitHub…")
    try:
        release = _get_json(API_URL)
    except urllib.error.HTTPError as exc:
        print(f"GitHub API returned HTTP {exc.code}. Try again later.", file=sys.stderr)
        return 1
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        print(f"Could not connect to GitHub: {exc}", file=sys.stderr)
        return 1

    tag = str(release.get("tag_name") or "?")
    asset = _pick_asset(release)
    print(f"Downloading {asset['name']} ({tag})…")

    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(".exe.tmp")

    try:
        _download(str(asset["browser_download_url"]), temp)
        _verify(temp)
        temp.replace(target)
    except (urllib.error.URLError, OSError, RuntimeError, TimeoutError) as exc:
        temp.unlink(missing_ok=True)
        print(f"Download failed: {exc}", file=sys.stderr)
        return 1

    print(f"Done: {target} ({target.stat().st_size // 1024} KB, {tag})")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Downloads PresentMon into the tools/ folder.")
    parser.add_argument(
        "--target",
        type=Path,
        default=DEFAULT_TARGET,
        help=f"target path (default: {DEFAULT_TARGET})",
    )
    parser.add_argument("--force", action="store_true", help="download even if the file exists")
    args = parser.parse_args(argv)
    return install(args.target, args.force)


if __name__ == "__main__":
    raise SystemExit(main())
