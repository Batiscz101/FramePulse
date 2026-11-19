"""Spouštění PresentMonu a parsování jeho CSV výstupu.

Agent používá PresentMon 2.x (oficiální konzolová aplikace Intelu) s výstupem na
stdout:

    PresentMon --process_id <pid> --output_stdout --no_console_stats \
               --session_name FramePulseAgent --terminate_on_proc_exit

CSV formát se mezi verzemi mírně liší (2.x „FrameTime“, 1.x „msBetweenPresents“),
proto se sloupce hledají podle hlavičky, ne podle pořadí.
"""

from __future__ import annotations

import csv
import logging
import os
import re
import subprocess
import threading
from collections import deque
from dataclasses import dataclass
from pathlib import Path

LOG = logging.getLogger(__name__)

CREATE_NO_WINDOW = 0x08000000

# PresentMon 2.x vypisuje chyby na stderr – tohle je jeho hláška bez elevace.
PERMISSION_MARKERS = (
    "access denied",
    "failed to start trace session",
    "requires either administrative privileges",
    "performance log users",
    "0x80070005",
)

# Sloupec s délkou framu, v pořadí priority (všechny varianty napříč verzemi).
FRAME_TIME_COLUMNS = (
    "msbetweenpresents",
    "frametime",
    "msbetweenappstart",
    "msbetweendisplaychange",
)

PID_COLUMN = "processid"
APPLICATION_COLUMN = "application"

_NORMALIZE = re.compile(r"[^a-z0-9]")

MAX_REASONABLE_FRAME_MS = 10_000.0


def normalize_header(name: str) -> str:
    return _NORMALIZE.sub("", name.strip().lower())


@dataclass(frozen=True)
class CaptureFailure:
    kind: str  # "permission" | "session" | "missing" | "unknown"
    message: str


def _exe_basename(value: str) -> str:
    """`C:\\Games\\Game.EXE` -> `game` (pro porovnání sloupce Application)."""
    name = value.replace("\\", "/").rsplit("/", 1)[-1]
    return name[:-4] if name.endswith(".exe") else name


class CsvFrameParser:
    """Převádí řádky CSV z PresentMonu na frame times v ms."""

    def __init__(
        self,
        process_id: int | None = None,
        application: str | None = None,
        max_frame_ms: float = MAX_REASONABLE_FRAME_MS,
    ) -> None:
        self._process_id = process_id
        self._application = (application or "").lower()
        self._max_frame_ms = max_frame_ms

        self._frame_index: int | None = None
        self._pid_index: int | None = None
        self._app_index: int | None = None
        self._header: list[str] | None = None

        self.rows_seen = 0
        self.frames_seen = 0

    @property
    def header(self) -> list[str] | None:
        return list(self._header) if self._header else None

    def feed(self, line: str) -> float | None:
        """Zpracuje jeden řádek; vrátí frame time v ms nebo None."""
        text = line.strip("\r\n")
        if not text.strip():
            return None

        if self._header is None:
            if "," not in text:
                return None  # úvodní text PresentMonu, ne CSV
            cells = self._split(text)
            normalized = [normalize_header(cell) for cell in cells]
            if PID_COLUMN not in normalized and APPLICATION_COLUMN not in normalized:
                return None
            if not any(column in normalized for column in FRAME_TIME_COLUMNS):
                return None

            self._header = cells
            self._pid_index = self._index(normalized, PID_COLUMN)
            self._app_index = self._index(normalized, APPLICATION_COLUMN)
            for column in FRAME_TIME_COLUMNS:
                index = self._index(normalized, column)
                if index is not None:
                    self._frame_index = index
                    break

            LOG.debug("CSV hlavička PresentMonu: %s", ",".join(cells))
            if self._frame_index is None:
                LOG.warning("V CSV PresentMonu chybí sloupec s frame time: %s", cells)
            return None

        if self._frame_index is None:
            return None

        self.rows_seen += 1
        cells = self._split(text)
        if len(cells) <= self._frame_index:
            return None

        if self._pid_index is not None and self._process_id is not None:
            raw_pid = cells[self._pid_index].strip()
            if raw_pid and raw_pid.isdigit() and int(raw_pid) != self._process_id:
                return None

        if self._app_index is not None and self._application:
            raw_app = cells[self._app_index].strip().lower()
            if raw_app and raw_app not in {"<unknown>", "unknown"}:
                if _exe_basename(raw_app) != _exe_basename(self._application.lower()):
                    return None

        raw_frame = cells[self._frame_index].strip()
        if not raw_frame or raw_frame.upper() == "NA":
            return None

        try:
            frame_ms = float(raw_frame)
        except ValueError:
            return None

        if not (0.0 < frame_ms <= self._max_frame_ms):
            return None

        self.frames_seen += 1
        return frame_ms

    # -- interní -------------------------------------------------------------

    @staticmethod
    def _split(line: str) -> list[str]:
        try:
            return next(csv.reader([line]))
        except (csv.Error, StopIteration):
            return line.split(",")

    @staticmethod
    def _index(normalized: list[str], column: str) -> int | None:
        try:
            return normalized.index(column)
        except ValueError:
            return None


def classify_failure(text: str) -> CaptureFailure:
    lowered = (text or "").lower()

    if any(marker in lowered for marker in PERMISSION_MARKERS):
        return CaptureFailure(
            "permission",
            "PresentMon nemá oprávnění (access denied). Spusťte agenta jako správce, "
            "nebo přidejte svůj účet do skupiny „Performance Log Users“ a přihlaste se znovu.",
        )

    if "already running" in lowered or "existing session" in lowered:
        return CaptureFailure(
            "session",
            "Relace PresentMonu je obsazená. Restartujte agenta (nebo PC) a zkuste to znovu.",
        )

    first_line = next((line.strip() for line in (text or "").splitlines() if line.strip()), "")
    if not first_line:
        first_line = "PresentMon skončil bez chybové zprávy."

    return CaptureFailure("unknown", f"PresentMon selhal: {first_line}")


def build_presentmon_args(
    exe_path: Path | str,
    process_id: int,
    session_name: str = "FramePulseAgent",
) -> list[str]:
    """Argumenty PresentMonu 2.x pro měření jednoho procesu na stdout."""
    return [
        str(exe_path),
        "--process_id",
        str(process_id),
        "--output_stdout",
        "--no_console_stats",
        "--stop_existing_session",
        "--terminate_on_proc_exit",
        "--session_name",
        session_name,
        "--no_track_input",
    ]


def build_preflight_args(
    exe_path: Path | str,
    process_id: int,
    session_name: str = "FramePulseAgentPreflight",
) -> list[str]:
    return [
        str(exe_path),
        "--process_id",
        str(process_id),
        "--output_stdout",
        "--no_console_stats",
        "--stop_existing_session",
        "--session_name",
        session_name,
        "--timed",
        "1",
        "--terminate_after_timed",
    ]


class PresentMonCapture:
    """Živý PresentMon proces + čtecí vlákna pro stdout (CSV) a stderr."""

    def __init__(
        self,
        exe_path: Path,
        process_id: int,
        on_frame,
        session_name: str = "FramePulseAgent",
        application: str | None = None,
    ) -> None:
        self._exe_path = Path(exe_path)
        self._process_id = process_id
        self._on_frame = on_frame
        self._session_name = session_name
        self._application = application

        self._process: subprocess.Popen[str] | None = None
        self._stdout_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None
        self._stderr: deque[str] = deque(maxlen=40)
        self._parser: CsvFrameParser | None = None
        self._lock = threading.Lock()
        self.frames_received = 0
        self.started_at = None

    # -- životní cyklus ------------------------------------------------------

    def start(self) -> None:
        if self._process is not None:
            raise RuntimeError("Capture už běží.")

        args = build_presentmon_args(self._exe_path, self._process_id, self._session_name)
        LOG.info("Spouštím PresentMon: %s", " ".join(args))

        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE

        self._parser = CsvFrameParser(process_id=self._process_id, application=self._application)

        self._process = subprocess.Popen(
            args,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8-sig",
            errors="replace",
            bufsize=1,
            creationflags=CREATE_NO_WINDOW,
            startupinfo=startupinfo,
        )

        self._stdout_thread = threading.Thread(
            target=self._read_stdout, name="presentmon-stdout", daemon=True
        )
        self._stderr_thread = threading.Thread(
            target=self._read_stderr, name="presentmon-stderr", daemon=True
        )
        self._stdout_thread.start()
        self._stderr_thread.start()

    def stop(self, grace_seconds: float = 5.0) -> None:
        """Nechá PresentMon dojet (flush CSV), jinak ho ukončí."""
        process = self._process
        if process is None:
            return

        try:
            process.wait(timeout=grace_seconds)
        except subprocess.TimeoutExpired:
            LOG.info("PresentMon neukončil sám, ukončuji.")
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()

        for thread in (self._stdout_thread, self._stderr_thread):
            if thread is not None:
                thread.join(timeout=3)

    # -- stav ----------------------------------------------------------------

    @property
    def running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    @property
    def exit_code(self) -> int | None:
        return self._process.poll() if self._process else None

    @property
    def stderr_text(self) -> str:
        with self._lock:
            return "\n".join(self._stderr)

    @property
    def has_header(self) -> bool:
        parser = self._parser
        return parser is not None and parser.header is not None

    # -- čtení potrubí -------------------------------------------------------

    def _read_stdout(self) -> None:
        process = self._process
        parser = self._parser
        if process is None or process.stdout is None or parser is None:
            return

        try:
            for line in process.stdout:
                frame_ms = parser.feed(line)
                if frame_ms is None:
                    continue
                self.frames_received += 1
                try:
                    self._on_frame(frame_ms)
                except Exception:  # callback nesmí zabít čtecí vlákno
                    LOG.exception("Chyba při zpracování frame time")
        except Exception:
            LOG.exception("Čtení stdout PresentMonu selhalo")
        finally:
            try:
                process.stdout.close()
            except OSError:
                pass

    def _read_stderr(self) -> None:
        process = self._process
        if process is None or process.stderr is None:
            return

        try:
            for line in process.stderr:
                text = line.rstrip()
                if not text:
                    continue
                with self._lock:
                    self._stderr.append(text)
                LOG.debug("PresentMon: %s", text)
        except Exception:
            LOG.exception("Čtení stderr PresentMonu selhalo")
        finally:
            try:
                process.stderr.close()
            except OSError:
                pass


def preflight(exe_path: Path, timeout: float = 25.0) -> CaptureFailure | None:
    """Ověří, že PresentMon umí otevřít ETW relaci. None = vše v pořádku."""
    exe = Path(exe_path)
    if not exe.exists():
        return CaptureFailure(
            "missing",
            f"PresentMon nebyl nalezen ({exe}). Spusťte setup.bat nebo download_presentmon.py.",
        )

    args = build_preflight_args(exe, os.getpid())
    LOG.info("Ověřuji PresentMon: %s", " ".join(args))

    try:
        result = subprocess.run(
            args,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=CREATE_NO_WINDOW,
        )
    except subprocess.TimeoutExpired:
        return CaptureFailure("unknown", "PresentMon neodpověděl včas (timeout).")
    except OSError as exc:
        return CaptureFailure("missing", f"PresentMon se nepodařilo spustit: {exc}")

    if result.returncode == 0:
        return None

    details = "\n".join(part for part in (result.stderr, result.stdout) if part)
    return classify_failure(details)
