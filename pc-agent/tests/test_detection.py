from __future__ import annotations

import os
import unittest
from ctypes import wintypes
from unittest import mock

from framepulse_agent.detection import (
    WindowInfo,
    choose_candidate,
    display_mode_for_window,
    game_window_facts,
    is_probable_game,
    process_alive,
)


def window(
    exe: str = "game.exe",
    *,
    pid: int = 100,
    title: str = "My Game",
    class_name: str = "UnrealWindow",
    area_ratio: float = 0.95,
    is_foreground: bool = False,
    is_minimized: bool = False,
    exe_path: str = r"D:\Games\MyGame\game.exe",
) -> WindowInfo:
    return WindowInfo(
        pid=pid,
        exe=exe,
        exe_path=exe_path,
        title=title,
        class_name=class_name,
        area_ratio=area_ratio,
        is_foreground=is_foreground,
        is_minimized=is_minimized,
    )


class IsProbableGameTests(unittest.TestCase):
    def test_big_window_is_candidate(self) -> None:
        self.assertTrue(is_probable_game(window()))

    def test_known_process_with_small_window(self) -> None:
        self.assertTrue(
            is_probable_game(
                window(area_ratio=0.2),
                known_processes=frozenset({"game.exe"}),
            )
        )

    def test_unknown_small_window_is_not_game(self) -> None:
        self.assertFalse(is_probable_game(window(area_ratio=0.2)))

    def test_browsers_are_ignored(self) -> None:
        for exe in ("chrome.exe", "msedge.exe", "firefox.exe"):
            self.assertFalse(is_probable_game(window(exe=exe)), exe)

    def test_launchers_and_chat_are_ignored(self) -> None:
        for exe in ("steam.exe", "discord.exe", "explorer.exe", "epicgameslauncher.exe"):
            self.assertFalse(is_probable_game(window(exe=exe)), exe)

    def test_helper_processes_are_ignored(self) -> None:
        for exe in ("crashpad_handler.exe", "updater.exe", "game_service.exe"):
            self.assertFalse(is_probable_game(window(exe=exe)), exe)

    def test_minimized_or_untitled_is_ignored(self) -> None:
        self.assertFalse(is_probable_game(window(is_minimized=True)))
        self.assertFalse(is_probable_game(window(title=" ")))

    def test_system_binaries_are_ignored(self) -> None:
        self.assertFalse(
            is_probable_game(
                window(
                    exe="weird.exe",
                    area_ratio=0.1,
                    exe_path=os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "System32", "weird.exe"),
                )
            )
        )

    def test_force_and_ignore_lists(self) -> None:
        self.assertTrue(
            is_probable_game(
                window(exe="weird.exe", area_ratio=0.1, exe_path=""),
                force_games=frozenset({"weird.exe"}),
            )
        )
        self.assertFalse(
            is_probable_game(window(), ignore_processes=frozenset({"game.exe"}))
        )

    def test_own_process_is_ignored(self) -> None:
        self.assertFalse(is_probable_game(window(pid=42), own_pids=frozenset({42})))

    def test_game_folder_hint(self) -> None:
        self.assertTrue(
            is_probable_game(
                window(
                    exe="whatever.exe",
                    area_ratio=0.3,
                    exe_path=r"C:\Program Files (x86)\Steam\steamapps\common\Game\whatever.exe",
                )
            )
        )


class ChooseCandidateTests(unittest.TestCase):
    def test_prefers_foreground(self) -> None:
        windows = [
            window(exe="a.exe", pid=101, area_ratio=0.9),
            window(exe="b.exe", pid=102, area_ratio=0.6, is_foreground=True),
        ]
        candidate = choose_candidate(windows)
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate.process_name, "b.exe")

    def test_prefers_known_game(self) -> None:
        windows = [
            window(exe="unknown.exe", pid=101, area_ratio=0.8),
            window(exe="known.exe", pid=102, area_ratio=0.5),
        ]
        candidate = choose_candidate(windows, known_processes=frozenset({"known.exe"}))
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate.process_name, "known.exe")
        self.assertTrue(candidate.is_known)

    def test_respects_blocked_processes(self) -> None:
        windows = [window(exe="blocked.exe", pid=101)]
        candidate = choose_candidate(
            windows, blocked={"blocked.exe": 100.0}, now=50.0
        )
        self.assertIsNone(candidate)

        candidate = choose_candidate(
            windows, blocked={"blocked.exe": 10.0}, now=50.0
        )
        self.assertIsNotNone(candidate)

    def test_none_when_nothing_matches(self) -> None:
        self.assertIsNone(choose_candidate([window(exe="chrome.exe")]))


class ProcessAliveTests(unittest.TestCase):
    def test_current_process_is_alive(self) -> None:
        self.assertTrue(process_alive(os.getpid()))

    def test_missing_process(self) -> None:
        self.assertFalse(process_alive(999_999))


def game_window(
    *,
    pid: int = 500,
    width: int = 2560,
    height: int = 1440,
    monitor: tuple[int, int, int, int] = (0, 0, 2560, 1440),
    topmost: bool = False,
    is_foreground: bool = True,
    area_ratio: float = 1.0,
) -> WindowInfo:
    rect = wintypes.RECT()
    rect.left, rect.top, rect.right, rect.bottom = 0, 0, width, height
    return WindowInfo(
        pid=pid,
        exe="game.exe",
        exe_path=r"D:\Games\MyGame\game.exe",
        title="My Game",
        class_name="UnrealWindow",
        area_ratio=area_ratio,
        is_foreground=is_foreground,
        is_minimized=False,
        rect=rect,
        monitor_rect=monitor,
        is_topmost=topmost,
        style=0x00C00000,
    )


class DisplayModeTests(unittest.TestCase):
    def test_fullscreen(self) -> None:
        self.assertEqual(display_mode_for_window(game_window(topmost=False)), "Fullscreen")

    def test_borderless(self) -> None:
        self.assertEqual(display_mode_for_window(game_window(topmost=True)), "Borderless")

    def test_windowed(self) -> None:
        self.assertEqual(display_mode_for_window(game_window(width=1280, height=720)), "Windowed")

    def test_approximate_monitor_covers_is_fullscreen(self) -> None:
        window = game_window(width=2550, height=1438, topmost=False)
        self.assertEqual(display_mode_for_window(window), "Fullscreen")


class GameWindowFactsTests(unittest.TestCase):
    def test_returns_resolution_and_display_mode(self) -> None:
        info = game_window(pid=77, width=2560, height=1440, topmost=False)
        with mock.patch("framepulse_agent.detection.enumerate_windows", return_value=[info]):
            self.assertEqual(game_window_facts(77), ("2560x1440", "Fullscreen"))

    def test_prefers_foreground_window_of_the_game(self) -> None:
        background = game_window(pid=500, width=2560, height=1440, is_foreground=False)
        foreground = game_window(pid=500, width=800, height=600, is_foreground=True)
        with mock.patch("framepulse_agent.detection.enumerate_windows", return_value=[background, foreground]):
            resolution, _ = game_window_facts(500)
        self.assertEqual(resolution, "800x600")

    def test_largest_window_when_not_in_foreground(self) -> None:
        small = game_window(pid=500, width=640, height=360, area_ratio=0.25, is_foreground=False)
        large = game_window(pid=500, width=2560, height=1440, area_ratio=0.95, is_foreground=False)
        with mock.patch("framepulse_agent.detection.enumerate_windows", return_value=[small, large]):
            resolution, _ = game_window_facts(500)
        self.assertEqual(resolution, "2560x1440")

    def test_falls_back_to_foreground_window_of_the_game(self) -> None:
        with mock.patch("framepulse_agent.detection.enumerate_windows", return_value=[]), \
                mock.patch(
                    "framepulse_agent.detection._foreground_window_of_game",
                    return_value=game_window(pid=77, width=1920, height=1080),
                ):
            resolution, _ = game_window_facts(77)
        self.assertEqual(resolution, "1920x1080")

    def test_resolution_is_filled_from_monitor_when_no_window(self) -> None:
        with mock.patch("framepulse_agent.detection.enumerate_windows", return_value=[]), \
                mock.patch("framepulse_agent.detection._foreground_window_of_game", return_value=None), \
                mock.patch("framepulse_agent.detection._monitor_resolution", return_value="1920x1080"):
            self.assertEqual(game_window_facts(999), ("1920x1080", None))

    def test_no_window_and_no_monitor(self) -> None:
        with mock.patch("framepulse_agent.detection.enumerate_windows", return_value=[]), \
                mock.patch("framepulse_agent.detection._foreground_window_of_game", return_value=None), \
                mock.patch("framepulse_agent.detection._monitor_resolution", return_value=None):
            self.assertEqual(game_window_facts(999), (None, None))


if __name__ == "__main__":
    unittest.main()
