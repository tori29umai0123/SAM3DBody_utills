# Body Utils Standalone WebUI

**Language:** 日本語 / [English](README.en.md)

ComfyUI なしで、単一画像または動画から rig 付き 3D キャラクターとモーション FBX / BVH を生成する FastAPI + Three.js ベースの standalone WebUI です。

## 概要

- 画像タブ: BiRefNet で前景マスクを作成し、ポーズ推定後に rigged FBX または 1 フレーム BVH を出力
- 動画タブ: フレームごとにモーションを推定し、animated FBX または全フレーム BVH を出力
- Character Make タブ: 体型、骨長、blendshape を調整して preset JSON を保存
- Preset Admin タブ: preset pack の切り替えと、編集済み FBX からの blendshape データ再構築

## 機能

### 画像

- 画像を入力し、推定したポーズからリターゲット可能な rig を構築します。
- ポーズ編集、体型変更、lean 補正は FBX / BVH 出力へ反映されます。

### 動画

- 動画を入力し、モーションをフレーム単位で抽出し、選択中のキャラクター rig に焼き込みます。
- `root_motion_mode`, `bbox thr`, `fps`, `stride`, `max frames` を調整できます。
- 現在の animated FBX を全フレーム BVH に変換できます。

### キャラメイク

- UIで確認しながらキャラクターの体形を設定できます
- 設定したキャラクターはjsonとして保存されます。SAM3DBody_utills/presets/default/chara_settings_presetsに追加すると読みこまれますし、ブラウザからjsonをD＆Dすることもできます

### Preset Admin

- 開発者向けの機能です。Blenderで作成したブレンドシェイプを追加したり色々できます。

## 動作要件

| 項目 | バージョン |
|---|---|
| OS | Windows 11 / Linux (x86_64, aarch64) |
| Python | 3.11 |
| PyTorch | x86_64 / Windows: 2.10.0+cu128 |
| CUDA | x86_64 / Windows: 12.8 |
| GPU | NVIDIA GPU 推奨 |
| Blender | 4.1.1 |
| [uv](https://docs.astral.sh/uv/) | setup に必要 |

推論時のモデル重みは GPU 上に常駐します。CPU でも動作しますが低速です。

## セットアップ

先に [uv](https://docs.astral.sh/uv/) をインストールしてください。

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

setup 中に `.venv` の再作成有無を選べます。Blender 4.1 以上の既存パスを指定するか、portable 版を自動取得できます。

## 起動

### Windows

```cmd
run.cmd
```

### Linux

```bash
./run.sh
```

起動時にローカル用と LAN 用の URL が表示されます。既定ポートが使用中なら、次の空きポートへ自動で切り替わります。

## 設定

`config.ini` はリクエストごとに hot-reload されます。

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

Blender 実行ファイルの解決順:

1. `SAM3DBODY_BLENDER_EXE`
2. `config.ini` の `[blender] exe_path`
3. 同梱の portable Blender
4. `PATH` 上の `blender` / `blender.exe`

## License

現在の配布物に関するライセンス情報は、ルートの [`LICENSE`](LICENSE) と同梱の third-party notices を参照してください。

## Community / Issues

- この standalone WebUI への issue / PR はこのリポジトリに送ってください。
