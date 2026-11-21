"""Detection of running games on Windows.

A game = a process with a visible window that is not in the ignore list and
either is already known from the database, has a window covering most of the
screen, or lies in a typical game folder (Steam, Epic, Xbox…). The fact that
it is a game is confirmed by PresentMon – without captured frames, the
session is not saved.
"""

from __future__ import annotations

import ctypes
import logging
import os
import re
from dataclasses import dataclass
from ctypes import wintypes

import psutil

LOG = logging.getLogger(__name__)

# Window style: tool windows are palettes/overlays, never games.
WS_EX_TOOLWINDOW = 0x00000080
GWL_EXSTYLE = -20

MONITOR_DEFAULTTONEAREST = 2

MIN_WINDOW_AREA_RATIO = 0.45

WINDIR = os.environ.get("WINDIR", r"C:\Windows").lower()

# Applications that are definitely not games.
IGNORED_PROCESSES = frozenset(
    {
        # shell a Windows
        "explorer.exe",
        "searchapp.exe",
        "searchhost.exe",
        "startmenuexperiencehost.exe",
        "shellexperiencehost.exe",
        "applicationframehost.exe",
        "textinputhost.exe",
        "lockapp.exe",
        "dwm.exe",
        "taskmgr.exe",
        "regedit.exe",
        "mmc.exe",
        "control.exe",
        "cmd.exe",
        "powershell.exe",
        "pwsh.exe",
        "windowsterminal.exe",
        "openconsole.exe",
        "conhost.exe",
        "msiexec.exe",
        "notepad.exe",
        "wordpad.exe",
        "mspaint.exe",
        "snippingtool.exe",
        "systemsettings.exe",
        # browsers
        "chrome.exe",
        "msedge.exe",
        "msedgewebview2.exe",
        "firefox.exe",
        "brave.exe",
        "opera.exe",
        "opera_gx.exe",
        "vivaldi.exe",
        "iexplore.exe",
        # communication, launchers, media
        "discord.exe",
        "discordcanary.exe",
        "discordptb.exe",
        "teams.exe",
        "ms-teams.exe",
        "slack.exe",
        "zoom.exe",
        "spotify.exe",
        "steam.exe",
        "steamwebhelper.exe",
        "epicgameslauncher.exe",
        "epicwebhelper.exe",
        "battle.net.exe",
        "agent.exe",
        "galaxyclient.exe",
        "galaxyclienthelper.exe",
        "origin.exe",
        "eadesktop.exe",
        "eaapp.exe",
        "ubisoftconnect.exe",
        "upc.exe",
        "uplaywebcore.exe",
        "riotclientservices.exe",
        "riotclientux.exe",
        "rockstargameslauncher.exe",
        "xboxpcapp.exe",
        "gamebar.exe",
        "xboxgamebarwidgets.exe",
        "widgets.exe",
        # development, overlay and capture tools
        "code.exe",
        "devenv.exe",
        "idea64.exe",
        "pycharm64.exe",
        "rider64.exe",
        "obs64.exe",
        "obs32.exe",
        "streamlabs obs.exe",
        "msiafterburner.exe",
        "rtss.exe",
        "rtsshost.exe",
        "presentmon.exe",
        "python.exe",
        "pythonw.exe",
        "py.exe",
        "pyw.exe",
        # UWP apps that are not games
        "whatsapp.exe",
        "netflix.exe",
        "disney+.exe",
        "primevideo.exe",
        "photos.exe",
        "calculatorapp.exe",
        "windowscamera.exe",
        "mail.exe",
        "calendar.exe",
        "msnweather.exe",
        "news.exe",
        "stickynotes.exe",
        "phoneexperiencehost.exe",
    }
)

IGNORED_CLASSES = frozenset(
    {
        "Progman",
        "WorkerW",
        "Shell_TrayWnd",
        "Shell_SecondaryTrayWnd",
        "MultitaskingViewFrame",
        "ForegroundStaging",
    }
)

IGNORED_TITLES = frozenset(
    {
        "program manager",
        "settings",
        "task manager",
        "file explorer",
        "microsoft text input application",
        "search",
        "start",
        "notification center",
        "windows security",
    }
)

# Processes whose name suggests they are a helper tool, not a game.
_IGNORED_NAME_PATTERN = re.compile(
    r"^(?:"
    r"(?:setup|installer|unins\d*|update|updater|crashpad_handler|crashreporter|"
    r"rundll32|dllhost|svchost|consent|backgroundtaskhost|runtimebroker|"
    r"smartscreen|securityhealth|searchprotocolhost).*\.exe"
    r"|.*(?:helper|service)\.exe"
    r")$",
    re.IGNORECASE,
)

# Typical game install folders – treated as a hint for windowed (non-fullscreen) games.
GAME_PATH_MARKERS = (
    "\\steamapps\\common\\",
    "\\epic games\\",
    "\\gog galaxy\\games\\",
    "\\gog games\\",
    "\\xboxgames\\",
    "\\windowsapps\\",
    "\\riot games\\",
    "\\battle.net\\",
    "\\ubisoft game launcher\\games\\",
    "\\ea games\\",
    "\\origin games\\",
    "\\amazon games\\",
    "\\itch games\\",
)

user32 = ctypes.WinDLL("user32", use_last_error=True)

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
user32.EnumWindows.restype = wintypes.BOOL
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL
user32.IsIconic.argtypes = [wintypes.HWND]
user32.IsIconic.restype = wintypes.BOOL
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClassNameW.restype = ctypes.c_int
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetWindowRect.restype = wintypes.BOOL
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowLongW.restype = wintypes.LONG
user32.GetForegroundWindow.restype = wintypes.HWND
user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
user32.MonitorFromWindow.restype = wintypes.HANDLE
user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MONITORINFO)]
user32.GetMonitorInfoW.restype = wintypes.BOOL


@dataclass(frozen=True)
class WindowInfo:
    pid: int
    exe: str
    exe_path: str
    title: str
    class_name: str
    area_ratio: float
    is_foreground: bool
    is_minimized: bool


@dataclass(frozen=True)
class GameCandidate:
    pid: int
    process_name: str
    exe_path: str
    title: str
    area_ratio: float
    is_foreground: bool
    is_known: bool


def _process_snapshot() -> dict[int, tuple[str, str]]:
    """pid -> (process name, path to exe)."""
    result: dict[int, tuple[str, str]] = {}
    for process in psutil.process_iter(["pid", "name", "exe"]):
        try:
            info = process.info
            pid = int(info.get("pid") or 0)
            if pid <= 0:
                continue
            name = (info.get("name") or "").lower()
            exe_path = info.get("exe") or ""
            result[pid] = (name, exe_path)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return result


def _window_area_ratio(hwnd: int) -> float:
    rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return 0.0

    width = max(0, rect.right - rect.left)
    height = max(0, rect.bottom - rect.top)
    if width <= 0 or height <= 0:
        return 0.0

    monitor = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
    if not monitor:
        return 0.0

    info = MONITORINFO()
    info.cbSize = ctypes.sizeof(MONITORINFO)
    if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        return 0.0

    screen_width = max(0, info.rcMonitor.right - info.rcMonitor.left)
    screen_height = max(0, info.rcMonitor.bottom - info.rcMonitor.top)
    screen_area = screen_width * screen_height
    if screen_area <= 0:
        return 0.0

    return min(1.0, (width * height) / screen_area)


def enumerate_windows() -> list[WindowInfo]:
    """Returns visible windows with process information."""
    processes = _process_snapshot()
    foreground = int(user32.GetForegroundWindow() or 0)
    windows: list[WindowInfo] = []

    def callback(hwnd: int, _lparam: int) -> bool:
        try:
            if not user32.IsWindowVisible(hwnd):
                return True
            if user32.GetWindowTextLengthW(hwnd) <= 0:
                return True
            if user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW:
                return True

            title_buffer = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(hwnd, title_buffer, 512)
            title = title_buffer.value.strip()
            if not title:
                return True

            class_buffer = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, class_buffer, 256)
            class_name = class_buffer.value

            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            pid_value = int(pid.value)
            if pid_value <= 0 or pid_value not in processes:
                return True

            exe, exe_path = processes[pid_value]
            if not exe:
                return True

            windows.append(
                WindowInfo(
                    pid=pid_value,
                    exe=exe,
                    exe_path=exe_path,
                    title=title,
                    class_name=class_name,
                    area_ratio=_window_area_ratio(hwnd),
                    is_foreground=hwnd == foreground,
                    is_minimized=bool(user32.IsIconic(hwnd)),
                )
            )
        except Exception:  # the window disappeared meanwhile – no problem
            return True
        return True

    try:
        user32.EnumWindows(WNDENUMPROC(callback), 0)
    except Exception:
        LOG.exception("EnumWindows failed")

    return windows


def is_probable_game(
    window: WindowInfo,
    *,
    known_processes: frozenset[str] = frozenset(),
    ignore_processes: frozenset[str] = frozenset(),
    force_games: frozenset[str] = frozenset(),
    own_pids: frozenset[int] = frozenset(),
) -> bool:
    """Heuristic: can this window belong to a game?"""
    exe = window.exe.lower()
    if not exe or window.pid in own_pids or window.pid <= 4:
        return False
    if exe in IGNORED_PROCESSES or exe in ignore_processes:
        return False
    if _IGNORED_NAME_PATTERN.match(exe):
        return False
    if window.is_minimized:
        return False
    if not window.title.strip() or window.title.strip().lower() in IGNORED_TITLES:
        return False
    if window.class_name in IGNORED_CLASSES:
        return False

    exe_path = (window.exe_path or "").lower()
    if exe_path and exe_path.startswith(WINDIR) and exe not in force_games:
        return False

    if exe in force_games:
        return True
    if exe in known_processes:
        return True
    if window.area_ratio >= MIN_WINDOW_AREA_RATIO:
        return True
    if exe_path and any(marker in exe_path for marker in GAME_PATH_MARKERS):
        return True

    return False


def choose_candidate(
    windows: list[WindowInfo],
    *,
    known_processes: frozenset[str] = frozenset(),
    ignore_processes: frozenset[str] = frozenset(),
    force_games: frozenset[str] = frozenset(),
    own_pids: frozenset[int] = frozenset(),
    blocked: dict[str, float] | None = None,
    now: float = 0.0,
) -> GameCandidate | None:
    """Selects the most likely game (foreground → known → largest window)."""
    blocked = blocked or {}
    best: WindowInfo | None = None
    best_key: tuple[float, float, float] | None = None

    for window in windows:
        exe = window.exe.lower()
        if blocked.get(exe, 0.0) > now:
            continue
        if not is_probable_game(
            window,
            known_processes=known_processes,
            ignore_processes=ignore_processes,
            force_games=force_games,
            own_pids=own_pids,
        ):
            continue

        key = (
            1.0 if window.is_foreground else 0.0,
            1.0 if exe in known_processes or exe in force_games else 0.0,
            window.area_ratio,
        )
        if best_key is None or key > best_key:
            best = window
            best_key = key

    if best is None:
        return None

    return GameCandidate(
        pid=best.pid,
        process_name=best.exe,
        exe_path=best.exe_path,
        title=best.title,
        area_ratio=best.area_ratio,
        is_foreground=best.is_foreground,
        is_known=best.exe in known_processes,
    )


def process_create_time(pid: int) -> float | None:
    try:
        return psutil.Process(pid).create_time()
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return None


def process_alive(pid: int, create_time: float | None = None) -> bool:
    """Verifies that the process still exists (and that the PID was not reused in the meantime)."""
    try:
        process = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return False
    except psutil.AccessDenied:
        return True

    if create_time is not None:
        try:
            if abs(process.create_time() - create_time) > 0.5:
                return False
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass

    try:
        return process.status() != psutil.STATUS_ZOMBIE
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return True
