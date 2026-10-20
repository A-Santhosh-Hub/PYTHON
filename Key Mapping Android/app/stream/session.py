"""Starts the scrcpy server on the phone and opens its video + control sockets."""
from __future__ import annotations

import logging
import queue
import random
import socket
import struct
import threading
import time
from collections import deque
from dataclasses import dataclass

from .. import paths
from ..device.adb import Adb, AdbError
from . import protocol

log = logging.getLogger(__name__)


class ScrcpyError(RuntimeError):
    pass


@dataclass
class StreamConfig:
    max_size: int = 1920          # longest side in pixels, 0 = native
    max_fps: int = 60
    bit_rate: int = 8_000_000
    codec: str = "h264"           # h264 | h265
    show_touches: bool = False
    stay_awake: bool = True


def read_exact(sock: socket.socket, count: int) -> bytes:
    buf = bytearray(count)
    view = memoryview(buf)
    got = 0
    while got < count:
        n = sock.recv_into(view[got:], count - got)
        if n == 0:
            raise ConnectionError("connection closed by the device")
        got += n
    return bytes(buf)


class ControlChannel:
    """Thread-safe control sender. Messages are queued and written by a dedicated thread, so the
    GUI thread never blocks on the socket. Incoming device messages are drained and ignored."""

    def __init__(self, sock: socket.socket) -> None:
        self._sock = sock
        self._queue: queue.SimpleQueue[bytes | None] = queue.SimpleQueue()
        self.closed = False
        threading.Thread(target=self._writer, name="control-writer", daemon=True).start()
        threading.Thread(target=self._drain, name="control-drain", daemon=True).start()

    def send(self, data: bytes) -> bool:
        if self.closed:
            return False
        self._queue.put(data)
        return True

    def close(self) -> None:
        self.closed = True
        self._queue.put(None)

    def key(self, keycode: int) -> None:
        self.send(protocol.encode_keycode(protocol.KEY_DOWN, keycode)
                  + protocol.encode_keycode(protocol.KEY_UP, keycode))

    def touch(self, action: int, pointer_id: int, x: int, y: int, width: int, height: int,
              pressure: float = 1.0) -> None:
        self.send(protocol.encode_touch(action, pointer_id, x, y, width, height, pressure))

    def _writer(self) -> None:
        while True:
            data = self._queue.get()
            if data is None:
                return
            try:
                self._sock.sendall(data)
            except OSError as exc:
                if not self.closed:
                    log.warning("Control channel closed: %s", exc)
                self.closed = True
                return

    def _drain(self) -> None:
        try:
            while self._sock.recv(4096):
                pass
        except OSError:
            pass
        self.closed = True
        self._queue.put(None)


class ScrcpySession:
    """Owns the server process, the adb tunnel and the sockets for one phone."""

    START_TIMEOUT = 12.0

    def __init__(self, adb: Adb, serial: str, config: StreamConfig) -> None:
        self.adb = adb
        self.serial = serial
        self.config = config
        self.device_name = ""
        self.codec = ""
        self.video_sock: socket.socket | None = None
        self.control: ControlChannel | None = None
        self._control_sock: socket.socket | None = None
        self._port = 0
        self._proc = None
        self._server_log: deque[str] = deque(maxlen=30)

    # -- lifecycle -------------------------------------------------------------------------
    def start(self) -> None:
        jar = paths.server_jar()
        if not jar.is_file():
            raise ScrcpyError(f"scrcpy server not found: {jar}")
        scid = random.getrandbits(31)
        socket_name = f"scrcpy_{scid:08x}"
        try:
            log.info("Pushing scrcpy server %s to %s", paths.SCRCPY_VERSION, self.serial)
            self.adb.push(self.serial, jar, paths.DEVICE_SERVER_PATH)
            self._port = self.adb.forward(self.serial, f"localabstract:{socket_name}")
            self._proc = self.adb.popen_shell(self.serial, self._server_command(scid))
            threading.Thread(target=self._pump_server_output, name="server-log", daemon=True).start()
            self._open_sockets()
        except (AdbError, OSError) as exc:
            self.stop()
            raise ScrcpyError(str(exc)) from exc
        except Exception:
            self.stop()
            raise

    def stop(self) -> None:
        if self.control is not None:
            self.control.close()
        for sock in (self.video_sock, self._control_sock):
            if sock is not None:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                try:
                    sock.close()
                except OSError:
                    pass
        self.video_sock = None
        self._control_sock = None
        if self._proc is not None:
            try:
                self._proc.terminate()
            except OSError:
                pass
            self._proc = None
        if self._port:
            try:
                self.adb.forward_remove(self.serial, self._port)
            except AdbError:
                pass
            self._port = 0

    # -- internals -------------------------------------------------------------------------
    def _server_command(self, scid: int) -> str:
        c = self.config
        args = [
            f"CLASSPATH={paths.DEVICE_SERVER_PATH}", "app_process", "/",
            "com.genymobile.scrcpy.Server", paths.SCRCPY_VERSION,
            f"scid={scid:08x}", "log_level=info", "tunnel_forward=true",
            "audio=false", "control=true", f"video_codec={c.codec}",
            f"max_size={c.max_size}", f"max_fps={c.max_fps}", f"video_bit_rate={c.bit_rate}",
            f"show_touches={str(c.show_touches).lower()}", f"stay_awake={str(c.stay_awake).lower()}",
            "clipboard_autosync=false", "cleanup=true",
        ]
        return " ".join(args)

    def _pump_server_output(self) -> None:
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        for raw in iter(proc.stdout.readline, b""):
            line = raw.decode("utf-8", "replace").rstrip()
            if line:
                self._server_log.append(line)
                log.info("[server] %s", line)

    def _server_failure(self) -> ScrcpyError:
        tail = "\n".join(self._server_log) or "no output"
        return ScrcpyError(f"The scrcpy server stopped unexpectedly:\n{tail}")

    def _connect_first(self, deadline: float) -> socket.socket:
        while time.monotonic() < deadline:
            if self._proc is not None and self._proc.poll() is not None:
                raise self._server_failure()
            sock = None
            try:
                sock = socket.create_connection(("127.0.0.1", self._port), timeout=2)
                sock.settimeout(1.0)
                if sock.recv(1):            # the dummy byte proves the device side is connected
                    sock.settimeout(None)
                    return sock
            except OSError:
                pass
            if sock is not None:
                sock.close()
            time.sleep(0.1)
        raise ScrcpyError("Timed out waiting for the scrcpy server on the phone.\n"
                          + "\n".join(self._server_log))

    def _open_sockets(self) -> None:
        deadline = time.monotonic() + self.START_TIMEOUT
        video = self._connect_first(deadline)
        self.video_sock = video
        control = socket.create_connection(("127.0.0.1", self._port), timeout=5)
        control.settimeout(None)
        control.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self._control_sock = control

        name = read_exact(video, 64).split(b"\0", 1)[0].decode("utf-8", "replace")
        codec_id = struct.unpack(">I", read_exact(video, 4))[0]
        if codec_id in (0, 1):
            raise ScrcpyError("The phone refused to start the video stream:\n"
                              + "\n".join(self._server_log))
        self.codec = protocol.CODEC_IDS.get(codec_id, "")
        if not self.codec:
            raise ScrcpyError(f"Unsupported video codec id 0x{codec_id:08x}")
        self.device_name = name
        self.control = ControlChannel(control)
        log.info("Connected to '%s' (%s)", name, self.codec)

    def read_video_packet(self) -> protocol.SessionPacket | tuple[protocol.MediaHeader, bytes]:
        assert self.video_sock is not None
        header = protocol.parse_packet_header(read_exact(self.video_sock, protocol.PACKET_HEADER_SIZE))
        if isinstance(header, protocol.SessionPacket):
            return header
        return header, read_exact(self.video_sock, header.size)
