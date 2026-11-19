from __future__ import annotations

import unittest

from framepulse_agent.capture import (
    CsvFrameParser,
    build_presentmon_args,
    classify_failure,
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
        self.assertIn("bez chybové zprávy", failure.message)


class PresentMonArgsTests(unittest.TestCase):
    def test_build_args(self) -> None:
        args = build_presentmon_args("C:/tools/PresentMon.exe", 4321)
        self.assertEqual(args[0], "C:/tools/PresentMon.exe")
        self.assertIn("--process_id", args)
        self.assertIn("4321", args)
        self.assertIn("--output_stdout", args)
        self.assertIn("--terminate_on_proc_exit", args)
        self.assertIn("--no_console_stats", args)


if __name__ == "__main__":
    unittest.main()
