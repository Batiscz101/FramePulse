"""Assembling the session record and sending it to Supabase (with an offline queue)."""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

from framepulse_agent.metrics import FpsMetrics
from framepulse_agent.supabase import SupabaseClient, SupabaseError, is_duplicate

LOG = logging.getLogger(__name__)


@dataclass
class SessionRecord:
    process_name: str
    name: str
    played_at: str
    avg_fps: float
    min_fps: float
    max_fps: float
    duration_seconds: int
    samples: list[dict[str, float]] = field(default_factory=list)
    session_id: str | None = None

    def to_json(self) -> str:
        return json.dumps(self.__dict__, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SessionRecord":
        return cls(
            process_name=str(data["process_name"]),
            name=str(data["name"]),
            played_at=str(data["played_at"]),
            avg_fps=float(data.get("avg_fps", 0)),
            min_fps=float(data.get("min_fps", 0)),
            max_fps=float(data.get("max_fps", 0)),
            duration_seconds=int(data.get("duration_seconds", 0)),
            samples=[dict(item) for item in data.get("samples", [])],
            session_id=data.get("session_id"),
        )


def build_record(
    *,
    process_name: str,
    name: str,
    started_at: datetime,
    metrics: FpsMetrics,
    samples: Iterable[tuple[float, float]],
) -> SessionRecord:
    """Converts measured data to a row for `sessions` + bodies for `fps_samples`."""
    played_at = started_at.astimezone(timezone.utc).isoformat(timespec="seconds")
    values = metrics.as_session_values()

    return SessionRecord(
        process_name=process_name,
        name=name,
        played_at=played_at,
        avg_fps=float(values["avg_fps"]),
        min_fps=float(values["min_fps"]),
        max_fps=float(values["max_fps"]),
        duration_seconds=int(values["duration_seconds"]),
        samples=[
            {"timestamp_offset": round(float(offset), 2), "fps": round(float(fps), 2)}
            for offset, fps in samples
        ],
    )


def chunked(items: Iterable[Any], size: int) -> Iterator[list[Any]]:
    batch: list[Any] = []
    for item in items:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


class Uploader:
    """Saves sessions to Supabase; on outage, holds them in `outbox/` and tries again.

    The write is idempotent: sessions and games have pre-generated UUIDs,
    samples are deleted before insertion and inserted with
    `resolution=ignore-duplicates`.
    """

    def __init__(
        self,
        client: SupabaseClient,
        outbox_dir: Path,
        chunk_size: int = 500,
    ) -> None:
        self._client = client
        self._outbox = Path(outbox_dir)
        self._outbox.mkdir(parents=True, exist_ok=True)
        self._chunk_size = max(1, chunk_size)
        self.last_error: str | None = None

    # -- public API ---------------------------------------------------------

    @property
    def client(self) -> SupabaseClient:
        return self._client

    def pending_count(self) -> int:
        try:
            return sum(1 for _ in self._outbox.glob("*.json"))
        except OSError:
            return 0

    def submit(self, record: SessionRecord) -> bool:
        """Tries to send the session; on error leaves it in the queue. Never raises."""
        path = self.save(record)
        try:
            self._upload(record, path)
        except SupabaseError as exc:
            self.last_error = str(exc)
            LOG.error("Session upload failed (%s). Remains in the queue: %s", exc, path.name)
            return False
        except Exception:
            self.last_error = "Unexpected error during session upload."
            LOG.exception("Unexpected error during session upload")
            return False

        self.last_error = None
        self._delete(path)
        return True

    def flush(self) -> tuple[int, int]:
        """Tries to send all waiting sessions. Returns (successes, errors)."""
        uploaded = 0
        failed = 0

        for path in sorted(self._outbox.glob("*.json")):
            try:
                record = SessionRecord.from_dict(
                    json.loads(path.read_text(encoding="utf-8"))
                )
            except (OSError, ValueError, KeyError, TypeError):
                LOG.exception("Corrupted file in the queue: %s", path.name)
                failed += 1
                continue

            try:
                self._upload(record, path)
            except SupabaseError as exc:
                failed += 1
                self.last_error = str(exc)
                LOG.warning("Queue: %s still waiting (%s)", path.name, exc)
            except Exception:
                failed += 1
                LOG.exception("Queue: unexpected error with %s", path.name)
            else:
                uploaded += 1
                self._delete(path)

        if uploaded:
            LOG.info("Sent from the queue: %s session(s).", uploaded)
        return uploaded, failed

    def save(self, record: SessionRecord, path: Path | None = None) -> Path:
        self._outbox.mkdir(parents=True, exist_ok=True)
        target = path or (
            self._outbox / f"{int(time.time() * 1000):013d}-{uuid.uuid4().hex[:8]}.json"
        )
        temp = target.with_suffix(".json.tmp")
        temp.write_text(record.to_json(), encoding="utf-8")
        temp.replace(target)
        return target

    # -- internal -------------------------------------------------------------

    def _upload(self, record: SessionRecord, path: Path) -> None:
        game = self._client.find_game(record.process_name)

        if game is None:
            created = self._client.create_game(record.name, record.process_name)
            if created is None:
                game = self._client.find_game(record.process_name)
            else:
                game = created

        if not game or not game.get("id"):
            raise SupabaseError(
                f"Could not create game '{record.name}' or find it in the games table."
            )

        game_id = str(game["id"])

        if record.session_id is None:
            record.session_id = str(uuid.uuid4())

        # Write the id before anything is sent – a retry then never creates a duplicate.
        self.save(record, path)

        self._client.create_session(
            session_id=record.session_id,
            game_id=game_id,
            played_at=record.played_at,
            avg_fps=round(record.avg_fps, 2),
            min_fps=round(record.min_fps, 2),
            max_fps=round(record.max_fps, 2),
            duration_seconds=int(record.duration_seconds),
        )

        # Idempotent sample write: old rows are deleted before insertion.
        # If a duplicate still occurs (previous attempt), the whole block is repeated
        # from the start – otherwise some samples would be missing.
        rows = [
            {
                "session_id": record.session_id,
                "timestamp_offset": float(sample["timestamp_offset"]),
                "fps": float(sample["fps"]),
            }
            for sample in record.samples
        ]

        for attempt in (1, 2):
            try:
                self._client.delete_samples(record.session_id)
                for batch in chunked(rows, self._chunk_size):
                    self._client.insert_samples(batch)
                break
            except SupabaseError as exc:
                if attempt == 1 and is_duplicate(exc):
                    LOG.warning(
                        "Samples of session %s already partially exist, rewriting.",
                        record.session_id,
                    )
                    continue
                raise

        LOG.info(
            "Uploaded: %s (%s) – %s samples, average %.1f FPS",
            record.name,
            record.process_name,
            len(rows),
            record.avg_fps,
        )

    def _delete(self, path: Path) -> None:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            LOG.warning("Failed to delete the queue file: %s", path)
