from __future__ import annotations

import os
import unittest

from framepulse_agent.detection import (
    WindowInfo,
    choose_candidate,
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


if __name__ == "__main__":
    unittest.main()
