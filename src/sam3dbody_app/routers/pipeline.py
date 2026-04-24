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
):
    """Run SAM3 person mask + SAM3DBody pose estimation on the uploaded image.

    SAM3 parameters come from ``config.ini [sam3]`` — edit the ini to change
    them. Inference type stays on the URL since it's a per-call choice."""
    if image.content_type and not image.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail=f"expected image/*, got {image.content_type}")

    raw = await image.read()
    try:
        pil = Image.open(io.BytesIO(raw))
        pil.load()
        # Composite transparency over white and drop alpha so downstream
        # SAM3 / SAM3DBody never sees RGBA / LA / palette-with-alpha modes
        # (they crash on anything other than 3-channel RGB).
        pil = _normalize_input_image(pil)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"could not decode image: {exc}") from exc

    # Read fresh every call so config.ini edits hot-reload.
    settings = AppSettings.load()
    sam3 = settings.sam3
    try:
        result = run_image_to_obj(
            pil,
            inference_type=inference_type,
            text_prompt=sam3.text_prompt,
            use_sam3=sam3.use_sam3,
            confidence_threshold=sam3.confidence_threshold,
            min_width_pixels=sam3.min_width_pixels,
            min_height_pixels=sam3.min_height_pixels,
            device_mode=settings.device,
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
