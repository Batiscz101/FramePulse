from __future__ import annotations

import unittest

from framepulse_agent.naming import clean_window_title, derive_game_name, pretty_process_name


class PrettyProcessNameTests(unittest.TestCase):
    def test_camel_case_and_digits(self) -> None:
        self.assertEqual(pretty_process_name("Cyberpunk2077.exe"), "Cyberpunk 2077")

    def test_camel_case_without_digits(self) -> None:
        self.assertEqual(pretty_process_name("DOOMEternal.exe"), "DOOM Eternal")
        self.assertEqual(pretty_process_name("EldenRing.exe"), "Elden Ring")

    def test_unreal_suffix(self) -> None:
        self.assertEqual(pretty_process_name("MyGame-Win64-Shipping.exe"), "My Game")

    def test_removes_path_and_extension(self) -> None:
        self.assertEqual(
            pretty_process_name(r"C:\Games\Hades\Hades.exe"),
            "Hades",
        )

    def test_keeps_word_case(self) -> None:
        self.assertEqual(pretty_process_name("HITMAN3.exe"), "HITMAN 3")


class CleanWindowTitleTests(unittest.TestCase):
    def test_removes_launcher_suffix(self) -> None:
        self.assertEqual(clean_window_title("Cyberpunk 2077 - Steam"), "Cyberpunk 2077")
        self.assertEqual(clean_window_title("Hades — Epic Games Launcher"), "Hades")

    def test_removes_technical_brackets(self) -> None:
        self.assertEqual(clean_window_title("My Game (x64)"), "My Game")
        self.assertEqual(clean_window_title("My Game [1.6.1]"), "My Game")

    def test_keeps_meaningful_brackets(self) -> None:
        self.assertEqual(
            clean_window_title("Sea of Thieves (Insider)"),
            "Sea of Thieves (Insider)",
        )

    def test_rejects_non_game_titles(self) -> None:
        self.assertIsNone(clean_window_title("Settings"))
        self.assertIsNone(clean_window_title("Program Manager"))
        self.assertIsNone(clean_window_title("Game.exe"))
        self.assertIsNone(clean_window_title("123456"))
        self.assertIsNone(clean_window_title(""))

    def test_rejects_error_windows(self) -> None:
        self.assertIsNone(clean_window_title("Crash Reporter"))
        self.assertIsNone(clean_window_title("Game - Not Responding"))


class DeriveGameNameTests(unittest.TestCase):
    def test_prefers_window_title(self) -> None:
        self.assertEqual(
            derive_game_name("Cyberpunk2077.exe", "Cyberpunk 2077"),
            "Cyberpunk 2077",
        )

    def test_falls_back_to_process(self) -> None:
        self.assertEqual(derive_game_name("EldenRing.exe", None), "Elden Ring")
        self.assertEqual(derive_game_name("EldenRing.exe", "Settings"), "Elden Ring")

    def test_unknown_process(self) -> None:
        self.assertEqual(derive_game_name("", None), "Unknown game")


if __name__ == "__main__":
    unittest.main()
