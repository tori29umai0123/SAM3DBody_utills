"""Runtime configuration. Everything the user can tweak lives in a single
``config.ini`` at the project root:

    [active]
    pack = default                 # current preset pack

    [features]
    preset_pack_admin = false      # gate Tab ③

    [blender]
    exe_path =                     # absolute path to blender(.exe)

Blender の実行ファイルの解決順:
    1. 環境変数 ``SAM3DBODY_BLENDER_EXE`` (明示指定のエスケープハッチ)
    2. ``config.ini`` の ``[blender] exe_path`` (setup.cmd/setup.sh が自動で書く)
    3. プロジェクト直下の同梱ポータブル版 (``_bundled_blender_exe``)
    4. ``PATH`` 上の ``blender`` / ``blender.exe``

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

    if "segmentation" not in cp:
        cp["segmentation"] = {}
    cp["segmentation"].setdefault("enabled", "true")
    cp["segmentation"].setdefault("backend", "birefnet_lite")
    cp["segmentation"].setdefault("confidence_threshold", "0.5")
    cp["segmentation"].setdefault("min_width_pixels", "0")
    cp["segmentation"].setdefault("min_height_pixels", "0")

    if "blender" not in cp:
        cp["blender"] = {}
    cp["blender"].setdefault("exe_path", "")

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
            "# [segmentation] segmentation defaults for image + video pipelines. The UI no longer\n"
            "#             exposes these — edit here to change them (hot-reload on each request).\n"
            "#               enabled, backend, confidence_threshold,\n"
            "#               min_width_pixels, min_height_pixels\n"
            "# [blender]   exe_path : absolute path to blender(.exe). Normally written by\n"
            "#                        setup.cmd/setup.sh. Leave empty to fall back to the\n"
            "#                        bundled portable build (or PATH).\n"
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


def _config_blender_exe(paths: "AppPaths") -> str | None:
    """config.ini の ``[blender] exe_path`` を読み、実在するファイルなら絶対パス
    を返す。未設定または不在なら ``None``。"""
    cp = _read_config_ini(paths)
    raw = cp.get("blender", "exe_path", fallback="").strip().strip('"').strip("'")
    if not raw:
        return None
    expanded = os.path.expandvars(os.path.expanduser(raw))
    p = Path(expanded)
    if not p.is_file():
        return None
    return str(p.resolve())


def _resolve_blender_exe() -> str:
    """Blender 実行ファイルを解決する。優先順:
      1. 環境変数 ``SAM3DBODY_BLENDER_EXE`` (明示指定のエスケープハッチ)
      2. ``config.ini`` の ``[blender] exe_path`` (setup.cmd/setup.sh が自動で書く)
      3. プロジェクト直下の同梱ポータブル版 (``_bundled_blender_exe``)
      4. PATH 上の ``blender`` / ``blender.exe``
    どれも無ければ空文字を返し、呼び出し側で分かりやすいエラーを出させる。"""
    import shutil
    env = os.environ.get("SAM3DBODY_BLENDER_EXE")
    if env:
        return env
    cfg = _config_blender_exe(get_paths())
    if cfg:
        return cfg
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
class SegmentationSettings:
    """Segmentation defaults read from `[segmentation]`."""

    enabled: bool
    backend: str
    confidence_threshold: float
    min_width_pixels: int
    min_height_pixels: int


def _ini_segmentation_settings(paths: AppPaths) -> SegmentationSettings:
    cp = _read_config_ini(paths)
    section = "segmentation"
    def _bool(s: str) -> bool:
        return s.strip().lower() in ("1", "true", "yes", "on")
    def _float(s: str, d: float) -> float:
        try: return float(s)
        except Exception: return d
    def _int(s: str, d: int) -> int:
        try: return int(s)
        except Exception: return d
    return SegmentationSettings(
        enabled=_bool(cp.get(section, "enabled", fallback="true")),
        backend=cp.get(section, "backend", fallback="birefnet_lite").strip() or "birefnet_lite",
        confidence_threshold=_float(cp.get(section, "confidence_threshold", fallback="0.5"), 0.5),
        min_width_pixels=_int(cp.get(section, "min_width_pixels", fallback="0"), 0),
        min_height_pixels=_int(cp.get(section, "min_height_pixels", fallback="0"), 0),
    )


@dataclass(frozen=True)
class AppSettings:
    blender_exe: str
    host: str
    port: int
    device: str
    feature_preset_pack_admin: bool
    feature_debug: bool
    segmentation: SegmentationSettings

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
            segmentation=_ini_segmentation_settings(paths),
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
