// Static-text i18n for the SAM 3D Body Standalone UI.
//
// - Every static DOM string carries a `data-i18n="key"` attribute (or
//   `data-i18n-placeholder` / `data-i18n-title` for input placeholders and
//   button tooltips). `applyLang()` walks the tree and overwrites those
//   fragments with the current dictionary's value.
// - Language preference persists in localStorage under `sam3d.lang`.
// - app.js emits a `sam3d:langchange` event after switching so dynamic
//   components can refresh their own copy if needed.

const DICT = {
  ja: {
    "app.title": "SAM 3D Body Standalone",
    "tab.image": "画像",
    "tab.video": "動画",
    "tab.make": "キャラメイク",
    "tab.admin": "Preset Admin",

    "section.input": "Input",
    "section.video": "動画 → アニメーション FBX",
    "section.make": "キャラメイク",
    "section.pack_admin": "Preset Pack 管理",
    "section.fbx_rebuild": "FBX Rebuild",
    "section.character": "Character",
    "section.health": "Health",

    "make.hint": "MHR 既定の T-pose 素体に対して、下の Character スライダーで体形を調整できます。完成したら「json をダウンロード」で JSON をローカル保存してください。",
    "make.download": "json をダウンロード",
    "make.downloaded": "JSON を保存しました",

    "input.drop": "クリックして画像を選択 / ドロップ",
    "input.sam3_settings": "SAM3 segmentation",
    "input.use_sam3": "SAM3 マスクを使う",
    "input.prompt": "prompt",
    "input.threshold": "threshold",
    "input.min_w": "min w (px)",
    "input.min_h": "min h (px)",
    "input.run": "ポーズを推定",
    "input.cancel": "推定を中止",
    "input.cancelled": "キャンセルしました",
    "input.done": "推定終了",

    "video.drop": "動画を選択 / ドロップ",
    "video.params": "パラメータ",
    "video.use_sam3": "SAM3 マスクを使う",
    "video.sam3_thr": "sam3 threshold",
    "video.bbox_thr": "bbox thr",
    "video.root_motion": "root motion",
    "video.fps": "fps (0 = 自動)",
    "video.stride": "stride",
    "video.max_frames": "max frames (0 = 全フレーム)",
    "video.run": "モーションを推定",
    "video.cancel": "推定を中止",
    "video.cancelled": "キャンセルしました",
    "video.done": "推定終了",
    "video.download": "FBX をダウンロード",
    "video.rebuilding": "キャラクター差し替え中…",
    "video.hint": "※ 体形は下の Character パネル (preset / JSON) で指定した値を rig にベイクします。モーション推定後に preset を切り替えると、キャラを差し替えた FBX が自動再生されます。",

    "character.preset_placeholder": "(preset)",
    "character.load": "Load",
    "character.reset": "Reset",
    "character.export_fbx": "FBX をダウンロード",
    "character.body_summary": "Body (PCA 9 軸)",
    "character.bone_summary": "Bone length (4 部位)",
    "character.bs_summary": "Blendshapes",
    "character.json_drop": "キャラクター JSON をアップロード (任意)",
    "character.json_loaded": "JSON 適用済み:",
    "character.preset_loaded": "preset 適用済み:",

    "admin.active_label": "active: -",
    "admin.switch": "Switch",
    "admin.new_name": "新しい pack 名...",
    "admin.clone": "Clone",
    "admin.delete": "選択中の pack を削除",
    "admin.fbx_hint": "Blender で tools/bone_backup/all_parts_bs.fbx を編集してシェイプキーを追加・編集した後、下にドロップして Rebuild を押すと face_blendshapes.npz と <obj>_vertices.json が再生成されて、スライダー一覧にも反映されます。",
    "admin.fbx_drop": "新 FBX を選択 / ドロップ (all_parts_bs.fbx)",
    "admin.rebuild": "Rebuild",
    "admin.placeholder": "Preset Pack の管理タブです。左のセクションで pack の switch / clone / delete、FBX の再構築を行えます。",

    "viewport.initial": "画像を読み込んで「ポーズを推定」を押すと 3D メッシュが表示されます",
    "viewport.save_png": "PNG 保存",
    "status.init": "initializing…",

    "tooltip.pack_switch": "選択したプリセットを適用",
    "tooltip.reset": "全スライダーを既定値に戻す",
    "tooltip.export_fbx": "Blender 経由でリグ付き FBX を書き出す",
    "tooltip.pack_clone": "default を複製して新規 pack 作成",
    "tooltip.pack_delete": "選択中の pack を削除 (default は不可)",
    "tooltip.fbx_rebuild": "Blender で npz と vertex JSON を再生成",
    "tooltip.save_png": "現在のビュワー表示を PNG として保存",
    "tooltip.make_download": "現在の Character スライダー値を character JSON としてダウンロード",
    "tooltip.video_download": "現在表示中のアニメーション FBX をローカルに保存",

    "lang.label": "言語",
  },
  en: {
    "app.title": "SAM 3D Body Standalone",
    "tab.image": "Image",
    "tab.video": "Video",
    "tab.make": "Character Make",
    "tab.admin": "Preset Admin",

    "section.input": "Input",
    "section.video": "Video → animated FBX",
    "section.make": "Character Make",
    "section.pack_admin": "Preset pack admin",
    "section.fbx_rebuild": "FBX rebuild",
    "section.character": "Character",
    "section.health": "Health",

    "make.hint": "Tweak the MHR neutral T-pose character with the sliders below. Hit \"Download JSON\" to save the current body shape as a JSON file.",
    "make.download": "Download JSON",
    "make.downloaded": "JSON saved",

    "input.drop": "Click to pick an image, or drop one here",
    "input.sam3_settings": "SAM3 segmentation",
    "input.use_sam3": "use SAM3 mask",
    "input.prompt": "prompt",
    "input.threshold": "threshold",
    "input.min_w": "min w (px)",
    "input.min_h": "min h (px)",
    "input.run": "Run pose estimation",
    "input.cancel": "Cancel",
    "input.cancelled": "Cancelled",
    "input.done": "Inference done",

    "video.drop": "Click to pick a video, or drop one here",
    "video.params": "Parameters",
    "video.use_sam3": "use SAM3 mask",
    "video.sam3_thr": "sam3 threshold",
    "video.bbox_thr": "bbox thr",
    "video.root_motion": "root motion",
    "video.fps": "fps (0 = auto)",
    "video.stride": "stride",
    "video.max_frames": "max frames (0 = all)",
    "video.run": "Infer motion",
    "video.cancel": "Cancel",
    "video.cancelled": "Cancelled",
    "video.done": "Inference done",
    "video.download": "Download FBX",
    "video.rebuilding": "rebuilding FBX with new character…",
    "video.hint": "The Character panel below (preset / JSON) is baked into the rig. After motion inference, swapping a preset re-builds the FBX with the new body automatically.",

    "character.preset_placeholder": "(preset)",
    "character.load": "Load",
    "character.reset": "Reset",
    "character.export_fbx": "Download FBX",
    "character.body_summary": "Body (PCA 9 axes)",
    "character.bone_summary": "Bone length (4 chains)",
    "character.bs_summary": "Blendshapes",
    "character.json_drop": "Upload character JSON (optional)",
    "character.json_loaded": "JSON applied:",
    "character.preset_loaded": "preset applied:",

    "admin.active_label": "active: -",
    "admin.switch": "Switch",
    "admin.new_name": "new pack name...",
    "admin.clone": "Clone",
    "admin.delete": "Delete selected",
    "admin.fbx_hint": "Edit tools/bone_backup/all_parts_bs.fbx in Blender (add or edit shape keys), drop it below and hit Rebuild. face_blendshapes.npz and <obj>_vertices.json are regenerated and the slider list refreshes.",
    "admin.fbx_drop": "Drop a new FBX here (all_parts_bs.fbx)",
    "admin.rebuild": "Rebuild",
    "admin.placeholder": "Preset Pack management. Use the left panel to switch / clone / delete packs and rebuild blend-shape data from an FBX.",

    "viewport.initial": "Pick an image and press \"Run pose estimation\" to see the 3D mesh here.",
    "viewport.save_png": "Save PNG",
    "status.init": "initializing…",

    "tooltip.pack_switch": "Apply the selected preset",
    "tooltip.reset": "Reset all sliders to defaults",
    "tooltip.export_fbx": "Export a rigged FBX via Blender",
    "tooltip.pack_clone": "Clone default into a new pack",
    "tooltip.pack_delete": "Delete the selected pack (default is protected)",
    "tooltip.fbx_rebuild": "Rebuild npz + vertex JSON via Blender",
    "tooltip.save_png": "Save the current 3D view as PNG",
    "tooltip.make_download": "Download the current Character slider values as a character JSON",
    "tooltip.video_download": "Download the currently-playing animated FBX",

    "lang.label": "Language",
  },
};

const SUPPORTED = Object.keys(DICT);
const STORAGE_KEY = "sam3d.lang";

function resolveInitialLang() {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved && SUPPORTED.includes(saved)) return saved;
  } catch (_e) {}
  // Browser preference: anything that starts with `ja` → Japanese; else English.
  const nav = (navigator.language || "en").toLowerCase();
  return nav.startsWith("ja") ? "ja" : "en";
}

let currentLang = resolveInitialLang();

function t(key) {
  const d = DICT[currentLang] || DICT.ja;
  return d[key] ?? DICT.ja[key] ?? key;
}

function applyLang(lang) {
  if (!SUPPORTED.includes(lang)) lang = "ja";
  currentLang = lang;
  document.documentElement.setAttribute("lang", lang);
  try { localStorage.setItem(STORAGE_KEY, lang); } catch (_e) {}

  document.querySelectorAll("[data-i18n]").forEach((el) => {
    const v = t(el.dataset.i18n);
    if (v !== undefined) el.textContent = v;
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
    const v = t(el.dataset.i18nPlaceholder);
    if (v !== undefined) el.placeholder = v;
  });
  document.querySelectorAll("[data-i18n-title]").forEach((el) => {
    const v = t(el.dataset.i18nTitle);
    if (v !== undefined) el.title = v;
  });

  // Keep the <select> in sync if someone else called applyLang().
  const sel = document.getElementById("lang-select");
  if (sel && sel.value !== lang) sel.value = lang;

  // Let the rest of the app (dynamic strings) react if they want.
  document.dispatchEvent(new CustomEvent("sam3d:langchange", { detail: { lang } }));
}

function initLanguagePicker() {
  const sel = document.getElementById("lang-select");
  if (!sel) return;
  sel.value = currentLang;
  sel.addEventListener("change", (e) => applyLang(e.target.value));
  applyLang(currentLang);
}

// Expose a tiny helper so app.js can localize dynamic strings too.
window.i18n = {
  t,
  get lang() { return currentLang; },
  applyLang,
};

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initLanguagePicker);
} else {
  initLanguagePicker();
}
