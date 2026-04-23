# Third-Party Notices

`sam3dbody-standalone` (`E:\SAM3DBody_utills\`) は以下のサードパーティのソフトウェア・モデル重み・データを再配布 / 参照しています。各ライセンスの原文は同じ `docs/licenses/` ディレクトリに同梱しています。

---

## 1. ComfyUI-SAM3DBody_utills (GPL v3 upstream fork)

- Upstream: <https://github.com/tori29umai0123/ComfyUI-SAM3DBody_utills>
- ライセンス: **GNU General Public License v3.0** (ルート `LICENSE` を参照)
- 本プロジェクトのバックエンド (SAM 3D Body / MHR ランタイム, tools/, presets/ 構造, Blender subprocess 連携) は
  このフォークから派生しています。
- GPL v3 の要件に従い、本プロジェクト全体を **GPL v3 で再配布** します。

Upstream fork 内部の多ライセンス構造も継承しています:

### 1a. Wrapper code — MIT License

- 対象: ComfyUI 連携コード (ノード、UI、install スクリプト)
- Copyright (c) 2025 Andrea Pozzetti
- ライセンス全文: [`LICENSE-MIT-SAM3DBody`](LICENSE-MIT-SAM3DBody)
- さらにその元となる: <https://github.com/PozzettiAndrea/ComfyUI-SAM3DBody>

### 1b. SAM 3D Body — SAM License (Meta Platforms)

- Upstream: <https://github.com/facebookresearch/sam-3d-body>
- 重み: <https://huggingface.co/jetjodh/sam-3d-body-dinov3>
- Copyright (c) Meta Platforms, Inc. and affiliates
- ライセンス全文: [`LICENSE-SAM`](LICENSE-SAM)
- 本プロジェクトの `src/sam3dbody_app/core/sam_3d_body/` は SAM 3D Body の vendored copy です。

### 1c. Momentum Human Rig (MHR) — Apache License 2.0

- モデル資産: `mhr_model.pt` および MHR topology / blend-shape
- Copyright (c) Meta Platforms, Inc. and affiliates
- ライセンス全文: [`LICENSE-MHR`](LICENSE-MHR)
- 帰属表記: [`NOTICE-MHR`](NOTICE-MHR)
- 本プロジェクトの `presets/default/face_blendshapes.npz` など MHR topology から派生したデータは
  Apache 2.0 を継承します。

---

## 2. comfyui_sam3 (SAM3 person mask utility) — MIT License

- Upstream: ComfyUI SAM3 custom node (`C:\ComfyUI\custom_nodes\comfyui_sam3`)
- Copyright (c) 2025 Wouter Verweirder
- ライセンス全文: [`LICENSE-MIT-comfyui_sam3`](LICENSE-MIT-comfyui_sam3)
- 本プロジェクトは SAM3 人物マスク前処理のロジックを参考にしています。
- SAM3 モデル本体 (`facebook/sam3`) は Meta のライセンスに従います: <https://huggingface.co/facebook/sam3>

---

## ライセンス適合性について

GPL v3 (コピーレフト) が最も強い制約なので、**本プロジェクト全体は GPL v3 で配布** します。
MIT / Apache-2.0 / SAM License のコードや重みは、それぞれ帰属表記を残したまま
GPL v3 ツリーの一部として再配布されます (GPL v3 との互換性:
MIT / Apache-2.0 は互換、SAM License は Meta の研究ライセンスで非独占・商用可)。

再配布する場合は最低限以下を同梱してください:

- ルートの `LICENSE` (GPL v3)
- `docs/licenses/LICENSE-MIT-SAM3DBody`
- `docs/licenses/LICENSE-MIT-comfyui_sam3`
- `docs/licenses/LICENSE-SAM`
- `docs/licenses/LICENSE-MHR`
- `docs/licenses/NOTICE-MHR`
- 本ファイル (`THIRD_PARTY_NOTICES.md`)
