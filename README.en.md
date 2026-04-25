# Body Utils Standalone WebUI

**Language:** [日本語](README.md) / English

A standalone FastAPI + Three.js web app for turning a single image or video into a rigged 3D character and motion FBX / BVH without ComfyUI.

## Overview

- Image tab: create a foreground mask with BiRefNet, estimate pose, and export a rigged FBX or single-frame BVH.
- Video tab: estimate motion per frame and export an animated FBX or full-length BVH.
- Character Make tab: edit body shape, bone lengths, and blendshape sliders, then save a preset JSON.
- Preset Admin tab: switch preset packs and rebuild blendshape data from an edited FBX.

## Features

### Image

- BiRefNet masks a person or mascot-like foreground subject.
- Transparent PNGs are composited onto white before inference.
- The app builds a retargetable rig from the estimated pose.
- Pose edits, body shape changes, and lean correction are baked into FBX / BVH export.

### Video

- Motion is extracted frame by frame and baked onto the selected character rig.
- `root_motion_mode`, `bbox thr`, `fps`, `stride`, and `max frames` can be adjusted.
- The current animated FBX can be converted to full-length BVH.

### Presets

- Character presets live under `presets/<pack>/chara_settings_presets/`.
- Existing packs that follow the current `presets/<pack>/` layout can be reused as-is.
- Blendshape delta data can be rebuilt from an edited FBX in the Preset Admin tab.

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
