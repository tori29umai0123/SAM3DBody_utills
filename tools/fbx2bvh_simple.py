"""FBX -> BVH with rest correction for trunk bones.

The correction straightens the trunk chain in rest pose while preserving the
world transform of branch roots such as shoulders and upper legs so the parent
spine correction does not drag those branches into a new angle.

Usage:
    blender --background --python tools/fbx2bvh_simple.py -- \
        <input.fbx> <output.bvh> [--strength T] [--correction PATH]
"""

import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Matrix


DEFAULT_CORRECTION_JSON = Path(__file__).resolve().parent / "rest_correction.json"
CORRECT_PREFIXES = (
    "Hips",
    "Spine",
    "Neck",
    "Head",
)


def _should_correct(name: str) -> bool:
    for prefix in CORRECT_PREFIXES:
        if name == prefix or name.startswith(prefix):
            return True
    return False


def _slerp_matrix(m0: Matrix, m1: Matrix, t: float) -> Matrix:
    q0 = m0.to_quaternion()
    q1 = m1.to_quaternion()
    q = q0.slerp(q1, t)
    p = m0.translation.lerp(m1.translation, t)
    return Matrix.Translation(p) @ q.to_matrix().to_4x4()


def _apply_rest_correction(armature, correction_path: Path, strength: float) -> None:
    if strength <= 1e-6:
        return
    if not correction_path.is_file():
        print(f"[fbx2bvh] WARNING: correction JSON not found at {correction_path}")
        return

    with correction_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    clean_local = {bone["name"]: Matrix(bone["local_matrix"]) for bone in data["bones"]}

    bpy.context.view_layer.objects.active = armature
    bpy.ops.object.mode_set(mode="EDIT")
    try:
        eb = armature.data.edit_bones

        orig_local: dict[str, Matrix] = {}
        orig_world: dict[str, Matrix] = {}
        for bone in eb:
            orig_world[bone.name] = bone.matrix.copy()
            if bone.parent is None:
                orig_local[bone.name] = bone.matrix.copy()
            else:
                orig_local[bone.name] = bone.parent.matrix.inverted() @ bone.matrix

        order: list[str] = []

        def walk(bone) -> None:
            order.append(bone.name)
            for child in bone.children:
                walk(child)

        for bone in eb:
            if bone.parent is None:
                walk(bone)

        matched = 0
        for name in order:
            bone = eb.get(name)
            if bone is None:
                continue

            local_orig = orig_local[name]
            self_is_corrected = _should_correct(name) and name in clean_local
            parent_is_corrected = bone.parent is not None and _should_correct(bone.parent.name)

            if self_is_corrected:
                matched += 1
                local_clean = clean_local[name]
                if strength >= 1.0 - 1e-6:
                    local_target = local_clean
                else:
                    local_target = _slerp_matrix(local_orig, local_clean, strength)
                if bone.parent is None:
                    bone.matrix = local_target
                else:
                    bone.matrix = bone.parent.matrix @ local_target
                continue

            if parent_is_corrected:
                # Keep branch-root world transforms unchanged so corrected trunk
                # bones do not rotate shoulders, legs, or other non-corrected
                # branches.
                bone.matrix = orig_world[name]
                continue

            if bone.parent is None:
                bone.matrix = local_orig
            else:
                bone.matrix = bone.parent.matrix @ local_orig

        print(
            f"[fbx2bvh] rest correction: matched {matched}/{len(order)} bones "
            f"(strength={strength:.2f})"
        )
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")


def fbx2bvh(
    src_fbx: str,
    dst_bvh: str,
    *,
    strength: float = 1.0,
    correction_path: Path = DEFAULT_CORRECTION_JSON,
    single_frame: bool = False,
) -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=src_fbx)

    armature = next((obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"), None)
    if armature is None:
        raise RuntimeError("imported FBX has no armature")

    _apply_rest_correction(armature, correction_path, strength)

    bpy.ops.object.select_all(action="DESELECT")
    armature.select_set(True)
    bpy.context.view_layer.objects.active = armature
    armature.rotation_euler = (math.radians(-90.0), 0.0, 0.0)
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)

    if not bpy.data.actions:
        raise RuntimeError("imported FBX contains no Action")

    action = bpy.data.actions[-1]
    frame_start = int(round(action.frame_range[0]))
    frame_end = int(round(action.frame_range[1]))
    if single_frame:
        frame_end = frame_start
    if frame_end < frame_start:
        frame_end = frame_start

    bpy.ops.export_anim.bvh(
        filepath=dst_bvh,
        frame_start=frame_start,
        frame_end=frame_end,
        root_transform_only=True,
    )
    print(
        f"[fbx2bvh] {src_fbx} -> {dst_bvh} "
        f"(frames {frame_start}-{frame_end}, strength={strength}, "
        f"single_frame={single_frame})"
    )


def _parse_argv() -> tuple[str, str, float, Path, bool]:
    if "--" not in sys.argv:
        raise SystemExit(
            "usage: blender -b --python fbx2bvh_simple.py -- "
            "<in.fbx> <out.bvh> [--strength T] [--correction PATH]"
        )
    args = sys.argv[sys.argv.index("--") + 1 :]
    strength = 1.0
    correction = DEFAULT_CORRECTION_JSON
    single_frame = False
    positional: list[str] = []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg in ("--strength", "--straighten"):
            strength = float(args[i + 1])
            i += 2
            continue
        if arg == "--correction":
            correction = Path(args[i + 1])
            i += 2
            continue
        if arg == "--single-frame":
            single_frame = True
            i += 1
            continue
        positional.append(arg)
        i += 1
    if len(positional) != 2:
        raise SystemExit(
            "usage: blender -b --python fbx2bvh_simple.py -- "
            "<in.fbx> <out.bvh> [--strength T] [--correction PATH] [--single-frame]"
        )
    return positional[0], positional[1], strength, correction, single_frame


if __name__ == "__main__":
    fbx_path, bvh_path, strength, correction, single_frame = _parse_argv()
    fbx2bvh(
        fbx_path,
        bvh_path,
        strength=strength,
        correction_path=correction,
        single_frame=single_frame,
    )
