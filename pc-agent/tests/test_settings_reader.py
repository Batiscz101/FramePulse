from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from framepulse_agent import settings_reader as sr

UNREAL_GAME_USER_SETTINGS = """\
[/Script/EngineSettings.GameUserSettings]
ResolutionSizeX=2560
ResolutionSizeY=1440
bUseVsync=True
FrameRateLimit=144
"""

GAME_SETTINGS_INI = """\
[Video]
DLSSEnabled=true
FSR2Enabled=true
RayTracing=true
VsyncEnabled=false
MaxFPS=120
QualityPreset=Medium
"""

GAME_SETTINGS_JSON = """\
{
  "graphics": {
    "quality": "High",
    "dlss": true,
    "vsync": false,
    "fps_limit": 60
  },
  "misc": 42
}
"""


class ParseIniTextTests(unittest.TestCase):
    def test_unreal_keys_are_canonicalized(self) -> None:
        data = sr.parse_ini_text(UNREAL_GAME_USER_SETTINGS)
        self.assertTrue(any("frameratelimit" in key for key in data), data)
        self.assertTrue(any("vsync" in key for key in data), data)
        self.assertTrue(any("resolutionsizex" in key for key in data), data)

    def test_sections_are_folded_into_keys(self) -> None:
        data = sr.parse_ini_text("[Video]\nDLSSEnabled=true\n")
        self.assertTrue(any("dlss" in key for key in data), data)
        self.assertEqual(list(data.values()), ["true"])

    def test_comments_and_separators(self) -> None:
        data = sr.parse_ini_text("; comment\n# another\nKey: Value\nNoSeparator\n")
        self.assertEqual(data, {"key": "Value"})

    def test_quoted_values(self) -> None:
        data = sr.parse_ini_text('"My Game"=1\n[X]\nY="2"\n')
        self.assertEqual(data, {"mygame": "1", "xy": "2"})


class ParseJsonFileTests(unittest.TestCase):
    def test_flattens_nested_objects(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            path.write_text(GAME_SETTINGS_JSON, encoding="utf-8")
            data = sr.parse_json_file(path)
        self.assertEqual(data["graphics.quality"], "High")
        self.assertEqual(data["graphics.dlss"], True)
        self.assertEqual(data["graphics.vsync"], False)
        self.assertEqual(data["graphics.fps_limit"], 60)

    def test_garbage_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "broken.json"
            path.write_text("{not json", encoding="utf-8")
            self.assertEqual(sr.parse_json_file(path), {})


class ReadGameSettingsTests(unittest.TestCase):
    def test_unreal_game_user_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "GameUserSettings.ini"
            path.write_text(UNREAL_GAME_USER_SETTINGS, encoding="utf-8")
            settings = sr.read_game_settings(files=[path])
        self.assertEqual(settings["vsync"], True)
        self.assertEqual(settings["fps_limit"], 144)

    def test_scalability_number_becomes_quality(self) -> None:
        settings = sr.normalize_settings({"scalabilitylevel": 2})
        self.assertEqual(settings, {"quality": "High"})

    def test_generic_game_ini(self) -> None:
        settings = sr.normalize_settings(sr.parse_ini_text(GAME_SETTINGS_INI))
        self.assertEqual(
            settings,
            {
                "dlss": True,
                "fsr": True,
                "ray_tracing": True,
                "vsync": False,
                "fps_limit": 120,
                "quality": "Medium",
            },
        )

    def test_json_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            path.write_text(GAME_SETTINGS_JSON, encoding="utf-8")
            settings = sr.read_game_settings(files=[path])
        self.assertEqual(
            settings,
            {"quality": "High", "dlss": True, "vsync": False, "fps_limit": 60},
        )

    def test_unrelated_keys_are_ignored(self) -> None:
        settings = sr.normalize_settings({"video": 5, "totaltime": 3600, "music": True})
        self.assertEqual(settings, {})

    def test_fps_limit_zero_means_no_limit(self) -> None:
        settings = sr.normalize_settings({"frameratelimit": "0"})
        self.assertNotIn("fps_limit", settings)

    def test_garbage_files_are_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            broken = Path(tmp) / "broken.ini"
            broken.write_text("definitely not an ini file at all", encoding="utf-8")
            self.assertEqual(sr.read_game_settings(files=[broken]), {})
            missing = Path(tmp) / "missing.json"
            self.assertEqual(sr.read_game_settings(files=[missing]), {})

    def test_read_game_settings_from_roots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp) / "LocalAppData"
            docs = Path(tmp) / "My Games"
            game_dir = local / "Game" / "Saved" / "Config" / "Windows"
            game_dir.mkdir(parents=True)
            (game_dir / "GameUserSettings.ini").write_text(
                UNREAL_GAME_USER_SETTINGS, encoding="utf-8"
            )
            docs_game = docs / "SomeGame"
            docs_game.mkdir(parents=True)
            (docs_game / "Config.ini").write_text("[Video]\nMaxFPS=90\n", encoding="utf-8")

            discovered = sr.discover_config_files(roots=[local, docs])
            self.assertEqual(
                sorted(path.name for path in discovered), ["Config.ini", "GameUserSettings.ini"]
            )

            settings = sr.read_game_settings(roots=[local, docs])
            self.assertEqual(settings, {"vsync": True, "fps_limit": 90})

    def test_depth_and_file_limits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            deep = Path(tmp) / "deep"
            for _ in range(sr._MAX_DEPTH + 3):
                deep = deep / "level"
            deep.mkdir(parents=True)
            (deep / "Config.ini").write_text("[Video]\nMaxFPS=90\n", encoding="utf-8")
            self.assertEqual(sr.discover_config_files(roots=[Path(tmp)]), [])

    def test_json_settings_via_read_game_settings_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            path.write_text(json.dumps({"quality": "Ultra"}), encoding="utf-8")
            settings = sr.read_game_settings(files=[path])
        self.assertEqual(settings, {"quality": "Ultra"})


if __name__ == "__main__":
    unittest.main()
