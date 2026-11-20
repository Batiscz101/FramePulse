"""Tray icon and the agent menu (pystray + Pillow)."""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path

import pystray
from PIL import Image, ImageDraw

from framepulse_agent.capture import CaptureFailure
from framepulse_agent.config import Config
from framepulse_agent.monitor import (
    STATE_CAPTURING,
    STATE_ERROR,
    STATE_PAUSED,
    STATE_STARTING,
    AgentStatus,
    GameAgent,
)
from framepulse_agent.upload import Uploader

LOG = logging.getLogger(__name__)

REFRESH_SECONDS = 1.5
ICON_SIZE = 64

COLORS = {
    STATE_CAPTURING: (52, 211, 153),  # mint
    STATE_STARTING: (94, 234, 212),  # teal
    STATE_PAUSED: (251, 191, 36),  # amber
    STATE_ERROR: (248, 113, 113),  # red
}
DEFAULT_COLOR = (161, 161, 170)  # zinc

BACKGROUND = (18, 18, 21, 255)
BORDER = (39, 39, 42, 255)

# Pulse curve – minimalist heartbeat, no neon.
PULSE_POINTS = ((10, 38), (19, 38), (25, 21), (33, 47), (41, 29), (47, 38), (54, 38))


def _accent_for(state: str, last_error: str | None) -> tuple[int, int, int]:
    if state == STATE_ERROR or (state not in COLORS and last_error):
        return COLORS[STATE_ERROR]
    return COLORS.get(state, DEFAULT_COLOR)


def make_icon(state: str = "idle", last_error: str | None = None) -> Image.Image:
    """Renders the 64×64 icon according to the agent state."""
    image = Image.new("RGBA", (ICON_SIZE, ICON_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    draw.rounded_rectangle(
        (2, 2, ICON_SIZE - 3, ICON_SIZE - 3), radius=14, fill=BACKGROUND, outline=BORDER, width=2
    )
    draw.line(PULSE_POINTS, fill=_accent_for(state, last_error), width=5, joint="curve")

    return image


def _truncate(text: str, limit: int = 120) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


class TrayApp:
    """Tray icon, menu and connection to `GameAgent`."""

    def __init__(
        self,
        config: Config,
        uploader: Uploader,
        startup_issue_message: str | None = None,
    ) -> None:
        self._config = config
        self._agent = GameAgent(config, uploader, notifier=self._notify)
        self._last_status: AgentStatus | None = None
        self._last_icon_key: tuple[str, bool] | None = None
        self._stop_refresh = threading.Event()
        self._refresh_thread: threading.Thread | None = None
        self._startup_issue_message = startup_issue_message

        if startup_issue_message:
            self._agent.set_startup_issue(CaptureFailure("startup", startup_issue_message))

        self._icon = pystray.Icon(
            "FramePulseAgent",
            make_icon("idle"),
            "FramePulse – starting…",
            menu=self._build_menu(),
        )

    # -- run -----------------------------------------------------------------

    def run(self) -> None:
        self._icon.run(setup=self._setup)

    def _setup(self, _icon) -> None:
        self._agent.start()
        self._refresh_thread = threading.Thread(
            target=self._refresh_loop, name="tray-refresh", daemon=True
        )
        self._refresh_thread.start()

        if self._startup_issue_message:
            self._notify("FramePulse", self._startup_issue_message)

    def _refresh_loop(self) -> None:
        while not self._stop_refresh.wait(REFRESH_SECONDS):
            try:
                self._apply_status(self._agent.status())
            except Exception:
                LOG.debug("Tray refresh failed", exc_info=True)

    def _apply_status(self, status: AgentStatus) -> None:
        if status == self._last_status:
            return
        self._last_status = status

        state_key = (status.state, bool(status.last_error))
        if state_key != self._last_icon_key:
            self._last_icon_key = state_key
            self._icon.icon = make_icon(status.state, status.last_error)

        self._icon.title = _truncate(f"FramePulse – {status.title}")

        if status.state == STATE_ERROR and status.last_error:
            self._icon.title = _truncate(f"FramePulse – error: {status.last_error}")

        try:
            self._icon.update_menu()
        except Exception:
            LOG.debug("update_menu selhal", exc_info=True)

    # -- menu ----------------------------------------------------------------

    def _build_menu(self) -> pystray.Menu:
        return pystray.Menu(
            pystray.MenuItem(self._status_text, None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(self._pause_text, self._on_toggle_pause),
            pystray.MenuItem(
                self._pending_text,
                lambda: self._agent.flush_outbox(),
                enabled=lambda item: self._pending_count() > 0,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Open log", self._open_log),
            pystray.MenuItem("Open data folder", self._open_data_dir),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit FramePulse", self._on_quit),
        )

    def _status_text(self, _item=None) -> str:
        status = self._agent.status()
        text = status.title
        if status.state in (STATE_CAPTURING, STATE_STARTING) and status.session_seconds:
            text = f"{text} ({status.session_seconds:.0f} s)"
        return text

    def _pause_text(self, _item=None) -> str:
        return "Resume measuring" if self._agent.paused else "Pause measuring"

    def _pending_text(self, _item=None) -> str:
        pending = self._pending_count()
        return f"Send queue ({pending})" if pending else "Queue is empty"

    def _pending_count(self) -> int:
        return self._agent.status().pending_uploads

    # -- actions ----------------------------------------------------------------

    def _on_toggle_pause(self, _icon=None, _item=None) -> None:
        self._agent.toggle_pause()

    def _on_quit(self, _icon=None, _item=None) -> None:
        LOG.info("Quitting the agent from the menu.")
        self._stop_refresh.set()
        try:
            self._icon.visible = False  # immediate feedback
        except Exception:
            LOG.debug("Hiding the icon failed", exc_info=True)
        self._agent.stop()
        self._icon.stop()

    def _notify(self, title: str, message: str) -> None:
        try:
            self._icon.notify(message, title)
        except Exception:
            LOG.debug("Balloon notification failed", exc_info=True)

    def _open_log(self) -> None:
        file = self._config.log_dir / "agent.log"
        target = file if file.exists() else self._config.log_dir
        self._open_path(target)

    def _open_data_dir(self) -> None:
        self._open_path(self._config.data_dir)

    @staticmethod
    def _open_path(path: Path) -> None:
        try:
            if not path.suffix and not path.exists():
                path.mkdir(parents=True, exist_ok=True)
            os.startfile(str(path))  # type: ignore[attr-defined]
        except OSError:
            LOG.warning("The path %s could not be opened.", path)
