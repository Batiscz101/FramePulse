from __future__ import annotations

import unittest
from pathlib import Path

from framepulse_agent.capture import (
    CsvFrameParser,
    PresentMonCapture,
    build_presentmon_args,
    classify_failure,
    failure_from_exception,
    map_runtime_to_api,
)

HEADER_V2 = (
    "Application,ProcessID,SwapChainAddress,Runtime,SyncInterval,PresentFlags,"
    "AllowsTearing,PresentMode,FrameTime,CPUBusy,CPUWait,GPUWait,"
    "msUntilRenderComplete,msUntilDisplayed"
)
ROW_V2 = "game.exe,1234,0x0,DXGI,1,0,1,Hardware,16.667,1.0,0.5,0.2,0.0,0.0"

HEADER_V1 = (
    "Application,ProcessID,SwapChainAddress,Runtime,SyncInterval,PresentFlags,"
    "AllowsTearing,PresentMode,msUntilRenderComplete,msUntilDisplayed,"
    "msBetweenDisplayChange,msInPresentAPI,msBetweenPresents,TimeInSeconds"
)


class CsvFrameParserTests(unittest.TestCase):
    def test_parses_v2_header(self) -> None:
        parser = CsvFrameParser(process_id=1234, application="game.exe")
        self.assertIsNone(parser.feed(HEADER_V2))
        self.assertIsNotNone(parser.header)
        self.assertAlmostEqual(parser.feed(ROW_V2), 16.667, places=3)
        self.assertEqual(parser.frames_seen, 1)

    def test_parses_v1_header(self) -> None:
        parser = CsvFrameParser(process_id=1234)
        parser.feed(HEADER_V1)
        row = "game.exe,1234,0x0,DXGI,1,0,1,Hardware,0,0,16.7,0.1,8.35,1.5"
        self.assertAlmostEqual(parser.feed(row), 8.35, places=3)

    def test_skips_other_processes(self) -> None:
        parser = CsvFrameParser(process_id=1234)
        parser.feed(HEADER_V2)
        self.assertIsNone(parser.feed(ROW_V2.replace(",1234,", ",9999,")))

    def test_skips_unknown_application(self) -> None:
        parser = CsvFrameParser(process_id=1234, application="other.exe")
        parser.feed(HEADER_V2)
        self.assertIsNone(parser.feed(ROW_V2))

    def test_application_with_path_matches_basename(self) -> None:
        parser = CsvFrameParser(process_id=1234, application="game.exe")
        parser.feed(HEADER_V2)
        row = ROW_V2.replace("game.exe", r"C:\\Games\\Game\\game.exe")
        self.assertIsNotNone(parser.feed(row))

    def test_accepts_unknown_application_marker(self) -> None:
        parser = CsvFrameParser(process_id=1234, application="game.exe")
        parser.feed(HEADER_V2)
        row = ROW_V2.replace("game.exe", "<unknown>")
        self.assertIsNotNone(parser.feed(row))

    def test_ignores_non_csv_and_na_values(self) -> None:
        parser = CsvFrameParser(process_id=1234)
        self.assertIsNone(parser.feed("PresentMon 2.6.0"))
        self.assertIsNone(parser.feed(""))
        parser.feed(HEADER_V2)
        self.assertIsNone(parser.feed(ROW_V2.replace("16.667", "NA")))
        self.assertIsNone(parser.feed("game.exe,1234,0x0"))
        self.assertIsNone(parser.feed(ROW_V2.replace("16.667", "not-a-number")))

    def test_ignores_absurd_frame_times(self) -> None:
        parser = CsvFrameParser(process_id=1234)
        parser.feed(HEADER_V2)
        self.assertIsNone(parser.feed(ROW_V2.replace("16.667", "-5")))
        self.assertIsNone(parser.feed(ROW_V2.replace("16.667", "999999")))


class FailureClassificationTests(unittest.TestCase):
    def test_permission_error(self) -> None:
        text = (
            "error: failed to start trace session: access denied.\n"
            'PresentMon requires either administrative privileges or to be run by a user in the\n'
            '"Performance Log Users" user group.'
        )
        failure = classify_failure(text)
        self.assertEqual(failure.kind, "permission")
        self.assertIn("Performance Log Users", failure.message)

    def test_missing_visual_cpp_runtime(self) -> None:
        text = (
            "The code execution cannot proceed because VCRUNTIME140.dll was not found. "
            "Reinstalling the program may fix this problem."
        )
        failure = classify_failure(text)
        self.assertEqual(failure.kind, "runtime")
        self.assertIn("Visual C++ Redistributable", failure.message)

    def test_runtime_failure_from_launch_error(self) -> None:
        failure = failure_from_exception(
            OSError(2, "The specified module could not be found")
        )
        self.assertEqual(failure.kind, "runtime")
        self.assertIn("x64", failure.message)

    def test_existing_session(self) -> None:
        failure = classify_failure("error: a session is already running.")
        self.assertEqual(failure.kind, "session")

    def test_unknown_error(self) -> None:
        failure = classify_failure("error: something odd happened")
        self.assertEqual(failure.kind, "unknown")
        self.assertIn("something odd", failure.message)

    def test_empty_error(self) -> None:
        failure = classify_failure("")
        self.assertEqual(failure.kind, "unknown")
        self.assertIn("without an error message", failure.message)


class PresentMonArgsTests(unittest.TestCase):
    def test_build_args(self) -> None:
        args = build_presentmon_args("C:/tools/PresentMon.exe", 4321)
        self.assertEqual(args[0], "C:/tools/PresentMon.exe")
        self.assertIn("--process_id", args)
        self.assertIn("4321", args)
        self.assertIn("--output_stdout", args)
        self.assertIn("--terminate_on_proc_exit", args)
        self.assertIn("--no_console_stats", args)


class GraphicsApiTests(unittest.TestCase):
    HEADER = "Application,ProcessID,Runtime,FrameTime\n"

    def _feed_api_row(self, parser: CsvFrameParser, runtime: str) -> None:
        parser.feed(self.HEADER)
        parser.feed(f"game.exe,1234,{runtime},16.667")

    def test_runtime_column_maps_to_api(self) -> None:
        parser = CsvFrameParser(process_id=1234)
        self._feed_api_row(parser, "DXGI")
        self.assertEqual(parser.graphics_api, "DX11")

    def test_d3d9_maps_to_dx9(self) -> None:
        parser = CsvFrameParser(process_id=1234)
        self._feed_api_row(parser, "D3D9")
        self.assertEqual(parser.graphics_api, "DX9")

    def test_vulkan_and_opengl(self) -> None:
        for runtime, expected in (("Vulkan", "Vulkan"), ("OpenGL", "OpenGL"), ("DX12", "DX12")):
            parser = CsvFrameParser(process_id=1234)
            self._feed_api_row(parser, runtime)
            self.assertEqual(parser.graphics_api, expected)

    def test_no_api_column_means_none(self) -> None:
        parser = CsvFrameParser(process_id=1234)
        parser.feed("Application,ProcessID,FrameTime\n")
        parser.feed("game.exe,1234,16.667")
        self.assertIsNone(parser.graphics_api)

    def test_capture_graphics_api_is_none_before_start(self) -> None:
        capture = PresentMonCapture(Path("PresentMon.exe"), 1234, on_frame=lambda frame_ms: None)
        self.assertIsNone(capture.graphics_api)


class MapRuntimeToApiTests(unittest.TestCase):
    def test_mapping(self) -> None:
        self.assertEqual(map_runtime_to_api("DXGI"), "DX11")
        self.assertEqual(map_runtime_to_api("D3D9"), "DX9")
        self.assertEqual(map_runtime_to_api("Vulkan"), "Vulkan")
        self.assertEqual(map_runtime_to_api("OpenGL"), "OpenGL")
        self.assertEqual(map_runtime_to_api("DX12"), "DX12")
        self.assertIsNone(map_runtime_to_api(""))
        self.assertIsNone(map_runtime_to_api("unknown"))


if __name__ == "__main__":
    unittest.main()
