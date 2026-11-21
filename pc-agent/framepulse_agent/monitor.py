"""State machine of the agent: game detection, measurement via PresentMon,
session saving.

It runs in a single worker thread that checks windows and measurement state
every 2 seconds. The tray only reads `GameAgent.status()` and sends commands
(pause, queue flush, quit) – it never blocks.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from framepulse_agent.capture import (
    CaptureFailure,
    PresentMonCapture,
    classify_failure,
    failure_from_exception,
)
from framepulse_agent.config import Config, normalize_exe
from framepulse_agent.detection import (
    GameCandidate,
    choose_candidate,
    enumerate_windows,
    process_alive,
    process_create_time,
)
from framepulse_agent.metrics import FrameAggregator
from framepulse_agent.naming import derive_game_name
from framepulse_agent.supabase import SupabaseError
from framepulse_agent.upload import SessionRecord, Uploader, build_record

LOG = logging.getLogger(__name__)

STATE_IDLE = "idle"
STATE_STARTING = "starting"
STATE_CAPTURING = "capturing"
STATE_PAUSED = "paused"
STATE_ERROR = "error"

# How often to refresh the list of known games from Supabase.
KNOWN_REFRESH_SECONDS = 600.0

# How often to recalculate the file count in the outbox.
PENDING_REFRESH_SECONDS = 5.0

Notifier = Callable[[str, str], None]


@dataclass(frozen=True)
class AgentStatus:
    """Immutable status snapshot for the tray (read from another thread)."""

    state: str = STATE_IDLE
    game: str | None = None
    process_name: str | None = None
    live_fps: float | None = None
    samples: int = 0
    session_seconds: float = 0.0
    pending_uploads: int = 0
    last_upload: str | None = None
    last_error: str | None = None
    paused: bool = False

    @property
    def title(self) -> str:
        """Short description for the tooltip and the first menu item."""
        if self.state == STATE_CAPTURING and self.game:
            if self.live_fps:
                return f"{self.game} – {self.live_fps:.0f} FPS"
            return f"{self.game} – measuring"
        if self.state == STATE_STARTING and self.game:
            return f"{self.game} – starting"
        if self.state == STATE_PAUSED:
            return "Paused"
        if self.state == STATE_ERROR:
            return "Measurement error"
        return "Waiting for a game"


@dataclass
class _Active:
    """Work-in-progress session (modified only by the worker thread)."""

    pid: int
    process_name: str
    exe_path: str
    title: str
    create_time: float | None
    started_at: datetime
    aggregator: FrameAggregator
    start_monotonic: float
    capture: PresentMonCapture | None = None
    confirmed: bool = False
    last_frame_at: float | None = None
    last_frame_count: int = 0


class GameAgent:
    """Watches windows, starts PresentMon and saves finished sessions."""

    def __init__(
        self,
        config: Config,
        uploader: Uploader,
        *,
        notifier: Notifier | None = None,
    ) -> None:
        self._config = config
        self._uploader = uploader
        self._notifier = notifier

        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._paused = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None

        self._active: _Active | None = None
        self._state = STATE_IDLE
        self._blocked: dict[str, float] = {}
        self._known: frozenset[str] = frozenset()
        self._known_loaded_at = 0.0
        self._known_loading = False
        self._startup_issue: CaptureFailure | None = None

        self._last_error: str | None = None
        self._last_upload: str | None = None
        self._pending = 0
        self._pending_at = 0.0

        self._status = AgentStatus()

    # -- public API (tray) --------------------------------------------------

    def set_startup_issue(self, issue: CaptureFailure | None) -> None:
        self._startup_issue = issue
        if issue is not None:
            self._last_error = issue.message
            self._state = STATE_ERROR

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="game-agent", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 10.0) -> None:
        """Stops watching; the work-in-progress session is saved to the outbox."""
        self._stop_event.set()
        self._wake.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=timeout)
            if thread.is_alive():
                LOG.warning("The agent worker thread did not exit in time.")

    def toggle_pause(self) -> bool:
        """Returns True if the agent is paused after the call."""
        if self._paused.is_set():
            self._paused.clear()
            with self._lock:
                if self._state == STATE_PAUSED:
                    self._state = STATE_IDLE
            LOG.info("Measurement resumed.")
        else:
            self._paused.set()
            with self._lock:
                if self._state != STATE_ERROR:
                    self._state = STATE_PAUSED
            LOG.info("Measurement paused.")
        self._wake.set()
        self._publish()
        return self._paused.is_set()

    @property
    def paused(self) -> bool:
        return self._paused.is_set()

    def flush_outbox(self) -> None:
        """Sends waiting sessions in the background (the tray must not freeze)."""
        threading.Thread(
            target=self._flush_worker, name="outbox-flush", daemon=True
        ).start()

    def status(self) -> AgentStatus:
        with self._lock:
            return self._status

    # -- worker thread -----------------------------------------------------

    def _run(self) -> None:
        LOG.info("Watching games started (interval %.1f s).", self._config.poll_interval)
        # We load the game list and the queue in the background so the first detection doesn't wait on the network.
        self._refresh_known(force=True)

        pending = self._uploader.pending_count()
        if pending:
            LOG.info("Waiting %s sessions in the queue, trying to send.", pending)
            self.flush_outbox()

        while not self._stop_event.is_set():
            try:
                if self._paused.is_set():
                    if self._active is not None:
                        self._finish_active("pozastaveno")
                    self._publish()
                    self._sleep(self._config.poll_interval)
                    continue
                self._tick()
            except Exception:
                LOG.exception("Error in the monitoring loop")
                self._last_error = "Unexpected agent error (details in the log)."
                self._publish()
            self._sleep(self._config.poll_interval)

        self._finish_active("agent exit", try_upload=False)
        LOG.info("Game watching stopped.")

    def _sleep(self, seconds: float) -> None:
        self._wake.wait(seconds)
        self._wake.clear()

    def _tick(self) -> None:
        with self._lock:
            active = self._active

        if active is None:
            self._maybe_start()
        else:
            self._monitor(active)

        self._publish()

    # -- measurement start --------------------------------------------------------

    def _maybe_start(self) -> None:
        if time.monotonic() - self._known_loaded_at > KNOWN_REFRESH_SECONDS:
            self._refresh_known()

        now = time.monotonic()
        self._blocked = {exe: until for exe, until in self._blocked.items() if until > now}

        candidate = choose_candidate(
            enumerate_windows(),
            known_processes=self._known,
            ignore_processes=self._config.ignore_processes,
            force_games=self._config.force_games,
            own_pids=frozenset({os.getpid()}),
            blocked=self._blocked,
            now=now,
        )
        if candidate is None:
            return

        self._begin_session(candidate)

    def _begin_session(self, candidate: GameCandidate) -> None:
        name = derive_game_name(candidate.process_name, candidate.title)
        LOG.info(
            "Game detected: %s (%s, pid %s, window %.0f %%)",
            name,
            candidate.process_name,
            candidate.pid,
            candidate.area_ratio * 100,
        )

        aggregator = FrameAggregator(
            sample_seconds=self._config.sample_interval,
            warmup_seconds=self._config.warmup_seconds,
        )
        active = _Active(
            pid=candidate.pid,
            process_name=candidate.process_name,
            exe_path=candidate.exe_path,
            title=candidate.title,
            create_time=process_create_time(candidate.pid),
            started_at=datetime.now(timezone.utc),
            aggregator=aggregator,
            start_monotonic=time.monotonic(),
        )

        capture = PresentMonCapture(
            exe_path=self._config.presentmon_path,
            process_id=candidate.pid,
            on_frame=aggregator.add_frame,
            session_name="FramePulseAgent",
            application=candidate.process_name,
        )

        try:
            capture.start()
        except OSError as exc:
            failure = failure_from_exception(exc)
            LOG.error("PresentMon failed to start: %s", failure.message)
            self._block(candidate.process_name)
            self._set_error(failure.message)
            self._notify("FramePulse", failure.message)
            return

        active.capture = capture
        with self._lock:
            self._active = active
            self._state = STATE_STARTING

    # -- measurement progress -------------------------------------------------------

    def _monitor(self, active: _Active) -> None:
        capture = active.capture
        if capture is None:
            self._finish_active("without capture")
            return

        now = time.monotonic()
        frames = capture.frames_received

        if frames != active.last_frame_count:
            active.last_frame_count = frames
            active.last_frame_at = now
            if not active.confirmed and frames > 0:
                active.confirmed = True
                with self._lock:
                    self._state = STATE_CAPTURING
                name = derive_game_name(active.process_name, active.title)
                LOG.info("Measurement confirmed: %s", name)
                self._notify("FramePulse", f"Measuring game {name}.")

        if not process_alive(active.pid, active.create_time):
            LOG.info("Process %s exited.", active.process_name)
            self._finish_active("process exited")
            return

        if not capture.running:
            # PresentMon exited even though the process is alive – usually a permission error.
            capture.stop(grace_seconds=1.0)
            if frames == 0:
                failure = classify_failure(capture.stderr_text)
                LOG.error("PresentMon failed: %s", failure.message)
                self._handle_failure(active, failure)
                return
            self._finish_active("PresentMon exited")
            return

        elapsed = now - active.start_monotonic

        if not active.confirmed and elapsed > self._config.confirm_frames_seconds:
            LOG.info(
                "PresentMon captured no frames for %s in %.0f s – not a game.",
                active.process_name,
                elapsed,
            )
            self._block(active.process_name)
            self._finish_active("no frames")
            return

        if active.confirmed and active.last_frame_at is not None:
            if now - active.last_frame_at > self._config.stall_seconds:
                LOG.info(
                    "Frames stopped arriving for %.0f s, closing the session.",
                    now - active.last_frame_at,
                )
                self._finish_active("frames stopped")

    def _handle_failure(self, active: _Active, failure: CaptureFailure) -> None:
        self._block(active.process_name)
        with self._lock:
            self._active = None
            self._state = STATE_ERROR
        self._last_error = failure.message
        self._notify("Measurement failed", failure.message)

    # -- session finish -----------------------------------------------------

    def _finish_active(
        self,
        reason: str,
        *,
        try_upload: bool = True,
    ) -> None:
        with self._lock:
            active = self._active
            self._active = None
            if self._state in (STATE_STARTING, STATE_CAPTURING):
                self._state = STATE_IDLE

        if active is None:
            return

        if active.capture is not None:
            active.capture.stop()

        active.aggregator.finish()
        metrics = active.aggregator.metrics()

        if (
            not metrics.is_usable
            or metrics.total_seconds < self._config.min_session_seconds
        ):
            LOG.info(
                "Session discarded (%s): %.1f s total, %.1f s measured, %s frames.",
                reason,
                metrics.total_seconds,
                metrics.duration_seconds,
                metrics.frame_count,
            )
            self._publish()
            return

        name = derive_game_name(active.process_name, active.title)
        record = build_record(
            process_name=active.process_name,
            name=name,
            started_at=active.started_at,
            metrics=metrics,
            samples=active.aggregator.samples(),
        )
        self._known = self._known | {active.process_name}

        if try_upload:
            threading.Thread(
                target=self._submit_record,
                args=(record,),
                name="session-upload",
                daemon=True,
            ).start()
        else:
            try:
                self._uploader.save(record)
                LOG.info("Session %s saved to the queue on exit.", record.name)
            except OSError:
                LOG.exception("Failed to save session %s to the queue.", record.name)

        LOG.info(
            "Session %s: %.1f s, average %.1f FPS, 1%% low %.1f FPS, %s samples (%s).",
            name,
            metrics.duration_seconds,
            metrics.avg_fps,
            metrics.min_fps,
            metrics.sample_count,
            reason,
        )
        self._publish()

    # -- helpers -------------------------------------------------------------

    def _submit_record(self, record: SessionRecord) -> None:
        """The upload runs outside the detection loop so a network outage does not delay measurement."""
        ok = self._uploader.submit(record)
        with self._lock:
            if ok:
                self._last_error = None
                self._last_upload = f"{record.name} – {record.avg_fps:.0f} FPS"
            else:
                self._last_error = self._uploader.last_error

        if ok and self._config.notify_on_upload:
            self._notify(
                "FramePulse",
                f"Saved: {record.name}, {record.avg_fps:.0f} FPS average.",
            )
        self._publish()

    def _flush_worker(self) -> None:
        try:
            uploaded, failed = self._uploader.flush()
        except Exception:
            LOG.exception("Queue flush failed")
            return
        if uploaded:
            self._last_error = None
        self._publish()
        if uploaded and failed == 0:
            self._notify("FramePulse", f"Sent from the queue: {uploaded} session(s).")

    def _refresh_known(self, force: bool = False) -> None:
        now = time.monotonic()
        if self._known_loading:
            return
        if not force and now - self._known_loaded_at < KNOWN_REFRESH_SECONDS:
            return

        self._known_loading = True
        self._known_loaded_at = now
        threading.Thread(target=self._load_known, name="known-games", daemon=True).start()

    def _load_known(self) -> None:
        try:
            games = self._uploader.client.list_games()
        except SupabaseError as exc:
            LOG.warning("Failed to load the game list: %s", exc)
            return
        except Exception:
            LOG.exception("Failed to load the game list")
            return
        finally:
            self._known_loading = False

        known = {
            normalize_exe(str(game.get("process_name") or ""))
            for game in games
            if game.get("process_name")
        }
        self._known = frozenset(name for name in known if name)
        LOG.debug("Known games: %s", ", ".join(sorted(self._known)) or "–")

    def _block(self, process_name: str) -> None:
        exe = normalize_exe(process_name)
        if not exe:
            return
        self._blocked[exe] = time.monotonic() + self._config.no_game_cooldown_seconds
        LOG.info(
            "Process %s will not be measured for %s s.",
            exe,
            int(self._config.no_game_cooldown_seconds),
        )

    def _set_error(self, message: str) -> None:
        with self._lock:
            self._state = STATE_ERROR
            self._last_error = message
        self._publish()

    def _notify(self, title: str, message: str) -> None:
        if not self._config.notifications or self._notifier is None:
            return
        try:
            self._notifier(title, message)
        except Exception:
            LOG.debug("Failed to show the notification", exc_info=True)

    def _publish(self) -> None:
        now = time.monotonic()
        if now - self._pending_at > PENDING_REFRESH_SECONDS:
            self._pending = self._uploader.pending_count()
            self._pending_at = now

        with self._lock:
            active = self._active
            state = self._state
            if self._paused.is_set() and state != STATE_ERROR:
                state = STATE_PAUSED

            if active is None:
                status = AgentStatus(
                    state=state,
                    pending_uploads=self._pending,
                    last_upload=self._last_upload,
                    last_error=self._last_error,
                    paused=self._paused.is_set(),
                )
            else:
                name = derive_game_name(active.process_name, active.title)
                status = AgentStatus(
                    state=state,
                    game=name,
                    process_name=active.process_name,
                    live_fps=active.aggregator.live_fps() if active.confirmed else None,
                    samples=len(active.aggregator.samples()),
                    session_seconds=active.aggregator.duration_seconds(),
                    pending_uploads=self._pending,
                    last_upload=self._last_upload,
                    last_error=self._last_error,
                    paused=self._paused.is_set(),
                )
            self._status = status
