# Copyright (c) Meta Platforms, Inc. and affiliates. All Rights Reserved
#
# Register this vendored copy under the bare name ``sam3`` in sys.modules so
# the package's own absolute imports (``from sam3.model import ...``) resolve
# to our copy without needing a separate pip install.
import sys as _sys

_sys.modules.setdefault("sam3", _sys.modules[__name__])

from .model_builder import build_sam3_image_model  # noqa: E402

__version__ = "0.1.0"

__all__ = ["build_sam3_image_model"]
