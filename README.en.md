# Body Utils Standalone WebUI

**Language:** [Japanese](README.md) / English

A standalone FastAPI + Three.js web app for turning a single image or video into a rigged 3D character and motion FBX / BVH without ComfyUI.

## Overview

- Image tab: load an image, estimate pose, and export a rigged FBX or single-frame BVH.
- Video tab: load a video, estimate motion per frame, and export an animated FBX or full-length BVH.
- Character Make tab: adjust body shape in the UI and save character settings as preset JSON.
- Preset Admin tab: developer-oriented tools for adding blendshapes and managing preset data.

## Features

### Image

- The app builds a retargetable rig from the estimated pose.
- Pose edits, body shape changes, and lean correction are baked into FBX / BVH export.
- **Hand-image overrides**:
  - Below the main input there are drag-and-drop slots for **Left hand image** / **Right hand image**, each with a "Mirror" button.
  - Mirror flips the loaded image at the pixel level on a canvas so the bytes sent to the server match what you see.
  - When you provide a hand image and press "Run pose estimation", the server runs a hand-only decoder pass on each crop and overrides the body's `hand_pose_params[:54]` (left) / `[54:]` (right). Wrist orientation from the body decoder is preserved.
- **Range-capture mode** (renamed from "Save PNG"):
  - The viewport's top-left **"Range capture"** button enters the mode. The label becomes **"Finish capture"** and three more buttons (`Capture` / `Background color` / `Reset`) plus a red translucent drag-and-drop overlay appear.
  - While in the mode, the sidebar and tab nav are pointer-event-locked — only those buttons and the drag rectangle are interactive.
  - **Capture**: writes a PNG of the selected rectangle (or the full viewport if no range is set), painted onto the chosen background color (default white).
  - **Background color**: a color picker for the saved PNG's background.
  - **Reset**: clears just the red rectangle.
  - **Finish capture**: leaves the mode — the auxiliary buttons and the red overlay disappear, the entry button reverts to "Range capture", and the saved range is cleared.

### Video

- A video is processed frame by frame and baked onto the selected character rig.
- `root_motion_mode`, `bbox thr`, `fps`, `stride`, and `max frames` can be adjusted.
- The current animated FBX can be converted to full-length BVH.

### Character Make

- You can adjust the character body shape while previewing it in the UI.
- Saved character settings are stored as JSON. They are loaded automatically if placed in `SAM3DBody_utills/presets/default/chara_settings_presets`, and you can also drag and drop a JSON file from the browser.

### Preset Admin

- This is a developer-focused area. You can add blendshapes created in Blender and manage related preset data.

## Requirements

| Item | Version |
|---|---|
| OS | Windows 11 / Linux (x86_64, aarch64) |
| Python | 3.11 |
| PyTorch | x86_64 / Windows: 2.10.0+cu128 |
| CUDA | x86_64 / Windows: 12.8 |
| GPU | NVIDIA GPU recommended |
| Blender | 4.1.1 |
| [uv](https://docs.astral.sh/uv/) | Required for setup |

Model weights stay resident on the GPU during inference. CPU inference works, but is slower.

## Setup

Install [uv](https://docs.astral.sh/uv/) first.

### Windows

```cmd
cd E:\body-utils
setup.cmd
```

### Linux

```bash
cd /path/to/body-utils
./setup.sh
```

During setup, you can keep or recreate `.venv`, and you can either point to an existing Blender 4.1+ install or let setup download a portable build.

## Running

### Windows

```cmd
run.cmd
```

### Linux

```bash
./run.sh
```

The launcher prints the local and LAN URLs on startup. If the default port is busy, the next free port is selected automatically.

## Configuration

`config.ini` is hot-reloaded per request.

```ini
[active]
pack = default

[features]
preset_pack_admin = false
debug = false

[segmentation]
enabled = true
backend = birefnet_lite
confidence_threshold = 0.5
min_width_pixels = 0
min_height_pixels = 0

[blender]
exe_path =
```

Blender executable resolution order:

1. `SAM3DBODY_BLENDER_EXE`
2. `[blender] exe_path` in `config.ini`
3. Bundled portable Blender, if present
4. `blender` / `blender.exe` on `PATH`

## License

See the root [`LICENSE`](LICENSE) and any bundled third-party notices for the current project distribution.

## Community / Issues

- Issues and PRs for this standalone WebUI should go to this repository.
