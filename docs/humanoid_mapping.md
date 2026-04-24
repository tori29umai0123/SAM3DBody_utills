# Humanoid 命名へのボーン割り付け表

`E:/desktop/test.fbx` を実機ダンプして確定した、現行 SAM3DBody FBX (112 ボーン) → 汎用 Humanoid 命名 (65 ボーン) への変換表。命名規約は Mixamo / Unity Humanoid / Unreal が共通で使っている de-facto humanoid 規約を採用する。

- 実装: `tools/humanoid_convert.py` (`apply_humanoid_conversion`)
- 呼び出し元: `tools/build_rigged_fbx.py`, `tools/build_animated_fbx.py` のアーマチュア構築直後
- ダンプスクリプト: `C:/tmp/fbx_inspect/dump_bones.py`
- 分析スクリプト: `C:/tmp/fbx_inspect/analyze_fingers_v2.py`

## 変換フロー

`apply_humanoid_conversion(arm_obj, mesh_obj)` が以下を順に実行する:

1. **ウェイト統合** — 削除対象のボーンの vertex group 重みを、統合先ボーンの vertex group に `ADD` モードで加算 (総和保存)。
2. **子ボーンの再親付け** — 削除対象の子供は、削除されない最近祖先を辿って直接親付け。
3. **ボーン削除** — edit mode で bones.remove。
4. **リネーム** — 残ったボーンを humanoid 名に変更。vertex group も同時にリネーム。
5. **ルート変更** — `joint_000` を除去し `pelvis` (→ `Hips`) がアーマチュアのルートになる。

ポーズは変換後の階層に対して再計算する (統合でスキップされた中間ボーンがあっても、MHR の絶対世界回転をそのまま使って各ボーンの親-自身差分を組み直せるため、崩れない)。

凡例:
- **rename** = ボーン名を変更してそのまま保持
- **MERGE `A → B`** = `A` の頂点ウェイトを `B` へ統合し、`A` を削除
- **MERGE `A → (parent)`** = `A` のウェイトを親ボーンへ統合して削除

---

## 1. 体幹・頭部

| 現行 (MHR) | Humanoid | 操作 |
|---|---|---|
| `joint_000` | — | **MERGE → (親なし、剪定してアーマチュア直下から除去)** |
| `pelvis` | `Hips` | rename |
| `joint_034` | — | **MERGE `joint_034 → Hips`**（pelvis と spine_01 の間の挿入骨） |
| `spine_01` | `Spine` | rename |
| `spine_02` | `Spine1` | rename |
| `spine_03` | `Spine2` | rename |
| `neck_01` | `Neck` | rename |
| `joint_111` | — | **MERGE `joint_111 → Neck`** |
| `head` | `Head` | rename |
| `joint_114` | `HeadTop_End` | rename（Humanoid 側は End 扱い / スキンなし） |

---

## 2. 左腕

### 主要ボーン

| 現行 | Humanoid | 操作 |
|---|---|---|
| `clavicle_l` | `LeftShoulder` | rename |
| `upperarm_l` | `LeftArm` | rename |
| `joint_105`〜`joint_109` | — | **MERGE → `LeftArm` (5 本の上腕 twist 補助骨)** |
| `lowerarm_l` | `LeftForeArm` | rename |
| `joint_101`〜`joint_104` | — | **MERGE → `LeftForeArm` (4 本の前腕 twist 補助骨)** |
| `joint_077` | — | **MERGE `joint_077 → LeftForeArm`**（前腕と手の間の挿入骨） |
| `hand_l` | `LeftHand` | rename |

### 左指（5 chains = 22 bones → Humanoid 20 bones）

空間位置で確定（hand-local 座標）:

| MHR 指根 | chain_len | hand-local 位置 | Humanoid 指 | 判定根拠 |
|---|---:|---|---|---|
| `joint_096` | 5 | (+0.0045, +0.0076, +0.0090) | **Thumb** | 原点に最近接 (dist=0.013) |
| `joint_092` | 4 | (+0.0559, +0.0177, +0.0061) | **Index** | 親指側 (+Y) の 4-node chain |
| `joint_088` | 4 | (+0.0578, −0.0001, +0.0027) | **Middle** | Y ≈ 0 |
| `joint_084` | 4 | (+0.0521, −0.0135, +0.0055) | **Ring** | −Y 寄り |
| `joint_079` | 5 | (+0.0144, −0.0159, +0.0075) | **Pinky** | 小指側に metacarpal 露出 |

割付詳細:

**LeftHandThumb** (MHR 5 節 → Humanoid 4 節、1 節合流)
- `joint_096` → `LeftHandThumb1`
- `joint_097` → `LeftHandThumb2`
- `joint_098` → `LeftHandThumb3`
- `joint_099` → **MERGE → `LeftHandThumb3`**
- `joint_100` → `LeftHandThumb4` (End)

**LeftHandIndex** (4 → 4、そのまま)
- `joint_092/093/094/095` → `LeftHandIndex1/2/3/4`

**LeftHandMiddle**
- `joint_088/089/090/091` → `LeftHandMiddle1/2/3/4`

**LeftHandRing**
- `joint_084/085/086/087` → `LeftHandRing1/2/3/4`

**LeftHandPinky** (MHR 5 節 → Humanoid 4 節、metacarpal を Hand に吸収)
- `joint_079` → **MERGE → `LeftHand`** (MHR は小指 metacarpal を露出、Humanoid は非露出)
- `joint_080` → `LeftHandPinky1`
- `joint_081` → `LeftHandPinky2`
- `joint_082` → `LeftHandPinky3`
- `joint_083` → `LeftHandPinky4` (End)

---

## 3. 右腕（左腕のミラー）

### 主要ボーン

| 現行 | Humanoid | 操作 |
|---|---|---|
| `clavicle_r` | `RightShoulder` | rename |
| `upperarm_r` | `RightArm` | rename |
| `joint_069`〜`joint_073` | — | **MERGE → `RightArm`** |
| `lowerarm_r` | `RightForeArm` | rename |
| `joint_065`〜`joint_068` | — | **MERGE → `RightForeArm`** |
| `joint_041` | — | **MERGE `joint_041 → RightForeArm`** |
| `hand_r` | `RightHand` | rename |

### 右指

| MHR 指根 | chain_len | hand-local 位置 | Humanoid 指 |
|---|---:|---|---|
| `joint_060` | 5 | (−0.0045, −0.0077, −0.0091) | **Thumb** |
| `joint_056` | 4 | (−0.0561, −0.0177, −0.0061) | **Index** |
| `joint_052` | 4 | (−0.0579, +0.0001, −0.0027) | **Middle** |
| `joint_048` | 4 | (−0.0522, +0.0135, −0.0055) | **Ring** |
| `joint_043` | 5 | (−0.0144, +0.0160, −0.0076) | **Pinky** |

**RightHandThumb**: `060/061/062/064` → `RightHandThumb1/2/3/4`、`063` MERGE→`062`

**RightHandIndex**: `056/057/058/059` → `RightHandIndex1/2/3/4`

**RightHandMiddle**: `052/053/054/055` → `RightHandMiddle1/2/3/4`

**RightHandRing**: `048/049/050/051` → `RightHandRing1/2/3/4`

**RightHandPinky**: `043` MERGE → `RightHand`、`044/045/046/047` → `RightHandPinky1/2/3/4`

---

## 4. 左脚

| 現行 | Humanoid | 操作 |
|---|---|---|
| `thigh_l` | `LeftUpLeg` | rename |
| `joint_014`〜`joint_017` | — | **MERGE → `LeftUpLeg`**（太腿の補助骨 4 本） |
| `calf_l` | `LeftLeg` | rename |

### 左つま先

MHR は 1 本の 4 節つま先チェーン (foot_l 配下) + 4 本の単独スタブ (calf_l 配下)。

| 現行 | Humanoid | 操作 |
|---|---|---|
| `foot_l` | `LeftFoot` | rename |
| `joint_005` | `LeftToeBase` | rename |
| `joint_006` | — | **MERGE `joint_006 → LeftToeBase`** |
| `joint_007` | — | **MERGE `joint_007 → LeftToeBase`** |
| `joint_008` | `LeftToe_End` | rename |
| `joint_009`〜`joint_012` | — | **MERGE → `LeftLeg`**（calf 配下の twist 補助骨 4 本。calf-local X=0.06〜0.24 に分布＝ふくらはぎ上半分の twist helper） |

---

## 5. 右脚

| 現行 | Humanoid | 操作 |
|---|---|---|
| `thigh_r` | `RightUpLeg` | rename |
| `joint_030`〜`joint_033` | — | **MERGE → `RightUpLeg`** |
| `calf_r` | `RightLeg` | rename |
| `foot_r` | `RightFoot` | rename |
| `joint_021` | `RightToeBase` | rename |
| `joint_022` | — | **MERGE → `RightToeBase`** |
| `joint_023` | — | **MERGE → `RightToeBase`** |
| `joint_024` | `RightToe_End` | rename |
| `joint_025`〜`joint_028` | — | **MERGE → `RightLeg`**（calf twist 補助、左と対称） |

---

## 6. 集計

- **入力**: 112 本（`joint_000` + pelvis + 体幹補助 + spine×3 + neck_01 + head + 補助 + 左右 arm 5本×2 + 左右 twist 9本×2 + 左右 hand 指 22本×2 + 左右 leg 3本×2 + 左右 toe 12本×2 ≈ 112）
- **出力**: Humanoid 規約 65 本
  - 体幹: 6 (Hips, Spine, Spine1, Spine2, Neck, Head) + `HeadTop_End`
  - 左右 Shoulder/Arm/ForeArm/Hand: 4×2 = 8
  - 左右 指: 20×2 = 40 (4 指 × 4 節 × 2手)
  - 左右 UpLeg/Leg/Foot/ToeBase: 4×2 = 8 + `Left/RightToe_End` ×2
  - 合計: 7 + 8 + 40 + 10 = **65**

- **削除（MERGE で吸収）**: 47 本
  - 体幹補助: `joint_000` (剪定), `joint_034`, `joint_111` = 3
  - 上腕/前腕 twist: 5+4+4+1 (左) + 5+4+4+1 (右) = 28
  - 手の metacarpal: 1 (左 pinky) + 1 (右 pinky) = 2
  - 指の中間節: 1 (左 thumb) + 1 (右 thumb) = 2
  - 脚の補助: 4×2 = 8
  - つま先中間: 2×2 = 4
  - つま先スタブ: 4×2 = 8 → ※再集計  
    合計 3 + 28 + 2 + 2 + 8 + 4 + 8 = 55 程度（細部で要再カウント）

※ 実装時は `fbx_export.py` のパッケージ JSON を書き換えるのではなく、**Blender 側 (`build_*_fbx.py`) で骨を組んだ直後・エクスポート前** に上表に従って rename / merge を行うポストプロセス関数として実装するのが素直。

---

## 7. 未確定事項 / 検証が必要

1. **THUMB の merge 位置**
   MHR thumb の 5 節の解剖学的解釈が不確定。現在は `joint_099` を `joint_098` に畳み込む方針だが、もし実データで `joint_097` が冗長であれば前方へ畳み込む方が自然。ビューでの確認を推奨。
2. **`joint_111`** の役割
   Humanoid 側は `neck_01` と `head` の間に中間骨を持たないため `Neck` に吸収する想定。実データでは 932 頂点が該当、`Neck` 吸収で合計 0.9〜1.1 の正規化を保てている。
3. **calf 配下の toe スタブ (`joint_009`〜`012` / `joint_025`〜`028`)**
   実計測では calf-local X が 0.06〜0.24 (足指ではなく「ふくらはぎ上半の twist helper」) だったため、`LeftLeg` / `RightLeg` へ統合する実装を採用。`LeftFoot` に吸収する選択肢もあったが、足首から遠いため脚側に寄せた方が skinning の挙動が自然。
4. **twist 骨の吸収**
   前腕・上腕の twist 補助は通常「親ボーンへそのまま統合」で問題ないが、Unity Humanoid で前腕ロールを綺麗に見せたい場合、カスタムで `LeftForeArmRoll` / `LeftArmRoll` として残す選択肢もある（Humanoid 標準には無いが Unity は認識する）。
