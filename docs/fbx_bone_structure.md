# FBX ボーン構成 仕様書

SAM3DBody Utills が出力する FBX (rigged / animated) のアーマチュア (ボーン) 構造・命名・姿勢・座標系の仕様をまとめたドキュメント。

- 出力コード: `src/sam3dbody_app/services/fbx_export.py` (rigged), `src/sam3dbody_app/services/animated_fbx_export.py` (animated)
- Blender 組立スクリプト: `tools/build_rigged_fbx.py`, `tools/build_animated_fbx.py`

---

## 1. 概要

FBX は以下の 2 種類が書き出される。いずれも Blender をヘッドレスで起動し、Python API 経由で FBX エクスポータに流している。

| 出力 | 用途 | アニメ区間 | スクリプト |
|---|---|---|---|
| `rigged.fbx` | 静止ポーズ付きリグ | frame 1 〜 30 (同一ポーズを両端にキー) | `tools/build_rigged_fbx.py` |
| `animated.fbx` | モーション付きリグ (動画由来) | frame 1 〜 N (N = フレーム数) | `tools/build_animated_fbx.py` |

両者ともに以下は共通:
- アーマチュアオブジェクト名: `SAM3D_Armature` / アーマチュアデータ名: `SAM3D_ArmatureData`
- メッシュオブジェクト名: `SAM3D_Character` / メッシュデータ名: `SAM3D_Mesh`
- メッシュの `parent` はアーマチュア
- メッシュに `ARMATURE` モディファイア (`use_vertex_groups=True`) を付与しリグに追従
- `add_leaf_bones=False` で末端ダミーボーンは作らない

---

## 2. 座標系

内部計算は MHR ネイティブ座標系 (X: 右, Y: 上, Z: 前) で行い、Blender 内では Blender 内部座標系 (X: 右, Y: 奥, Z: 上) に変換して組み立てる。

変換行列 `A`:

```
A = [[1,  0,  0],
     [0,  0, -1],
     [0,  1,  0]]
```

- ベクトル: `v_blender = (v.x, -v.z, v.y)`
- 回転行列: `R_blender = A @ R_mhr @ Aᵀ`

FBX ファイル書き出し時のエクスポータ設定:

| パラメータ | 値 |
|---|---|
| `axis_forward` | `"-Z"` |
| `axis_up` | `"Y"` |
| `global_scale` | `1.0` |
| `apply_unit_scale` | `True` |
| `bake_space_transform` | `False` |

→ ディスクに書き出される FBX は **Y-up / -Z-forward** (Unity / Unreal 互換) となる。

> 注: `bake_space_transform` は意図的に OFF。明示的な `axis_forward`/`axis_up` と組み合わせると軸入れ替えが二重掛けになる不具合が出たため。

---

## 3. 骨格 (アーマチュア) 構造

### 3.1 ジョイント数

MHR モデルの全関節は最大 127。出力時には以下のルールで剪定される (`fbx_export.py` / `animated_fbx_export.py`):

1. LBS ウェイトを持つジョイント (`lbs_weights.sum(axis=0) > 1e-6`) を `keep` としてマーク。
2. そこから親方向へ祖先をすべて `keep` に追加 (親が欠けるとリグが壊れるため)。
3. 残った `kept_idx` のみを書き出し、親 index は `j_remap` で再採番される。

結果として「スキニングに使われている骨と、その親チェーンのみ」が出力される。

### 3.2 親子関係

`joint_parents[j]` に親 index を保持。ルートは `-1`。MHR の元の階層をそのまま保持している (剪定後の採番に再マッピング)。

ルートジョイントは通常 1 個。`animated_fbx` では `parents[j] < 0` を満たす最初の j をルート扱いとしてロケーションキーを打つ。

### 3.3 既知ボーン名

`_KNOWN_JOINT_NAMES` (fbx_export.py:38-46) で主要関節のみ人間可読名を付けている。該当しない関節は `joint_NNN` (NNN は元の MHR index 3 桁ゼロ埋め) となる。

| MHR index | ボーン名 | 部位 |
|---:|---|---|
| 1 | `pelvis` | 骨盤 (ルート近傍) |
| 2 | `thigh_l` | 左大腿 |
| 3 | `calf_l` | 左下腿 |
| 4 | `foot_l` | 左足 |
| 18 | `thigh_r` | 右大腿 |
| 19 | `calf_r` | 右下腿 |
| 20 | `foot_r` | 右足 |
| 35 | `spine_01` | 背骨 1 |
| 36 | `spine_02` | 背骨 2 |
| 37 | `spine_03` | 背骨 3 |
| 38 | `clavicle_r` | 右鎖骨 |
| 39 | `upperarm_r` | 右上腕 |
| 40 | `lowerarm_r` | 右前腕 |
| 42 | `hand_r` | 右手 |
| 74 | `clavicle_l` | 左鎖骨 |
| 75 | `upperarm_l` | 左上腕 |
| 76 | `lowerarm_l` | 左前腕 |
| 78 | `hand_l` | 左手 |
| 110 | `neck_01` | 首 |
| 113 | `head` | 頭 |

上記以外 (指の細かな骨、顔面ジョイントなど) は `joint_041`, `joint_114` … の形で出力される。

### 3.4 チェーン分類 (骨長スケール用)

ボーン長スライダー (`torso` / `neck` / `arm` / `leg`) の適用範囲を決めるカテゴリ。`_compute_bone_chain_categories` (character_shape.py:165) で計算される。

| cat | 対象 | 計算元 |
|---:|---|---|
| 0 | その他 (ルート、顔、手指など) | 既定値 |
| 1 | 胴 | `_TORSO_JOINT_IDS = {1, 34, 35, 36, 37, 110}` |
| 2 | 首 | `_NECK_JOINT_IDS = {113}` |
| 3 | 腕 | `_ARM_BRANCH_IDS = (38, 74)` の**子孫** (枝の根自体は除く) |
| 4 | 脚 | `_LEG_BRANCH_IDS = (2, 18)` の**子孫** (枝の根自体は除く) |

注: 枝の根 (clavicle / thigh 自身) は腕・脚カテゴリから外れる。これは枝の付け根を動かさずに長さスケールを子へ伝播させる設計。

---

## 4. ボーンのレスト姿勢 (rest pose)

`build_*_fbx.py` 内の edit mode でボーンを生成する。

### 4.1 ボーン長

各ボーンの長さは「代表子ジョイントまでの距離」を採用する。子が 1 つならその子、複数あるときは `_pick_chain_child` が「親→自分」の向きに一番揃う子を選ぶ (脊椎・首などが枝分かれで折れないようにするため)。

- ルート (親なし) で子が複数ある場合は最も Z 値が高い子を採用。
- 子がまったく無い (葉) 場合は `DEFAULT_LENGTH = 0.05` (単位: Blender 内部、≒ 5 cm)。

### 4.2 ボーンの回転軸 (rest orientation)

head / tail / roll ではなく `edit_bone.matrix` に 4x4 を直接代入してレスト姿勢を決める。

```
M = R_rest_j.to_4x4()   # MHR → Blender 変換済みの rest world 回転
M.translation = rest_coords[j]
bone.matrix = M
```

`edit_bone.matrix` は現在の bone.length を保ったまま head/tail を張り直すため、必ず length を先に正の値にしてから matrix を書く。

> この設計が重要な理由: Blender が head/tail から導出するデフォルト向きは MHR の rest 回転と一致しないため、ポーズモードでの `pose_bone.rotation_quaternion` がそのズレ分だけ余計に傾く。rest 向きを MHR と揃えることで、後述の「ローカル差分回転」だけで正しい姿勢が出る。

### 4.3 親子接続

親設定は `edit_bones.new()` 後の 2 パス目で `jb.parent = pb` として行う。**`use_connect` は意図的に False** のまま (連結すると head が親 tail に強制的に移動し、レスト位置が壊れるため)。

親→子は空間的に離れていてもよい。FBX でも親子オフセットはリンク変換として保持される。

---

## 5. ポーズ姿勢 (pose mode)

### 5.1 回転

各ポーズボーンに**ローカル差分回転** (local delta) をクォータニオンで書き込む。world の合成回転をそのまま `pose_bone.matrix` に入れると `pose_bone.location` に巨大な値が落ちてしまい、FBX bake 時にリグが破壊されるため、必ずローカル差分で与える。

- ルート (`parents[j] < 0`):
  ```
  delta = R_rest_j.T @ R_posed_j
  ```
- 非ルート:
  ```
  delta = R_rest_j.T @ R_rest_p  @  R_posed_p.T @ R_posed_j
  ```
  (`p` は親 index)

導出:

```
bone_world_posed = parent_world_posed
                   @ (R_rest_p⁻¹ @ R_rest_j)      ← rest link (親→子の相対)
                   @ pose_delta
```
より `pose_delta = (R_rest_j⁻¹ @ R_rest_p) @ (R_posed_p⁻¹ @ R_posed_j)`

### 5.2 位置・スケール

- 非ルートボーンの `location` / `scale` は常に `(0,0,0)` / `(1,1,1)`。
- ルートボーンは `location` にルートモーションのローカル変位を書き込める (animated のみ)。
  ```
  world_delta = mhr_to_blender_vec(frames_root_trans[f])
  local_delta = R_rest_root.T @ world_delta
  root_bone.location = local_delta
  ```
- `rotation_mode` は全ポーズボーンで `'QUATERNION'` に固定。

### 5.3 キーフレーム

| 出力 | キー打ちフレーム | 備考 |
|---|---|---|
| rigged | 1 と 30 の両端 | 同一ポーズを 2 回打ち、Unity 等が 0 長クリップを空と扱うのを回避するため 1 秒の "static pose" クリップを作る |
| animated | 1 〜 N 全フレーム | `bake_anim_force_startend_keying=True` で端点を確実化 |

animated のルート translation はルートモーションが有効なとき全フレームにキーを打つ (Unity のクリップインポータが疎な F-Curve で保持扱いになるのを防ぐため)。

---

## 6. スキニング (LBS)

### 6.1 頂点グループ

各ボーン名と同名の頂点グループをメッシュに作成。LBS ウェイト (`lbs_v_idx`, `lbs_j_idx`, `lbs_weight`) を `vertex_groups[j].add([vi], w, 'REPLACE')` で書き込む。

- 疎表現: 閾値 `1e-5` 以上のウェイトのみパッケージ JSON に含める。
- 剪定で削られたジョイントに紐づくエントリは `j_remap < 0` で捨てる。

### 6.2 メッシュ

- 頂点座標: MHR rest verts を Blender 座標系に変換したもの (ボディ PCA・ボーン長・ブレンドシェイプ適用後の**キャラクタ固有 rest**)。
- 面: MHR の `faces` (三角形インデックス) そのまま。

### 6.3 アーマチュアモディファイア

```python
mod = mesh_obj.modifiers.new(name="Armature", type='ARMATURE')
mod.object = arm_obj
mod.use_vertex_groups = True
```

---

## 7. FBX エクスポータ設定 (共通)

```python
bpy.ops.export_scene.fbx(
    filepath=...,
    use_selection=True,
    object_types={"ARMATURE", "MESH"},
    axis_forward="-Z",
    axis_up="Y",
    global_scale=1.0,
    apply_unit_scale=True,
    bake_space_transform=False,
    add_leaf_bones=False,
    bake_anim=True,
    bake_anim_use_all_actions=False,
    bake_anim_use_nla_strips=False,
    bake_anim_use_all_bones=True,
    bake_anim_force_startend_keying=True,
    bake_anim_step=1.0,
    bake_anim_simplify_factor=0.0,
)
```

- `object_types`: アーマチュアとメッシュのみ (カメラ・ライト等は含めない)。
- `add_leaf_bones=False`: Blender が自動で足すリーフダミーを抑制し、入力ボーン構成をそのまま保つ。
- `bake_anim_use_all_bones=True`: カーブが付いていないボーンも含め全ボーンを bake し、実行時にフレーム欠落が起こらないようにする。
- `bake_anim_simplify_factor=0.0`: F-Curve の自動単純化を無効にして入力キーをそのまま保持。

---

## 8. パッケージ JSON スキーマ

Blender サブプロセスへ渡される中間データ (一時 JSON)。

### 8.1 rigged (`build_rigged_fbx.py`)

| key | 形状 | 説明 |
|---|---|---|
| `output_path` | str | 書き出し先 FBX パス |
| `rest_verts` | [V, 3] | MHR ネイティブ座標のキャラクタ rest 頂点 |
| `faces` | [F, 3] | 三角形インデックス |
| `joint_parents` | [J] | 親 index (-1 = ルート) |
| `joint_names` | [J] | ボーン名 (剪定・再採番後) |
| `rest_joint_coords` | [J, 3] | MHR rest world 位置 |
| `rest_joint_rots` | [J, 3, 3] | MHR rest world 回転 |
| `posed_joint_coords` | [J, 3] | MHR posed world 位置 |
| `posed_joint_rots` | [J, 3, 3] | MHR posed world 回転 |
| `lbs_v_idx` / `lbs_j_idx` / `lbs_weight` | [K] ずつ | 疎 LBS (v, j, w の三つ組) |

### 8.2 animated (`build_animated_fbx.py`)

rigged の `posed_joint_coords` / `posed_joint_rots` の代わりに:

| key | 形状 | 説明 |
|---|---|---|
| `frames_posed_joint_rots` | [N, J, 3, 3] | 各フレームの MHR posed world 回転 |
| `frames_root_trans` | [N, 3] または空 | ルートの world 変位 (最初の検出フレーム起点、任意) |
| `fps` | float | 元動画の FPS |

`frames_root_trans` が空 or 全て 0 のとき `has_root_motion = False` となり、ルートの translation キーは打たれない。

---

## 9. DCC / ゲームエンジンで取り込むときの想定

- **Unity**: Humanoid 化は自動マッピングできない場合があるため、`pelvis` / `spine_*` / `upperarm_*` / `hand_*` / `foot_*` 等を手動でマッピングする必要がある。`head` (113) は首の先のボーンであり、Unity の Head スロットに割り当てる。
- **Unreal**: Epic 標準 (`pelvis`, `thigh_l`, `calf_l`, `foot_l`, `upperarm_l`, ...) 規約に主要ボーン名を寄せており、リターゲット設定が比較的素直。
- **Blender**: 取り込み時はそのまま Z-up に変換される (エクスポータで -Z forward / Y up を指定しているため)。

---

## 10. 参考: 実装上の注意点 (過去のハマりどころ)

- `edit_bone.matrix` を書き換える**前**に `bone.length` を 0 より大きくしておく。length 0 のままだと matrix 代入後の head/tail 計算が壊れる。
- 親子を `use_connect=True` にしない (head がレスト位置から外れる)。
- ポーズは必ずローカル差分で入れる (`pose_bone.matrix` への直接代入は `pose_bone.location` に巨大値が残り、bake で破壊される)。
- rigged は 0 長アニメを避けるため frame 1 / 30 の 2 点キーを必ず打つ。
- `bake_space_transform=True` と `axis_forward/up` を同時指定すると軸が二重変換される。必ず片方 (本プロジェクトでは後者) のみを使う。
