"""Load Meta's official SAM3 image model and wrap it in a Sam3Processor.

This replaces the earlier loader that used the ComfyUI-patched vendor in
`comfyui-sam3`. We now base the mask pipeline on the vanilla `sam3` package
as bundled in `C:\\ComfyUI\\custom_nodes\\comfyui_sam3`. The checkpoint file
(`sam3.pt`) is downloaded from the gated HuggingFace repo `facebook/sam3`
on first use; users must run `hf auth login` with an account that has
access to that model.
"""
from __future__ import annotations

import logging
import os
import shutil
import threading
from dataclasses import dataclass
from pathlib import Path

import torch

from ..config import get_paths

log = logging.getLogger(__name__)

_HF_REPO = "facebook/sam3"
_SUBDIR = "sam3"
_CKPT_NAME = "sam3.pt"


@dataclass
class SAM3Bundle:
    model: object           # Sam3Image / sam3 image model
    processor: object       # sam3.model.sam3_image_processor.Sam3Processor
    device: torch.device
    use_video_model: bool   # always False in this build; present for parity with the ref node


_lock = threading.Lock()
_cached: SAM3Bundle | None = None


def model_path() -> Path:
    return get_paths().models_dir / _SUBDIR / _CKPT_NAME


def _ensure_checkpoint() -> Path:
    """Return a usable sam3.pt path, auto-populating from common local caches
    or HuggingFace on first use."""
    p = model_path()
    if p.is_file():
        return p

    p.parent.mkdir(parents=True, exist_ok=True)

    # Opportunistic copy from well-known local locations (ComfyUI install,
    # explicit env override) so gated HF access isn't required when the
    # weight already lives on disk.
    candidates: list[Path] = []
    env_override = os.environ.get("SAM3_CKPT_PATH", "").strip()
    if env_override:
        candidates.append(Path(env_override))
    # Windows: a common ComfyUI install
    if os.name == "nt":
        candidates.append(Path(r"C:/ComfyUI/models/sam3/sam3.pt"))
    else:
        # Linux: check common XDG-ish locations and user home
        home = Path(os.path.expanduser("~"))
        candidates += [
            home / "ComfyUI" / "models" / "sam3" / "sam3.pt",
            home / ".cache" / "huggingface" / "hub" / "models--facebook--sam3" / "blobs" / "sam3.pt",
            Path("/opt/ComfyUI/models/sam3/sam3.pt"),
        ]

    for candidate in candidates:
        if candidate.is_file():
            log.info("Copying existing SAM3 checkpoint from %s -> %s", candidate, p)
            shutil.copy2(candidate, p)
            return p

    log.info("SAM3 checkpoint not found; downloading from %s (gated, needs hf auth login)", _HF_REPO)
    try:
        from huggingface_hub import hf_hub_download
    except ImportError as exc:
        raise RuntimeError("huggingface_hub is required to download SAM3") from exc

    try:
        downloaded = hf_hub_download(repo_id=_HF_REPO, filename=_CKPT_NAME, local_dir=str(p.parent))
    except Exception as exc:
        raise RuntimeError(
            f"Failed to download SAM3 from {_HF_REPO}. This is a gated model; "
            f"visit https://huggingface.co/{_HF_REPO}, request access, then run "
            f"`hf auth login`. Alternatively place sam3.pt at {p}."
        ) from exc

    return Path(downloaded)


def load_bundle(*, use_video_model: bool = False) -> SAM3Bundle:
    """Build the SAM3 image model (or video model when requested) and wrap it
    in the official Sam3Processor. Cached for subsequent calls.
    """
    global _cached
    with _lock:
        if _cached is not None and _cached.use_video_model == use_video_model:
            return _cached

        ckpt = _ensure_checkpoint()
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        from ..core.sam3.model_builder import build_sam3_image_model, build_sam3_video_model
        from ..core.sam3.model.sam3_image_processor import Sam3Processor

        if use_video_model:
            log.info("Building SAM3 video model on %s", device)
            model = build_sam3_video_model(checkpoint_path=str(ckpt))
            model = model.to(device).eval()
            processor = Sam3Processor(model.detector, device=str(device))
        else:
            log.info("Building SAM3 image model on %s", device)
            model = build_sam3_image_model(checkpoint_path=str(ckpt))
            model = model.to(device).eval()
            processor = Sam3Processor(model, device=str(device))

        _cached = SAM3Bundle(
            model=model,
            processor=processor,
            device=device,
            use_video_model=use_video_model,
        )
        log.info("SAM3 ready (use_video_model=%s) on %s", use_video_model, device)
        return _cached


def drop_bundle() -> None:
    global _cached
    with _lock:
        if _cached is None:
            return
        del _cached.model
        del _cached.processor
        _cached = None
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
