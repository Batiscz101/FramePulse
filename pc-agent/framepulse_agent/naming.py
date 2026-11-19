"""Odvození čitelného názvu hry z názvu procesu a titulku okna."""

from __future__ import annotations

import re

# Titulky, které rozhodně nejsou hra (shell, systémová UI, chybová hlášení).
_BAD_TITLES = {
    "program manager",
    "desktop",
    "task switching",
    "settings",
    "nastavení",
    "microsoft text input application",
    "default ime",
    "msctfime ui",
    "untitled",
    "windows input experience",
}

_BAD_TITLE_PATTERN = re.compile(
    r"\b(error|crash|crash reporter|not responding|installer|installation|setup|"
    r"updater|update|uninstall|properties|compatibility|control panel|device manager|"
    r"task manager|file explorer|správce úloh|průzkumník)\b",
    re.IGNORECASE,
)

# Přípony, které do názvu hry nepatří.
_EXE_SUFFIX_PATTERN = re.compile(
    r"(?:[-_ ]?(?:win64|win32|x64|x86|shipping|retail|steam|gog|epic|egs))+$",
    re.IGNORECASE,
)

# Launchery, které se lepí za titulek okna („Hra – Steam“).
_TITLE_SUFFIX_PATTERN = re.compile(
    r"\s*[-–—]\s*(steam|gog(?:\.com)?|epic games(?: launcher)?|epic|ubisoft connect|"
    r"uplay|ea app|origin|battle\.net|battlenet|rockstar games launcher|xbox)\s*$",
    re.IGNORECASE,
)

# Závorky s technickými údaji: „(x64)“, „[1.6.1]“, „(DX12)“.
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

    Zvládá i běžné sufixy Unreal Enginu (`-Win64-Shipping`) a camelCase
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
    """Vrátí použitelný titulek okna, nebo None."""
    if not title:
        return None

    cleaned = title.strip().strip('"').strip()
    cleaned = _TITLE_SUFFIX_PATTERN.sub("", cleaned)

    # Odstraň technické závorky na konci (max. 2×), ale ne smysluplný podtitul.
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
    # Samé symboly nebo čísla nejsou název hry.
    if not re.search(r"[A-Za-zÀ-ž]", cleaned):
        return None

    return cleaned


def derive_game_name(exe: str, title: str | None = None) -> str:
    """Preferuje čistý titulek okna, jinak sestaví název z .exe."""
    from_title = clean_window_title(title)
    from_exe = pretty_process_name(exe)

    if from_title:
        # Titulek, který je jen verzí názvu procesu, nemá cenu preferovat.
        if from_title.lower().replace(" ", "") != from_exe.lower().replace(" ", ""):
            return from_title
        return from_title

    return from_exe or "Neznámá hra"
