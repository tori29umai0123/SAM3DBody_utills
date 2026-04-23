"""Run SAM3 text-prompted grounding on a single image and return the top
matching mask. Semantics mirror `SAM3Segmentation.segment()` (image-model
path) in `C:\\ComfyUI\\custom_nodes\\comfyui_sam3\\src\\comfyui_sam3\\nodes.py`:

  prompt / threshold / min_width_pixels / min_height_pixels, with
  use_video_model=False, unload_after_run=False, object_ids="" semantics.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import torch
from PIL import Image

from .sam3_loader import load_bundle

log = logging.getLogger(__name__)


@dataclass
class MaskResult:
    mask: np.ndarray          # (H, W) uint8, 1 where the subject is
    bbox_xyxy: np.ndarray     # (4,) float32 — x1, y1, x2, y2 in pixel coords
    score: float              # detector confidence [0..1]
    num_candidates: int       # candidates that passed all filters


def _mask_to_2d_uint8(m) -> np.ndarray:
    arr = m.detach().cpu().numpy() if hasattr(m, "detach") else np.asarray(m)
    arr = np.squeeze(arr)
    if arr.dtype == bool:
        return arr.astype(np.uint8)
    return (arr > 0.5).astype(np.uint8)


def _bbox_from_mask(mask: np.ndarray) -> np.ndarray:
    ys, xs = np.where(mask > 0)
    if xs.size == 0:
        return np.array([0.0, 0.0, float(mask.shape[1]), float(mask.shape[0])], dtype=np.float32)
    return np.array([xs.min(), ys.min(), xs.max() + 1, ys.max() + 1], dtype=np.float32)


def _box_to_xyxy_pixels(raw, img_w: int, img_h: int) -> np.ndarray:
    b = np.asarray(raw.detach().cpu() if hasattr(raw, "detach") else raw, dtype=np.float32).reshape(-1)
    if b.size < 4:
        return np.array([0.0, 0.0, float(img_w), float(img_h)], dtype=np.float32)
    return np.array([float(b[0]), float(b[1]), float(b[2]), float(b[3])], dtype=np.float32)


def extract_best_person_mask(
    pil_image: Image.Image,
    *,
    text_prompt: str = "person",
    confidence_threshold: float = 0.5,
    min_width_pixels: int = 0,
    min_height_pixels: int = 0,
) -> MaskResult:
    """Image-mode SAM3 grounding with the defaults from
    `comfyui_sam3/SAM3Segmentation`:

      prompt:             person
      threshold:          0.5
      min_width_pixels:   0
      min_height_pixels:  0
      use_video_model:    false   (always — we build the image model only)
      unload_after_run:   false   (model stays resident)
      object_ids:         ""      (single top-1 mask)

    Raises RuntimeError when no candidate passes all filters.
    """
    bundle = load_bundle(use_video_model=False)
    processor = bundle.processor

    # Match the node: propagate the threshold into the processor so internal
    # gating uses the same cutoff as the post-hoc filter below.
    try:
        processor.confidence_threshold = float(confidence_threshold)
    except Exception:
        pass

    state = processor.set_image(pil_image)
    state = processor.set_text_prompt(state=state, prompt=text_prompt)

    masks = state.get("masks")
    boxes = state.get("boxes")
    scores = state.get("scores")

    if masks is None or len(masks) == 0:
        raise RuntimeError(
            f"SAM3: no detections for prompt '{text_prompt}' at threshold {confidence_threshold}"
        )

    img_w, img_h = pil_image.size

    # Follow SAM3Segmentation.segment() exactly: iterate in source order,
    # filter by (score >= threshold) AND (bbox >= min_size), keep all
    # passing candidates. Return the top-score among them.
    kept_indices: list[int] = []
    kept_boxes: list[np.ndarray] = []
    for i in range(len(masks)):
        score = float(scores[i].item()) if scores is not None else 0.0
        if score < float(confidence_threshold):
            continue
        if boxes is not None and len(boxes) > i:
            bbox = _box_to_xyxy_pixels(boxes[i], img_w, img_h)
        else:
            bbox = _bbox_from_mask(_mask_to_2d_uint8(masks[i]))
        w_px = float(bbox[2] - bbox[0])
        h_px = float(bbox[3] - bbox[1])
        if w_px < float(min_width_pixels) or h_px < float(min_height_pixels):
            continue
        kept_indices.append(i)
        kept_boxes.append(bbox)

    if not kept_indices:
        raise RuntimeError(
            f"SAM3: {len(masks)} candidate(s) but none passed threshold={confidence_threshold} "
            f"AND min_size={min_width_pixels}x{min_height_pixels}px"
        )

    # Among the surviving candidates, pick the highest-scoring one to feed
    # into SAM3DBody.
    best_rel = int(np.argmax([float(scores[i].item()) if scores is not None else 0.0 for i in kept_indices]))
    best_i = kept_indices[best_rel]
    best_score = float(scores[best_i].item()) if scores is not None else 0.0
    best_mask_np = _mask_to_2d_uint8(masks[best_i])

    # Resize mask to the original image if the model operated at a different
    # resolution (can happen when SAM3 keeps things at 1008).
    if best_mask_np.shape != (img_h, img_w):
        m = Image.fromarray((best_mask_np * 255).astype(np.uint8), mode="L")
        m = m.resize((img_w, img_h), Image.NEAREST)
        best_mask_np = (np.array(m) > 0).astype(np.uint8)

    # Prefer a tight bbox derived from the resampled mask so downstream crops
    # are exact, falling back to the detector's box when the mask is empty.
    tight = _bbox_from_mask(best_mask_np)
    if tight[2] > tight[0] and tight[3] > tight[1]:
        best_bbox = tight
    else:
        best_bbox = kept_boxes[best_rel]

    log.info(
        "SAM3 mask for '%s': score=%.3f bbox=[%.1f,%.1f,%.1f,%.1f] kept=%d/%d thresh=%.2f min_size=%dx%d",
        text_prompt, best_score, *best_bbox.tolist(),
        len(kept_indices), len(masks),
        confidence_threshold, min_width_pixels, min_height_pixels,
    )

    return MaskResult(
        mask=best_mask_np,
        bbox_xyxy=best_bbox,
        score=best_score,
        num_candidates=len(kept_indices),
    )
