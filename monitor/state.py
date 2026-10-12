"""Thread-safe live state, monotonic freshness and one hour of bounded history."""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Callable


class MonitorState:
    def __init__(self, alias: str, interval: int, demo: bool = False, *,
                 source: str = 'ssh',
                 clock: Callable[[], float] = time.time,
                 monotonic: Callable[[], float] = time.monotonic):
        self.alias = alias
        self.interval = interval
        self.demo = demo
        self.source = source
        self._clock = clock
        self._monotonic = monotonic
        self._lock = threading.Lock()
        self._history: deque[dict] = deque(maxlen=3600 // interval + 1)
        self._latest: dict | None = None
        self._status = "connecting"
        self._message = ("Connecting. Enter the SSH password in the launch window if requested."
                         if source == 'ssh' else "Starting local metric collection.")
        self._last_received: float | None = None
        self._connected_since: int | None = None

    def begin_session(self) -> None:
        with self._lock:
            self._connected_since = None

    def set_status(self, status: str, message: str) -> None:
        with self._lock:
            self._status = status
            self._message = message

    def record(self, sample: dict) -> None:
        with self._lock:
            self._latest = sample
            self._last_received = self._monotonic()
            self._connected_since = self._connected_since or sample["ts"]
            self._history.append({key: value for key, value in sample.items()
                                  if key not in {"processes", "traffic"}})
            cutoff = sample["ts"] - 3_600_000
            while self._history and self._history[0]["ts"] < cutoff:
                self._history.popleft()
            self._status = "connected"
            self._message = ("Demo data" if self.demo else
                             "Connected through SSH" if self.source == 'ssh' else
                             "Local metric collection is running.")

    def _status_info(self) -> tuple[str, str]:
        # Both callers hold _lock; status in the sidebar matches the snapshot.
        if (self._status == "connected" and self._last_received is not None
                and self._monotonic() - self._last_received > max(8, self.interval * 4)):
            return "reconnecting", "No fresh data is arriving. The last values are preserved."
        return self._status, self._message

    def snapshot(self) -> dict:
        with self._lock:
            status, message = self._status_info()
            return {
                "status": status, "message": message, "alias": self.alias, "source": self.source,
                "interval": self.interval, "demo": self.demo,
                "server_time": round(self._clock() * 1000),
                "last_update": self._latest["ts"] if self._latest else None,
                "connected_since": self._connected_since,
                "latest": self._latest, "history": list(self._history),
            }

    def status(self) -> str:
        """Sidebar status without copying an hour of sample history."""
        with self._lock:
            return self._status_info()[0]
