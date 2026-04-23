"""Rigged FBX export — runs MHR forward on CPU/GPU to build the character's
rest + posed skeletons, sparse LBS weights, and mesh, then dumps the package
as JSON for the Blender subprocess in ``tools/build_rigged_fbx.py``.

Mirrors ``nodes/processing/export_rigged.py`` of the upstream custom node,
minus the ComfyUI input wiring — our inputs come from a cached pose session
(produced by ``/api/process``) + a settings dict (produced by the
body/bone/blendshape sliders).
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
from . import pose_session
from .preset_pack import active_pack_paths
from .sam3dbody_loader import load_bundle

log = logging.getLogger(__name__)


# MHR joint index → human-readable bone name (dominant joints only; the rest
# default to joint_NNN).
_KNOWN_JOINT_NAMES = {
    1:   "pelvis",
    2:   "thigh_l",   3:  "calf_l",   4:  "foot_l",
    18:  "thigh_r",  19:  "calf_r",  20:  "foot_r",
    35:  "spine_01", 36:  "spine_02", 37: "spine_03",
    38:  "clavicle_r", 39: "upperarm_r", 40: "lowerarm_r", 42: "hand_r",
    74:  "clavicle_l", 75: "upperarm_l", 76: "lowerarm_l", 78: "hand_l",
    110: "neck_01",  113: "head",
}


@dataclass
class FBXExportResult:
    fbx_path: str
    fbx_url: str
    elapsed_sec: float


def _scale_skeleton_rest(joint_coords: np.ndarray,
                         parents: np.ndarray,
                         cats: np.ndarray,
                         bone_scales: dict[str, float]) -> np.ndarray:
    """Recompute joint positions after applying the per-chain bone-length
    scales. Must be kept in sync with the forward sweep inside
    ``apply_bone_length_scales`` so the rigged rest skeleton matches the mesh."""
    scale_by_cat = np.array(
        [1.0, bone_scales["torso"], bone_scales["neck"],
         bone_scales["arm"], bone_scales["leg"]],
        dtype=np.float32,
    )
    new_pos = np.zeros_like(joint_coords)
    num_joints = joint_coords.shape[0]
    for j in range(num_joints):
        p = int(parents[j])
        if p < 0:
            new_pos[j] = joint_coords[j]
            continue
        off = joint_coords[j] - joint_coords[p]
        s = float(scale_by_cat[int(cats[j])])
        new_pos[j] = new_pos[p] + s * off
    return new_pos


def _unpack_mhr_forward(tensor_tuple):
    rots = coords = None
    for t in tensor_tuple:
        if t.ndim == 4 and t.shape[-1] == 3 and t.shape[-2] == 3:
            rots = t
        elif t.ndim == 3 and t.shape[-1] == 3 and t.shape[-2] != 3:
            coords = t
    r = rots.detach().cpu().numpy() if rots is not None else None
    c = coords.detach().cpu().numpy() if coords is not None else None
    if r is not None and r.ndim == 4:
        r = r[0]
    if c is not None and c.ndim == 3:
        c = c[0]
    return r, c


def export_rigged_fbx(
    job_id: str,
    settings: dict[str, Any] | None,
    *,
    blender_exe: str,
    timeout_sec: int = 600,
) -> FBXExportResult:
    """Build a rigged FBX for ``job_id`` with ``settings``. Spawns a Blender
    headless subprocess for the final step."""
    t0 = time.monotonic()
    sess = pose_session.get(job_id)
    if sess is None:
        raise KeyError(f"no pose session for job_id {job_id!r}")

    paths = get_paths()
    bundle = load_bundle()
    model = bundle.model
    device = torch.device(bundle.device)
    mhr_head = model.head_pose

    # Prime the rest-pose cache used by apply_bone_length_scales / apply_face_blendshapes.
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

    # Character REST pose (body_pose = 0).
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

    # Blend shapes (applied in rest frame: `R_rel = R_posed @ inv(R_rest)`
    # collapses to identity when posed==rest, so deltas are added in rest
    # orientation — what a rigged character needs).
    bs_sliders = {str(k): float(v) for k, v in bs.items()}
    if any(v != 0.0 for v in bs_sliders.values()):
        pack = active_pack_paths()
        char_rest_verts = cs.apply_face_blendshapes(
            char_rest_verts,
            cs._FACE_BS_CACHE["rest_verts"],
            bs_sliders,
            char_rest_rots,
            presets_dir=str(pack.pack_dir),
            npz_path=str(pack.npz_path),
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

    # POSED skeleton (body_pose from the cached pose session).
    global_rot_t = cs.to_tensor_1xN(sess.global_rot, device, width=3)
    body_pose_t = cs.to_tensor_1xN(sess.body_pose_params, device, width=133)
    hand_pose_t = cs.to_tensor_1xN(sess.hand_pose_params, device, width=108)
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
    posed_coords = posed_coords.astype(np.float32)
    if any_bone_scaled:
        posed_coords = _scale_skeleton_rest(posed_coords, parents, cats, bone_scales)

    # Single overwriting file — the frontend cache-busts with ?v=...
    output_path = (paths.tmp_dir / "rigged.fbx").resolve()

    names_full = [_KNOWN_JOINT_NAMES.get(i, f"joint_{i:03d}") for i in range(num_joints)]

    # Sparse LBS entries.
    nonzero = lbs_weights > 1e-5
    v_idx, j_idx = np.where(nonzero)
    w_val = lbs_weights[nonzero].astype(np.float32)

    # Prune weightless leaf joints (keep ancestors of weighted joints).
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
    posed_coords_out = posed_coords[kept_idx]
    posed_rots_out = posed_rots[kept_idx]

    j_idx_new = j_remap[j_idx]
    valid = j_idx_new >= 0
    v_idx = v_idx[valid]
    j_idx_new = j_idx_new[valid]
    w_val = w_val[valid]

    log.info("rigged FBX: job=%s kept %d / %d joints",
             job_id, len(kept_idx), num_joints)

    package = {
        "output_path": str(output_path),
        "rest_verts": char_rest_verts.tolist(),
        "faces": faces.tolist(),
        "joint_parents": new_parents,
        "joint_names": names,
        "rest_joint_coords": rest_coords_out.tolist(),
        "rest_joint_rots": rest_rots_out.tolist(),
        "posed_joint_coords": posed_coords_out.tolist(),
        "posed_joint_rots": posed_rots_out.tolist(),
        "lbs_v_idx": v_idx.astype(np.int32).tolist(),
        "lbs_j_idx": j_idx_new.astype(np.int32).tolist(),
        "lbs_weight": w_val.tolist(),
    }

    # Build script lives next to the app root (tools/build_rigged_fbx.py).
    build_script = (paths.root / "tools" / "build_rigged_fbx.py").resolve()
    if not build_script.is_file():
        raise RuntimeError(f"Blender build script missing: {build_script}")

    if not blender_exe or not Path(blender_exe).exists():
        raise RuntimeError(
            f"Blender executable not found: {blender_exe!r}. "
            "Set SAM3DBODY_BLENDER_EXE or pass blender_exe explicitly."
        )

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tmp:
        json.dump(package, tmp)
        tmp_json = tmp.name

    cmd = [blender_exe, "--background", "--python", str(build_script), "--", "--input", tmp_json]
    log.info("blender subprocess: %s", " ".join(shlex.quote(c) for c in cmd))
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_sec)
        if result.returncode != 0:
            log.error("blender stdout:\n%s", result.stdout or "")
            log.error("blender stderr:\n%s", result.stderr or "")
            raise RuntimeError(
                f"Blender FBX export failed (exit {result.returncode}). See server log."
            )
        if result.stdout:
            tail = result.stdout[-800:]
            log.info("blender stdout tail:\n%s", tail)
    finally:
        try:
            os.unlink(tmp_json)
        except OSError:
            pass

    if not output_path.is_file():
        # 終了コード 0 でも FBX が無い ≒ bpy.ops.export_scene.fbx 側の silent 失敗。
        # トラブルシュート用に subprocess 出力を残す。
        log.error("blender stdout:\n%s", result.stdout or "")
        log.error("blender stderr:\n%s", result.stderr or "")
        raise RuntimeError(f"Blender reported success but {output_path} was not created.")

    fbx_url = f"/tmp/rigged.fbx?v={uuid.uuid4().hex[:8]}"
    elapsed = time.monotonic() - t0
    log.info("rigged FBX written: %s (%.2fs)", output_path, elapsed)
    return FBXExportResult(fbx_path=str(output_path), fbx_url=fbx_url, elapsed_sec=elapsed)
