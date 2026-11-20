"""Deriving a readable game name from the process name and window title."""

from __future__ import annotations

import re

# Window titles that are definitely not games (shell, system UI, error messages).
_BAD_TITLES = {
    "program manager",
    "desktop",
    "task switching",
    "settings",
    "microsoft text input application",
    "default ime",
    "msctfime ui",
    "untitled",
    "windows input experience",
}

_BAD_TITLE_PATTERN = re.compile(
    r"\b(error|crash|crash reporter|not responding|installer|installation|setup|"
    r"updater|update|uninstall|properties|compatibility|control panel|device manager|"
    r"task manager|file explorer)\b",
    re.IGNORECASE,
)

# Suffixes that do not belong to the game name.
_EXE_SUFFIX_PATTERN = re.compile(
    r"(?:[-_ ]?(?:win64|win32|x64|x86|shipping|retail|steam|gog|epic|egs))+$",
    re.IGNORECASE,
)

# Launchers that stick to the window title ("Game – Steam").
_TITLE_SUFFIX_PATTERN = re.compile(
    r"\s*[-–—]\s*(steam|gog(?:\.com)?|epic games(?: launcher)?|epic|ubisoft connect|"
    r"uplay|ea app|origin|battle\.net|battlenet|rockstar games launcher|xbox)\s*$",
    re.IGNORECASE,
)

# Brackets with technical details: "(x64)", "[1.6.1]", "(DX12)".
_TRAILING_BRACKETS = re.compile(r"\s*[\(\[\{][^\)\]\}]{0,24}[\)\]\}]\s*$")

_TECH_BRACKET = re.compile(
    r"\d|dx\d*|vulkan|opengl|x64|x86|win64|win32|windowed|fullscreen|version|verze|v\d",
    re.IGNORECASE,
)

_CAMEL_LOWER_UPPER = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_ACRONYM_LOWER = re.compile(r"(?<=[A-Z])(?=[A-Z][a-z])")
_LETTER_DIGIT = re.compile(r"(?<=[A-Za-z])(?=\d)")
_DIGIT_LETTER = re.compile(r"(?<=\d)(?=[A-Za-z])")
_SEPARATORS = re.compile(r"[-_]+")
_SPACES = re.compile(r"\s+")

MAX_TITLE_LENGTH = 64


def pretty_process_name(exe: str) -> str:
    """`Cyberpunk2077.exe` -> `Cyberpunk 2077`.

    Handles common Unreal Engine suffixes (`-Win64-Shipping`) and camelCase
    (`DOOMEternal` -> `DOOM Eternal`).
    """
    base = str(exe).strip().strip('"')
    base = re.split(r"[\\/]", base)[-1]
    if base.lower().endswith(".exe"):
        base = base[:-4]

    base = _EXE_SUFFIX_PATTERN.sub("", base)
    base = _ACRONYM_LOWER.sub(" ", base)
    base = _CAMEL_LOWER_UPPER.sub(" ", base)
    base = _LETTER_DIGIT.sub(" ", base)
    base = _DIGIT_LETTER.sub(" ", base)
    base = _SEPARATORS.sub(" ", base)
    base = _SPACES.sub(" ", base).strip()

    words: list[str] = []
    for word in base.split(" "):
        if not word:
            continue
        if word.islower():
            words.append(word.capitalize())
        else:
            words.append(word)

    return " ".join(words)


def clean_window_title(title: str | None) -> str | None:
    """Returns the usable window title, or None."""
    if not title:
        return None

    cleaned = title.strip().strip('"').strip()
    cleaned = _TITLE_SUFFIX_PATTERN.sub("", cleaned)

    # Remove technical brackets at the end (up to 2×), but not a meaningful subtitle.
    for _ in range(2):
        match = _TRAILING_BRACKETS.search(cleaned)
        if not match or not _TECH_BRACKET.search(match.group(0)):
            break
        cleaned = cleaned[: match.start()].strip()

    cleaned = _SPACES.sub(" ", cleaned).strip(" -–—:•·|")

    if len(cleaned) < 2 or len(cleaned) > MAX_TITLE_LENGTH:
        return None
    if cleaned.lower() in _BAD_TITLES:
        return None
    if _BAD_TITLE_PATTERN.search(cleaned):
        return None
    if cleaned.lower().endswith(".exe"):
        return None
    # Symbols or numbers alone are not a game name.
    if not re.search(r"[A-Za-zÀ-ž]", cleaned):
        return None

    return cleaned


def derive_game_name(exe: str, title: str | None = None) -> str:
    """Prefers the clean window title, otherwise builds the name from the .exe."""
    from_title = clean_window_title(title)
    from_exe = pretty_process_name(exe)

    if from_title:
        # A title that is just a version of the process name is not worth preferring.
        if from_title.lower().replace(" ", "") != from_exe.lower().replace(" ", ""):
            return from_title
        return from_title

    return from_exe or "Unknown game"
