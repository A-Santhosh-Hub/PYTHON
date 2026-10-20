"""H.264/H.265 decoding through PyAV (FFmpeg) with optional Windows hardware acceleration."""
from __future__ import annotations

import logging

import av

log = logging.getLogger(__name__)

HW_DEVICE_TYPES = ("d3d11va", "dxva2", "cuda")


class VideoDecoder:
    """Decodes scrcpy video packets. `mode` is 'auto', 'software' or a hwaccel device type."""

    def __init__(self, codec: str = "h264", mode: str = "auto") -> None:
        self.codec_name = "hevc" if codec in ("h265", "hevc") else codec
        self.backend = "software"
        self._ctx = self._open(mode)
        self._config = b""

    def _open(self, mode: str) -> av.CodecContext:
        # "auto" means software: measured faster than PyAV hardware decoding (GPU->CPU copies).
        candidates = [] if mode in ("auto", "software") else [mode]
        for device_type in candidates:
            try:
                from av.codec.hwaccel import HWAccel
                ctx = av.CodecContext.create(self.codec_name, "r", hwaccel=HWAccel(device_type=device_type,
                                                                                   allow_software_fallback=False))
                self._tune(ctx)
                ctx.open()
                self.backend = device_type
                log.info("Video decoder: hardware (%s)", device_type)
                return ctx
            except Exception as exc:  # noqa: BLE001 - any failure means 'try the next backend'
                log.info("Hardware decoder %s unavailable: %s", device_type, exc)
        ctx = av.CodecContext.create(self.codec_name, "r")
        self._tune(ctx)
        ctx.open()
        log.info("Video decoder: software (%s)", self.codec_name)
        return ctx

    @staticmethod
    def _tune(ctx: av.CodecContext) -> None:
        try:
            ctx.thread_type = "SLICE"      # frame threading would add whole frames of latency
            ctx.thread_count = 2
        except Exception:  # noqa: BLE001
            pass
        try:
            ctx.flags |= av.codec.context.Flags.low_delay
        except Exception:  # noqa: BLE001
            pass

    def decode(self, data: bytes, pts: int, config: bool) -> list[av.VideoFrame]:
        """Feed one scrcpy packet. Config packets (SPS/PPS) are merged into the next media packet."""
        if config:
            self._config = data
            return []
        if self._config:
            data = self._config + data
            self._config = b""
        packet = av.Packet(data)
        packet.pts = pts
        try:
            return list(self._ctx.decode(packet))
        except av.error.InvalidDataError as exc:
            log.warning("Dropped undecodable packet: %s", exc)
            return []
