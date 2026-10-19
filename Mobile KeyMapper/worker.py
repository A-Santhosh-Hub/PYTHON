"""Background thread: runs a scrcpy session, decodes video and hands the newest frame to the GUI."""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass

from PySide6.QtCore import QThread, Signal

from ..device.adb import Adb
from ..video.decoder import VideoDecoder
from ..video.frame import YuvFrame, frame_to_yuv
from . import protocol
from .session import ControlChannel, ScrcpyError, ScrcpySession, StreamConfig

log = logging.getLogger(__name__)


@dataclass
class StatsSnapshot:
    fps: float = 0.0
    shown_fps: float = 0.0
    mbps: float = 0.0
    decode_ms: float = 0.0
    convert_ms: float = 0.0
    dropped: int = 0


class MirrorWorker(QThread):
    status = Signal(str)
    connected = Signal(str, str, str)       # device name, codec, decoder backend
    videoSizeChanged = Signal(int, int)
    frameReady = Signal()
    failed = Signal(str)

    def __init__(self, adb: Adb, serial: str, config: StreamConfig, decoder_mode: str = "auto",
                 parent=None) -> None:
        super().__init__(parent)
        self._adb = adb
        self.serial = serial
        self._config = config
        self._decoder_mode = decoder_mode
        self._stop_requested = False
        self._session: ScrcpySession | None = None

        self.video_size: tuple[int, int] = (0, 0)
        self.control: ControlChannel | None = None

        self._frame_lock = threading.Lock()
        self._frame: YuvFrame | None = None
        self._frame_stamp = 0.0
        self._notified = False

        self._stats_lock = threading.Lock()
        self._reset_counters()
        self._last_snapshot_time = time.perf_counter()

    # -- GUI-thread API --------------------------------------------------------------------
    def stop(self) -> None:
        self._stop_requested = True
        session = self._session
        if session is not None:
            session.stop()          # closes the sockets, which unblocks the reader thread

    def take_frame(self) -> tuple[YuvFrame | None, float]:
        with self._frame_lock:
            frame, stamp = self._frame, self._frame_stamp
            self._frame = None
            self._notified = False
        if frame is not None:
            with self._stats_lock:
                self._shown += 1
        return frame, stamp

    def snapshot(self) -> StatsSnapshot:
        now = time.perf_counter()
        with self._stats_lock:
            elapsed = max(now - self._last_snapshot_time, 1e-6)
            snap = StatsSnapshot(
                fps=self._decoded / elapsed,
                shown_fps=self._shown / elapsed,
                mbps=self._bytes * 8 / elapsed / 1e6,
                decode_ms=(self._decode_time / self._decoded * 1000) if self._decoded else 0.0,
                convert_ms=(self._convert_time / self._decoded * 1000) if self._decoded else 0.0,
                dropped=self._dropped,
            )
            self._reset_counters()
            self._last_snapshot_time = now
        return snap

    # -- worker thread ---------------------------------------------------------------------
    def run(self) -> None:
        session = ScrcpySession(self._adb, self.serial, self._config)
        self._session = session
        try:
            self.status.emit("Starting server on the phone...")
            session.start()
            if self._stop_requested:
                return
            self.control = session.control
            decoder = VideoDecoder(session.codec, self._decoder_mode)
            self.connected.emit(session.device_name, session.codec, decoder.backend)
            self._read_loop(session, decoder)
        except (ScrcpyError, ConnectionError, OSError) as exc:
            if not self._stop_requested:
                log.error("Mirroring stopped: %s", exc)
                self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001 - never let the thread die silently
            log.exception("Unexpected mirroring error")
            if not self._stop_requested:
                self.failed.emit(f"Unexpected error: {exc}")
        finally:
            session.stop()
            self.control = None
            self._session = None

    def _read_loop(self, session: ScrcpySession, decoder: VideoDecoder) -> None:
        while not self._stop_requested:
            packet = session.read_video_packet()
            if isinstance(packet, protocol.SessionPacket):
                self.video_size = (packet.width, packet.height)
                log.info("Video size %dx%d", packet.width, packet.height)
                self.videoSizeChanged.emit(packet.width, packet.height)
                continue
            header, data = packet
            arrival = time.perf_counter()
            with self._stats_lock:
                self._bytes += len(data)
            t0 = time.perf_counter()
            frames = decoder.decode(data, header.pts, header.config)
            t1 = time.perf_counter()
            if not frames:
                continue
            with self._stats_lock:
                self._decoded += len(frames)
                self._decode_time += t1 - t0
                self._dropped += len(frames) - 1       # only the newest frame of a batch is shown
            yuv = frame_to_yuv(frames[-1])
            with self._stats_lock:
                self._convert_time += time.perf_counter() - t1
            self._publish(yuv, arrival)

    def _publish(self, frame: YuvFrame, stamp: float) -> None:
        with self._frame_lock:
            if self._frame is not None:
                with self._stats_lock:
                    self._dropped += 1               # GUI had not consumed the previous frame
            self._frame = frame
            self._frame_stamp = stamp
            notify = not self._notified
            self._notified = True
        if notify:
            self.frameReady.emit()

    def _reset_counters(self) -> None:
        self._decoded = 0
        self._shown = 0
        self._bytes = 0
        self._decode_time = 0.0
        self._convert_time = 0.0
        self._dropped = 0
