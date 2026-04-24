# Mixamo 標準ボーン構成（完全一覧）

## 概要
Adobeの自動リギングサービス「Mixamo」で生成される標準的なヒューマノイドスケルトンのボーン構成を網羅的に列挙する。

---

## ルート・体幹
```
Hips
Spine
Spine1
Spine2
Neck
Head
HeadTop_End
```

---

## 左腕（Left Arm）
```
LeftShoulder
LeftArm
LeftForeArm
LeftHand
```

### 左手の指
```
LeftHandThumb1
LeftHandThumb2
LeftHandThumb3
LeftHandThumb4

LeftHandIndex1
LeftHandIndex2
LeftHandIndex3
LeftHandIndex4

LeftHandMiddle1
LeftHandMiddle2
LeftHandMiddle3
LeftHandMiddle4

LeftHandRing1
LeftHandRing2
LeftHandRing3
LeftHandRing4

LeftHandPinky1
LeftHandPinky2
LeftHandPinky3
LeftHandPinky4
```

---

## 右腕（Right Arm）
```
RightShoulder
RightArm
RightForeArm
RightHand
```

### 右手の指
```
RightHandThumb1
RightHandThumb2
RightHandThumb3
RightHandThumb4

RightHandIndex1
RightHandIndex2
RightHandIndex3
RightHandIndex4

RightHandMiddle1
RightHandMiddle2
RightHandMiddle3
RightHandMiddle4

RightHandRing1
RightHandRing2
RightHandRing3
RightHandRing4

RightHandPinky1
RightHandPinky2
RightHandPinky3
RightHandPinky4
```

---

## 左脚（Left Leg）
```
LeftUpLeg
LeftLeg
LeftFoot
LeftToeBase
LeftToe_End
```

---

## 右脚（Right Leg）
```
RightUpLeg
RightLeg
RightFoot
RightToeBase
RightToe_End
```

---

## 補足

### ボーン数
- 約65〜70本（指ありフル構成）
- 指なしの場合は20〜30本程度

### 特徴
- ルートボーンは `Hips`
- IKボーンなし（FK構成）
- Twistボーンなし
- フェイシャルボーンなし
- 命名規則は左右で `Left / Right`

### Endボーンについて
- `HeadTop_End`, `Toe_End` などは補助ノード
- スキニングには使用されない
- エクスポート時に削除されることがある

---

## エンジン互換性

### Unity
- Humanoid Avatarに自動対応
- そのまま使用可能

### Unreal Engine
- 標準マネキンとは非互換（Twist不足）
- リターゲットが必要
