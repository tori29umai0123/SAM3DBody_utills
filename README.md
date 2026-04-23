# SAM3DBody Standalone WebUI

**Language:** 🇯🇵 日本語 (current) ・ [🇬🇧 English](README.en.md)

**1 枚の画像 / 動画から、リグ付き 3D キャラクターとモーション FBX を作る** ための Web UI アプリケーション。ComfyUI を介さずに FastAPI + Three.js で動くスタンドアロンサーバーとして動作します。

- 画像タブ: 画像 → SAM3 人物マスク → SAM 3D Body ポーズ推定 → 任意体型 3D 素体レンダ → リグ付き FBX 書き出し
- 動画タブ: 動画 → 各フレームのポーズ推定 → モーション付き FBX 書き出し (Blender subprocess 経由)
- 体型 (PCA 9 軸)・ボーン長・ブレンドシェイプ (約 20 種) をスライダーで自由に調整
- プリセット pack によるブレンドシェイプ定義の切替・配布に対応

## 🧬 派生元のプロジェクト

このリポジトリは以下の 2 つの既存プロジェクトの**組み合わせ・スタンドアロン化**として作られています。ComfyUI カスタムノード実装を外して単独の WebUI として動かせるようにしたものです。

| 派生元 | 役割 | ライセンス |
|---|---|---|
| **[tori29umai0123/ComfyUI-SAM3DBody_utills](https://github.com/tori29umai0123/ComfyUI-SAM3DBody_utills)** | ベース: SAM 3D Body + MHR のランタイム、blendshape/bone スケール/preset pack の全ロジック、Blender FBX 出力パイプライン (`tools/build_rigged_fbx.py` / `tools/build_animated_fbx.py`) | **GPL v3** |
| ├ [PozzettiAndrea/ComfyUI-SAM3DBody](https://github.com/PozzettiAndrea/ComfyUI-SAM3DBody) | さらにその元コード (オリジナルの ComfyUI カスタムノード) | MIT |
| ├ [facebookresearch/sam-3d-body](https://github.com/facebookresearch/sam-3d-body) | SAM 3D Body 本体 (`src/sam3dbody_app/core/sam_3d_body/` に vendor 済み) | SAM License (Meta) |
| └ MHR (Momentum Human Rig) | パラメトリック人体モデル (`mhr_model.pt` + topology) | Apache 2.0 (Meta) |
| **[comfyui_sam3](https://github.com/wouterverweirder/comfyui-sam3)** (参照実装) | SAM3 (Meta Segment Anything 3) による人物マスク抽出ロジック。本プロジェクトでは `src/sam3dbody_app/core/sam3/` に vendor 済み | MIT (Copyright (c) 2025 Wouter Verweirder) |
| └ [facebook/sam3](https://huggingface.co/facebook/sam3) | SAM3 モデル重み本体 | Meta ライセンス |

ライセンスの詳細と帰属表記は [`docs/licenses/THIRD_PARTY_NOTICES.md`](docs/licenses/THIRD_PARTY_NOTICES.md) を参照してください。

## ✨ できること (タブごとの機能)

Web UI は上部に **4 つのタブ** を持ち、画像処理・動画処理・キャラクター作成・pack 管理を切り替えて使えます。

### 📷 1. 画像タブ

1 枚の画像から、任意の体型の 3D 素体にポーズを当てはめてレンダリング・FBX 書き出しするタブ。

- 画像アップロード → SAM3 で人物領域をマスキング (`text_prompt = "person"` がデフォルト)
- SAM 3D Body で全身ポーズを推定
- 下段の **Character パネル** で preset を選択するか、既存のキャラクター JSON をドロップして体型を指定
- Three.js でリアルタイムにレンダリングプレビュー
- `FBX をダウンロード` ボタン押下時のみ Blender subprocess (`tools/build_rigged_fbx.py`) が起動して rigged FBX を生成 (Blender 必須)

### 🎬 2. 動画タブ

動画から連続モーションを抽出して、アニメーション FBX として書き出すタブ。

- 動画アップロード → 各フレームを SAM 3D Body に通してジョイント回転を推定
- 下段の **Character パネル** で preset を選択すると、その体型でリグ付けされたキャラクターに全フレームがキーフレームとしてベイクされる
- `root_motion_mode` で地面ロック補正を選択 (`auto_ground_lock` / `free` / `xz_only`)
- `bbox thr` / `fps` / `stride` / `max frames` などの推定パラメータを詳細調整
- Blender subprocess (`tools/build_animated_fbx.py`) でアニメーション FBX を書き出し (Blender 必須)
- Unity / Unreal にドロップすればそのまま Humanoid リターゲット対象として使える
- モーション推定後に preset を切り替えると、**キャラを差し替えた FBX が自動再生される**

### 🧑‍🎨 3. キャラメイクタブ (新しい preset を作る)

スライダーで体型を作り込んで、**新しいキャラクター preset を JSON として保存**するタブ。

- MHR ニュートラル T-pose の素体に対して以下のスライダーで体型を調整:
  - **Body (PCA 9 軸)**: `body_fat` / `body_muscle` / `body_limb_girth` / `body_chest_shoulder` / `body_waist_hip` など
  - **Bone length (4 チェーン)**: `bone_torso` / `bone_neck` / `bone_arm` / `bone_leg`
  - **Blendshapes (約 20 種)**: `bs_face_big` / `bs_neck_thick` / `bs_breast_full` / `bs_MuscleScale` など
- `Reset` で全スライダーをニュートラルに戻す
- `json をダウンロード` で現在の体型を JSON として保存 → `presets/<pack>/chara_settings_presets/` に置けば画像 / 動画タブの preset プルダウンに現れる
- 作った preset はそのまま画像タブ・動画タブで使い回せる

### ⚙ 4. Preset Admin タブ (pack 切替と Blendshape 更新)

preset pack の管理と、Blender で編集した FBX からブレンドシェイプを更新するタブ。`config.ini` の `[features] preset_pack_admin = true` で有効化。

**Pack 切替・クローン・削除:**
- preset pack = `presets/<pack>/` 配下のディレクトリ一式 (ブレンドシェイプ npz + 頂点マップ JSON + キャラクタープリセット群)
- プルダウンから active pack を選択して `Switch` で切替
- `Clone` で現在の pack を別名で複製
- `Delete selected` で未使用 pack を削除
- 上流 `ComfyUI-SAM3DBody_utills` と **互換性のある pack 構造** を維持しているので、既存 pack をそのまま持ってこられる

**FBX Rebuild (Blendshape 更新):**
- Blender で `tools/bone_backup/all_parts_bs.fbx` を開き、シェイプキーを追加・編集
- 編集済み FBX をドロップして `Rebuild` を押すと:
  - `face_blendshapes.npz` (ブレンドシェイプ delta 本体) が再生成
  - `<obj>_vertices.json` (FBX 頂点 → MHR 頂点マップ) が再生成
  - 新しく追加したシェイプキーが**自動的にキャラメイクタブのスライダー一覧に現れる** (コード変更不要)
- 内部で `tools/extract_face_blendshapes.py` と `tools/rebuild_vertex_jsons.py` を順に実行

## 🔧 動作環境

| 項目 | バージョン |
|---|---|
| OS | Windows 11 / Linux (x86_64, aarch64) |
| Python | 3.11 |
| PyTorch | x86_64 / Windows: 2.10.0+cu128<br>aarch64 (GB10 等 sm_121): 2.13.0.dev (nightly) + cu130 |
| CUDA | x86_64 / Windows: 12.8<br>aarch64: 13.0 (Blackwell Ultra sm_121 公式サポート) |
| GPU | NVIDIA GPU (VRAM 4 GB 以上を推奨、8 GB で快適)<br>DGX Spark (GB10 / sm_121) 対応済み |
| Blender | 4.1.1 (手持ちのパスを setup で指定するか、未入力ならポータブル版が自動 DL される) |
| [uv](https://docs.astral.sh/uv/) | setup の前提。未インストールなら公式サイトから入れてください。 |

SAM 3D Body 重みは約 3.4 GB を GPU に常駐。CPU でも動きますが大幅に遅くなります。

> ℹ️ **aarch64 (NVIDIA GB10 / DGX Spark) について**
> GB10 は compute capability 12.1 (sm_121) で、PyTorch 2.10 (cu128) の NVRTC は sm_120 までしか対応していません。そのため aarch64 環境のみ自動で nightly cu130 wheel (sm_121 対応) を解決します (`pyproject.toml` で platform_machine 条件分岐)。x86_64 / Windows は cu128 stable のまま。

## 📦 セットアップ

事前に [uv](https://docs.astral.sh/uv/) を入れておいてください。

### Windows

```cmd
cd E:\SAM3DBody_utills
setup.cmd
```

またはエクスプローラーで `setup.cmd` をダブルクリック。

### Linux / macOS

```bash
cd /path/to/SAM3DBody_utills
./setup.sh
```

### 実行中に聞かれる2つのプロンプト

**1. `.venv` を作り直すかどうか**

```
Delete .venv and reinstall all dependencies from scratch? [y/N]:
```

- Enter (既定 `N`) または `n` → 既存 `.venv` を温存、`uv sync` だけ走らせて短時間で終了
- `y` → `.venv` を削除して完全再作成（torch 等の再 DL で数分～）
- 初回 setup（`.venv` が無い時）はプロンプトを飛ばして強制作成

**2. Blender パス**

```
Blender path (ENTER to auto-download):
```

- **手持ちの Blender 4.1+ を使う**: フルパスを入力して Enter（ダブルクォート付きでも可）
  - Windows 例: `C:\Program Files\Blender Foundation\Blender 4.1\blender.exe`
  - Linux 例:   `/opt/blender-4.1/blender`
- **自動DLしたい**: 何も入力せずそのまま Enter（ポータブル版 Blender 4.1.1 が落ちてきて `blender41-portable/` に展開、約400MB）
- `n` / `skip` / `auto` と入力しても自動 DL に分岐

Linux ARM64 は独立バイナリが無いため、プロンプトは出ず自動 DL 固定です。

### モデル重みの配置

初回起動時に HuggingFace から自動ダウンロードされ `models/` 配下に配置されます:
- `models/sam3dbody/` — SAM 3D Body + MHR 重み (約 3.5 GB, `jetjodh/sam-3d-body-dinov3`)
- `models/sam3/` — SAM3 重み (`facebook/sam3`, 事前に `hf auth login` が必要)

手動配置する場合:

```
E:\SAM3DBody_utills\models\
├── sam3dbody\
│   ├── model.ckpt
│   ├── model_config.yaml
│   └── assets\mhr_model.pt
└── sam3\
    └── sam3.pt
```

## 🚀 起動

### Windows

```cmd
run.cmd
```

### Linux / macOS

```bash
./run.sh
```

起動すると次のようなアクセス URL が表示されます。このPCからでも LAN 内の他 PC / スマホからでも同じページを開けます。

```
Access URL:
  http://127.0.0.1:8766       (this PC)
  http://192.168.10.121:8766  (LAN)
```

- **ポート自動回避**: 既定 8765 が使用中なら隣の空きポートに自動で逃げます。
- **LAN 公開既定**: 既定でホストは `0.0.0.0` にバインド。自分のPCのみに制限したい時は `SAM3DBODY_HOST=127.0.0.1` を指定。
- **ポート固定**: `SAM3DBODY_PORT=9000` のように環境変数で指定可能。

```cmd
set SAM3DBODY_HOST=127.0.0.1
set SAM3DBODY_PORT=9000
run.cmd
```

## ⚙ 設定 (`config.ini`)

```ini
[active]
pack = default                    ; 現在アクティブな preset pack

[features]
preset_pack_admin = false         ; true で preset pack 管理タブを表示
debug = false                     ; true で Health パネル表示

[sam3]
use_sam3 = true                   ; SAM3 による人物マスク抽出を有効化
text_prompt = person              ; SAM3 のテキストプロンプト
confidence_threshold = 0.5
min_width_pixels = 0
min_height_pixels = 0

[blender]
exe_path =                        ; Blender 実行ファイルの絶対パス (setup が自動で書く)
```

UI を再読み込みすれば設定はホットリロードされます (リクエストごとに読み直し)。

### Blender 実行ファイルの解決

通常は `setup.cmd` / `setup.sh` のプロンプトで指定（または自動 DL）した値が `[blender] exe_path` に書き込まれ、そのまま使われます。Blender を手で差し替えたい場合は `config.ini` の `exe_path =` を直接編集してもOK。

解決の優先順:

1. 環境変数 `SAM3DBODY_BLENDER_EXE` (エスケープハッチ、明示指定したいとき用)
2. `config.ini` の `[blender] exe_path`
3. プロジェクト同梱のポータブル Blender（存在すれば）
   - Windows: `blender41-portable/blender.exe`
   - Linux x86_64: `blender41-portable/blender`
   - Linux aarch64: `ARM_blender41-portable/bin/blender`
4. `PATH` 上の `blender` / `blender.exe`

## 📂 プロジェクト構成

```
SAM3DBody_utills/
├── LICENSE                         ← GPL v3 (上流から継承)
├── README.md                       ← このファイル (日本語)
├── README.en.md                    ← English version
├── config.ini
├── pyproject.toml
├── run.cmd / run.sh                ← uvicorn 起動 (ポート自動回避 + LAN URL 表示)
├── setup.cmd / setup.sh            ← 薄いラッパ (uv で Python 3.11 を起動して setup.py に渡す)
├── setup.py                        ← 本体: リセット → uv venv/sync → Blender パス設定
├── wheels/                         ← 再配布用 CUDA wheels
├── blender41-portable/             ← setup が配置するポータブル Blender (Win / Linux x86_64, 自動 DL)
├── ARM_blender41-portable/         ← setup が配置するポータブル Blender (Linux aarch64, 自動 DL)
├── models/                         ← SAM 3D Body / SAM3 重み (自動 DL)
├── presets/
│   └── default/                    ← 既定 preset pack (上流と互換)
│       ├── face_blendshapes.npz
│       ├── mhr_reference_vertices.json
│       └── chara_settings_presets/
├── src/sam3dbody_app/
│   ├── main.py                     ← FastAPI エントリポイント
│   ├── core/
│   │   ├── sam_3d_body/            ← SAM 3D Body vendor (SAM License)
│   │   └── sam3/                   ← SAM3 vendor (Meta ライセンス)
│   ├── routers/                    ← /api/* 各エンドポイント
│   ├── services/                   ← Blender 連携 / renderer / motion session
│   └── ...
├── web/                            ← フロントエンド (Three.js + Vite 不要の素 JS)
│   ├── index.html
│   └── static/app.js
├── tools/                          ← Blender ヘッドレス subprocess スクリプト
│   ├── build_rigged_fbx.py
│   ├── build_animated_fbx.py
│   └── extract_face_blendshapes.py
└── docs/licenses/                  ← サブライセンス全文
```

## 📝 ライセンス

本プロジェクトは **GNU General Public License v3.0** で配布されます (上流 `tori29umai0123/ComfyUI-SAM3DBody_utills` から継承)。ルートの [`LICENSE`](LICENSE) を参照してください。

内包するサードパーティのライセンス:

- **ComfyUI-SAM3DBody_utills wrapper**: MIT (Andrea Pozzetti)
- **SAM 3D Body** (`src/sam3dbody_app/core/sam_3d_body/`): SAM License (Meta)
- **MHR (Momentum Human Rig)** (`mhr_model.pt` + topology + `face_blendshapes.npz`): Apache 2.0 (Meta)
- **comfyui_sam3** (SAM3 マスク抽出ロジックの参考実装): MIT (Wouter Verweirder)
- **SAM3** (重み): Meta ライセンス

帰属表記とライセンス全文は [`docs/licenses/THIRD_PARTY_NOTICES.md`](docs/licenses/THIRD_PARTY_NOTICES.md) にまとまっています。再配布時は GPL v3 の条件に従い、**ソースコードと全ライセンスファイルを同梱**してください。

## 🙏 Credits

- **SAM 3D Body**: Meta AI / facebookresearch ([paper](https://ai.meta.com/research/publications/sam-3d-body-robust-full-body-human-mesh-recovery/))
- **Momentum Human Rig (MHR)**: Meta Platforms, Inc.
- **SAM3 (Segment Anything 3)**: Meta AI / <https://huggingface.co/facebook/sam3>
- **ComfyUI-SAM3DBody_utills**: [@tori29umai0123](https://github.com/tori29umai0123)
- **PozzettiAndrea/ComfyUI-SAM3DBody**: [@PozzettiAndrea](https://github.com/PozzettiAndrea)
- **comfyui_sam3**: [@wouterverweirder](https://github.com/wouterverweirder)

## 🗣 Community / Issues

- 本プロジェクト (standalone WebUI) への issue / PR は本リポジトリへ
- SAM 3D Body / MHR / ComfyUI 版の議論は上流 [PozzettiAndrea/ComfyUI-SAM3DBody の Discussions](https://github.com/PozzettiAndrea/ComfyUI-SAM3DBody/discussions) や [tori29umai0123/ComfyUI-SAM3DBody_utills の Issues](https://github.com/tori29umai0123/ComfyUI-SAM3DBody_utills/issues) が参考になります
