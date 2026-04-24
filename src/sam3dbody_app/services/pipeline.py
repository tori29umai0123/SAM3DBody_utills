"""Image → SAM3 person mask → SAM3DBody → OBJ pipeline."""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from PIL import Image

from ..config import get_paths
from . import pose_session
from .obj_export import write_obj_flip_y
from .renderer import render_from_session
from .sam3_mask import extract_best_person_mask
from .sam3dbody_loader import load_bundle

log = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    job_id: str
    obj_url: str
    obj_path: str
    width: int
    height: int
    num_detections: int
    best_score: float | None
    elapsed_sec: float
    mask_url: str | None = None
    bbox_xyxy: list[float] | None = None
    pose_json: dict[str, Any] = field(default_factory=dict)


def _normalize_input_image(img: Image.Image) -> Image.Image:
    """Return a plain RGB image safe for SAM3/SAM3DBody.

    Transparent PNGs often arrive as RGBA/LA or palette images with a
    transparency table. Passing those modes through PIL/NumPy is fine for our
    RGB conversion, but downstream model code expects a 3-channel image
    consistently. Composite transparency over white, then drop alpha.
    """
    if img.mode == "RGB":
        return img

    has_alpha = (
        img.mode in ("RGBA", "LA")
        or (img.mode == "P" and "transparency" in img.info)
    )
    if has_alpha:
        rgba = img.convert("RGBA")
        bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        return Image.alpha_composite(bg, rgba).convert("RGB")
    return img.convert("RGB")


def _to_rgb_uint8(img: Image.Image) -> np.ndarray:
    return np.asarray(_normalize_input_image(img))


def _numpy_clean(obj: Any) -> Any:
    """Recursively convert numpy types to plain Python for JSON safety."""
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, dict):
        return {k: _numpy_clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_numpy_clean(x) for x in obj]
    return obj


def _save_mask_png(mask: np.ndarray, path) -> None:
    Image.fromarray((mask * 255).astype(np.uint8), mode="L").save(path)


def _mask_url() -> str:
    """Cache-busted URL for the single-file mask preview."""
    return f"/tmp/mask.png?v={uuid.uuid4().hex[:8]}"


def run_image_to_obj(
    pil_image: Image.Image,
    *,
    inference_type: str = "full",
    text_prompt: str = "person",
    use_sam3: bool = True,
    confidence_threshold: float = 0.5,
    min_width_pixels: int = 0,
    min_height_pixels: int = 0,
    device_mode: str | None = None,
) -> PipelineResult:
    """Run SAM3 person mask → SAM3DBody on a single image and produce an OBJ.

    `use_sam3=False` falls back to using the entire image as the bbox (used for
    debugging or when SAM3 is unavailable).
    """
    t0 = time.monotonic()
    paths = get_paths()
    bundle = load_bundle(device_mode)

    pil_image = _normalize_input_image(pil_image)
    rgb = _to_rgb_uint8(pil_image)
    h, w = rgb.shape[:2]

    mask_url: str | None = None
    sam3_score: float | None = None
    num_candidates = 0

    if use_sam3:
        mask_result = extract_best_person_mask(
            pil_image,
            text_prompt=text_prompt,
            confidence_threshold=confidence_threshold,
            min_width_pixels=min_width_pixels,
            min_height_pixels=min_height_pixels,
        )
        bboxes = mask_result.bbox_xyxy.reshape(1, 4).astype(np.float32)
        # SAM3DBody expects (-1, H, W, 1) uint8.
        masks = mask_result.mask.reshape(1, h, w, 1).astype(np.uint8)
        sam3_score = mask_result.score
        num_candidates = mask_result.num_candidates
    else:
        bboxes = np.array([[0, 0, w, h]], dtype=np.float32)
        masks = None

    results = bundle.estimator.process_one_image(
        rgb, bboxes=bboxes, masks=masks, inference_type=inference_type
    )
    if not results:
        raise RuntimeError("SAM3DBody returned no detections")

    best = results[0]
    faces = bundle.estimator.faces  # (F, 3)
    job_id = uuid.uuid4().hex[:12]

    if use_sam3 and masks is not None:
        # Single overwriting file — the frontend adds a cache-bust query
        # string so each call's PNG is distinct from the browser's view.
        mask_path = paths.tmp_dir / "mask.png"
        _save_mask_png(masks[0, :, :, 0], mask_path)
        mask_url = _mask_url()

    pose_json: dict[str, Any] = {
        "bbox": _numpy_clean(best.get("bbox")),
        "pred_cam_t": _numpy_clean(best.get("pred_cam_t")),
        "global_rot": _numpy_clean(best.get("global_rot")),
        "body_pose_params": _numpy_clean(best.get("body_pose_params")),
        "hand_pose_params": _numpy_clean(best.get("hand_pose_params")),
        "shape_params": _numpy_clean(best.get("shape_params")),
        "scale_params": _numpy_clean(best.get("scale_params")),
        "expr_params": _numpy_clean(best.get("expr_params")),
        "focal_length": _numpy_clean(best.get("focal_length")),
        "pred_keypoints_3d": _numpy_clean(best.get("pred_keypoints_3d")),
    }

    # Cache the pose so slider changes can re-render without re-running SAM3+SAM3DBody.
    pose_session.put(pose_session.PoseSession(
        job_id=job_id,
        pose_json=pose_json,
        global_rot=np.asarray(best.get("global_rot")),
        body_pose_params=np.asarray(best.get("body_pose_params")),
        hand_pose_params=np.asarray(best.get("hand_pose_params")),
        image_width=w, image_height=h,
        orig_focal_length=(
            float(np.asarray(best.get("focal_length")).reshape(-1)[0])
            if best.get("focal_length") is not None else None
        ),
        orig_cam_t=np.asarray(best["pred_cam_t"]) if best.get("pred_cam_t") is not None else None,
        orig_keypoints_3d=(
            np.asarray(best["pred_keypoints_3d"])
            if best.get("pred_keypoints_3d") is not None else None
        ),
        bbox_xyxy=bboxes[0].astype(np.float32),
    ))

    # Initial render: MHR neutral body with zero shape params — the subject's
    # predicted body type is intentionally dropped so sliders always drive
    # the output regardless of who was in the input image. The frontend will
    # re-render once the user moves a slider or loads a preset.
    render = render_from_session(job_id, None)
    obj_url = render.obj_url

    elapsed = time.monotonic() - t0
    log.info(
        "pipeline job %s: image=%dx%d sam3_score=%s cands=%d elapsed=%.2fs",
        job_id, w, h,
        f"{sam3_score:.3f}" if sam3_score is not None else "n/a",
        num_candidates, elapsed,
    )
    return PipelineResult(
        job_id=job_id,
        obj_url=obj_url,
        obj_path=render.obj_path,
        width=w,
        height=h,
        num_detections=num_candidates or len(results),
        best_score=sam3_score,
        elapsed_sec=elapsed,
        mask_url=mask_url,
        bbox_xyxy=bboxes[0].tolist(),
        pose_json=pose_json,
    )
