# SAM3DBody Standalone WebUI

**Language:** [🇯🇵 日本語](README.md) ・ 🇬🇧 English (current)

A **standalone FastAPI + Three.js web app** for turning a single image or video into a rigged 3D character and motion FBX / BVH — without needing ComfyUI.

- **Image tab**: image → SAM3 person mask → SAM 3D Body pose estimation → render onto any body shape → export rigged FBX or single-frame BVH
- **Video tab**: video → per-frame pose estimation → bake all frames as keyframes on a T-pose rig → export animated FBX or full-length BVH (via a Blender subprocess)
- Full control over body shape (9-axis PCA), bone lengths, and ~20 blend shapes via sliders
- Swappable **preset packs** for shipping custom blend-shape definitions

## 🧬 Components & licenses

This project uses a **multi-license layout**. The wrapper code is MIT,
while vendored SAM 3D Body / MHR / SAM3 each follow their original
upstream licenses.

| Component | Scope | License | Copyright holder |
|---|---|---|---|
| **Wrapper code** (standalone WebUI integration) | `src/sam3dbody_app/` (excluding vendored sub-dirs), `tools/`, `web/`, `setup.py`, `run.cmd`/`run.sh` | **MIT License** | Copyright (c) 2025 Andrea Pozzetti (inherited from [PozzettiAndrea/ComfyUI-SAM3DBody](https://github.com/PozzettiAndrea/ComfyUI-SAM3DBody)) |
| **SAM 3D Body** (core model) | `src/sam3dbody_app/core/sam_3d_body/` (vendored) | **SAM License** | Copyright (c) Meta Platforms, Inc. ([facebookresearch/sam-3d-body](https://github.com/facebookresearch/sam-3d-body)) |
| **MHR (Momentum Human Rig)** | `mhr_model.pt` + MHR-topology derivative data (`presets/default/face_blendshapes.npz`, `presets/default/*_vertices.json`) | **Apache License 2.0** | Copyright (c) Meta Platforms, Inc. |
| **SAM3** (person mask utility) | `src/sam3dbody_app/core/sam3/` (vendored) | **MIT License** | Copyright (c) 2025 Wouter Verweirder ([comfyui_sam3](https://github.com/wouterverweirder/comfyui-sam3)) |
| **SAM3 model weights** | `models/sam3/sam3.pt` (auto-downloaded) | Meta license | [facebook/sam3](https://huggingface.co/facebook/sam3) |

See [`docs/licenses/THIRD_PARTY_NOTICES.md`](docs/licenses/THIRD_PARTY_NOTICES.md) for the full attribution chain and license texts.

## ✨ Features (per tab)

The web UI has **four tabs** at the top for image processing, video processing, character authoring, and pack management.

### 📷 1. Image tab

Retarget a pose from a single image onto any body shape and export a rigged FBX / BVH.

- Upload an image → SAM3 masks the person (default `text_prompt = "person"`). Transparent PNGs are composited onto white automatically before inference.
- SAM 3D Body estimates the full-body pose
- A **Lean correction** slider (0–1, default 0) un-bends a forward-leaning upper body along the spine→neck chain
- In the bottom **Character panel**, pick a preset or drop in a custom character JSON to choose the target body shape
- Three.js renders the result live
- Clicking `Download FBX` kicks off a Blender subprocess (`tools/build_rigged_fbx.py`) that emits a rigged FBX — the interactive preview never touches Blender.
- Clicking `Download BVH` builds the same rigged FBX and converts it to a **single-frame** BVH via `tools/fbx2bvh_simple.py`.
- Blender is required for both FBX and BVH export.

### 🎬 2. Video tab

Extract continuous motion from a video and export an animated FBX / BVH.

- Upload a video → each frame runs through SAM 3D Body to estimate joint rotations
- Pick a preset in the **Character panel** → all frames are baked as keyframes onto a rig built from that body shape
- A **Lean correction** slider (0–1, default 0) is baked into every frame's rig (rebuild fires when you release the slider)
- `root_motion_mode` picks the root-Y correction: `auto_ground_lock` (default), `free`, or `xz_only`
- Fine-tune estimation with `bbox thr` / `fps` / `stride` / `max frames`
- A Blender subprocess (`tools/build_animated_fbx.py`) emits the animated FBX
- `Download BVH` rebuilds the current animated FBX and converts **all frames** to BVH via `tools/fbx2bvh_simple.py`
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
| Blender | 4.1.1 — enter your existing install path at setup, or press ENTER to let setup auto-download a portable build |
| [uv](https://docs.astral.sh/uv/) | Required before running setup. Install from the official site if you don't have it. |

The SAM 3D Body weights (~3.4 GB) stay resident on the GPU. CPU inference works but is considerably slower.

> ℹ️ **Note on aarch64 (NVIDIA GB10 / DGX Spark)**
> GB10 is compute capability 12.1 (sm_121). PyTorch 2.10 (cu128) only ships an NVRTC that targets up to sm_120, so aarch64 installs automatically resolve to a nightly cu130 wheel (with sm_121 support) — the split is declared in `pyproject.toml` via `platform_machine` markers. x86_64 and Windows stay on cu128 stable.

## 📦 Setup

Install [uv](https://docs.astral.sh/uv/) first.

### Windows

```cmd
cd E:\SAM3DBody_utills
setup.cmd
```

Or double-click `setup.cmd` in Explorer.

### Linux

```bash
cd /path/to/SAM3DBody_utills
./setup.sh
```

### Two prompts during setup

**1. Rebuild `.venv`?**

```
Delete .venv and reinstall all dependencies from scratch? [y/N]:
```

- Press Enter (default `N`) or `n` → keep the existing `.venv`; just run `uv sync` (fast).
- Type `y` → wipe `.venv` and reinstall everything (several minutes — torch etc. get re-downloaded).
- On a fresh install (no `.venv` yet) this prompt is skipped and a new venv is created automatically.

**2. Blender path**

```
Blender path (ENTER to auto-download):
```

- **Use your existing Blender 4.1+**: paste the full path and press Enter (quotes allowed).
  - Windows example: `C:\Program Files\Blender Foundation\Blender 4.1\blender.exe`
  - Linux example:   `/opt/blender-4.1/blender`
- **Auto-download**: press Enter. The official portable Blender 4.1.1 (~400 MB) is fetched into `blender41-portable/`.
- Typing `n` / `skip` / `auto` also triggers auto-download.

Linux ARM64 skips this prompt and always auto-downloads the self-built portable build (no widely-distributed standalone binary exists).

### Model weights

Weights auto-download from HuggingFace on first launch into `models/`:
- `models/sam3dbody/` — SAM 3D Body + MHR weights (~3.5 GB, `jetjodh/sam-3d-body-dinov3`)
- `models/sam3/` — SAM3 weights (`facebook/sam3`; requires `hf auth login` beforehand)

## 🚀 Running

### Windows

```cmd
run.cmd
```

### Linux

```bash
./run.sh
```

On startup the launcher prints the URLs to open in your browser (works from this PC and from other PCs on the same LAN):

```
Access URL:
  http://127.0.0.1:8766       (this PC)
  http://192.168.10.121:8766  (LAN)
```

- **Auto port fallback**: if the default 8765 is taken, the next free port is picked automatically.
- **LAN-accessible by default**: the server binds to `0.0.0.0`. Set `SAM3DBODY_HOST=127.0.0.1` to restrict to localhost.
- **Pin a port**: set `SAM3DBODY_PORT=9000` (or any other).

```cmd
set SAM3DBODY_HOST=127.0.0.1
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

[blender]
exe_path =                        ; absolute path to blender(.exe) — written by setup
```

Settings are hot-reloaded per request — no server restart needed.

### How the Blender executable is resolved

`setup.cmd` / `setup.sh` writes your chosen (or auto-downloaded) path into `config.ini`'s `[blender] exe_path`. If you want to swap Blender without re-running setup, edit that value directly.

Resolution order:

1. `SAM3DBODY_BLENDER_EXE` environment variable (escape hatch for explicit overrides)
2. `[blender] exe_path` in `config.ini`
3. Bundled portable Blender, if present
   - Windows: `blender41-portable/blender.exe`
   - Linux x86_64: `blender41-portable/blender`
   - Linux aarch64: `ARM_blender41-portable/bin/blender`
3. `blender` / `blender.exe` on `PATH`

## 📝 License

This project uses a **multi-license layout** (see root [`LICENSE`](LICENSE)).

| Component | License | Scope |
|---|---|---|
| **Wrapper code** | **MIT License** (Copyright (c) 2025 Andrea Pozzetti) | standalone WebUI integration code |
| **SAM 3D Body** | **SAM License** (Meta) | `src/sam3dbody_app/core/sam_3d_body/` (vendored) |
| **MHR (Momentum Human Rig)** | **Apache License 2.0** (Meta) | `mhr_model.pt` + topology-derived data |
| **SAM3 utility** | **MIT License** (Wouter Verweirder) | `src/sam3dbody_app/core/sam3/` (vendored) |

### Using this project

- ✅ The wrapper code is freely usable / modifiable / redistributable under MIT (commercial OK)
- ✅ SAM 3D Body is usable for both research and commercial purposes under the SAM License
- ✅ MHR and any data authored against its topology (blend-shape deltas, region JSONs) are commercially usable under Apache 2.0
- ⚠️ When redistributing, include **LICENSE-MIT-SAM3DBody / LICENSE-SAM / LICENSE-MHR / NOTICE-MHR / LICENSE-MIT-comfyui_sam3**
- ⚠️ Blend shapes authored on MHR topology by third parties become MHR derivative works (Apache 2.0) — keep the MHR attribution with any shipped deltas / meshes
- ⚠️ When publishing work that uses SAM 3D Body (e.g. papers), acknowledge it per the SAM License

All attribution and full license texts live in [`docs/licenses/THIRD_PARTY_NOTICES.md`](docs/licenses/THIRD_PARTY_NOTICES.md).

## 🙏 Credits

- **SAM 3D Body**: Meta AI / facebookresearch ([paper](https://ai.meta.com/research/publications/sam-3d-body-robust-full-body-human-mesh-recovery/))
- **Momentum Human Rig (MHR)**: Meta Platforms, Inc.
- **SAM3 (Segment Anything 3)**: Meta AI / <https://huggingface.co/facebook/sam3>
- **PozzettiAndrea/ComfyUI-SAM3DBody** (wrapper code MIT copyright holder): [@PozzettiAndrea](https://github.com/PozzettiAndrea)
- **comfyui_sam3**: [@wouterverweirder](https://github.com/wouterverweirder)

## 🗣 Community / Issues

- Issues / PRs for the standalone WebUI itself go here in this repository.
- For SAM 3D Body / MHR discussion, see the upstream [PozzettiAndrea/ComfyUI-SAM3DBody Discussions](https://github.com/PozzettiAndrea/ComfyUI-SAM3DBody/discussions) and the [Comfy3D Discord](https://discord.gg/bcdQCUjnHE).
