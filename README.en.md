# SAM3DBody Standalone WebUI

**Language:** [🇯🇵 日本語](README.md) ・ 🇬🇧 English (current)

A **standalone FastAPI + Three.js web app** for turning a single image or video into a rigged 3D character and motion FBX — without needing ComfyUI.

- **Image tab**: image → SAM3 person mask → SAM 3D Body pose estimation → render onto any body shape → export rigged FBX
- **Video tab**: video → per-frame pose estimation → bake all frames as keyframes on a T-pose rig → export animated FBX (via a Blender subprocess)
- Full control over body shape (9-axis PCA), bone lengths, and ~20 blend shapes via sliders
- Swappable **preset packs** for shipping custom blend-shape definitions

## 🧬 Upstream projects

This project is a **standalone repackaging** of two existing ComfyUI extensions. The ComfyUI wrapper has been removed and replaced by a standalone FastAPI server.

| Upstream | Role | License |
|---|---|---|
| **[tori29umai0123/ComfyUI-SAM3DBody_utills](https://github.com/tori29umai0123/ComfyUI-SAM3DBody_utills)** | Base — SAM 3D Body + MHR runtime, blendshape / bone-scale / preset-pack logic, Blender FBX pipeline (`tools/build_rigged_fbx.py`, `tools/build_animated_fbx.py`) | **GPL v3** |
| ├ [PozzettiAndrea/ComfyUI-SAM3DBody](https://github.com/PozzettiAndrea/ComfyUI-SAM3DBody) | Original ComfyUI custom node (upstream of the fork above) | MIT |
| ├ [facebookresearch/sam-3d-body](https://github.com/facebookresearch/sam-3d-body) | SAM 3D Body model code (vendored under `src/sam3dbody_app/core/sam_3d_body/`) | SAM License (Meta) |
| └ MHR (Momentum Human Rig) | Parametric body model (`mhr_model.pt` + mesh topology) | Apache 2.0 (Meta) |
| **[comfyui_sam3](https://github.com/wouterverweirder/comfyui-sam3)** (reference implementation) | SAM3 (Meta Segment Anything 3) person-mask logic. Vendored under `src/sam3dbody_app/core/sam3/` | MIT (Copyright (c) 2025 Wouter Verweirder) |
| └ [facebook/sam3](https://huggingface.co/facebook/sam3) | SAM3 model weights | Meta license |

See [`docs/licenses/THIRD_PARTY_NOTICES.md`](docs/licenses/THIRD_PARTY_NOTICES.md) for the full attribution chain and license texts.

## ✨ Features (per tab)

The web UI has **four tabs** at the top for image processing, video processing, character authoring, and pack management.

### 📷 1. Image tab

Retarget a pose from a single image onto any body shape and export a rigged FBX.

- Upload an image → SAM3 masks the person (default `text_prompt = "person"`)
- SAM 3D Body estimates the full-body pose
- In the bottom **Character panel**, pick a preset or drop in a custom character JSON to choose the target body shape
- Three.js renders the result live
- Clicking `Download FBX` kicks off a Blender subprocess (`tools/build_rigged_fbx.py`) that emits a rigged FBX — the interactive preview never touches Blender. (Blender required for FBX export.)

### 🎬 2. Video tab

Extract continuous motion from a video and export an animated FBX.

- Upload a video → each frame runs through SAM 3D Body to estimate joint rotations
- Pick a preset in the **Character panel** → all frames are baked as keyframes onto a rig built from that body shape
- `root_motion_mode` picks the root-Y correction: `auto_ground_lock` (default), `free`, or `xz_only`
- Fine-tune estimation with `bbox thr` / `fps` / `stride` / `max frames`
- A Blender subprocess (`tools/build_animated_fbx.py`) emits the animated FBX
- Drop the FBX into Unity / Unreal — it imports as a Humanoid-retargetable rig out of the box
- Switching presets *after* estimation **rebuilds the FBX with the new character automatically**, reusing the cached motion

### 🧑‍🎨 3. Character Make tab (author a new preset)

Sculpt a body shape with sliders and **save it as a new character preset JSON**.

- Starting from the MHR neutral T-pose, adjust the body shape with these sliders:
  - **Body (PCA 9 axes)**: `body_fat`, `body_muscle`, `body_limb_girth`, `body_chest_shoulder`, `body_waist_hip`, …
  - **Bone length (4 chains)**: `bone_torso`, `bone_neck`, `bone_arm`, `bone_leg`
  - **Blendshapes (~20)**: `bs_face_big`, `bs_neck_thick`, `bs_breast_full`, `bs_MuscleScale`, …
- `Reset` returns every slider to neutral
- `Download JSON` saves the current shape — drop it into `presets/<pack>/chara_settings_presets/` and it appears in the preset dropdown on the image / video tabs
- Presets you author here can be reused across the image and video tabs

### ⚙ 4. Preset Admin tab (pack switching & blend-shape updates)

Manage preset packs and regenerate blend-shape data from an FBX edited in Blender. Enable via `[features] preset_pack_admin = true` in `config.ini`.

**Pack switch / clone / delete:**
- A preset pack is the `presets/<pack>/` directory tree (blend-shape npz + vertex map JSONs + character presets)
- Pick an active pack from the dropdown and click `Switch`
- `Clone` duplicates the current pack under a new name
- `Delete selected` removes unused packs
- The pack layout is **fully compatible with the upstream `ComfyUI-SAM3DBody_utills`**, so existing packs drop in unchanged

**FBX Rebuild (blend-shape update):**
- Open `tools/bone_backup/all_parts_bs.fbx` in Blender, add / edit shape keys, save
- Drop the edited FBX onto this tab and click `Rebuild`:
  - `face_blendshapes.npz` (the blend-shape deltas) is regenerated
  - `<obj>_vertices.json` (FBX-vertex → MHR-vertex map) is regenerated
  - Newly added shape keys **appear as sliders on the Character Make tab automatically** — no code changes needed
- Internally runs `tools/extract_face_blendshapes.py` followed by `tools/rebuild_vertex_jsons.py`

## 🔧 Requirements

| Item | Version |
|---|---|
| OS | Windows 11 / Linux (x86_64, aarch64) |
| Python | 3.11 |
| PyTorch | x86_64 / Windows: 2.10.0+cu128<br>aarch64 (e.g. GB10 / sm_121): 2.13.0.dev (nightly) + cu130 |
| CUDA | x86_64 / Windows: 12.8<br>aarch64: 13.0 (official Blackwell Ultra sm_121 support) |
| GPU | NVIDIA GPU (≥ 4 GB VRAM recommended, 8 GB for comfort)<br>DGX Spark (GB10 / sm_121) supported |
| Blender | 4.1.1 — `setup.sh` / `setup.cmd` auto-downloads a portable build, so no separate install is required |

The SAM 3D Body weights (~3.4 GB) stay resident on the GPU. CPU inference works but is considerably slower.

> ℹ️ **Note on aarch64 (NVIDIA GB10 / DGX Spark)**
> GB10 is compute capability 12.1 (sm_121). PyTorch 2.10 (cu128) only ships an NVRTC that targets up to sm_120, so aarch64 installs automatically resolve to a nightly cu130 wheel (with sm_121 support) — the split is declared in `pyproject.toml` via `platform_machine` markers. x86_64 and Windows stay on cu128 stable.

## 📦 Setup

### Windows

```cmd
cd E:\SAM3DBody_utills
setup.cmd
```

`setup.cmd`:
- Creates `.venv` (Python 3.11) via [uv](https://docs.astral.sh/uv/)
- Installs dependencies from `pyproject.toml` / `uv.lock` (cu128 wheels for torch/torchvision/torchaudio)
- Installs redistributable CUDA wheels bundled under `wheels/`
- Downloads the official portable **Blender 4.1.1** (`blender-4.1.1-windows-x64.zip`, ~400 MB) into `blender41-portable/` (skipped if already present)

### Linux (x86_64 / aarch64)

```bash
cd /path/to/SAM3DBody_utills
./setup.sh
```

`setup.sh` performs the following automatically per architecture:

| Architecture | torch / triton | Portable Blender |
|---|---|---|
| x86_64 | cu128 stable (via pypi) | Official `blender-4.1.1-linux-x64.tar.xz` auto-DL from `download.blender.org` → `blender41-portable/` |
| aarch64 (ARM64) | nightly cu130 + matching triton wheel (platform-split via `pyproject.toml`) | Self-built portable auto-DL from this repo's [GitHub Release (`blender-arm64-v1.0`)](https://github.com/tori29umai0123/SAM3DBody_utills/releases/tag/blender-arm64-v1.0) with sha256 check → `ARM_blender41-portable/` |

After extraction, `setup.sh` also injects `numpy` into Blender's bundled `site-packages/` (the self-built Blender does not ship it, which otherwise causes the FBX exporter to fail).

### Model weights

Weights auto-download from HuggingFace on first launch into `models/`:
- `models/sam3dbody/` — SAM 3D Body + MHR weights (~3.5 GB, `jetjodh/sam-3d-body-dinov3`)
- `models/sam3/` — SAM3 weights (`facebook/sam3`; requires `hf auth login` beforehand)

Manual layout:

```
E:\SAM3DBody_utills\models\
├── sam3dbody\
│   ├── model.ckpt
│   ├── model_config.yaml
│   └── assets\mhr_model.pt
└── sam3\
    └── sam3.pt
```

## 🚀 Running

### Windows

```cmd
run.cmd
```

Then open <http://127.0.0.1:8765/> in a browser.

### Linux

```bash
./run.sh
```

### Overriding host / port

```cmd
set SAM3DBODY_HOST=0.0.0.0
set SAM3DBODY_PORT=9000
run.cmd
```

## ⚙ Configuration (`config.ini`)

```ini
[active]
pack = default                    ; currently active preset pack

[features]
preset_pack_admin = false         ; true to show the preset pack admin tab
debug = false                     ; true to show the Health panel

[sam3]
use_sam3 = true                   ; enable SAM3 person masking
text_prompt = person              ; SAM3 text prompt
confidence_threshold = 0.5
min_width_pixels = 0
min_height_pixels = 0
```

Settings are hot-reloaded per request — no server restart needed.

### How the Blender executable is resolved

`config.ini` does not carry a Blender path. `setup.sh` / `setup.cmd` drop a portable build next to the project, which the app resolves relatively in this order:

1. `SAM3DBODY_BLENDER_EXE` environment variable (escape hatch for explicit overrides)
2. Bundled portable Blender
   - Windows: `blender41-portable/blender.exe`
   - Linux x86_64: `blender41-portable/blender`
   - Linux aarch64: `ARM_blender41-portable/bin/blender`
3. `blender` / `blender.exe` on `PATH`

## 📂 Project layout

```
SAM3DBody_utills/
├── LICENSE                         ← GPL v3 (inherited from upstream)
├── README.md                       ← Japanese
├── README.en.md                    ← this file (English)
├── config.ini
├── pyproject.toml
├── run.cmd / run.sh                ← starts uvicorn
├── setup.cmd / setup.sh            ← uv + dependency install
├── wheels/                         ← redistributable CUDA wheels
├── blender41-portable/             ← setup-installed portable Blender (Win / Linux x86_64, auto-DL)
├── ARM_blender41-portable/         ← setup-installed portable Blender (Linux aarch64, auto-DL)
├── models/                         ← SAM 3D Body / SAM3 weights (auto-DL)
├── presets/
│   └── default/                    ← default preset pack (upstream-compatible)
│       ├── face_blendshapes.npz
│       ├── mhr_reference_vertices.json
│       └── chara_settings_presets/
├── src/sam3dbody_app/
│   ├── main.py                     ← FastAPI entrypoint
│   ├── core/
│   │   ├── sam_3d_body/            ← vendored SAM 3D Body (SAM License)
│   │   └── sam3/                   ← vendored SAM3 (Meta license)
│   ├── routers/                    ← /api/* endpoints
│   ├── services/                   ← Blender bridge / renderer / motion session
│   └── ...
├── web/                            ← frontend (Three.js, plain JS — no Vite)
│   ├── index.html
│   └── static/app.js
├── tools/                          ← headless Blender subprocess scripts
│   ├── build_rigged_fbx.py
│   ├── build_animated_fbx.py
│   └── extract_face_blendshapes.py
└── docs/licenses/                  ← full sub-license texts
```

## 📝 License

This project is distributed under the **GNU General Public License v3.0**, inherited from the upstream `tori29umai0123/ComfyUI-SAM3DBody_utills`. See the root [`LICENSE`](LICENSE).

Bundled third-party licenses:

- **ComfyUI-SAM3DBody_utills wrapper code**: MIT (Andrea Pozzetti)
- **SAM 3D Body** (`src/sam3dbody_app/core/sam_3d_body/`): SAM License (Meta)
- **MHR — Momentum Human Rig** (`mhr_model.pt` + topology + `face_blendshapes.npz`): Apache 2.0 (Meta)
- **comfyui_sam3** (reference implementation of the SAM3 masking flow): MIT (Wouter Verweirder)
- **SAM3** (weights): Meta license

All attribution and full license texts live in [`docs/licenses/THIRD_PARTY_NOTICES.md`](docs/licenses/THIRD_PARTY_NOTICES.md). When redistributing, **include the source and all license files** per GPL v3 requirements.

## 🙏 Credits

- **SAM 3D Body**: Meta AI / facebookresearch ([paper](https://ai.meta.com/research/publications/sam-3d-body-robust-full-body-human-mesh-recovery/))
- **Momentum Human Rig (MHR)**: Meta Platforms, Inc.
- **SAM3 (Segment Anything 3)**: Meta AI / <https://huggingface.co/facebook/sam3>
- **ComfyUI-SAM3DBody_utills**: [@tori29umai0123](https://github.com/tori29umai0123)
- **PozzettiAndrea/ComfyUI-SAM3DBody**: [@PozzettiAndrea](https://github.com/PozzettiAndrea)
- **comfyui_sam3**: [@wouterverweirder](https://github.com/wouterverweirder)

## 🗣 Community / Issues

- Issues / PRs for the standalone WebUI itself go here in this repository.
- For SAM 3D Body / MHR / ComfyUI-version discussion, see the upstream [PozzettiAndrea/ComfyUI-SAM3DBody Discussions](https://github.com/PozzettiAndrea/ComfyUI-SAM3DBody/discussions) and [tori29umai0123/ComfyUI-SAM3DBody_utills Issues](https://github.com/tori29umai0123/ComfyUI-SAM3DBody_utills/issues).
