"""Video → frame generator using PyAV (already in the base deps).

Returns numpy RGB uint8 arrays one frame at a time. Optional max-frame cap
so accidental 30-minute uploads don't silently turn into 30-minute waits.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterator

import numpy as np

log = logging.getLogger(__name__)


def iter_frames_rgb(
    video_path: str | Path,
    *,
    max_frames: int | None = None,
    stride: int = 1,
) -> Iterator[np.ndarray]:
    """Yield RGB uint8 frames from ``video_path`` using PyAV.

    Parameters
    ----------
    video_path : path to the video file
    max_frames : stop after this many frames are emitted (``None`` = all)
    stride     : keep only every Nth frame (1 = every frame, 2 = half, ...)
    """
    try:
        import av  # type: ignore
    except ImportError as exc:  # noqa: BLE001
        raise RuntimeError(
            "PyAV is required for video decoding (install `av`)."
        ) from exc

    container = av.open(str(video_path))
    try:
        stream = next(s for s in container.streams if s.type == "video")
    except StopIteration:
        container.close()
        raise RuntimeError(f"no video stream in {video_path}")
    stream.thread_type = "AUTO"

    emitted = 0
    index = 0
    try:
        for frame in container.decode(stream):
            if stride > 1 and (index % stride) != 0:
                index += 1
                continue
            rgb = frame.to_ndarray(format="rgb24")
            yield rgb
            emitted += 1
            index += 1
            if max_frames is not None and emitted >= max_frames:
                break
    finally:
        container.close()


def probe_video(video_path: str | Path) -> dict:
    """Return basic video metadata without loading frames into memory.

    Keys: ``fps``, ``duration_sec``, ``frame_count``, ``width``, ``height``.
    ``frame_count`` may be 0 for sources where the container doesn't expose
    frame counts cheaply.
    """
    import av  # type: ignore

    container = av.open(str(video_path))
    try:
        stream = next(s for s in container.streams if s.type == "video")
    except StopIteration:
        container.close()
        raise RuntimeError(f"no video stream in {video_path}")

    avg = stream.average_rate
    fps = float(avg) if avg else 30.0
    info = {
        "fps": fps,
        "duration_sec": float(stream.duration * stream.time_base) if stream.duration else 0.0,
        "frame_count": int(stream.frames or 0),
        "width": int(stream.width or 0),
        "height": int(stream.height or 0),
    }
    container.close()
    return info
