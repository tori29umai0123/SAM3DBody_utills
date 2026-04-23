# Third-Party Notices

`sam3dbody-standalone` (`E:\SAM3DBody_utills\`) は以下のサードパーティのソフトウェア・モデル重み・データを再配布 / 参照しています。各ライセンスの原文は同じ `docs/licenses/` ディレクトリに同梱しています。

ライセンス構成:

| 区分 | 対象 | ライセンス | 著作権者 |
|---|---|---|---|
| **Wrapper code** | `src/sam3dbody_app/` (vendored sub-dirs を除く), `tools/`, `web/`, `setup.py`, `run.cmd` / `run.sh`, `pyproject.toml`, `config.ini` など standalone WebUI の統合コード全般 | **MIT License** ([LICENSE-MIT-SAM3DBody](LICENSE-MIT-SAM3DBody)) | Copyright (c) 2025 Andrea Pozzetti |
| **SAM 3D Body** | `src/sam3dbody_app/core/sam_3d_body/` のベンダードライブラリ | **SAM License** ([LICENSE-SAM](LICENSE-SAM)) | Copyright (c) Meta Platforms, Inc. and affiliates |
| **MHR** | `mhr_model.pt` アセット、および MHR トポロジ派生データ (`presets/default/face_blendshapes.npz`、`presets/default/*_vertices.json`) | **Apache License 2.0** ([LICENSE-MHR](LICENSE-MHR) / [NOTICE-MHR](NOTICE-MHR)) | Copyright (c) Meta Platforms, Inc. and affiliates |
| **SAM3 (person mask utility)** | `src/sam3dbody_app/core/sam3/` のベンダードライブラリ | **MIT License** ([LICENSE-MIT-comfyui_sam3](LICENSE-MIT-comfyui_sam3)) | Copyright (c) 2025 Wouter Verweirder |

---

## 1. Wrapper code — MIT License

- Upstream: <https://github.com/PozzettiAndrea/ComfyUI-SAM3DBody>
- Copyright (c) 2025 Andrea Pozzetti
- ライセンス全文: [`LICENSE-MIT-SAM3DBody`](LICENSE-MIT-SAM3DBody)

ComfyUI カスタムノードから standalone FastAPI + Three.js WebUI として再パッケージする過程で、ノード層は外し、サービス・ルータ・フロントエンド・Blender subprocess スクリプトなど WebUI 統合コードを新規に書き起こしています。オリジナルの MIT 著作権表記はそのまま継承します。

## 2. SAM 3D Body — SAM License (Meta Platforms)

- Upstream: <https://github.com/facebookresearch/sam-3d-body>
- 重み: <https://huggingface.co/jetjodh/sam-3d-body-dinov3>
- Copyright (c) Meta Platforms, Inc. and affiliates
- ライセンス全文: [`LICENSE-SAM`](LICENSE-SAM)

本プロジェクトの `src/sam3dbody_app/core/sam_3d_body/` は SAM 3D Body の vendored copy です。

使用条件 (要約):
- 再配布時に SAM License 同梱必須
- 論文等で使用する場合は謝辞を明記
- Trade Controls 遵守

## 3. Momentum Human Rig (MHR) — Apache License 2.0

- Upstream: <https://github.com/facebookresearch/MHR>
- モデル資産: `mhr_model.pt` (MHR v1.0.0 release から自動 DL)
- MHR トポロジから派生した: `presets/default/face_blendshapes.npz`、`presets/default/*_vertices.json`
- Copyright (c) Meta Platforms, Inc. and affiliates
- ライセンス全文: [`LICENSE-MHR`](LICENSE-MHR)
- 帰属表記: [`NOTICE-MHR`](NOTICE-MHR)

MHR メッシュトポロジを前提に作成したブレンドシェイプ delta データは、Apache 2.0 の派生物として同ライセンスを継承します。再配布時は `LICENSE-MHR` / `NOTICE-MHR` を同梱し、MHR への帰属を維持してください。

## 4. comfyui_sam3 (SAM3 person mask utility) — MIT License

- Upstream: <https://github.com/wouterverweirder/comfyui-sam3>
- Copyright (c) 2025 Wouter Verweirder
- ライセンス全文: [`LICENSE-MIT-comfyui_sam3`](LICENSE-MIT-comfyui_sam3)

`src/sam3dbody_app/core/sam3/` は SAM3 (Meta Segment Anything 3) による人物マスク抽出ユーティリティの vendored copy です。SAM3 モデル本体 (`facebook/sam3`) は Meta のライセンスに従います: <https://huggingface.co/facebook/sam3>

---

## 再配布時に同梱すべきファイル

本プロジェクトを再配布する場合、最低限以下を同梱してください:

- ルートの `LICENSE` (multi-license サマリ)
- `docs/licenses/LICENSE-MIT-SAM3DBody`
- `docs/licenses/LICENSE-MIT-comfyui_sam3`
- `docs/licenses/LICENSE-SAM`
- `docs/licenses/LICENSE-MHR`
- `docs/licenses/NOTICE-MHR`
- 本ファイル (`THIRD_PARTY_NOTICES.md`)

## ライセンス適合性について

- MIT と Apache 2.0 は相互に互換、SAM License は Meta の研究ライセンスで商用利用可 — いずれも対立せず共存します。
- **商用利用 OK**: MIT / Apache 2.0 / SAM License いずれも商用を許可しています。
- 成果物 (レンダ画像、出力 FBX) の利用には WebUI 側のライセンス制約はかかりません (MIT / Apache / SAM のいずれも生成物の自由利用を妨げません)。
