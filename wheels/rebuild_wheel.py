"""
Rebuild a .whl file from an already-installed package by reading its RECORD.

Usage:
    python rebuild_wheel.py <site-packages> <dist-info-dirname> <wheel-version-tag> <output-dir>

Example:
    python rebuild_wheel.py \
        C:/ComfyUI/.venv/Lib/site-packages \
        cc_torch-0.2.dist-info \
        0.2+cu128torch210-cp311-cp311-win_amd64 \
        E:/SAM3DBody_utills/wheels

This regenerates `cc_torch-0.2+cu128torch210-cp311-cp311-win_amd64.whl` from the
installed layout, preserving the existing RECORD hashes. The resulting wheel is
a valid PEP 427 archive suitable for `pip install`.
"""

from __future__ import annotations

import csv
import sys
import zipfile
from pathlib import Path


def main() -> None:
    if len(sys.argv) != 5:
        print(__doc__)
        sys.exit(2)

    site_pkgs = Path(sys.argv[1]).resolve()
    dist_info_name = sys.argv[2]
    wheel_tag = sys.argv[3]  # full "<version>-<python>-<abi>-<platform>"
    out_dir = Path(sys.argv[4]).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    dist_info_dir = site_pkgs / dist_info_name
    if not dist_info_dir.is_dir():
        raise SystemExit(f"not found: {dist_info_dir}")

    record_path = dist_info_dir / "RECORD"
    if not record_path.is_file():
        raise SystemExit(f"RECORD missing: {record_path}")

    # Derive package name from dist-info dir (everything before the last `-<ver>.dist-info`).
    stem = dist_info_name[: -len(".dist-info")]
    # stem is like "cc_torch-0.2"; the first dash before the version.
    pkg_name = stem.split("-", 1)[0]
    whl_name = f"{pkg_name}-{wheel_tag}.whl"
    out_path = out_dir / whl_name

    # Read RECORD file list.
    with record_path.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))

    # Deduplicate + collect (rel_path, size, hash) tuples. RECORD entries are relative
    # to site-packages.
    entries: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for row in rows:
        if not row:
            continue
        rel = row[0]
        if rel in seen:
            continue
        seen.add(rel)
        h = row[1] if len(row) > 1 else ""
        sz = row[2] if len(row) > 2 else ""
        entries.append((rel, h, sz))

    missing: list[str] = []
    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rel, _h, _sz in entries:
            # Skip RECORD itself; we re-add below.
            if rel.endswith("/RECORD") or rel == "RECORD":
                continue
            src = site_pkgs / rel
            if not src.exists():
                missing.append(rel)
                continue
            # Wheel zip entries use forward slashes.
            arcname = rel.replace("\\", "/")
            zf.write(src, arcname=arcname)
        # RECORD is written unchanged so hashes stay consistent.
        zf.write(record_path, arcname=f"{dist_info_name}/RECORD".replace("\\", "/"))

    print(f"wrote: {out_path}")
    if missing:
        print(f"WARNING: {len(missing)} files from RECORD not found on disk:")
        for m in missing[:10]:
            print("  -", m)


if __name__ == "__main__":
    main()
