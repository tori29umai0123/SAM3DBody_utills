"""In-memory cache for animated-FBX motion data.

Video motion inference (per-frame SAM3 + SAM3DBody) is the slow step and
shape-independent. The Blender FBX build is comparatively cheap but depends
on the current character settings. Separating the two lets us:

  1. Run `/api/process_video` once to get the raw per-frame pose params,
     cached here under a ``motion_id``.
  2. Play back the first animated FBX in the viewer.
  3. Let the user switch presets / upload a character JSON without
     re-inferring: `/api/build_animated_fbx` only re-runs MHR forward +
     the Blender subprocess against the cached motion.
"""
from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import dataclass
from typing import List, Optional

import numpy as np


@dataclass
class MotionSession:
    motion_id: str
    # Per-frame raw SAM3DBody outputs. ``None`` whenever that frame had no
    # detection — callers reuse the last good frame's values to keep clips
    # contiguous, same as the old monolithic pipeline did.
    frames_body_pose: List[Optional[np.ndarray]]   # (133,) each
    frames_hand_pose: List[Optional[np.ndarray]]   # (108,)
    frames_global_rot: List[Optional[np.ndarray]]  # (3,)
    frames_cam_t: List[Optional[np.ndarray]]       # (3,) — from pred_cam_t
    num_frames: int
    skipped_frames: int
    fps: float
    source_name: str


class _Store:
    def __init__(self, max_size: int = 8) -> None:
        self._d: "OrderedDict[str, MotionSession]" = OrderedDict()
        self._lock = threading.Lock()
        self._max = max_size

    def put(self, s: MotionSession) -> None:
        with self._lock:
            self._d[s.motion_id] = s
            self._d.move_to_end(s.motion_id)
            while len(self._d) > self._max:
                self._d.popitem(last=False)

    def get(self, motion_id: str) -> MotionSession | None:
        with self._lock:
            s = self._d.get(motion_id)
            if s is not None:
                self._d.move_to_end(motion_id)
            return s

    def drop(self, motion_id: str) -> None:
        with self._lock:
            self._d.pop(motion_id, None)


_store = _Store()


def put(s: MotionSession) -> None:
    _store.put(s)


def get(motion_id: str) -> MotionSession | None:
    return _store.get(motion_id)


def drop(motion_id: str) -> None:
    _store.drop(motion_id)
