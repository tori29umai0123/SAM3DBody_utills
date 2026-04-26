"""HTTP endpoints for the image→pose→OBJ pipeline."""
from __future__ import annotations

import io
import logging

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from PIL import Image

from ..config import AppSettings
from ..services.pipeline import _normalize_input_image, run_image_to_obj

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["pipeline"])


@router.post("/process")
async def process_image(
    request: Request,
    image: UploadFile = File(...),
    inference_type: str = "full",
    left_hand_image: UploadFile | None = File(None),
    right_hand_image: UploadFile | None = File(None),
):
    """Run segmentation + pose estimation on the uploaded image.

    Segmentation parameters come from ``config.ini [segmentation]`` — edit the ini to change
    them. Inference type stays on the URL since it's a per-call choice.
    Optional ``left_hand_image`` / ``right_hand_image`` multipart fields
    trigger a hand-only decoder pass that overrides the body's hand pose."""
    if image.content_type and not image.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail=f"expected image/*, got {image.content_type}")

    raw = await image.read()
    try:
        pil = Image.open(io.BytesIO(raw))
        pil.load()
        # Composite transparency over white and drop alpha so downstream
        # Segmentation / pose estimation never sees RGBA / LA / palette-with-alpha modes
        # (they crash on anything other than 3-channel RGB).
        pil = _normalize_input_image(pil)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"could not decode image: {exc}") from exc

    async def _decode_optional(upload: UploadFile | None) -> Image.Image | None:
        if upload is None:
            return None
        try:
            data = await upload.read()
            if not data:
                return None
            im = Image.open(io.BytesIO(data))
            im.load()
            return _normalize_input_image(im)
        except Exception as exc:  # noqa: BLE001
            log.warning("hand image decode failed: %s", exc)
            return None

    pil_lhand = await _decode_optional(left_hand_image)
    pil_rhand = await _decode_optional(right_hand_image)

    # Read fresh every call so config.ini edits hot-reload.
    settings = AppSettings.load()
    segmentation = settings.segmentation
    try:
        result = run_image_to_obj(
            pil,
            inference_type=inference_type,
            use_segmentation=segmentation.enabled,
            segmentation_backend=segmentation.backend,
            confidence_threshold=segmentation.confidence_threshold,
            min_width_pixels=segmentation.min_width_pixels,
            min_height_pixels=segmentation.min_height_pixels,
            device_mode=settings.device,
            left_hand_image=pil_lhand,
            right_hand_image=pil_rhand,
        )
    except Exception as exc:
        log.exception("pipeline failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "job_id": result.job_id,
        "obj_url": result.obj_url,
        "mask_url": result.mask_url,
        "bbox_xyxy": result.bbox_xyxy,
        "width": result.width,
        "height": result.height,
        "elapsed_sec": round(result.elapsed_sec, 3),
        "best_score": result.best_score,
        "num_candidates": result.num_detections,
        "pose_json": result.pose_json,
    }
