"""Character body-shape application (PCA body shape + bone-length scaling +
blend shapes), ported from ``nodes/processing/process.py`` of the upstream
ComfyUI-SAM3DBody_utills fork.

The heavy lifting is all ``numpy`` on the CPU:
  * ``_apply_bone_length_scales``  — isotropic per-joint mesh scaling
  * ``_apply_face_blendshapes``    — morph-target deltas with per-vertex
                                     SVD-orthogonalised rotation
  * ``_normalize_bone_lengths``    — pose-corrective normalisation

A single module-level cache (``_FACE_BS_CACHE``) holds the MHR rest vertices,
joint rotations / coords and LBS weights — all computed once per MHR model
instance and reused for every subsequent slider-change render.
"""
from __future__ import annotations

import json
import logging
import math
import os
from pathlib import Path

import numpy as np
import torch

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pose adjustment — "lean correction" applied AFTER mhr_forward.
# ---------------------------------------------------------------------------
#
# ``lean_correction`` is a 0..1 slider that counteracts SAM3DBody's tendency
# to return slightly forward-leaning poses on upright standing subjects.
#
# We modify the ``body_pose_params`` indirectly by post-rotating the
# spine → neck kinematic chain, joint by joint, in body-local world space:
#
#     spine_01 (35)  → smallest backward pitch
#     spine_02 (36)
#     spine_03 (37)
#     neck_01  (110) → largest backward pitch
#
# Each joint contributes an independent rotation around its own pivot; the
# rotations compound down the chain so the head straightens up more than
# the hips do (matches how real humans un-bend a forward-leaning spine).
# The mesh variant blends the rotation by LBS subtree weight so vertices
# dominated by e.g. arms / hands aren't dragged along with the torso. The
# rig variant (used by FBX export) applies the full rotation to every
# descendant joint so the exported rig carries the correction.
#
# Earlier version of this helper composed the correction into ``global_rot``
# (ZYX euler) instead, but that tilted the whole body (including legs) and
# came out diagonal whenever the body had any yaw. The chain-pivot approach
# keeps the feet planted and only straightens the upper body.

POSE_ADJUST_KEYS = ("lean_correction",)
# Per-key neutral / default value for pose_adjust. ``lean_correction`` ships
# at 0.5 ("いい感じ") because SAM3DBody's output is biased slightly forward
# for standing subjects — starting at zero would require every user to move
# the slider up to get a natural stance.
POSE_ADJUST_DEFAULTS: dict[str, float] = {
    "lean_correction": 0.5,
}

# (joint_id, base_angle_rad) pairs applied in chain order. base_angle scaled
# by slider strength ∈ [0, 1]. strength=1.0 → ~20° cumulative backward tilt
# at the head; strength=0.5 → ~10° (calibrated against standing reference
# images 04_11, 01_10, 01_11, 02_11, 03_10, 04_10).
LEAN_CHAIN_DEFAULT: tuple[tuple[int, float], ...] = (
    (35,  math.radians(14.0)),    # spine_01
    (36,  math.radians(14.0)),    # spine_02
    (37,  math.radians(14.0)),   # spine_03
    (110, math.radians(2.0)),   # neck_01
    (113, math.radians(2.0)),    # head
)

def _subtree_indices(parents: np.ndarray, root: int) -> list[int]:
    """Return ``root`` + all its descendants in ``parents``-encoded tree."""
    num_joints = int(parents.shape[0])
    children: dict[int, list[int]] = {}
    for j in range(num_joints):
        p = int(parents[j])
        if p >= 0:
            children.setdefault(p, []).append(j)
    out: list[int] = []
    stack = [root]
    while stack:
        n = stack.pop()
        out.append(n)
        stack.extend(children.get(n, ()))
    return out


def _rotx_x_axis(theta: float) -> np.ndarray:
    c, s = math.cos(theta), math.sin(theta)
    return np.array([[1.0, 0.0, 0.0],
                     [0.0,   c,  -s],
                     [0.0,   s,   c]], dtype=np.float32)


def apply_pose_lean_correction_mesh(
    vertices: np.ndarray,
    joint_coords_posed: np.ndarray,
    strength: float,
    *,
    chain: tuple[tuple[int, float], ...] | None = None,
) -> np.ndarray:
    """Bend the posed mesh backward along the spine→neck chain, each joint
    contributing its ``_LEAN_CHAIN`` share scaled by ``strength``.

    Per-joint, rotates vertices around the joint's posed position by an angle
    proportional to that vertex's total LBS weight in the joint's subtree —
    so torso/head verts rotate fully while arm / hand / leg verts don't move
    just because they share a subtree root. Corrections are applied in order
    (spine→neck), and joint positions are carried forward between rounds so
    each pivot reflects the previous rotations.

    Requires ``_FACE_BS_CACHE`` populated via ``ensure_mhr_rest_cache``. The
    MHR coord system (X right, Y up, Z forward) governs the rotation axis —
    the X axis is the hip-lateral direction, so backward pitch = rotation
    around X.
    """
    if strength is None:
        return vertices
    try:
        s = float(strength)
    except (TypeError, ValueError):
        return vertices
    if not math.isfinite(s) or s <= 1e-6:
        return vertices

    W = _FACE_BS_CACHE.get("lbs_weights")
    parents = _FACE_BS_CACHE.get("joint_parents")
    if W is None or parents is None or joint_coords_posed is None:
        return vertices
    num_joints = int(parents.shape[0])

    # Normalised LBS weights (sum-to-1 per vertex), so subtree weight <= 1.
    Wsum = W.sum(axis=1, keepdims=True).astype(np.float32)
    Wsum_safe = np.where(Wsum > 1e-6, Wsum, 1.0)
    W_norm = (W / Wsum_safe).astype(np.float32)

    v = vertices.astype(np.float32, copy=True)
    jc = joint_coords_posed.astype(np.float32, copy=True)

    active_chain = chain if chain is not None else LEAN_CHAIN_DEFAULT
    for joint_id, base_angle in active_chain:
        if joint_id >= num_joints:
            continue
        theta = s * float(base_angle)
        if abs(theta) < 1e-8:
            continue

        subtree = _subtree_indices(parents, joint_id)
        if not subtree:
            continue

        pivot = jc[joint_id].copy()
        # Per-vertex effective angle = subtree LBS weight × theta. Negative
        # theta pitches backward (a point at +Z moves toward +Y), which is
        # the "un-bend forward lean" direction in MHR coords.
        sub_w = W_norm[:, subtree].sum(axis=1).astype(np.float32)  # (V,)
        eff = (-theta) * sub_w  # (V,)
        c = np.cos(eff)
        sn = np.sin(eff)
        dy = v[:, 1] - pivot[1]
        dz = v[:, 2] - pivot[2]
        v[:, 1] = pivot[1] + dy * c - dz * sn
        v[:, 2] = pivot[2] + dy * sn + dz * c
        # X untouched — rotation is around the world X axis at the pivot.

        # Carry forward: rotate descendants' joint_coords by the FULL theta
        # so subsequent chain pivots (spine_02 after spine_01, etc.) sit at
        # the correct post-rotation position.
        full_c = math.cos(-theta)
        full_s = math.sin(-theta)
        for k in subtree:
            ky = jc[k, 1] - pivot[1]
            kz = jc[k, 2] - pivot[2]
            jc[k, 1] = pivot[1] + ky * full_c - kz * full_s
            jc[k, 2] = pivot[2] + ky * full_s + kz * full_c

    return v.astype(vertices.dtype)


def apply_pose_lean_correction_rig(
    posed_joint_rots: np.ndarray,
    posed_joint_coords: np.ndarray,
    parents: np.ndarray,
    strength: float,
    *,
    chain: tuple[tuple[int, float], ...] | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Rig-space counterpart of ``apply_pose_lean_correction_mesh``.

    Applies each chain joint's backward pitch rotation to that joint and
    all descendants (no LBS blending — joints are rigid). Returns
    ``(new_posed_joint_rots, new_posed_joint_coords)``. Used by the FBX
    exporter so the correction rides in the exported rig.
    """
    rots = posed_joint_rots.astype(np.float32, copy=True)
    coords = posed_joint_coords.astype(np.float32, copy=True)
    if strength is None:
        return rots, coords
    try:
        s = float(strength)
    except (TypeError, ValueError):
        return rots, coords
    if not math.isfinite(s) or s <= 1e-6:
        return rots, coords
    if parents is None:
        return rots, coords

    num_joints = int(parents.shape[0])
    active_chain = chain if chain is not None else LEAN_CHAIN_DEFAULT
    for joint_id, base_angle in active_chain:
        if joint_id >= num_joints:
            continue
        theta = s * float(base_angle)
        if abs(theta) < 1e-8:
            continue

        subtree = _subtree_indices(parents, joint_id)
        if not subtree:
            continue

        pivot = coords[joint_id].copy()
        R_corr = _rotx_x_axis(-theta)  # world-frame backward pitch
        for k in subtree:
            off = coords[k] - pivot
            coords[k] = pivot + R_corr @ off
            rots[k] = R_corr @ rots[k]

    return rots, coords


# ---------------------------------------------------------------------------
# Constants — directly mirror the upstream node so presets stay compatible.
# ---------------------------------------------------------------------------

_UI_BLENDSHAPE_ORDER: tuple[str, ...] = (
    # face
    "face_big", "face_small", "face_mangabig", "face_manga", "chin_sharp", "face_wide",
    # neck
    "neck_thick", "neck_thin",
    # chest
    "breast_full", "breast_flat", "chest_slim",
    # shoulder
    "shoulder_wide", "shoulder_narrow", "shoulder_slope",
    # waist
    "waist_slim",
    # limbs
    "limb_thick", "limb_thin", "hand_big", "foot_big",
    # other
    "MuscleScale",
)

# FBX world-frame → MHR world-frame rotation used when loading blend-shape
# deltas from face_blendshapes.npz.
_FBX_TO_MHR_ROT = np.array(
    [[1.0,  0.0,  0.0],
     [0.0,  0.0,  1.0],
     [0.0, -1.0,  0.0]],
    dtype=np.float32,
)

# PCA slider normalisation & sign (see upstream comments in process.py).
SHAPE_SLIDER_NORM = (1.00, 2.78, 4.42, 8.74, 10.82, 11.70, 13.39, 13.83, 16.62)
SHAPE_SLIDER_SIGN = (+1, -1, -1, +1, -1, +1, -1, +1, +1)
# index 2 (fat_muscle) flipped after user reports the slider produced the
# opposite effect from its label. MHR's PCA basis has no guaranteed sign.
BODY_PARAM_KEYS = (
    "fat", "muscle", "fat_muscle", "limb_girth", "limb_muscle", "limb_fat",
    "chest_shoulder", "waist_hip", "thigh_calf",
)
BONE_LENGTH_KEYS = ("torso", "neck", "arm", "leg")

# Joint categories for bone-length scaling.
_TORSO_JOINT_IDS = frozenset({1, 34, 35, 36, 37, 110})
_NECK_JOINT_IDS = frozenset({113})
_ARM_BRANCH_IDS = (38, 74)
_LEG_BRANCH_IDS = (2, 18)
_MESH_SCALE_STRENGTH = 0.5

# Cache keyed by id(mhr_head). Matches upstream layout.
_FACE_BS_CACHE: dict = {
    "v_count": None,
    "rest_key": None,
    "rest_verts": None,
    "rest_joint_rots": None,
    "rest_joint_coords": None,
    "dominant_joint": None,
    "lbs_weights": None,
    "rest_weighted_joint_pos": None,
    "rest_offset_len": None,
    "normalize_mask": None,
    "region_ids": {},
    "region_deltas": {},
    "joint_parents": None,
    "joint_chain_cats": None,
}


# ---------------------------------------------------------------------------
# Blend-shape discovery (reads meta_shapes from face_blendshapes.npz).
# ---------------------------------------------------------------------------

def discover_blendshape_names(npz_path: str | Path) -> tuple[str, ...]:
    """Return the list of blend-shape names in the active pack's npz,
    ordered so the canonical UI order (``_UI_BLENDSHAPE_ORDER``) comes first
    and any extra shapes are appended alphabetically."""
    npz_path = str(npz_path)
    if not os.path.exists(npz_path):
        return _UI_BLENDSHAPE_ORDER
    shapes: tuple[str, ...] = ()
    try:
        with np.load(npz_path) as npz:
            if "meta_shapes" in npz.files:
                shapes = tuple(str(s) for s in np.asarray(npz["meta_shapes"]))
    except Exception:  # noqa: BLE001 — fall back cleanly if the npz is malformed
        pass
    if not shapes:
        return ()
    shapes_set = set(shapes)
    head = [s for s in _UI_BLENDSHAPE_ORDER if s in shapes_set]
    tail = sorted(s for s in shapes if s not in _UI_BLENDSHAPE_ORDER)
    return tuple(head + tail)


# ---------------------------------------------------------------------------
# MHR LBS / rest-pose extraction.
# ---------------------------------------------------------------------------

def _build_lbs_weights(mhr_head, num_verts: int, num_joints: int) -> np.ndarray:
    bufs = dict(mhr_head.mhr.named_buffers())
    key_v = key_j = key_w = None
    for k in bufs:
        lk = k.lower()
        if "vert_indices_flattened" in lk:
            key_v = k
        elif "skin_indices_flattened" in lk:
            key_j = k
        elif "skin_weights_flattened" in lk:
            key_w = k
    W = np.zeros((num_verts, num_joints), dtype=np.float32)
    if not (key_v and key_j and key_w):
        return W
    v_idx = bufs[key_v].detach().cpu().numpy().astype(np.int64)
    j_idx = bufs[key_j].detach().cpu().numpy().astype(np.int64)
    w_val = bufs[key_w].detach().cpu().numpy().astype(np.float32)
    valid = (v_idx >= 0) & (j_idx >= 0) & (v_idx < num_verts) & (j_idx < num_joints)
    np.add.at(W, (v_idx[valid], j_idx[valid]), w_val[valid])
    return W


def _compute_rest_lbs_anchors(
    rest_verts: np.ndarray, rest_joint_coords: np.ndarray, W: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    Wsum = W.sum(axis=1)
    Wsum_safe = np.where(Wsum > 1e-6, Wsum, 1.0).astype(np.float32)
    rest_anchor = (W @ rest_joint_coords) / Wsum_safe[:, None]
    rest_offset = rest_verts - rest_anchor
    rest_len = np.linalg.norm(rest_offset, axis=1).astype(np.float32)
    return rest_anchor.astype(np.float32), rest_len, Wsum_safe


def _compute_dominant_joints(mhr_head, num_verts: int, num_joints: int = 127) -> np.ndarray:
    W = _build_lbs_weights(mhr_head, num_verts, num_joints)
    if not np.any(W):
        return np.zeros(num_verts, dtype=np.int32)
    return np.argmax(W, axis=1).astype(np.int32)


def _compute_bone_chain_categories(parents: np.ndarray) -> np.ndarray:
    J = parents.shape[0]
    cats = np.zeros(J, dtype=np.int8)

    children: dict[int, list[int]] = {}
    for j in range(J):
        p = int(parents[j])
        if p >= 0:
            children.setdefault(p, []).append(j)

    def _subtree(root):
        out = []
        stack = [root]
        while stack:
            n = stack.pop()
            out.append(n)
            stack.extend(children.get(n, ()))
        return out

    for j in range(J):
        if j in _TORSO_JOINT_IDS:
            cats[j] = 1
        elif j in _NECK_JOINT_IDS:
            cats[j] = 2
    for branch in _ARM_BRANCH_IDS:
        if 0 <= branch < J:
            for k in _subtree(branch):
                if k != branch:
                    cats[k] = 3
    for branch in _LEG_BRANCH_IDS:
        if 0 <= branch < J:
            for k in _subtree(branch):
                if k != branch:
                    cats[k] = 4
    return cats


def ensure_mhr_rest_cache(mhr_head, device) -> np.ndarray:
    """Populate ``_FACE_BS_CACHE`` with rest vertices / joint rotations /
    LBS weights etc. for ``mhr_head``. Cached per ``id(mhr_head)``."""
    key = id(mhr_head)
    if _FACE_BS_CACHE["rest_key"] == key and _FACE_BS_CACHE["rest_verts"] is not None:
        return _FACE_BS_CACHE["rest_verts"]

    zeros3 = torch.zeros((1, 3), dtype=torch.float32, device=device)
    body_p = torch.zeros((1, 133), dtype=torch.float32, device=device)
    hand_p = torch.zeros((1, 108), dtype=torch.float32, device=device)
    scale = torch.zeros((1, mhr_head.num_scale_comps), dtype=torch.float32, device=device)
    shape = torch.zeros((1, mhr_head.num_shape_comps), dtype=torch.float32, device=device)
    expr = torch.zeros((1, mhr_head.num_face_comps), dtype=torch.float32, device=device)
    with torch.no_grad():
        out = mhr_head.mhr_forward(
            zeros3, zeros3, body_p, hand_p, scale, shape, expr,
            return_joint_rotations=True, return_joint_coords=True,
        )
    verts_t = out[0]
    rots_t = None
    coords_t = None
    for t in out[1:]:
        if t.ndim in (3, 4) and t.shape[-1] == 3 and t.shape[-2] == 3:
            rots_t = t
        elif t.ndim in (2, 3) and t.shape[-1] == 3:
            coords_t = t
    v = verts_t.detach().cpu().numpy()
    if v.ndim == 3:
        v = v[0]
    r = rots_t.detach().cpu().numpy() if rots_t is not None else None
    if r is not None and r.ndim == 4:
        r = r[0]
    c = coords_t.detach().cpu().numpy() if coords_t is not None else None
    if c is not None and c.ndim == 3:
        c = c[0]
    v = v.astype(np.float32)

    _FACE_BS_CACHE["rest_key"] = key
    _FACE_BS_CACHE["rest_verts"] = v
    _FACE_BS_CACHE["rest_joint_rots"] = r.astype(np.float32) if r is not None else None
    _FACE_BS_CACHE["rest_joint_coords"] = c.astype(np.float32) if c is not None else None
    _FACE_BS_CACHE["dominant_joint"] = _compute_dominant_joints(
        mhr_head,
        num_verts=v.shape[0],
        num_joints=r.shape[0] if r is not None else 127,
    )

    if c is not None:
        num_joints = r.shape[0] if r is not None else 127
        W = _build_lbs_weights(mhr_head, num_verts=v.shape[0], num_joints=num_joints)
        _FACE_BS_CACHE["lbs_weights"] = W
        anchor, rest_len, _ = _compute_rest_lbs_anchors(v, c, W)
        _FACE_BS_CACHE["rest_weighted_joint_pos"] = anchor
        _FACE_BS_CACHE["rest_offset_len"] = rest_len
        LOW, HIGH = 0.6, 0.9
        max_w = W.max(axis=1)
        strength = np.clip((max_w - LOW) / (HIGH - LOW), 0.0, 1.0).astype(np.float32)
        _FACE_BS_CACHE["normalize_mask"] = strength
    else:
        _FACE_BS_CACHE["lbs_weights"] = None
        _FACE_BS_CACHE["rest_weighted_joint_pos"] = None
        _FACE_BS_CACHE["rest_offset_len"] = None
        _FACE_BS_CACHE["normalize_mask"] = None

    parents = None
    try:
        bufs = dict(mhr_head.mhr.named_buffers())
        for k in bufs:
            if "joint_parents" in k.lower():
                parents = bufs[k].detach().cpu().numpy().astype(np.int32)
                break
    except Exception:  # noqa: BLE001
        parents = None
    _FACE_BS_CACHE["joint_parents"] = parents
    _FACE_BS_CACHE["joint_chain_cats"] = (
        _compute_bone_chain_categories(parents) if parents is not None else None
    )

    _FACE_BS_CACHE["v_count"] = None
    _FACE_BS_CACHE["region_ids"] = {}
    _FACE_BS_CACHE["region_deltas"] = {}
    return _FACE_BS_CACHE["rest_verts"]


# ---------------------------------------------------------------------------
# Bone-length normalisation (pose-corrective).
# ---------------------------------------------------------------------------

def normalize_bone_lengths(vertices: np.ndarray, posed_joint_coords: np.ndarray) -> np.ndarray:
    W = _FACE_BS_CACHE.get("lbs_weights")
    rest_len = _FACE_BS_CACHE.get("rest_offset_len")
    strength = _FACE_BS_CACHE.get("normalize_mask")
    if W is None or rest_len is None or strength is None or not np.any(strength):
        return vertices
    Wsum = W.sum(axis=1)
    Wsum_safe = np.where(Wsum > 1e-6, Wsum, 1.0).astype(np.float32)
    posed_anchor = (W @ posed_joint_coords) / Wsum_safe[:, None]
    posed_offset = vertices - posed_anchor
    posed_len = np.linalg.norm(posed_offset, axis=1).astype(np.float32)
    safe_posed = np.where(posed_len > 1e-6, posed_len, 1.0)
    scale = rest_len / safe_posed
    scale = np.where(np.abs(scale - 1.0) < 0.003, 1.0, scale)
    scale = np.clip(scale, 0.7, 1.3).astype(np.float32)
    effective_scale = (1.0 + (scale - 1.0) * strength).astype(np.float32)
    out = posed_anchor + posed_offset * effective_scale[:, None]
    return out.astype(vertices.dtype)


# ---------------------------------------------------------------------------
# Face / body blend shapes.
# ---------------------------------------------------------------------------

def _load_face_blendshapes(
    mhr_rest_verts: np.ndarray, presets_dir: str, npz_path: str
):
    v_count = int(mhr_rest_verts.shape[0])
    if _FACE_BS_CACHE["v_count"] == v_count and _FACE_BS_CACHE["region_ids"]:
        return _FACE_BS_CACHE["region_ids"], _FACE_BS_CACHE["region_deltas"]
    if not os.path.exists(npz_path):
        _FACE_BS_CACHE["v_count"] = v_count
        _FACE_BS_CACHE["region_ids"] = {}
        _FACE_BS_CACHE["region_deltas"] = {}
        return {}, {}

    npz = np.load(npz_path)
    if "meta_objects" not in npz.files:
        log.warning("face_blendshapes.npz has no 'meta_objects' key; regenerate with the Blender script")
        _FACE_BS_CACHE["v_count"] = v_count
        _FACE_BS_CACHE["region_ids"] = {}
        _FACE_BS_CACHE["region_deltas"] = {}
        return {}, {}

    object_names = [str(x) for x in np.asarray(npz["meta_objects"])]

    try:
        from scipy.spatial import cKDTree
    except Exception:  # noqa: BLE001
        cKDTree = None

    region_ids: dict[str, np.ndarray] = {}
    region_deltas: dict[str, dict[str, np.ndarray]] = {}
    for obj_name in object_names:
        base_key = f"base__{obj_name}"
        if base_key not in npz.files:
            continue
        fbx_base = np.asarray(npz[base_key], dtype=np.float32)
        fbx_base_mhr = fbx_base @ _FBX_TO_MHR_ROT.T

        json_path = os.path.join(presets_dir, f"{obj_name}_vertices.json")
        if not os.path.exists(json_path):
            log.warning("no region JSON for FBX object '%s' (%s); skipping its blend shapes", obj_name, json_path)
            continue
        with open(json_path, "r", encoding="utf-8") as f:
            mhr_ids = np.asarray(json.load(f), dtype=np.int64)
        mhr_pos = mhr_rest_verts[mhr_ids].astype(np.float32)

        if cKDTree is not None:
            tree = cKDTree(fbx_base_mhr)
            _, fbx_for_mhr = tree.query(mhr_pos, k=1)
        else:
            fbx_for_mhr = np.empty(len(mhr_pos), dtype=np.int64)
            for i, p in enumerate(mhr_pos):
                d2 = ((fbx_base_mhr - p) ** 2).sum(axis=1)
                fbx_for_mhr[i] = int(d2.argmin())

        region_ids[obj_name] = mhr_ids
        region_deltas[obj_name] = {}

        prefix = f"delta__{obj_name}__"
        for key in npz.files:
            if not key.startswith(prefix):
                continue
            shape_name = key[len(prefix):]
            delta_fbx = np.asarray(npz[key], dtype=np.float32)
            delta_mhr_all = delta_fbx @ _FBX_TO_MHR_ROT.T
            region_deltas[obj_name][shape_name] = delta_mhr_all[fbx_for_mhr].astype(np.float32)

    _FACE_BS_CACHE["v_count"] = v_count
    _FACE_BS_CACHE["region_ids"] = region_ids
    _FACE_BS_CACHE["region_deltas"] = region_deltas
    return region_ids, region_deltas


def apply_face_blendshapes(
    vertices: np.ndarray,
    mhr_rest_verts: np.ndarray,
    sliders: dict,
    joint_rots_posed: np.ndarray,
    presets_dir: str,
    npz_path: str,
) -> np.ndarray:
    if not any(float(v) != 0.0 for v in sliders.values()):
        return vertices
    rest_rots = _FACE_BS_CACHE.get("rest_joint_rots")
    W = _FACE_BS_CACHE.get("lbs_weights")
    if rest_rots is None or W is None:
        return vertices

    region_ids, region_deltas = _load_face_blendshapes(mhr_rest_verts, presets_dir, npz_path)
    if not region_deltas:
        return vertices

    R_rel_all = np.zeros_like(rest_rots)
    for j in range(rest_rots.shape[0]):
        R_posed = joint_rots_posed[j].astype(np.float32)
        R_rest = rest_rots[j]
        try:
            R_rest_inv = np.linalg.inv(R_rest).astype(np.float32)
        except np.linalg.LinAlgError:
            R_rest_inv = R_rest.T.astype(np.float32)
        R_rel_all[j] = (R_posed @ R_rest_inv).astype(np.float32)

    Wsum = W.sum(axis=1, keepdims=True)
    Wsum_safe = np.where(Wsum > 1e-6, Wsum, 1.0).astype(np.float32)
    W_norm = (W / Wsum_safe).astype(np.float32)

    out = vertices.copy()
    for obj_name, shape_dict in region_deltas.items():
        mhr_ids = region_ids[obj_name]
        if mhr_ids.size == 0:
            continue
        accum = np.zeros((mhr_ids.shape[0], 3), dtype=np.float32)
        had_any = False
        for shape_name, d in shape_dict.items():
            w = float(sliders.get(shape_name, 0.0))
            if w == 0.0:
                continue
            accum += w * d
            had_any = True
        if not had_any:
            continue
        region_W = W_norm[mhr_ids]
        R_eff = np.einsum("vj,jab->vab", region_W, R_rel_all)
        U, _S, Vt = np.linalg.svd(R_eff)
        det_uvt = np.linalg.det(np.einsum("vij,vjk->vik", U, Vt))
        flip = det_uvt < 0
        if np.any(flip):
            Vt[flip, -1, :] *= -1
        R_ortho = np.einsum("vij,vjk->vik", U, Vt).astype(np.float32)
        rotated = np.einsum("vab,vb->va", R_ortho, accum)
        out[mhr_ids] = (out[mhr_ids] + rotated).astype(vertices.dtype)
    return out


# ---------------------------------------------------------------------------
# Bone-length scaling.
# ---------------------------------------------------------------------------

def apply_bone_length_scales(
    vertices: np.ndarray,
    arm_scale: float,
    leg_scale: float,
    torso_scale: float,
    neck_scale: float,
    joint_rots_posed: np.ndarray,
) -> np.ndarray:
    if arm_scale == 1.0 and leg_scale == 1.0 and torso_scale == 1.0 and neck_scale == 1.0:
        return vertices
    W = _FACE_BS_CACHE.get("lbs_weights")
    rest_rots = _FACE_BS_CACHE.get("rest_joint_rots")
    rest_coords = _FACE_BS_CACHE.get("rest_joint_coords")
    rest_verts = _FACE_BS_CACHE.get("rest_verts")
    parents = _FACE_BS_CACHE.get("joint_parents")
    cats = _FACE_BS_CACHE.get("joint_chain_cats")
    if (W is None or rest_rots is None or rest_coords is None
            or rest_verts is None or parents is None or cats is None
            or joint_rots_posed is None):
        return vertices
    num_joints = rest_rots.shape[0]

    R_rel_all = np.zeros_like(rest_rots)
    for j in range(num_joints):
        R_posed = joint_rots_posed[j].astype(np.float32)
        R_rest = rest_rots[j]
        try:
            R_rest_inv = np.linalg.inv(R_rest).astype(np.float32)
        except np.linalg.LinAlgError:
            R_rest_inv = R_rest.T.astype(np.float32)
        R_rel_all[j] = (R_posed @ R_rest_inv).astype(np.float32)

    scale_by_cat = np.array(
        [1.0, float(torso_scale), float(neck_scale),
         float(arm_scale), float(leg_scale)],
        dtype=np.float32,
    )
    joint_scale = scale_by_cat[cats].astype(np.float32)

    _PELVIS_ID = 1
    mesh_scale = np.ones(num_joints, dtype=np.float32)
    for j in range(num_joints):
        c = int(cats[j])
        if c == 2:
            mesh_scale[j] = 1.0
        elif c != 0:
            js = float(joint_scale[j])
            if j == _PELVIS_ID:
                mesh_scale[j] = js
            else:
                mesh_scale[j] = 1.0 + _MESH_SCALE_STRENGTH * (js - 1.0)
        else:
            p = int(parents[j])
            if p >= 0:
                if int(cats[p]) == 2:
                    mesh_scale[j] = mesh_scale[p]
                else:
                    parent_js = float(joint_scale[p])
                    if abs(parent_js - 1.0) > 1e-6:
                        mesh_scale[j] = parent_js
                    else:
                        mesh_scale[j] = mesh_scale[p]

    joint_scale_no_neck = joint_scale.copy()
    joint_scale_no_neck[cats == 2] = 1.0
    posed_delta = np.zeros_like(rest_coords)
    posed_delta_no_neck = np.zeros_like(rest_coords)
    for j in range(num_joints):
        p = int(parents[j])
        if p < 0:
            continue
        off = (rest_coords[j] - rest_coords[p]).astype(np.float32)
        link = R_rel_all[p] @ off
        posed_delta[j] = posed_delta[p] + (float(joint_scale[j]) - 1.0) * link
        posed_delta_no_neck[j] = posed_delta_no_neck[p] + (float(joint_scale_no_neck[j]) - 1.0) * link

    Wsum = W.sum(axis=1, keepdims=True)
    Wsum_safe = np.where(Wsum > 1e-6, Wsum, 1.0).astype(np.float32)
    W_norm = (W / Wsum_safe).astype(np.float32)

    mesh_delta = np.zeros_like(rest_verts, dtype=np.float32)
    for j in range(num_joints):
        ms = float(mesh_scale[j])
        if abs(ms - 1.0) < 1e-6:
            continue
        local = (rest_verts - rest_coords[j]).astype(np.float32)
        rotated = local @ R_rel_all[j].T
        mesh_delta += (ms - 1.0) * W_norm[:, j:j + 1] * rotated

    _HEAD_ID = 113
    _FACE_JOINT_RANGE = np.arange(113, min(127, num_joints), dtype=np.int64)
    posed_delta_neck = posed_delta - posed_delta_no_neck
    term_C_no_neck = (W_norm @ posed_delta_no_neck).astype(np.float32)
    term_C_neck_lbs = (W_norm @ posed_delta_neck).astype(np.float32)

    face_weight = W_norm[:, _FACE_JOINT_RANGE].sum(axis=1).astype(np.float32)
    LOW, HIGH = 0.5, 0.9
    t = np.clip((face_weight - LOW) / (HIGH - LOW), 0.0, 1.0)
    face_strength = (t * t * (3.0 - 2.0 * t)).astype(np.float32)

    rigid_neck_shift = posed_delta_neck[_HEAD_ID].astype(np.float32)
    term_C_neck = (
        (1.0 - face_strength[:, None]) * term_C_neck_lbs
        + face_strength[:, None] * rigid_neck_shift[None, :]
    ).astype(np.float32)
    term_C = (term_C_no_neck + term_C_neck).astype(np.float32)

    posed_shift = (mesh_delta + term_C).astype(np.float32)
    return (vertices + posed_shift).astype(vertices.dtype)


# ---------------------------------------------------------------------------
# Slider → PCA shape_params tensor.
# ---------------------------------------------------------------------------

def build_shape_params(body_params: dict, num_shape_comps: int, device) -> torch.Tensor:
    """Convert 9 UI body_params into a full MHR shape_params tensor."""
    axes = [float(body_params.get(k, 0.0)) for k in BODY_PARAM_KEYS]
    t = torch.zeros((1, num_shape_comps), dtype=torch.float32, device=device)
    n = min(len(axes), num_shape_comps)
    for i in range(n):
        t[0, i] = axes[i] * SHAPE_SLIDER_NORM[i] * SHAPE_SLIDER_SIGN[i]
    return t


def to_tensor_1xN(value, device, width: int | None = None) -> torch.Tensor:
    if value is None:
        if width is None:
            raise ValueError("width is required when creating a default tensor")
        return torch.zeros((1, width), dtype=torch.float32, device=device)
    if isinstance(value, torch.Tensor):
        t = value.to(device=device, dtype=torch.float32)
    else:
        t = torch.tensor(value, dtype=torch.float32, device=device)
    if t.dim() == 1:
        t = t.unsqueeze(0)
    return t
