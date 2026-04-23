"""Animated FBX export — runs SAM3DBody per-frame on a video, then bakes the
motion into an FBX via Blender. The pipeline is split into two halves:

1. ``run_motion_inference(video_path, ...)``: the slow phase (SAM3 +
   SAM3DBody per frame). Writes a ``MotionSession`` into ``motion_session``'s
   LRU cache and returns it. The session stores raw per-frame pose params
   (``body_pose_params``, ``hand_pose_params``, ``global_rot``,
   ``pred_cam_t``) which are shape-independent — swapping characters later
   doesn't need another round of inference.
2. ``build_animated_fbx_from_motion(motion_id, settings, ...)``: the fast
   phase. Applies the current character settings (body PCA / bone / blend
   shapes) to the rest mesh, runs MHR forward per-frame to resolve posed
   joint rotations + coords for ground-lock, packages the data and spawns
   ``tools/build_animated_fbx.py`` under Blender.

``export_animated_fbx(video_path, settings, ...)`` remains as a convenience
wrapper that runs both phases in one call.
"""
from __future__ import annotations

import json
import logging
import os
import shlex
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch

from ..config import get_paths
from . import character_shape as cs
from . import motion_session
from .fbx_export import _KNOWN_JOINT_NAMES, _scale_skeleton_rest, _unpack_mhr_forward
from .motion_session import MotionSession
from .preset_pack import active_pack_paths
from .sam3_mask import extract_best_person_mask
from .sam3dbody_loader import load_bundle
from .video_frames import iter_frames_rgb, probe_video

log = logging.getLogger(__name__)

# MHR joint ids for feet (match upstream constants for ground-lock logic).
_FOOT_JOINT_L = 4
_FOOT_JOINT_R = 20

_ROOT_MOTION_MODES = ("auto_ground_lock", "free", "xz_only")

# Ground-lock tunables (per upstream; see docstrings in export_animated.py).
_GL_Y_THR = 0.15
_GL_V_THR = 0.03
_GL_MIN_CONTACT_RUN = 2
_GL_SMOOTH_WINDOW = 5
_GL_SMOOTH_ORDER = 2
_GL_MIN_CONTACTS_TOTAL = 3


# ---------------------------------------------------------------------------
# Ground-lock helpers (ported verbatim from upstream).
# ---------------------------------------------------------------------------

def _y_central_diff(y: np.ndarray) -> np.ndarray:
    n = y.shape[0]
    out = np.zeros_like(y)
    if n < 2:
        return out
    out[1:-1] = np.abs(y[2:] - y[:-2]) / 2.0
    out[0] = np.abs(y[1] - y[0])
    out[-1] = np.abs(y[-1] - y[-2])
    return out


def _apply_contact_hysteresis(is_contact_raw: np.ndarray, min_run: int) -> np.ndarray:
    n, nf = is_contact_raw.shape
    out = np.zeros_like(is_contact_raw)
    for f in range(nf):
        col = is_contact_raw[:, f]
        i = 0
        while i < n:
            if col[i]:
                j = i
                while j < n and col[j]:
                    j += 1
                if (j - i) >= min_run:
                    out[i:j, f] = True
                i = j
            else:
                i += 1
    return out


def _fill_nan_linear(arr: np.ndarray) -> np.ndarray:
    arr = arr.copy()
    nan_mask = np.isnan(arr)
    if not nan_mask.any():
        return arr
    if nan_mask.all():
        return np.zeros_like(arr)
    valid_idx = np.where(~nan_mask)[0]
    all_idx = np.arange(len(arr))
    arr[nan_mask] = np.interp(all_idx[nan_mask], valid_idx, arr[valid_idx])
    return arr


def _smooth_offset(offset: np.ndarray, window: int, order: int) -> np.ndarray:
    n = len(offset)
    if n < window or window < 3:
        return offset
    try:
        from scipy.signal import savgol_filter
        return savgol_filter(offset, window_length=window, polyorder=order).astype(np.float32)
    except Exception:  # noqa: BLE001
        k = window // 2
        padded = np.pad(offset, k, mode='edge')
        kernel = np.ones(window, dtype=np.float32) / float(window)
        return np.convolve(padded, kernel, mode='valid').astype(np.float32)


def _compute_ground_lock_offset(
    feet_pos_arr: np.ndarray, trans_arr: np.ndarray, rest_foot_y: float
) -> np.ndarray:
    n = feet_pos_arr.shape[0]
    if n == 0:
        return np.zeros(0, dtype=np.float32)
    pose_feet_y = feet_pos_arr[..., 1].astype(np.float32)
    world_feet_y = pose_feet_y + trans_arr[:, 1:2].astype(np.float32)

    is_low = pose_feet_y <= (rest_foot_y + _GL_Y_THR)
    world_y_vel = _y_central_diff(world_feet_y)
    is_still = world_y_vel <= _GL_V_THR
    is_contact_raw = is_low & is_still
    is_contact = _apply_contact_hysteresis(is_contact_raw, _GL_MIN_CONTACT_RUN)

    contact_frame_count = int(is_contact.any(axis=1).sum())
    if contact_frame_count < _GL_MIN_CONTACTS_TOTAL:
        min_world = float(world_feet_y.min())
        correction = float(rest_foot_y - min_world)
        log.info("ground_lock fallback (%d/%d frames): global min correction=%+.3f",
                 contact_frame_count, n, correction)
        return np.full(n, correction, dtype=np.float32)

    anchor_y = np.full(n, np.nan, dtype=np.float32)
    for i in range(n):
        row_mask = is_contact[i]
        if row_mask.any():
            anchor_y[i] = float(world_feet_y[i, row_mask].min())
    anchor_y = _fill_nan_linear(anchor_y)
    offset = (rest_foot_y - anchor_y).astype(np.float32)
    offset = _smooth_offset(offset, _GL_SMOOTH_WINDOW, _GL_SMOOTH_ORDER)
    log.info(
        "ground_lock contact-based: %d/%d frames with contact, offset=[%+.3f, %+.3f], mean=%+.3f",
        contact_frame_count, n, float(offset.min()), float(offset.max()), float(offset.mean()),
    )
    return offset


def _as_vec3(value):
    if value is None:
        return None
    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    try:
        arr = np.asarray(value, dtype=np.float32).reshape(-1)
    except Exception:  # noqa: BLE001
        return None
    if arr.size < 3:
        return None
    return arr[:3].copy()


def _normalise_translations(raw_trans: list) -> list:
    n = len(raw_trans)
    if n == 0:
        return []
    anchor = None
    last_known = np.zeros(3, dtype=np.float32)
    out = []
    for t in raw_trans:
        if t is not None:
            if anchor is None:
                anchor = t.copy()
            last_known = t
        if anchor is None:
            out.append(np.zeros(3, dtype=np.float32))
        else:
            out.append((last_known - anchor).astype(np.float32))
    return [v.tolist() for v in out]


# ---------------------------------------------------------------------------
# Phase 1: per-frame SAM3 + SAM3DBody inference → cached MotionSession
# ---------------------------------------------------------------------------

@dataclass
class AnimatedFBXResult:
    fbx_path: str
    fbx_url: str
    elapsed_sec: float
    num_frames: int
    skipped_frames: int
    motion_id: str


def run_motion_inference(
    video_path: str | Path,
    *,
    bbox_threshold: float = 0.8,
    inference_type: str = "full",
    max_frames: int | None = None,
    stride: int = 1,
    use_sam3: bool = True,
    sam3_text_prompt: str = "person",
    sam3_threshold: float = 0.5,
    fps: float | None = None,
) -> MotionSession:
    """Iterate frames, run SAM3 (optional) + SAM3DBody on each, and cache
    the raw per-frame outputs under a fresh ``motion_id``. Subsequent
    ``build_animated_fbx_from_motion`` calls reuse the cache so swapping
    character presets/JSON doesn't re-run the slow inference."""
    t0 = time.monotonic()
    video_path = Path(video_path)
    info = probe_video(video_path)
    effective_fps = float(fps) if fps else float(info["fps"] or 30.0) / max(stride, 1)
    log.info("motion inference: %s (%dx%d, %d frames, src fps=%.2f, stride=%d)",
             video_path.name, info["width"], info["height"], info["frame_count"],
             info["fps"], stride)

    bundle = load_bundle()

    frames_body: list[np.ndarray | None] = []
    frames_hand: list[np.ndarray | None] = []
    frames_grot: list[np.ndarray | None] = []
    frames_cam: list[np.ndarray | None] = []
    skipped = 0
    frame_count = 0

    for f_i, frame_rgb in enumerate(iter_frames_rgb(video_path, max_frames=max_frames, stride=stride)):
        frame_count = f_i + 1
        mask_np = None
        bboxes = None
        if use_sam3:
            try:
                from PIL import Image as _Image
                pil = _Image.fromarray(frame_rgb)
                mr = extract_best_person_mask(
                    pil,
                    text_prompt=sam3_text_prompt,
                    confidence_threshold=sam3_threshold,
                )
                h, w = frame_rgb.shape[:2]
                bboxes = mr.bbox_xyxy.reshape(1, 4).astype(np.float32)
                mask_np = mr.mask.reshape(1, h, w, 1).astype(np.uint8)
            except Exception as exc:  # noqa: BLE001
                log.warning("frame %d SAM3 mask failed (%s); falling back to full frame", f_i, exc)

        try:
            outputs = bundle.estimator.process_one_image(
                frame_rgb,
                bboxes=bboxes,
                masks=mask_np,
                bbox_thr=bbox_threshold,
                use_mask=(mask_np is not None),
                inference_type=inference_type,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("frame %d estimator failed: %s", f_i, exc)
            outputs = []

        if not outputs:
            skipped += 1
            frames_body.append(None)
            frames_hand.append(None)
            frames_grot.append(None)
            frames_cam.append(None)
            continue

        raw = outputs[0]
        frames_body.append(np.asarray(raw.get("body_pose_params"), dtype=np.float32))
        frames_hand.append(np.asarray(raw.get("hand_pose_params"), dtype=np.float32))
        frames_grot.append(np.asarray(raw.get("global_rot"), dtype=np.float32))
        cam_vec = None
        for key in ("pred_cam_t", "camera", "global_trans"):
            cam_vec = _as_vec3(raw.get(key))
            if cam_vec is not None:
                break
        frames_cam.append(cam_vec)

        if (f_i + 1) % 10 == 0:
            log.info("motion inference %d frames…", f_i + 1)

    if frame_count == 0:
        raise RuntimeError(f"no frames decoded from {video_path}")

    motion = MotionSession(
        motion_id=uuid.uuid4().hex[:12],
        frames_body_pose=frames_body,
        frames_hand_pose=frames_hand,
        frames_global_rot=frames_grot,
        frames_cam_t=frames_cam,
        num_frames=frame_count,
        skipped_frames=skipped,
        fps=effective_fps,
        source_name=video_path.name,
    )
    motion_session.put(motion)
    log.info("motion cached: id=%s frames=%d skipped=%d elapsed=%.2fs",
             motion.motion_id, frame_count, skipped, time.monotonic() - t0)
    return motion


# ---------------------------------------------------------------------------
# Phase 2: build animated FBX from a cached MotionSession + character settings
# ---------------------------------------------------------------------------

def build_animated_fbx_from_motion(
    motion_id: str,
    settings: dict[str, Any] | None,
    *,
    blender_exe: str,
    root_motion_mode: str = "auto_ground_lock",
    timeout_sec_base: int = 600,
) -> AnimatedFBXResult:
    """Rebuild an animated FBX for ``motion_id`` with the given character
    ``settings``. The slow motion inference is NOT re-run — only MHR forward
    (fast) + the Blender subprocess."""
    t0 = time.monotonic()
    if root_motion_mode not in _ROOT_MOTION_MODES:
        root_motion_mode = "auto_ground_lock"

    motion = motion_session.get(motion_id)
    if motion is None:
        raise KeyError(f"no motion session for id {motion_id!r}")

    paths = get_paths()
    bundle = load_bundle()
    model = bundle.model
    device = torch.device(bundle.device)
    mhr_head = model.head_pose

    cs.ensure_mhr_rest_cache(mhr_head, device)
    parents = cs._FACE_BS_CACHE["joint_parents"].astype(np.int32)
    lbs_weights = cs._FACE_BS_CACHE["lbs_weights"].astype(np.float32)
    cats = cs._FACE_BS_CACHE["joint_chain_cats"]
    num_joints = parents.shape[0]
    faces = mhr_head.faces.detach().cpu().numpy().astype(np.int32)

    s = settings or {}
    bp = s.get("body_params") or {}
    bl = s.get("bone_lengths") or {}
    bs = s.get("blendshapes") or {}

    shape_params = cs.build_shape_params(bp, mhr_head.num_shape_comps, device)
    scale_params = torch.zeros((1, mhr_head.num_scale_comps), dtype=torch.float32, device=device)
    expr_params = torch.zeros((1, mhr_head.num_face_comps), dtype=torch.float32, device=device)

    # ===== Character rest pose =====
    zeros3 = torch.zeros((1, 3), dtype=torch.float32, device=device)
    body_zero = torch.zeros((1, 133), dtype=torch.float32, device=device)
    hand_zero = torch.zeros((1, 108), dtype=torch.float32, device=device)
    global_trans = torch.zeros((1, 3), dtype=torch.float32, device=device)

    with torch.no_grad():
        rest_out = mhr_head.mhr_forward(
            global_trans=global_trans, global_rot=zeros3,
            body_pose_params=body_zero, hand_pose_params=hand_zero,
            scale_params=scale_params, shape_params=shape_params,
            expr_params=expr_params,
            return_joint_rotations=True, return_joint_coords=True,
        )
    char_rest_verts = rest_out[0].detach().cpu().numpy().astype(np.float32)
    if char_rest_verts.ndim == 3:
        char_rest_verts = char_rest_verts[0]
    char_rest_rots, char_rest_coords = _unpack_mhr_forward(rest_out[1:])
    char_rest_rots = char_rest_rots.astype(np.float32)
    char_rest_coords = char_rest_coords.astype(np.float32)

    bs_sliders = {str(k): float(v) for k, v in bs.items()}
    if any(v != 0.0 for v in bs_sliders.values()):
        pack = active_pack_paths()
        char_rest_verts = cs.apply_face_blendshapes(
            char_rest_verts, cs._FACE_BS_CACHE["rest_verts"], bs_sliders,
            char_rest_rots,
            presets_dir=str(pack.pack_dir), npz_path=str(pack.npz_path),
        )

    bone_scales = {
        "torso": float(bl.get("torso", 1.0)),
        "neck":  float(bl.get("neck",  1.0)),
        "arm":   float(bl.get("arm",   1.0)),
        "leg":   float(bl.get("leg",   1.0)),
    }
    any_bone_scaled = any(v != 1.0 for v in bone_scales.values())
    if any_bone_scaled:
        char_rest_verts = cs.apply_bone_length_scales(
            char_rest_verts,
            arm_scale=bone_scales["arm"], leg_scale=bone_scales["leg"],
            torso_scale=bone_scales["torso"], neck_scale=bone_scales["neck"],
            joint_rots_posed=char_rest_rots,
        )
        char_rest_coords = _scale_skeleton_rest(char_rest_coords, parents, cats, bone_scales)

    # ===== Per-frame MHR forward (fast; no SAM3) =====
    frames_posed_rots: list[np.ndarray] = []
    frames_feet_pos: list[np.ndarray] = []
    last_good_pose = None
    last_good_feet_pos = np.stack([
        char_rest_coords[_FOOT_JOINT_L], char_rest_coords[_FOOT_JOINT_R],
    ], axis=0)

    for f_i in range(motion.num_frames):
        bpose = motion.frames_body_pose[f_i]
        hpose = motion.frames_hand_pose[f_i]
        grot = motion.frames_global_rot[f_i]
        if bpose is None:
            # Skipped frame: hold the previous good pose so the clip stays contiguous.
            if last_good_pose is None:
                posed_rots = char_rest_rots.copy()
            else:
                posed_rots = last_good_pose
            frames_posed_rots.append(posed_rots)
            frames_feet_pos.append(last_good_feet_pos.copy())
            continue

        body_pose_t = cs.to_tensor_1xN(bpose, device, width=133)
        hand_pose_t = cs.to_tensor_1xN(hpose, device, width=108)
        global_rot_t = cs.to_tensor_1xN(grot, device, width=3)
        with torch.no_grad():
            posed_out = mhr_head.mhr_forward(
                global_trans=global_trans, global_rot=global_rot_t,
                body_pose_params=body_pose_t, hand_pose_params=hand_pose_t,
                scale_params=scale_params, shape_params=shape_params,
                expr_params=expr_params,
                return_joint_rotations=True, return_joint_coords=True,
            )
        posed_rots, posed_coords = _unpack_mhr_forward(posed_out[1:])
        posed_rots = posed_rots.astype(np.float32)
        last_good_pose = posed_rots
        frames_posed_rots.append(posed_rots)

        if posed_coords is not None:
            pc = np.asarray(posed_coords, dtype=np.float32)
            feet_pos = np.stack([pc[_FOOT_JOINT_L], pc[_FOOT_JOINT_R]], axis=0)
            last_good_feet_pos = feet_pos
        else:
            feet_pos = last_good_feet_pos.copy()
        frames_feet_pos.append(feet_pos)

    # ===== Prune weightless leaves (same policy as rigged FBX) =====
    names_full = [_KNOWN_JOINT_NAMES.get(i, f"joint_{i:03d}") for i in range(num_joints)]
    nonzero = lbs_weights > 1e-5
    v_idx, j_idx = np.where(nonzero)
    w_val = lbs_weights[nonzero].astype(np.float32)

    keep = lbs_weights.sum(axis=0) > 1e-6
    for j in range(num_joints - 1, -1, -1):
        if keep[j]:
            p = int(parents[j])
            if p >= 0:
                keep[p] = True
    kept_idx = np.where(keep)[0]
    j_remap = np.full(num_joints, -1, dtype=np.int32)
    for new, old in enumerate(kept_idx):
        j_remap[old] = new

    new_parents = [
        int(j_remap[int(parents[o])]) if int(parents[o]) >= 0 else -1
        for o in kept_idx
    ]
    names = [names_full[o] for o in kept_idx]
    rest_coords_out = char_rest_coords[kept_idx]
    rest_rots_out = char_rest_rots[kept_idx]
    frames_posed_rots_out = [pr[kept_idx].tolist() for pr in frames_posed_rots]

    j_idx_new = j_remap[j_idx]
    valid = j_idx_new >= 0
    v_idx = v_idx[valid]
    j_idx_new = j_idx_new[valid]
    w_val = w_val[valid]

    # ===== Root translation & ground lock =====
    frames_root_trans = _normalise_translations(motion.frames_cam_t)
    detected_trans = sum(1 for t in motion.frames_cam_t if t is not None)
    if frames_root_trans:
        trans_arr = np.asarray(frames_root_trans, dtype=np.float32)
        if root_motion_mode == "xz_only":
            trans_arr[:, 1] = 0.0
            log.info("root_motion_mode=xz_only: zeroed Y component")
        elif root_motion_mode == "auto_ground_lock" and frames_feet_pos:
            feet_pos_arr = np.stack(frames_feet_pos, axis=0)
            rest_feet_y = float(min(
                char_rest_coords[_FOOT_JOINT_L][1],
                char_rest_coords[_FOOT_JOINT_R][1],
            ))
            offset = _compute_ground_lock_offset(feet_pos_arr, trans_arr, rest_feet_y)
            trans_arr[:, 1] += offset
        else:
            log.info("root_motion_mode=%s: no Y correction", root_motion_mode)
        frames_root_trans = trans_arr.tolist()

    log.info(
        "animated FBX build: motion_id=%s %d frames (cam_t on %d, skipped %d), %d / %d joints kept",
        motion.motion_id, motion.num_frames, detected_trans, motion.skipped_frames,
        len(kept_idx), num_joints,
    )

    # ===== Package + Blender subprocess =====
    # Single overwriting file — callers that want a distinct filename on
    # disk should copy it after download. The frontend cache-busts with ?v=.
    output_path = (paths.tmp_dir / "animated.fbx").resolve()

    package = {
        "output_path": str(output_path),
        "fps": float(motion.fps),
        "rest_verts": char_rest_verts.tolist(),
        "faces": faces.tolist(),
        "joint_parents": new_parents,
        "joint_names": names,
        "rest_joint_coords": rest_coords_out.tolist(),
        "rest_joint_rots": rest_rots_out.tolist(),
        "frames_posed_joint_rots": frames_posed_rots_out,
        "frames_root_trans": frames_root_trans,
        "lbs_v_idx": v_idx.astype(np.int32).tolist(),
        "lbs_j_idx": j_idx_new.astype(np.int32).tolist(),
        "lbs_weight": w_val.tolist(),
    }

    build_script = (paths.root / "tools" / "build_animated_fbx.py").resolve()
    if not build_script.is_file():
        raise RuntimeError(f"Blender build script missing: {build_script}")
    if not blender_exe or not Path(blender_exe).exists():
        raise RuntimeError(
            f"Blender executable not found: {blender_exe!r}. "
            "Set SAM3DBODY_BLENDER_EXE or pass blender_exe."
        )

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tmp:
        json.dump(package, tmp)
        tmp_json = tmp.name

    cmd = [blender_exe, "--background", "--python", str(build_script), "--", "--input", tmp_json]
    timeout_s = max(timeout_sec_base, 30 + 2 * motion.num_frames)
    log.info("blender subprocess: %s (timeout %ds)",
             " ".join(shlex.quote(c) for c in cmd), timeout_s)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
        if result.returncode != 0:
            log.error("blender stdout:\n%s", result.stdout or "")
            log.error("blender stderr:\n%s", result.stderr or "")
            raise RuntimeError(
                f"Blender animated FBX export failed (exit {result.returncode})."
            )
        if result.stdout:
            log.info("blender stdout tail:\n%s", result.stdout[-1200:])
    finally:
        try:
            os.unlink(tmp_json)
        except OSError:
            pass

    if not output_path.is_file():
        raise RuntimeError(f"Blender reported success but {output_path} was not created.")

    fbx_url = f"/tmp/animated.fbx?v={uuid.uuid4().hex[:8]}"
    elapsed = time.monotonic() - t0
    log.info("animated FBX written: %s (%.2fs, %d frames)",
             output_path, elapsed, motion.num_frames)
    return AnimatedFBXResult(
        fbx_path=str(output_path),
        fbx_url=fbx_url,
        elapsed_sec=elapsed,
        num_frames=motion.num_frames,
        skipped_frames=motion.skipped_frames,
        motion_id=motion.motion_id,
    )


# ---------------------------------------------------------------------------
# Convenience wrapper — used by the legacy ``/api/process_video`` path.
# ---------------------------------------------------------------------------

def export_animated_fbx(
    video_path: str | Path,
    settings: dict[str, Any] | None,
    *,
    blender_exe: str,
    fps: float | None = None,
    bbox_threshold: float = 0.8,
    inference_type: str = "full",
    root_motion_mode: str = "auto_ground_lock",
    max_frames: int | None = None,
    stride: int = 1,
    use_sam3: bool = True,
    sam3_text_prompt: str = "person",
    sam3_threshold: float = 0.5,
    timeout_sec_base: int = 600,
) -> AnimatedFBXResult:
    """Run motion inference + build the FBX in one call. Retained as a
    convenience for callers that don't need the motion-cache split."""
    motion = run_motion_inference(
        video_path,
        bbox_threshold=bbox_threshold,
        inference_type=inference_type,
        max_frames=max_frames,
        stride=stride,
        use_sam3=use_sam3,
        sam3_text_prompt=sam3_text_prompt,
        sam3_threshold=sam3_threshold,
        fps=fps,
    )
    return build_animated_fbx_from_motion(
        motion.motion_id,
        settings,
        blender_exe=blender_exe,
        root_motion_mode=root_motion_mode,
        timeout_sec_base=timeout_sec_base,
    )
