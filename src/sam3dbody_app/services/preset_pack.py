"""Preset pack I/O — discover packs, load/save character JSON files, autosave.

Directory layout (ComfyUI-SAM3DBody_utills compatible):
    presets/
        <pack_name>/
            face_blendshapes.npz
            mhr_reference_vertices.json
            chara_settings_presets/
                autosave.json
                chibi.json
                female.json
                male.json
                reset.json
                ...
    active_preset.ini   # [active]\npack = <pack_name>
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import get_paths

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class PresetPackPaths:
    pack_dir: Path
    npz_path: Path
    chara_settings_dir: Path


def active_pack_paths() -> PresetPackPaths:
    paths = get_paths()
    pack_dir = paths.active_pack_dir()
    return PresetPackPaths(
        pack_dir=pack_dir,
        npz_path=pack_dir / "face_blendshapes.npz",
        chara_settings_dir=pack_dir / "chara_settings_presets",
    )


def _valid_name(name: str) -> bool:
    if not name:
        return False
    return "/" not in name and "\\" not in name and ".." not in name


def list_presets() -> list[str]:
    d = active_pack_paths().chara_settings_dir
    if not d.is_dir():
        return []
    names = sorted(
        p.stem for p in d.glob("*.json")
        if p.is_file()
    )
    # "autosave" and "reset" are special but still listed so the UI can offer them.
    return names


def load_preset(name: str) -> dict[str, Any]:
    if not _valid_name(name):
        raise ValueError(f"invalid preset name: {name!r}")
    p = active_pack_paths().chara_settings_dir / f"{name}.json"
    if not p.is_file():
        raise FileNotFoundError(str(p))
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_preset(name: str, settings: dict[str, Any]) -> Path:
    if not _valid_name(name):
        raise ValueError(f"invalid preset name: {name!r}")
    d = active_pack_paths().chara_settings_dir
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{name}.json"
    with p.open("w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2, sort_keys=True)
    return p
