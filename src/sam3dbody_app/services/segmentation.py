"""Segmentation backends for image and video pipelines."""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

import numpy as np
from PIL import Image

log = logging.getLogger(__name__)


@dataclass
class MaskResult:
    mask: np.ndarray
    bbox_xyxy: np.ndarray
    score: float
    num_candidates: int
    backend: str


def _bbox_from_mask(mask: np.ndarray) -> np.ndarray:
    ys, xs = np.where(mask > 0)
    if xs.size == 0:
        return np.array([0.0, 0.0, float(mask.shape[1]), float(mask.shape[0])], dtype=np.float32)
    return np.array([xs.min(), ys.min(), xs.max() + 1, ys.max() + 1], dtype=np.float32)


def _largest_component(mask: np.ndarray) -> np.ndarray:
    try:
        import cv2

        num, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
        if num <= 1:
            return mask.astype(np.uint8)
        best = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        return (labels == best).astype(np.uint8)
    except Exception:
        return mask.astype(np.uint8)


def _validate_mask(mask: np.ndarray, *, min_width_pixels: int, min_height_pixels: int) -> np.ndarray:
    out = (mask > 0).astype(np.uint8)
    if not out.any():
        raise RuntimeError("segmentation produced an empty mask")
    out = _largest_component(out)
    bbox = _bbox_from_mask(out)
    width = int(bbox[2] - bbox[0])
    height = int(bbox[3] - bbox[1])
    if width < int(min_width_pixels) or height < int(min_height_pixels):
        raise RuntimeError(
            f"segmentation mask too small: got {width}x{height}px, "
            f"required at least {min_width_pixels}x{min_height_pixels}px"
        )
    return out


_MODEL_LOCK = threading.Lock()
_BIREFNET_MODEL = None
_BIREFNET_MODEL_ID: str | None = None
_BIREFNET_DEVICE: str | None = None


def _backend_to_model_id(backend: str) -> tuple[str, str]:
    name = (backend or "birefnet_lite").strip().lower()
    if name in ("birefnet", "birefnet_general"):
        return "ZhengPeng7/BiRefNet", "birefnet"
    if name in ("birefnet_lite", "birefnet_auto"):
        return "ZhengPeng7/BiRefNet_lite", "birefnet_lite"
    raise RuntimeError(
        f"unknown segmentation backend {backend!r}; "
        "expected one of birefnet_lite, birefnet, birefnet_general, birefnet_auto"
    )


def _load_birefnet(model_id: str):
    global _BIREFNET_MODEL, _BIREFNET_MODEL_ID, _BIREFNET_DEVICE
    with _MODEL_LOCK:
        if _BIREFNET_MODEL is not None and _BIREFNET_MODEL_ID == model_id:
            return _BIREFNET_MODEL, _BIREFNET_DEVICE or "cpu"

        import torch
        from transformers import AutoModelForImageSegmentation

        torch.set_float32_matmul_precision("high")
        device = "cuda" if torch.cuda.is_available() else "cpu"
        log.info("loading BiRefNet model %s on %s", model_id, device)
        model = AutoModelForImageSegmentation.from_pretrained(model_id, trust_remote_code=True)
        model.to(device)
        model.eval()
        if device == "cuda":
            model.half()

        _BIREFNET_MODEL = model
        _BIREFNET_MODEL_ID = model_id
        _BIREFNET_DEVICE = device
        return model, device


def _predict_birefnet_mask(
    pil_image: Image.Image,
    *,
    model_id: str,
    backend_name: str,
    confidence_threshold: float,
    min_width_pixels: int,
    min_height_pixels: int,
) -> MaskResult:
    import torch
    from torchvision import transforms

    model, device = _load_birefnet(model_id)
    original = pil_image.convert("RGB")
    ow, oh = original.size
    input_size = (1024, 1024)
    tfm = transforms.Compose([
        transforms.Resize(input_size),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])
    input_tensor = tfm(original).unsqueeze(0).to(device)
    if device == "cuda":
        input_tensor = input_tensor.half()

    with torch.no_grad():
        pred = model(input_tensor)[-1].sigmoid().float().cpu().numpy()[0, 0]

    mask_img = Image.fromarray(np.clip(pred * 255.0, 0.0, 255.0).astype(np.uint8), mode="L")
    score_map = np.asarray(mask_img.resize((ow, oh), Image.BILINEAR), dtype=np.float32) / 255.0
    mask = _validate_mask(
        score_map >= float(confidence_threshold),
        min_width_pixels=min_width_pixels,
        min_height_pixels=min_height_pixels,
    )
    bbox = _bbox_from_mask(mask)
    fg_scores = score_map[mask > 0]
    score = float(fg_scores.mean()) if fg_scores.size else 0.0
    return MaskResult(mask=mask, bbox_xyxy=bbox, score=score, num_candidates=1, backend=backend_name)


def extract_best_mask(
    pil_image: Image.Image,
    *,
    backend: str = "birefnet_lite",
    confidence_threshold: float = 0.5,
    min_width_pixels: int = 0,
    min_height_pixels: int = 0,
) -> MaskResult:
    model_id, backend_name = _backend_to_model_id(backend)
    return _predict_birefnet_mask(
        pil_image,
        model_id=model_id,
        backend_name=backend_name,
        confidence_threshold=confidence_threshold,
        min_width_pixels=min_width_pixels,
        min_height_pixels=min_height_pixels,
    )
