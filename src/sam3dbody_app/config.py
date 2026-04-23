"""Runtime configuration. Everything the user can tweak lives in a single
``config.ini`` at the project root:

    [active]
    pack = default                 # current preset pack

    [features]
    preset_pack_admin = false      # gate Tab ③

Blender の実行ファイルパスは config.ini では扱わない。``setup.sh`` /
``setup.cmd`` がプロジェクト直下にポータブル版を配置するので、そこを基準に
相対解決する (詳細は ``_bundled_blender_exe``)。明示的に差し替えたい場合は
環境変数 ``SAM3DBODY_BLENDER_EXE`` を使う。

Values can still be overridden at launch time via env vars (`SAM3DBODY_*`).
Legacy installs that only have ``active_preset.ini`` are migrated on the
first read.
"""
from __future__ import annotations

import configparser
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class AppPaths:
    root: Path
    models_dir: Path
    presets_dir: Path
    tmp_dir: Path            # ephemeral artifacts (mesh.obj / mask.png / *.fbx)
    web_dir: Path
    config_ini: Path
    legacy_active_preset_ini: Path  # old name, kept for migration only

    # Kept as a back-compat alias so older code paths still work.
    @property
    def active_preset_ini(self) -> Path:  # pragma: no cover — compat shim
        return self.config_ini

    def active_pack_name(self) -> str:
        cp = _read_config_ini(self)
        name = cp.get("active", "pack", fallback="default").strip()
        return name or "default"

    def active_pack_dir(self) -> Path:
        pack = self.active_pack_name()
        candidate = self.presets_dir / pack
        if candidate.is_dir():
            return candidate
        return self.presets_dir / "default"

    def chara_settings_dir(self) -> Path:
        return self.active_pack_dir() / "chara_settings_presets"


def _read_config_ini(paths: AppPaths) -> configparser.ConfigParser:
    """Return a ConfigParser pre-populated from ``config.ini`` (falling back
    to the legacy ``active_preset.ini`` if that's the only one present)."""
    cp = configparser.ConfigParser()
    if paths.config_ini.is_file():
        cp.read(paths.config_ini, encoding="utf-8")
        return cp
    if paths.legacy_active_preset_ini.is_file():
        cp.read(paths.legacy_active_preset_ini, encoding="utf-8")
    return cp


def _ensure_config_ini(paths: AppPaths) -> None:
    """Create ``config.ini`` with sensible defaults if it's missing. If an
    older ``active_preset.ini`` exists, migrate its ``[active]`` section."""
    if paths.config_ini.is_file():
        return

    cp = configparser.ConfigParser()
    if paths.legacy_active_preset_ini.is_file():
        cp.read(paths.legacy_active_preset_ini, encoding="utf-8")

    if "active" not in cp:
        cp["active"] = {}
    cp["active"].setdefault("pack", "default")

    if "features" not in cp:
        cp["features"] = {}
    cp["features"].setdefault("preset_pack_admin", "false")
    cp["features"].setdefault("debug", "false")

    if "sam3" not in cp:
        cp["sam3"] = {}
    cp["sam3"].setdefault("use_sam3", "true")
    cp["sam3"].setdefault("text_prompt", "person")
    cp["sam3"].setdefault("confidence_threshold", "0.5")
    cp["sam3"].setdefault("min_width_pixels", "0")
    cp["sam3"].setdefault("min_height_pixels", "0")

    with paths.config_ini.open("w", encoding="utf-8") as f:
        f.write(
            "# config.ini\n"
            "#\n"
            "# [active]    pack : currently-active preset pack name (directory under presets/)\n"
            "# [features]  preset_pack_admin : 'true' to enable the Preset Pack Admin tab\n"
            "#                                   (pack switch / clone / delete, FBX rebuild).\n"
            "#                                   Default 'false' so a fresh install ships a\n"
            "#                                   read-only UI until the user opts in.\n"
            "#             debug             : 'true' to show the Health panel in the UI.\n"
            "# [sam3]      segmentation defaults for image + video pipelines. The UI no longer\n"
            "#             exposes these — edit here to change them (hot-reload on each request).\n"
            "#               use_sam3, text_prompt, confidence_threshold,\n"
            "#               min_width_pixels, min_height_pixels\n"
            "\n"
        )
        cp.write(f)


def _bundled_blender_exe() -> Path | None:
    """プロジェクト直下に同梱されたポータブル Blender のパス (存在すれば) を返す。
    setup.sh / setup.cmd が以下のレイアウトで配置する想定:
      - Windows            : ``blender41-portable/blender.exe`` (公式 zip 平坦展開)
      - Linux x86_64       : ``blender41-portable/blender``     (公式 tar.xz 平坦展開)
      - Linux aarch64/ARM64: ``ARM_blender41-portable/bin/blender`` (自前ビルド、bin/ レイアウト)
    """
    import platform as _pf
    import sys as _sys
    root = _project_root()
    candidates: list[Path] = []
    if _sys.platform.startswith("linux"):
        machine = _pf.machine().lower()
        if machine in ("aarch64", "arm64"):
            candidates.append(root / "ARM_blender41-portable" / "bin" / "blender")
        else:
            candidates.append(root / "blender41-portable" / "blender")
    elif _sys.platform == "win32":
        candidates.append(root / "blender41-portable" / "blender.exe")
    for c in candidates:
        if c.is_file():
            return c
    return None


def _resolve_blender_exe() -> str:
    """Blender 実行ファイルを解決する。優先順:
      1. 環境変数 ``SAM3DBODY_BLENDER_EXE`` (明示指定のエスケープハッチ)
      2. プロジェクト直下の同梱ポータブル版 (``_bundled_blender_exe``)
      3. PATH 上の ``blender`` / ``blender.exe``
    どれも無ければ空文字を返し、呼び出し側で分かりやすいエラーを出させる。"""
    import shutil
    env = os.environ.get("SAM3DBODY_BLENDER_EXE")
    if env:
        return env
    bundled = _bundled_blender_exe()
    if bundled is not None:
        return str(bundled)
    return shutil.which("blender") or shutil.which("blender.exe") or ""


@lru_cache(maxsize=1)
def get_paths() -> AppPaths:
    root = Path(os.environ.get("SAM3DBODY_ROOT", _project_root())).resolve()
    paths = AppPaths(
        root=root,
        models_dir=root / "models",
        presets_dir=root / "presets",
        tmp_dir=root / "tmp",
        web_dir=root / "web",
        config_ini=root / "config.ini",
        legacy_active_preset_ini=root / "active_preset.ini",
    )
    for d in (paths.models_dir, paths.presets_dir, paths.tmp_dir):
        d.mkdir(parents=True, exist_ok=True)
    _ensure_config_ini(paths)
    return paths


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

def _ini_feature_flag(paths: AppPaths, key: str, default: bool = False) -> bool:
    cp = _read_config_ini(paths)
    raw = cp.get("features", key, fallback=str(default)).strip().lower()
    return raw in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Sam3Settings:
    """SAM3 person-mask segmentation defaults. Sourced from ``[sam3]``."""

    use_sam3: bool
    text_prompt: str
    confidence_threshold: float
    min_width_pixels: int
    min_height_pixels: int


def _ini_sam3_settings(paths: AppPaths) -> Sam3Settings:
    cp = _read_config_ini(paths)
    def _bool(s: str) -> bool:
        return s.strip().lower() in ("1", "true", "yes", "on")
    def _float(s: str, d: float) -> float:
        try: return float(s)
        except Exception: return d
    def _int(s: str, d: int) -> int:
        try: return int(s)
        except Exception: return d
    return Sam3Settings(
        use_sam3=_bool(cp.get("sam3", "use_sam3", fallback="true")),
        text_prompt=cp.get("sam3", "text_prompt", fallback="person").strip() or "person",
        confidence_threshold=_float(cp.get("sam3", "confidence_threshold", fallback="0.5"), 0.5),
        min_width_pixels=_int(cp.get("sam3", "min_width_pixels", fallback="0"), 0),
        min_height_pixels=_int(cp.get("sam3", "min_height_pixels", fallback="0"), 0),
    )


@dataclass(frozen=True)
class AppSettings:
    blender_exe: str
    host: str
    port: int
    device: str
    feature_preset_pack_admin: bool
    feature_debug: bool
    sam3: Sam3Settings

    @staticmethod
    def load() -> "AppSettings":
        paths = get_paths()
        return AppSettings(
            blender_exe=_resolve_blender_exe(),
            host=os.environ.get("SAM3DBODY_HOST", "127.0.0.1"),
            port=int(os.environ.get("SAM3DBODY_PORT", "8765")),
            device=os.environ.get("SAM3DBODY_DEVICE", "cuda"),
            feature_preset_pack_admin=_ini_feature_flag(paths, "preset_pack_admin", False),
            feature_debug=_ini_feature_flag(paths, "debug", False),
            sam3=_ini_sam3_settings(paths),
        )


def write_config_section(section: str, values: dict[str, str]) -> None:
    """Persist key/value pairs into ``config.ini`` under ``[section]``."""
    paths = get_paths()
    cp = configparser.ConfigParser()
    if paths.config_ini.is_file():
        cp.read(paths.config_ini, encoding="utf-8")
    if section not in cp:
        cp[section] = {}
    for k, v in values.items():
        cp[section][k] = str(v)
    with paths.config_ini.open("w", encoding="utf-8") as f:
        cp.write(f)
