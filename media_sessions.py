"""Leitura das sessões de mídia do Windows por Windows.Media.Control."""
from __future__ import annotations

import asyncio
import threading
import time

AMBIENT = {
    "title": "Som Ambiente",
    "artist": "Você está ouvindo apenas as vozes da sua cabeça no momento.",
    "source": "AMBIENTE",
    "playing": False,
    "position": 0,
    "duration": 0,
}


class MediaSessionMonitor:
    def __init__(self):
        self._lock = threading.Lock()
        self._current = dict(AMBIENT)
        self._last_poll = 0
        self._available = False
        self._thread = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="windows-media-sessions", daemon=True)
        self._thread.start()

    def snapshot(self):
        with self._lock:
            return dict(self._current)

    def _run(self):
        try:
            asyncio.run(self._poll_loop())
        except Exception:
            pass

    async def _poll_loop(self):
        from winrt.windows.media.control import (
            GlobalSystemMediaTransportControlsSessionManager as Manager,
            GlobalSystemMediaTransportControlsSessionPlaybackStatus as PlaybackStatus,
        )
        self._available = True
        while True:
            try:
                manager = await Manager.request_async()
                sessions = list(manager.get_sessions())
                candidates = []
                for session in sessions:
                    info = session.get_playback_info()
                    if info.playback_status == PlaybackStatus.PLAYING:
                        candidates.append(session)
                current = manager.get_current_session()
                session = candidates[0] if candidates else None
                if session is None and current is not None:
                    info = current.get_playback_info()
                    if info.playback_status == PlaybackStatus.PLAYING:
                        session = current
                if session is None:
                    new = dict(AMBIENT)
                else:
                    props = await session.try_get_media_properties_async()
                    info = session.get_playback_info()
                    timeline = session.get_timeline_properties()
                    app_id = str(session.source_app_user_model_id or "")
                    low = app_id.lower()
                    source = "Spotify" if "spotify" in low else ("YouTube / navegador" if any(x in low for x in ("edge", "chrome", "firefox", "opera")) else app_id.rsplit("!", 1)[-1] or "Player do Windows")
                    position = getattr(timeline, "position", 0)
                    end = getattr(timeline, "end_time", 0)
                    try:
                        position = max(0, int(position.total_seconds()))
                    except AttributeError:
                        position = max(0, int(position / 10_000_000))
                    try:
                        duration = max(0, int(end.total_seconds()))
                    except AttributeError:
                        duration = max(0, int(end / 10_000_000))
                    new = {
                        "title": str(props.title or "Reproduzindo"),
                        "artist": str(props.artist or props.album_artist or ""),
                        "source": source,
                        "playing": True,
                        "position": position,
                        "duration": duration,
                    }
                with self._lock:
                    self._current = new
                    self._last_poll = time.time()
            except Exception:
                with self._lock:
                    self._current = dict(AMBIENT)
            await asyncio.sleep(2)