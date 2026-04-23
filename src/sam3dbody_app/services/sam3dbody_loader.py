"""Load the SAM 3D Body model + MHR companion weights, auto-downloading from
HuggingFace on first use.

This mirrors the behavior of `nodes/processing/load_model.py` in the original
ComfyUI custom node, minus the ComfyUI coupling (folder_paths, Node schema).
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

import torch

from ..config import get_paths
from ..core.sam_3d_body import load_sam_3d_body, SAM3DBodyEstimator

log = logging.getLogger(__name__)

_HF_REPO = "jetjodh/sam-3d-body-dinov3"
_SUBDIR = "sam3dbody"
_CKPT_NAME = "model.ckpt"
_MHR_RELPATH = ("assets", "mhr_model.pt")


@dataclass
class SAM3DBodyBundle:
    model: object  # SAM3DBody nn.Module
    cfg: object
    estimator: SAM3DBodyEstimator
    device: str


_lock = threading.Lock()
_cached: SAM3DBodyBundle | None = None


def model_dir() -> Path:
    return get_paths().models_dir / _SUBDIR


def _ensure_weights() -> Tuple[Path, Path]:
    d = model_dir()
    ckpt = d / _CKPT_NAME
    mhr = d / Path(*_MHR_RELPATH)
    if ckpt.is_file() and mhr.is_file():
        return ckpt, mhr

    log.info("SAM3DBody weights not found under %s; downloading from %s", d, _HF_REPO)
    d.mkdir(parents=True, exist_ok=True)
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise RuntimeError("huggingface_hub is required to download SAM 3D Body weights") from exc

    snapshot_download(repo_id=_HF_REPO, local_dir=str(d))

    if not (ckpt.is_file() and mhr.is_file()):
        raise RuntimeError(
            f"SAM 3D Body download completed but expected files are missing:\n"
            f"  {ckpt}\n  {mhr}"
        )
    log.info("SAM3DBody weights ready at %s", d)
    return ckpt, mhr


def resolve_device(mode: str | None = None) -> str:
    mode = (mode or "auto").strip().lower()
    if mode == "auto":
        return "cuda" if torch.cuda.is_available() else "cpu"
    if mode == "cuda":
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA requested but not available")
        return "cuda"
    if mode == "cpu":
        return "cpu"
    raise ValueError(f"unsupported device mode: {mode}")


def load_bundle(device_mode: str | None = None) -> SAM3DBodyBundle:
    """Return a cached (model, cfg, estimator) bundle. Thread-safe + idempotent."""
    global _cached
    with _lock:
        if _cached is not None:
            return _cached
        ckpt, mhr = _ensure_weights()
        device = resolve_device(device_mode)
        log.info("Loading SAM3DBody on %s from %s", device, ckpt)
        model, cfg, _ = load_sam_3d_body(
            checkpoint_path=str(ckpt), device=device, mhr_path=str(mhr)
        )
        estimator = SAM3DBodyEstimator(model, cfg)
        _cached = SAM3DBodyBundle(model=model, cfg=cfg, estimator=estimator, device=device)
        log.info("SAM3DBody ready")
        return _cached


def drop_bundle() -> None:
    """Release GPU memory (used by tests / reload flows)."""
    global _cached
    with _lock:
        if _cached is None:
            return
        del _cached.model
        _cached = None
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
