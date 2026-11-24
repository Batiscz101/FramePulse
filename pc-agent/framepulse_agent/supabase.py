"""Minimal PostgREST (Neon Data API) client without heavy dependencies."""

from __future__ import annotations

import logging
import math
import time
from collections.abc import Mapping
from typing import Any

import requests

LOG = logging.getLogger(__name__)

TABLE_MISSING_CODES = frozenset({"42P01", "PGRST205"})
PERMISSION_CODES = frozenset({"42501"})
DUPLICATE_CODE = "23505"

# The live_status table has a single row; this is its fixed id.
LIVE_STATUS_ID = "default"

DEFAULT_TIMEOUT = 20.0
DEFAULT_RETRIES = 3

# ---------------------------------------------------------------------------
# Schema columns (mirror of neon/neon_schema.sql). Payloads are sanitized
# against these so a stray/invalid field only drops that field, never the
# whole write.
# ---------------------------------------------------------------------------

BOOLEAN_COLUMNS = frozenset({"is_playing"})

# Columns PostgREST reads as numbers; string values in these columns are
# parsed, anything not numeric is dropped instead of failing the request.
NUMERIC_COLUMNS = frozenset({
    "current_fps", "gpu_temp", "cpu_temp", "gpu_load", "cpu_load",
    "avg_fps", "min_fps", "max_fps", "duration_seconds",
    "gpu_temp_avg", "gpu_temp_max", "gpu_load_avg", "cpu_temp_avg", "cpu_load_avg",
    "timestamp_offset", "fps",
})

LIVE_STATUS_COLUMNS = frozenset({
    "id", "is_playing", "game_name", "process_name", "started_at",
    "current_fps", "gpu_temp", "cpu_temp", "gpu_load", "cpu_load",
    "resolution", "graphics_api", "updated_at",
})

SESSIONS_COLUMNS = frozenset({
    "id", "game_id", "played_at", "avg_fps", "min_fps", "max_fps",
    "duration_seconds", "resolution", "display_mode", "graphics_api",
    "game_settings", "gpu_temp_avg", "gpu_temp_max", "gpu_load_avg",
    "cpu_temp_avg", "cpu_load_avg",
})

FPS_SAMPLES_COLUMNS = frozenset({
    "session_id", "timestamp_offset", "fps", "gpu_temp", "cpu_temp",
    "gpu_load", "cpu_load",
})


def sanitize_row(columns: frozenset[str], row: Mapping[str, Any]) -> dict[str, Any]:
    """Keeps only schema columns with usable values; drops the rest.

    Numbers must convert to finite floats (strings accepted), other values
    must be non-empty strings or mappings/lists – invalid entries are dropped
    one by one instead of failing the whole request.
    """
    sanitized: dict[str, Any] = {}
    for key, value in row.items():
        if key not in columns:
            continue
        if value is None:
            sanitized[key] = None
            continue
        if isinstance(value, bool) and key in BOOLEAN_COLUMNS:
            sanitized[key] = value
            continue
        try:
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                number = float(value)
                if math.isfinite(number):
                    sanitized[key] = number
                continue
            if isinstance(value, str):
                text = value.strip()
                if not text:
                    continue
                if key in NUMERIC_COLUMNS:
                    number = float(text)
                    if math.isfinite(number):
                        sanitized[key] = number
                    continue
                sanitized[key] = text
                continue
            if isinstance(value, dict):
                if value:
                    sanitized[key] = value
                continue
            if isinstance(value, (list, tuple)):
                if value:
                    sanitized[key] = list(value)
                continue
        except (TypeError, ValueError):
            continue
    return sanitized


class SupabaseError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        code: str | None = None,
        details: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.details = details


def is_duplicate(error: SupabaseError) -> bool:
    """True when the write hit an existing row (unique constraint)."""
    return error.code == DUPLICATE_CODE or error.status == 409


def describe_response(status: int, payload: dict[str, Any] | None) -> SupabaseError:
    """Converts the PostgREST error response to a readable message."""
    payload = payload or {}
    code = str(payload.get("code") or "")
    message = str(payload.get("message") or "")
    details = str(payload.get("details") or "") or None
    lowered = message.lower()

    if code in TABLE_MISSING_CODES or "schema cache" in lowered:
        return SupabaseError(
            "The tables are not created. Run neon/neon_schema.sql in the SQL Editor.",
            status=status,
            code=code,
            details=details,
        )

    if code in PERMISSION_CODES or "permission denied" in lowered:
        return SupabaseError(
            "The database rejected the write – missing grants. "
            "Run neon/neon_schema.sql again.",
            status=status,
            code=code,
            details=details,
        )

    if status in (401, 403):
        return SupabaseError(
            "The data endpoint rejected the request – check the neon_url and "
            "neon_api_key in config.json.",
            status=status,
            code=code,
            details=details,
        )

    return SupabaseError(
        message or f"The data endpoint returned HTTP {status}.",
        status=status,
        code=code,
        details=details,
    )


class SupabaseClient:
    """Thin wrapper over the Neon Data API (PostgREST) endpoints
    for tables games/sessions/fps_samples/live_status."""

    def __init__(
        self,
        url: str,
        key: str = "",
        *,
        timeout: float = DEFAULT_TIMEOUT,
        retries: int = DEFAULT_RETRIES,
        session: requests.Session | None = None,
    ) -> None:
        base = url.rstrip("/")
        # The Neon Data API URL already ends with /rest/v1; append it only
        # when it is missing (a bare project base used to be appended before).
        if not base.endswith("/rest/v1"):
            base += "/rest/v1"
        self._base = base
        self._key = (key or "").strip()
        self._timeout = timeout
        self._retries = max(1, retries)
        self._session = session or requests.Session()
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        # The Data API serves the anonymous role without a key; the auth
        # headers are sent only when a key is configured.
        if self._key:
            headers["apikey"] = self._key
            headers["Authorization"] = f"Bearer {self._key}"
        self._session.headers.update(headers)

    def close(self) -> None:
        try:
            self._session.close()
        except Exception:
            pass

    # -- public operations -----------------------------------------------------

    def check_health(self) -> None:
        """Verifies the URL, the key and the table existence."""
        self._request("GET", "/games", params={"select": "id", "limit": "1"})

    def list_games(self) -> list[dict[str, Any]]:
        rows = self._request(
            "GET", "/games", params={"select": "id,name,process_name", "order": "name.asc"}
        )
        return rows if isinstance(rows, list) else []

    def find_game(self, process_name: str) -> dict[str, Any] | None:
        rows = self._request(
            "GET",
            "/games",
            params={
                "select": "id,name,process_name",
                "process_name": f"eq.{process_name}",
                "limit": "1",
            },
        )
        if isinstance(rows, list) and rows:
            return rows[0]
        return None

    def create_game(
        self, name: str, process_name: str, game_id: str | None = None
    ) -> dict[str, Any] | None:
        body: dict[str, Any] = {"name": name, "process_name": process_name}
        if game_id:
            body["id"] = game_id

        try:
            rows = self._request(
                "POST",
                "/games",
                json=body,
                prefer="return=representation",
            )
        except SupabaseError as exc:
            # Someone else created the game in the meantime – the caller will find it again.
            if is_duplicate(exc):
                LOG.debug("Game %s already exists.", process_name)
                return None
            raise

        if isinstance(rows, list) and rows:
            return rows[0]
        return None

    def create_session(
        self,
        *,
        session_id: str,
        game_id: str,
        played_at: str,
        avg_fps: float,
        min_fps: float,
        max_fps: float,
        duration_seconds: int,
        resolution: str | None = None,
        display_mode: str | None = None,
        graphics_api: str | None = None,
        game_settings: dict[str, Any] | None = None,
        gpu_temp_avg: float | None = None,
        gpu_temp_max: float | None = None,
        gpu_load_avg: float | None = None,
        cpu_temp_avg: float | None = None,
        cpu_load_avg: float | None = None,
    ) -> None:
        row: dict[str, Any] = {
            "id": session_id,
            "game_id": game_id,
            "played_at": played_at,
            "avg_fps": avg_fps,
            "min_fps": min_fps,
            "max_fps": max_fps,
            "duration_seconds": duration_seconds,
        }
        if resolution is not None:
            row["resolution"] = resolution
        if display_mode is not None:
            row["display_mode"] = display_mode
        if graphics_api is not None:
            row["graphics_api"] = graphics_api
        if game_settings is not None:
            row["game_settings"] = game_settings
        if gpu_temp_avg is not None:
            row["gpu_temp_avg"] = gpu_temp_avg
        if gpu_temp_max is not None:
            row["gpu_temp_max"] = gpu_temp_max
        if gpu_load_avg is not None:
            row["gpu_load_avg"] = gpu_load_avg
        if cpu_temp_avg is not None:
            row["cpu_temp_avg"] = cpu_temp_avg
        if cpu_load_avg is not None:
            row["cpu_load_avg"] = cpu_load_avg
        try:
            self._request("POST", "/sessions", json=sanitize_row(SESSIONS_COLUMNS, row))
        except SupabaseError as exc:
            # The ID is a UUID generated by the agent – an existing row means
            # the session was already uploaded (e.g., after a crash mid-upload).
            if is_duplicate(exc):
                LOG.debug("Session %s already exists, continuing with samples.", session_id)
                return
            raise

    def upsert_live_status(self, row: dict[str, Any]) -> None:
        """Inserts or updates the singleton `live_status` row (id = 'default')."""
        row = sanitize_row(LIVE_STATUS_COLUMNS, dict(row))
        row.setdefault("id", LIVE_STATUS_ID)
        updated = self._request("PATCH", "/live_status", params={"id": f"eq.{LIVE_STATUS_ID}"}, json=row)
        if not updated:
            # No row yet (e.g., first contact after a fresh install) – create it.
            try:
                self._request("POST", "/live_status", json=row)
            except SupabaseError as exc:
                LOG.debug("Could not create the live status row: %s", exc)

    def delete_samples(self, session_id: str) -> None:
        self._request("DELETE", "/fps_samples", params={"session_id": f"eq.{session_id}"})

    def insert_samples(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        sanitized = [sanitize_row(FPS_SAMPLES_COLUMNS, row) for row in rows]
        self._request("POST", "/fps_samples", json=sanitized)

    # -- HTTP ----------------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        json: Any = None,
        prefer: str | None = None,
    ) -> Any:
        url = f"{self._base}{path}"
        headers = {"Prefer": prefer} if prefer else {}

        last_error: SupabaseError | None = None

        for attempt in range(1, self._retries + 1):
            try:
                response = self._session.request(
                    method,
                    url,
                    params=params,
                    json=json,
                    headers=headers,
                    timeout=self._timeout,
                )
            except requests.RequestException as exc:
                last_error = SupabaseError(f"Could not connect to the data endpoint: {exc}")
                if attempt < self._retries:
                    self._backoff(attempt)
                    continue
                raise last_error from exc

            if response.ok:
                if not response.content:
                    return None
                try:
                    return response.json()
                except ValueError:
                    return None

            try:
                payload = response.json()
            except ValueError:
                payload = {"message": response.text[:300]}

            error = describe_response(response.status_code, payload)

            # Transient server errors are retried.
            if response.status_code >= 500 and attempt < self._retries:
                LOG.warning(
                    "The data endpoint returned HTTP %s (%s), attempt %s/%s",
                    response.status_code,
                    error,
                    attempt,
                    self._retries,
                )
                last_error = error
                self._backoff(attempt)
                continue

            raise error

        raise last_error or SupabaseError("Unknown Supabase communication error.")

    @staticmethod
    def _backoff(attempt: int) -> None:
        time.sleep(min(2 ** (attempt - 1), 8))
