"""Aggregating frame times into FPS samples and computing session metrics.

Units: PresentMon provides frame times in milliseconds. All samples in the
graph are 2-second averages (configurable), `min_fps` is the 1% low.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

# A frame time longer than this is more likely a capture artifact (pause, alt-tab) than a frame.
MAX_FRAME_MS = 10_000.0

# The last unfinished sample is stored only if it has at least this much content.
MIN_PARTIAL_SAMPLE_SECONDS = 0.25


@dataclass(frozen=True)
class FpsMetrics:
    avg_fps: float
    min_fps: float
    max_fps: float
    duration_seconds: float
    frame_count: int
    sample_count: int
    # The total duration including warmup – used for the minimum session length.
    total_seconds: float = 0.0

    @property
    def is_usable(self) -> bool:
        return self.frame_count > 0 and self.duration_seconds > 0

    def as_session_values(self) -> dict[str, float | int]:
        return {
            "avg_fps": round(self.avg_fps, 2),
            "min_fps": round(self.min_fps, 2),
            "max_fps": round(self.max_fps, 2),
            "duration_seconds": int(round(self.duration_seconds)),
        }


class FrameAggregator:
    """Accepts frame times and builds samples + metrics from them.

    It is thread-safe: frames are added by the PresentMon reader thread, the
    state is read by the monitor and tray threads.
    """

    def __init__(
        self,
        sample_seconds: float = 2.0,
        warmup_seconds: float = 5.0,
        max_frame_ms: float = MAX_FRAME_MS,
    ) -> None:
        self._sample_ms = max(250.0, sample_seconds * 1000.0)
        self._warmup_ms = max(0.0, warmup_seconds * 1000.0)
        self._max_frame_ms = max_frame_ms

        self._lock = threading.Lock()
        self._elapsed_ms = 0.0
        self._frame_times: list[float] = []
        self._samples: list[tuple[float, float]] = []

        self._bucket_ms = 0.0
        self._bucket_frames = 0
        self._bucket_start_ms = 0.0
        self._bucket_open = False

    # -- vstup ---------------------------------------------------------------

    def add_frame(self, frame_ms: float) -> bool:
        """Adds a frame; returns True when this closed a new sample."""
        if frame_ms <= 0 or frame_ms > self._max_frame_ms:
            return False

        with self._lock:
            self._elapsed_ms += frame_ms

            if self._elapsed_ms <= self._warmup_ms:
                return False

            self._frame_times.append(frame_ms)

            if not self._bucket_open:
                self._bucket_open = True
                self._bucket_start_ms = self._elapsed_ms - frame_ms

            self._bucket_ms += frame_ms
            self._bucket_frames += 1

            if self._bucket_ms >= self._sample_ms:
                self._close_bucket_locked()
                return True

            return False

    def finish(self) -> None:
        """Closes the last (unfinished) sample."""
        with self._lock:
            if self._bucket_open and self._bucket_ms >= MIN_PARTIAL_SAMPLE_SECONDS * 1000.0:
                self._close_bucket_locked()
            self._bucket_open = False

    # -- output --------------------------------------------------------------

    def samples(self) -> list[tuple[float, float]]:
        with self._lock:
            return list(self._samples)

    def frame_count(self) -> int:
        with self._lock:
            return len(self._frame_times)

    def duration_seconds(self) -> float:
        with self._lock:
            return max(0.0, (self._elapsed_ms - self._warmup_ms) / 1000.0)

    def live_fps(self) -> float | None:
        with self._lock:
            # The average of the currently open sample so the value in the tray "lives".
            if self._bucket_open and self._bucket_ms >= 200.0:
                return self._bucket_frames / (self._bucket_ms / 1000.0)
            if self._samples:
                return self._samples[-1][1]
            return None

    def metrics(self) -> FpsMetrics:
        with self._lock:
            frame_times = list(self._frame_times)
            samples = list(self._samples)
            measured_ms = max(0.0, self._elapsed_ms - self._warmup_ms)

        measured_seconds = measured_ms / 1000.0
        total_seconds = self._elapsed_ms / 1000.0
        frame_count = len(frame_times)

        if frame_count == 0 or measured_seconds <= 0:
            return FpsMetrics(0.0, 0.0, 0.0, 0.0, 0, len(samples), total_seconds)

        avg_fps = frame_count / measured_seconds

        # 1% low = the mean of the worst 1 % of frame times converted back to FPS.
        worst_count = max(1, int(round(frame_count * 0.01)))
        worst = sorted(frame_times, reverse=True)[:worst_count]
        min_fps = 1000.0 / (sum(worst) / len(worst))

        max_fps = max((fps for _, fps in samples), default=avg_fps)

        return FpsMetrics(
            avg_fps=avg_fps,
            min_fps=min_fps,
            max_fps=max_fps,
            duration_seconds=measured_seconds,
            frame_count=frame_count,
            sample_count=len(samples),
            total_seconds=total_seconds,
        )

    # -- internal -------------------------------------------------------------

    def _close_bucket_locked(self) -> None:
        seconds = self._bucket_ms / 1000.0
        if seconds <= 0 or self._bucket_frames == 0:
            self._bucket_ms = 0.0
            self._bucket_frames = 0
            return

        fps = self._bucket_frames / seconds
        offset = max(0.0, (self._bucket_start_ms - self._warmup_ms) / 1000.0)
        self._samples.append((round(offset, 1), round(fps, 2)))

        self._bucket_start_ms += self._bucket_ms
        self._bucket_ms = 0.0
        self._bucket_frames = 0
