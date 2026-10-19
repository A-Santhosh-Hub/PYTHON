"""Headless Step-2 test: connect, decode for N seconds, report fps / bitrate / decode time / CPU.

Usage:  .venv\\Scripts\\python.exe tools\\stream_test.py [--seconds 15] [--decoder auto|software|d3d11va]
                                                      [--max-size 1920] [--fps 60] [--mbps 8]
"""
from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psutil  # noqa: E402

from app.device.adb import Adb  # noqa: E402
from app.stream import protocol  # noqa: E402
from app.stream.session import ScrcpySession, StreamConfig  # noqa: E402
from app.video.decoder import VideoDecoder  # noqa: E402
from app.video.frame import frame_to_yuv  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=15)
    ap.add_argument("--decoder", default="auto")
    ap.add_argument("--max-size", type=int, default=1920)
    ap.add_argument("--fps", type=int, default=60)
    ap.add_argument("--mbps", type=int, default=8)
    ap.add_argument("--codec", default="h264")
    args = ap.parse_args()

    adb = Adb()
    adb.start_server()
    usable = [d for d in adb.devices() if d.usable]
    if not usable:
        print("No authorized device found:", adb.devices())
        return 2
    serial = usable[0].serial
    cfg = StreamConfig(max_size=args.max_size, max_fps=args.fps, bit_rate=args.mbps * 1_000_000, codec=args.codec)

    session = ScrcpySession(adb, serial, cfg)
    t_start = time.perf_counter()
    session.start()
    print(f"connected to {session.device_name!r} ({session.codec}) in {time.perf_counter() - t_start:.2f}s")
    decoder = VideoDecoder(session.codec, args.decoder)
    print("decoder backend:", decoder.backend)

    proc = psutil.Process()
    proc.cpu_percent(None)
    frames = bytes_in = 0
    decode_times: list[float] = []
    convert_times: list[float] = []
    intervals: list[float] = []
    size = (0, 0)
    first_frame_at = None
    last = None
    t_run = time.perf_counter()
    try:
        while time.perf_counter() - t_run < args.seconds:
            pkt = session.read_video_packet()
            if isinstance(pkt, protocol.SessionPacket):
                size = (pkt.width, pkt.height)
                continue
            header, data = pkt
            bytes_in += len(data)
            t0 = time.perf_counter()
            out = decoder.decode(data, header.pts, header.config)
            t1 = time.perf_counter()
            for frame in out:
                frame_to_yuv(frame)
                t2 = time.perf_counter()
                decode_times.append(t1 - t0)
                convert_times.append(t2 - t1)
                frames += 1
                if first_frame_at is None:
                    first_frame_at = t2 - t_start
                if last is not None:
                    intervals.append(t2 - last)
                last = t2
    finally:
        cpu = proc.cpu_percent(None)
        session.stop()

    elapsed = time.perf_counter() - t_run
    if not frames:
        print("FAIL: no frames decoded")
        return 1
    print(f"video size        : {size[0]}x{size[1]}")
    print(f"time to 1st frame : {first_frame_at:.2f} s")
    print(f"frames            : {frames} in {elapsed:.1f}s = {frames / elapsed:.1f} fps")
    print(f"bitrate           : {bytes_in * 8 / elapsed / 1e6:.2f} Mbps")
    print(f"decode time       : mean {statistics.mean(decode_times) * 1000:.2f} ms, "
          f"p95 {sorted(decode_times)[int(len(decode_times) * .95)] * 1000:.2f} ms")
    print(f"plane prep time : mean {statistics.mean(convert_times) * 1000:.2f} ms")
    if intervals:
        print(f"frame interval    : mean {statistics.mean(intervals) * 1000:.1f} ms, "
              f"max {max(intervals) * 1000:.0f} ms")
    print(f"this process CPU  : {cpu:.0f}% of one core")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

