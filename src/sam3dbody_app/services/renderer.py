"""Body-shape renderer: takes a cached pose + slider values, produces a new
OBJ mesh. This is the fast path used by every slider drag — the SAM3DBody
neutral-body mesh is regenerated via ``mhr_forward`` using user-provided
``shape_params``, then bone-length + blend-shape deltas are layered on top.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch

from ..config import get_paths
from . import character_shape as cs
from . import pose_session
from .obj_export import write_obj
from .preset_pack import active_pack_paths
from .sam3dbody_loader import load_bundle

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# In-memory LRU cache of the computed vertex array keyed on
# (job_id, normalized settings). Slider drags routinely bounce between a
# handful of nearby values — skipping the ~100–200 ms MHR forward + bone /
# blendshape passes on cache hit makes the UI feel instantaneous.
#
# - Cache stores the final vertex numpy array (post bone-length / blend-shape).
# - Faces come straight from the MHR model and are re-read on every call
#   (cheap: one tensor → numpy conversion).
# - Pack admin changes (FBX rebuild, pack switch) can invalidate keys —
#   call `invalidate_cache()` from those endpoints.
# --------------------------------------------------------------------------

_RENDER_CACHE_MAX = 128
_render_cache: "OrderedDict[str, np.ndarray]" = OrderedDict()


def _render_cache_key(job_id: str, settings_norm: dict[str, Any]) -> str:
    return json.dumps(
        {"j": job_id, "s": settings_norm}, sort_keys=True, separators=(",", ":")
    )


def _render_cache_get(key: str) -> np.ndarray | None:
    if key not in _render_cache:
        return None
    _render_cache.move_to_end(key)
    return _render_cache[key]


def _render_cache_put(key: str, verts: np.ndarray) -> None:
    _render_cache[key] = verts
    _render_cache.move_to_end(key)
    while len(_render_cache) > _RENDER_CACHE_MAX:
        _render_cache.popitem(last=False)


def invalidate_cache() -> None:
    """Drop all cached meshes. Pack admin / FBX rebuild flows call this
    when the blendshape / bone-length schema changes."""
    _render_cache.clear()


@dataclass
class RenderResult:
    job_id: str
    obj_url: str
    obj_path: str
    elapsed_sec: float
    settings: dict[str, Any]


def _empty_settings() -> dict[str, Any]:
    return {
        "body_params": {k: 0.0 for k in cs.BODY_PARAM_KEYS},
        "bone_lengths": {k: 1.0 for k in cs.BONE_LENGTH_KEYS},
        "blendshapes": {},
    }


def _normalise_settings(settings: dict[str, Any] | None) -> dict[str, Any]:
    """Fill missing keys with their neutral defaults."""
    base = _empty_settings()
    if not settings:
        return base
    bp = settings.get("body_params") or {}
    bl = settings.get("bone_lengths") or {}
    bs = settings.get("blendshapes") or {}
    for k in cs.BODY_PARAM_KEYS:
        base["body_params"][k] = float(bp.get(k, 0.0))
    for k in cs.BONE_LENGTH_KEYS:
        base["bone_lengths"][k] = float(bl.get(k, 1.0))
    base["blendshapes"] = {str(k): float(v) for k, v in bs.items()}
    return base


def render_from_session(
    job_id: str,
    settings: dict[str, Any] | None,
) -> RenderResult:
    """Build a mesh for ``job_id`` with the given slider values and write an
    OBJ under ``output/``. Reuses the cached SAM3DBody model + pose session.

    The reserved ``MAKE_JOB_ID`` renders the MHR neutral body in T-pose and
    is used by the Character Make tab — we auto-create it on first request
    so it stays available even if LRU eviction ever drops it."""
    t0 = time.monotonic()
    if job_id == pose_session.MAKE_JOB_ID:
        sess = pose_session.ensure_make_session()
    else:
        sess = pose_session.get(job_id)
        if sess is None:
            raise KeyError(f"no pose session for job_id {job_id!r}")

    s = _normalise_settings(settings)
    bundle = load_bundle()
    model = bundle.model
    device = torch.device(bundle.device)
    mhr_head = model.head_pose

    # Short-circuit on cache hit: skip MHR forward + all post-processing,
    # just re-write tmp/mesh.obj from the memoized vertices. This is the
    # hot path for slider drags that jitter between a few close values.
    faces = mhr_head.faces.detach().cpu().numpy()
    cache_key = _render_cache_key(job_id, s)
    cached_verts = _render_cache_get(cache_key)
    if cached_verts is not None:
        render_id = uuid.uuid4().hex[:8]
        obj_path = get_paths().tmp_dir / "mesh.obj"
        write_obj(
            obj_path, cached_verts, faces,
            header=f"# sam3dbody job {job_id} render {render_id} (cached)",
        )
        obj_url = f"/tmp/mesh.obj?v={render_id}"
        elapsed = time.monotonic() - t0
        log.info("render job=%s render=%s CACHED elapsed=%.3fs", job_id, render_id, elapsed)
        return RenderResult(
            job_id=job_id,
            obj_url=obj_url,
            obj_path=str(obj_path),
            elapsed_sec=elapsed,
            settings=s,
        )

    global_rot = cs.to_tensor_1xN(sess.global_rot, device, width=3)
    body_pose = cs.to_tensor_1xN(sess.body_pose_params, device, width=133)
    hand_pose = cs.to_tensor_1xN(sess.hand_pose_params, device, width=108)
    expr = torch.zeros((1, mhr_head.num_face_comps), dtype=torch.float32, device=device)
    global_trans = torch.zeros((1, 3), dtype=torch.float32, device=device)
    shape_params = cs.build_shape_params(s["body_params"], mhr_head.num_shape_comps, device)
    scale_params = torch.zeros((1, mhr_head.num_scale_comps), dtype=torch.float32, device=device)

    with torch.no_grad():
        out = mhr_head.mhr_forward(
            global_trans=global_trans,
            global_rot=global_rot,
            body_pose_params=body_pose,
            hand_pose_params=hand_pose,
            scale_params=scale_params,
            shape_params=shape_params,
            expr_params=expr,
            return_joint_rotations=True,
            return_joint_coords=True,
        )

    verts = out[0]
    joint_rots = None
    joint_coords = None
    for t in out[1:]:
        if t.ndim == 4 and t.shape[-1] == 3 and t.shape[-2] == 3:
            joint_rots = t
        elif t.ndim == 3 and t.shape[-1] == 3 and t.shape[-2] != 3:
            joint_coords = t

    vertices = verts.detach().cpu().numpy()
    if vertices.ndim == 3:
        vertices = vertices[0]
    rots_np = joint_rots.detach().cpu().numpy() if joint_rots is not None else None
    if rots_np is not None and rots_np.ndim == 4:
        rots_np = rots_np[0]
    coords_np = joint_coords.detach().cpu().numpy() if joint_coords is not None else None
    if coords_np is not None and coords_np.ndim == 3:
        coords_np = coords_np[0]
    # `faces` already loaded above for cache short-circuit.

    # Cache MHR rest data (idempotent per mhr_head).
    cs.ensure_mhr_rest_cache(mhr_head, device)

    if coords_np is not None:
        vertices = cs.normalize_bone_lengths(vertices, coords_np)

    pack = active_pack_paths()
    bs_sliders = s["blendshapes"]
    if any(v != 0.0 for v in bs_sliders.values()) and rots_np is not None:
        rest_verts = cs.ensure_mhr_rest_cache(mhr_head, device)
        vertices = cs.apply_face_blendshapes(
            vertices, rest_verts, bs_sliders, rots_np,
            presets_dir=str(pack.pack_dir),
            npz_path=str(pack.npz_path),
        )

    bl = s["bone_lengths"]
    if rots_np is not None and any(abs(bl[k] - 1.0) > 1e-9 for k in cs.BONE_LENGTH_KEYS):
        vertices = cs.apply_bone_length_scales(
            vertices,
            arm_scale=bl["arm"], leg_scale=bl["leg"],
            torso_scale=bl["torso"], neck_scale=bl["neck"],
            joint_rots_posed=rots_np,
        )

    # mhr_forward already produces vertices in an OpenGL-convention world
    # frame (Y up, Z toward the viewer); dropping them straight into Three.js
    # is correct.
    # Single overwriting file in tmp/; the `?v=...` query string below
    # defeats the browser/Three.js cache so each slider drag pulls the
    # fresh mesh rather than the stale one.
    render_id = uuid.uuid4().hex[:8]
    obj_path = get_paths().tmp_dir / "mesh.obj"
    write_obj(obj_path, vertices, faces, header=f"# sam3dbody job {job_id} render {render_id}")
    obj_url = f"/tmp/mesh.obj?v={render_id}"

    _render_cache_put(cache_key, vertices)

    elapsed = time.monotonic() - t0
    log.info("render job=%s render=%s verts=%d elapsed=%.2fs", job_id, render_id, len(vertices), elapsed)
    return RenderResult(
        job_id=job_id,
        obj_url=obj_url,
        obj_path=str(obj_path),
        elapsed_sec=elapsed,
        settings=s,
    )
