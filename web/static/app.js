import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { OBJLoader } from "three/addons/loaders/OBJLoader.js";
import { FBXLoader } from "three/addons/loaders/FBXLoader.js";

const $ = (id) => document.getElementById(id);
const statusEl = $("status");
const healthEl = $("health");
const fileInput = $("file-input");
const fileDrop = $("file-drop");
const fileLabel = $("file-label");
const previewEl = $("preview");
const runBtn = $("run-btn");
const runCancelBtn = $("run-cancel-btn");
const runInfo = $("run-info");
const overlay = $("viewport-overlay");
// SAM3 segmentation params now live in config.ini [sam3]; no longer in UI.
const characterSection = $("character-section");
const presetSelect = $("preset-select");
const loadPresetBtn = $("load-preset-btn");
const resetBtn = $("reset-btn");
const exportFbxBtn = $("export-fbx-btn");
const fbxInfo = $("fbx-info");
const renderInfo = $("render-info");
const charJsonInput = $("char-json-input");
const charJsonDrop = $("char-json-drop");
const charJsonLabel = $("char-json-label");
const charSourceInfo = $("char-source-info");
const bodyParamsEl = $("body-params-sliders");
const boneLengthsEl = $("bone-lengths-sliders");
const blendshapesEl = $("blendshapes-sliders");

// ---------------------------------------------------------------------------
// Tab nav
// ---------------------------------------------------------------------------

const TABS = ["image", "video", "make", "admin"];
const MAKE_JOB_ID = "make";

const featureFlags = { preset_pack_admin: false, debug: false };

function activateTab(name) {
  if (!TABS.includes(name)) return;
  // Honor runtime feature flags: if Preset Admin is disabled in config.ini,
  // bounce away silently when someone tries to activate it.
  if (name === "admin" && !featureFlags.preset_pack_admin) {
    name = "image";
  }
  document.querySelectorAll("[data-tab-panel]").forEach((el) => {
    el.hidden = el.dataset.tabPanel !== name;
  });
  // The Character panel (preset dropdown + JSON upload, plus sliders on
  // Make tab) is always available on image/video/make tabs — users can
  // stage a preset / upload a custom character before running inference.
  characterUnlocked = true;
  document.querySelectorAll("[data-tab-show]").forEach((el) => {
    const allowed = el.dataset.tabShow.split(/\s+/).filter(Boolean);
    el.hidden = !allowed.includes(name);
  });
  // `data-tab-hide="x y"` hides the element only on those tabs. Useful for
  // entries that live inside a shared section (e.g. Export FBX button in the
  // Character panel) but should disappear on one tab.
  document.querySelectorAll("[data-tab-hide]").forEach((el) => {
    const hidden = el.dataset.tabHide.split(/\s+/).filter(Boolean);
    el.hidden = hidden.includes(name);
  });
  document.querySelectorAll(".tab-nav button[data-tab]").forEach((b) => {
    b.classList.toggle("active", b.dataset.tab === name);
  });
  try { localStorage.setItem("sam3d.tab", name); } catch (_e) {}

  // Swap the viewport's cached mesh/animation/camera state to match the tab.
  viewer.switchTab(name);

  // Rebind settings + Character panel UI to the active tab's slot so each
  // tab keeps its own body_params / bone_lengths / blendshapes / preset
  // selection. Admin tab has no character state — leave `settings` alone.
  if (tabSettings[name]) {
    settings = tabSettings[name];
    refreshSlidersFromSettings();
    refreshCharPanelFromState();
  }

  // Rebind currentJobId so /api/render targets the right session. Image /
  // video fall back to MAKE_JOB_ID until inference produces a tab-specific
  // session — this lets the viewport show the MHR neutral body (with the
  // tab's current character settings) before the user runs anything.
  if (name in tabJobIds) {
    currentJobId = tabJobIds[name] || MAKE_JOB_ID;
  }

  // First-visit render: if the viewer has no cached mesh for this tab,
  // kick off a render so the viewport isn't empty on arrival. Subsequent
  // visits rely on viewer.switchTab() having restored the cached state.
  if ((name === "image" || name === "video" || name === "make")
      && !viewer.hasCachedMesh(name)) {
    scheduleRender();
  }
}

function initTabs() {
  document.querySelectorAll(".tab-nav button[data-tab]").forEach((b) => {
    b.addEventListener("click", () => activateTab(b.dataset.tab));
  });
  let initial = "image";
  try { initial = localStorage.getItem("sam3d.tab") || "image"; } catch (_e) {}
  activateTab(initial);
}

// Track whether a pose session exists so the Character panel only appears
// after the user has run /api/process at least once (matches prior behaviour).
let characterUnlocked = false;
let renderAvailable = false;  // Save PNG is disabled until the first mesh is drawn.

const viewer = initViewer();
let selectedFile = null;
let currentJobId = null;
// Per-tab job id. Image tab gets its id from /api/process, make tab uses a
// fixed neutral-body session key. Video tab has no OBJ-render job (it
// builds FBX animations via currentMotionId instead), so its entry stays
// null — scheduleRender short-circuits when on the video tab without motion.
// Kept in sync with `currentJobId` on every tab switch.
const tabJobIds = { image: null, video: null, make: MAKE_JOB_ID };
let schema = null;
// Per-tab character-shape state. Image / video / make tabs each own an
// independent `settings` snapshot and Character-panel UI state (selected
// preset, source label, JSON upload label). `settings` is rebound on tab
// switch to point at the active tab's slot so that existing readers
// (render calls, slider handlers) work unchanged. The Character panel
// (preset dropdown + JSON upload) itself is shared DOM across tabs — we
// just swap the values it displays when the tab changes.
function _freshSettings() {
  return { body_params: {}, bone_lengths: {}, blendshapes: {} };
}
function _freshCharState() {
  return { preset: "", sourceText: "", jsonLabel: null };
}
const tabSettings = {
  image: _freshSettings(),
  video: _freshSettings(),
  make:  _freshSettings(),
};
const tabCharState = {
  image: _freshCharState(),
  video: _freshCharState(),
  make:  _freshCharState(),
};
let settings = tabSettings.image;

function initViewer() {
  const canvas = $("three-canvas");
  // `preserveDrawingBuffer` is required for `canvas.toBlob()` / `toDataURL()`
  // to return the rendered image instead of a blank buffer (WebGL normally
  // clears the back buffer after each present).
  const renderer = new THREE.WebGLRenderer({
    canvas, antialias: true, preserveDrawingBuffer: true,
  });
  renderer.setPixelRatio(window.devicePixelRatio);
  renderer.setClearColor(0x22242a, 1);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(45, 1, 0.01, 100);
  camera.position.set(0, 1.0, 3.0);

  scene.add(new THREE.AmbientLight(0xffffff, 0.55));
  const dir = new THREE.DirectionalLight(0xffffff, 1.2);
  dir.position.set(3, 5, 2);
  scene.add(dir);
  const fill = new THREE.DirectionalLight(0xaaccff, 0.3);
  fill.position.set(-3, 2, -4);
  scene.add(fill);

  const grid = new THREE.GridHelper(4, 20, 0x555555, 0x333333);
  scene.add(grid);

  const controls = new OrbitControls(camera, canvas);
  controls.target.set(0, 0.9, 0);
  controls.update();

  let meshGroup = null;
  // Framing done once per job_id to avoid camera jump on every slider edit.
  let framedJob = null;
  // Animation bookkeeping (used when the viewer shows an animated FBX clip
  // produced by the video pipeline).
  let mixer = null;
  let animClip = null;
  const clock = new THREE.Clock();

  // Per-tab viewport cache so that switching between image / video / make
  // restores the mesh, animation and camera state the user last saw. Admin
  // tab has no viewport state and is skipped by switchTab().
  const tabStates = { image: null, video: null, make: null };
  let activeTabKey = "image";

  function _captureState() {
    return {
      meshGroup,
      mixer,
      animClip,
      framedJob,
      cameraPos: camera.position.clone(),
      target: controls.target.clone(),
    };
  }

  function _clearActive() {
    if (meshGroup && meshGroup.parent === scene) scene.remove(meshGroup);
    meshGroup = null;
    mixer = null;
    animClip = null;
    _dirty = true;
  }

  function _applyState(s) {
    if (!s) return;
    if (s.meshGroup) {
      if (s.meshGroup.parent !== scene) scene.add(s.meshGroup);
      meshGroup = s.meshGroup;
    }
    mixer = s.mixer || null;
    animClip = s.animClip || null;
    framedJob = s.framedJob || null;
    if (s.cameraPos) camera.position.copy(s.cameraPos);
    if (s.target) controls.target.copy(s.target);
    controls.update();
    _dirty = true;
  }

  function switchTab(tabKey) {
    if (!(tabKey in tabStates)) return;  // admin etc. — keep viewer untouched.
    if (tabKey === activeTabKey) return;
    tabStates[activeTabKey] = _captureState();
    _clearActive();
    activeTabKey = tabKey;
    _applyState(tabStates[tabKey]);
  }

  function hasCachedMesh(tabKey) {
    return !!(tabStates[tabKey] && tabStates[tabKey].meshGroup);
  }

  // Dirty-flag render loop. Re-rendering a static scene every frame burns
  // GPU / battery for no visible change, so `renderer.render` is gated on
  // a `_dirty` bit flipped by OrbitControls events, mesh swaps, camera
  // restores, and — every frame — an active AnimationMixer.
  let _dirty = true;
  const markDirty = () => { _dirty = true; };
  controls.addEventListener("change", markDirty);

  function resize() {
    const w = canvas.clientWidth;
    const h = canvas.clientHeight;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    markDirty();
  }
  window.addEventListener("resize", resize);
  resize();

  (function tick() {
    const dt = clock.getDelta();
    if (mixer) {
      mixer.update(dt);
      _dirty = true;
    }
    controls.update();
    if (_dirty) {
      renderer.render(scene, camera);
      _dirty = false;
    }
    requestAnimationFrame(tick);
  })();

  function _disposeMesh() {
    if (mixer) {
      mixer.stopAllAction();
      mixer.uncacheRoot(meshGroup);
      mixer = null;
    }
    animClip = null;
    if (meshGroup) {
      scene.remove(meshGroup);
      meshGroup.traverse?.((o) => {
        if (o.isMesh) {
          o.geometry?.dispose?.();
          if (Array.isArray(o.material)) {
            o.material.forEach((m) => m?.dispose?.());
          } else {
            o.material?.dispose?.();
          }
        }
      });
    }
  }

  async function loadObj(url, jobId) {
    const loader = new OBJLoader();
    const root = await new Promise((resolve, reject) => {
      loader.load(url, resolve, undefined, reject);
    });
    root.traverse((obj) => {
      if (obj.isMesh) {
        obj.material = new THREE.MeshStandardMaterial({
          color: 0xbbcddd, roughness: 0.75, metalness: 0.05, flatShading: false,
        });
      }
    });

    _disposeMesh();
    meshGroup = root;

    // Only re-frame when we switch to a new job; otherwise the camera stays
    // locked so slider drags don't bounce the view around.
    const box = new THREE.Box3().setFromObject(root);
    const size = new THREE.Vector3();
    box.getSize(size);
    const targetHeight = 1.7;
    const scale = targetHeight / Math.max(size.y, 1e-3);
    root.scale.setScalar(scale);
    const centered = new THREE.Box3().setFromObject(root);
    const center = new THREE.Vector3();
    centered.getCenter(center);
    root.position.x -= center.x;
    root.position.z -= center.z;
    root.position.y -= centered.min.y;

    scene.add(root);

    if (framedJob !== jobId) {
      controls.target.set(0, targetHeight * 0.5, 0);
      camera.position.set(0, targetHeight * 0.6, targetHeight * 2.2);
      controls.update();
      framedJob = jobId;
    }
    _dirty = true;
  }

  async function loadFbxAnimated(url, jobId) {
    const loader = new FBXLoader();
    const root = await new Promise((resolve, reject) => {
      loader.load(url, resolve, undefined, reject);
    });

    // FBX default material is often too dark; reassign a matte look so the
    // animated body reads well against the neutral viewport background.
    root.traverse((obj) => {
      if (obj.isMesh || obj.isSkinnedMesh) {
        obj.material = new THREE.MeshStandardMaterial({
          color: 0xbbcddd, roughness: 0.75, metalness: 0.05, flatShading: false,
        });
        obj.castShadow = false;
        obj.receiveShadow = false;
      }
    });

    _disposeMesh();
    meshGroup = root;

    // Fit roughly the same size + centering we use for OBJ so switching
    // between still and animated outputs doesn't jump the framing. FBX from
    // Blender sometimes arrives in cm (unit scale); a one-shot fit handles
    // both cases uniformly.
    const box = new THREE.Box3().setFromObject(root);
    const size = new THREE.Vector3();
    box.getSize(size);
    const targetHeight = 1.7;
    const scale = targetHeight / Math.max(size.y, 1e-3);
    root.scale.setScalar(scale);
    const centered = new THREE.Box3().setFromObject(root);
    const center = new THREE.Vector3();
    centered.getCenter(center);
    root.position.x -= center.x;
    root.position.z -= center.z;
    root.position.y -= centered.min.y;

    scene.add(root);

    // Start the first embedded animation clip, looping so the user can keep
    // watching the motion without re-triggering anything.
    if (root.animations && root.animations.length > 0) {
      mixer = new THREE.AnimationMixer(root);
      animClip = root.animations[0];
      const action = mixer.clipAction(animClip);
      action.setLoop(THREE.LoopRepeat, Infinity);
      action.play();
    } else {
      console.warn("FBX has no animation clips:", url);
    }

    if (framedJob !== jobId) {
      controls.target.set(0, targetHeight * 0.5, 0);
      camera.position.set(0, targetHeight * 0.6, targetHeight * 2.2);
      controls.update();
      framedJob = jobId;
    }
    _dirty = true;

    return {
      hasAnimation: !!animClip,
      clipDuration: animClip ? animClip.duration : 0,
    };
  }

  function savePng(filename) {
    // Swap to a white background and hide the ground grid for the capture,
    // then restore both so the on-screen view isn't disturbed. Using
    // toDataURL (synchronous) instead of toBlob avoids races with the tick
    // loop overwriting the back buffer before the async encode completes.
    const prevClearColor = renderer.getClearColor(new THREE.Color());
    const prevClearAlpha = renderer.getClearAlpha();
    const prevGridVisible = grid.visible;
    renderer.setClearColor(0xffffff, 1);
    grid.visible = false;
    try {
      renderer.render(scene, camera);
      const dataUrl = canvas.toDataURL("image/png");
      const a = document.createElement("a");
      a.href = dataUrl;
      a.download = filename || `render_${Date.now()}.png`;
      document.body.appendChild(a);
      a.click();
      a.remove();
    } finally {
      renderer.setClearColor(prevClearColor, prevClearAlpha);
      grid.visible = prevGridVisible;
      // Next tick needs to redraw with the restored background + grid.
      _dirty = true;
    }
  }

  return { loadObj, loadFbxAnimated, savePng, switchTab, hasCachedMesh };
}

// ---------------------------------------------------------------------------
// Health polling
// ---------------------------------------------------------------------------

async function pollHealth() {
  try {
    const r = await fetch("/api/health");
    const j = await r.json();
    healthEl.textContent = JSON.stringify(j, null, 2);
    statusEl.textContent = `ready — ${j.python} / torch ${j.torch ?? "n/a"} / ${j.cuda_device ?? "cpu"}`;
    statusEl.classList.add("ok"); statusEl.classList.remove("err", "busy");
  } catch (e) {
    healthEl.textContent = String(e);
    statusEl.textContent = "backend unreachable";
    statusEl.classList.add("err"); statusEl.classList.remove("ok", "busy");
  }
}

// ---------------------------------------------------------------------------
// File / image input
// ---------------------------------------------------------------------------

function onFileChosen(file) {
  if (!file) return;
  selectedFile = file;
  const url = URL.createObjectURL(file);
  previewEl.src = url;
  previewEl.hidden = false;
  fileLabel.textContent = file.name;
  runBtn.disabled = false;
  runInfo.textContent = "";
}

fileInput.addEventListener("change", (e) => onFileChosen(e.target.files?.[0]));
// NOTE: `<label class="file-drop">` already forwards clicks to the inner
// <input type="file"> via HTML's label→control binding, so adding
// `fileInput.click()` here on top fires the dialog twice (the user ends
// up needing to select their image in both dialogs). Rely on the native
// label behaviour — only drag&drop needs custom wiring below.
["dragenter", "dragover"].forEach((ev) =>
  fileDrop.addEventListener(ev, (e) => {
    e.preventDefault(); fileDrop.classList.add("dragover");
  })
);
["dragleave", "drop"].forEach((ev) =>
  fileDrop.addEventListener(ev, (e) => {
    e.preventDefault(); fileDrop.classList.remove("dragover");
  })
);
fileDrop.addEventListener("drop", (e) => {
  const f = e.dataTransfer.files?.[0];
  if (f) onFileChosen(f);
});

// ---------------------------------------------------------------------------
// Slider UI (built dynamically from /api/slider_schema)
// ---------------------------------------------------------------------------

function makeSlider(group, def) {
  const wrap = document.createElement("div");
  wrap.className = "slider-row";
  const label = document.createElement("label");
  label.textContent = def.key;
  label.title = def.key;
  const range = document.createElement("input");
  range.type = "range";
  range.min = def.min; range.max = def.max; range.step = def.step;
  range.value = settings[group][def.key] ?? def.default;
  const num = document.createElement("input");
  num.type = "number";
  num.min = def.min; num.max = def.max; num.step = def.step;
  num.value = range.value;

  const onInput = (v) => {
    const clamped = Math.max(def.min, Math.min(def.max, Number(v)));
    range.value = String(clamped);
    num.value = String(clamped);
    settings[group][def.key] = clamped;
    scheduleRender();
  };
  range.addEventListener("input", () => onInput(range.value));
  num.addEventListener("change", () => onInput(num.value));
  wrap.appendChild(label);
  wrap.appendChild(range);
  wrap.appendChild(num);
  return { wrap, range, num, def, group };
}

const sliderRefs = { body_params: {}, bone_lengths: {}, blendshapes: {} };

function buildSliders(el, group, defs) {
  el.innerHTML = "";
  const grid = document.createElement("div");
  grid.className = "slider-grid";
  for (const def of defs) {
    if (settings[group][def.key] === undefined) settings[group][def.key] = def.default;
    const s = makeSlider(group, def);
    grid.appendChild(s.wrap);
    sliderRefs[group][def.key] = s;
  }
  el.appendChild(grid);
}

function applySettingsToUi(newSettings) {
  for (const group of ["body_params", "bone_lengths", "blendshapes"]) {
    const src = newSettings[group] || {};
    for (const [k, ref] of Object.entries(sliderRefs[group])) {
      const v = Number(src[k] ?? ref.def.default);
      settings[group][k] = v;
      ref.range.value = String(v);
      ref.num.value = String(v);
    }
  }
}

// Called after rebinding `settings` to a different per-tab slot. Syncs the
// shared slider DOM to whatever the active tab's settings now holds, and
// backfills defaults for keys the tab hadn't touched yet.
function refreshSlidersFromSettings() {
  for (const group of ["body_params", "bone_lengths", "blendshapes"]) {
    for (const [k, ref] of Object.entries(sliderRefs[group])) {
      if (settings[group][k] === undefined) settings[group][k] = ref.def.default;
      const v = Number(settings[group][k]);
      ref.range.value = String(v);
      ref.num.value = String(v);
    }
  }
}

// Sync the shared Character-panel DOM (preset dropdown, source info text,
// JSON upload label) to the active tab's cached char state.
function refreshCharPanelFromState() {
  const name = document.querySelector(".tab-nav button.active")?.dataset.tab || "image";
  const state = tabCharState[name];
  if (!state) return;
  presetSelect.value = state.preset ?? "";
  charSourceInfo.textContent = state.sourceText ?? "";
  charJsonLabel.textContent =
    state.jsonLabel ??
    (window.i18n?.t("character.json_drop") || "Upload character JSON (optional)");
  // Clear the <input type="file"> so re-selecting the same file still triggers change.
  charJsonInput.value = "";
}

// True when at least one slider differs from its declared default. Used to
// decide whether to trigger an immediate re-render after /api/process
// (the pipeline's initial OBJ is always the neutral body, so if the user
// had already staged a preset / uploaded JSON we need to apply it).
function _settingsNonDefault() {
  for (const group of ["body_params", "bone_lengths", "blendshapes"]) {
    for (const [k, ref] of Object.entries(sliderRefs[group])) {
      if (Math.abs((settings[group][k] ?? ref.def.default) - ref.def.default) > 1e-9) {
        return true;
      }
    }
  }
  return false;
}

// ---------------------------------------------------------------------------
// Debounced render request
// ---------------------------------------------------------------------------

let renderInFlight = false;
let renderDirty = false;
let debounceTimer = null;

function scheduleRender() {
  // On the video tab, once motion inference has produced a cache we route
  // to /api/build_animated_fbx (animated FBX). Without motion the video
  // tab falls through to /api/render with MAKE_JOB_ID so the viewport
  // still shows the neutral MHR body with the tab's character settings.
  const activeTab = document.querySelector(".tab-nav button.active")?.dataset.tab;
  if (activeTab === "video" && currentMotionId) {
    rebuildAnimatedFbx();
    return;
  }
  if (!currentJobId) return;
  if (debounceTimer) clearTimeout(debounceTimer);
  debounceTimer = setTimeout(triggerRender, 60);
}

async function triggerRender() {
  if (!currentJobId) return;
  if (renderInFlight) { renderDirty = true; return; }
  renderInFlight = true;
  renderDirty = false;
  try {
    const t0 = performance.now();
    const r = await fetch("/api/render", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ job_id: currentJobId, settings }),
    });
    if (!r.ok) throw new Error(`HTTP ${r.status}: ${await r.text()}`);
    const j = await r.json();
    await viewer.loadObj(j.obj_url, currentJobId);
    // First rendered frame unlocks the PNG save button. Export FBX is
    // image-tab only and gated separately by /api/process success — we
    // don't flip it here so the neutral body preview before inference
    // can't be exported as a rigged FBX.
    renderAvailable = true;
    const savePngBtn = document.getElementById("save-render-btn");
    if (savePngBtn) savePngBtn.disabled = false;
    // Clear the initial viewport hint once a mesh is actually on screen.
    if (overlay.textContent) overlay.textContent = "";
    const ms = Math.round(performance.now() - t0);
    renderInfo.textContent = `render ${j.elapsed_sec}s (rt ${ms}ms)`;
  } catch (e) {
    console.error(e);
    renderInfo.textContent = `render error: ${e.message || e}`;
  } finally {
    renderInFlight = false;
    if (renderDirty) triggerRender();
  }
}

// ---------------------------------------------------------------------------
// Preset I/O
// ---------------------------------------------------------------------------

async function refreshPresets() {
  try {
    const r = await fetch("/api/presets");
    const j = await r.json();
    presetSelect.innerHTML = '<option value="">(preset)</option>';
    for (const name of (j.presets || [])) {
      const opt = document.createElement("option");
      opt.value = name; opt.textContent = name;
      presetSelect.appendChild(opt);
    }
  } catch (e) { console.error(e); }
}

loadPresetBtn.addEventListener("click", async () => {
  const name = presetSelect.value;
  if (!name) return;
  try {
    const r = await fetch(`/api/preset/${encodeURIComponent(name)}`);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const preset = await r.json();
    applySettingsToUi(preset);
    const prefix = window.i18n?.t("character.preset_loaded") || "preset applied:";
    const sourceText = `${prefix} ${name}`;
    charSourceInfo.textContent = sourceText;
    // Reset any lingering JSON upload label — picking a preset is the new source.
    charJsonInput.value = "";
    const defaultJsonLabel = window.i18n?.t("character.json_drop") || "Upload character JSON (optional)";
    charJsonLabel.textContent = defaultJsonLabel;
    // Persist to the active tab's char state so tab switches restore it.
    const activeTab = document.querySelector(".tab-nav button.active")?.dataset.tab;
    if (activeTab && tabCharState[activeTab]) {
      tabCharState[activeTab].preset = name;
      tabCharState[activeTab].sourceText = sourceText;
      tabCharState[activeTab].jsonLabel = null;
    }
    scheduleRender();
  } catch (e) { renderInfo.textContent = `load preset failed: ${e.message || e}`; }
});

// Upload a character JSON → parse → push into settings + sliders → re-render.
// The uploaded values override the currently-selected preset (whichever
// source runs last wins; that matches what the user expects).
async function handleCharJsonFile(file) {
  if (!file) return;
  try {
    const text = await file.text();
    const parsed = JSON.parse(text);
    if (typeof parsed !== "object" || parsed === null) {
      throw new Error("JSON must be an object with body_params / bone_lengths / blendshapes");
    }
    applySettingsToUi(parsed);
    const prefix = window.i18n?.t("character.json_loaded") || "JSON applied:";
    const sourceText = `${prefix} ${file.name}`;
    charSourceInfo.textContent = sourceText;
    charJsonLabel.textContent = file.name;
    // Deselect any preset — it's been overridden by the upload.
    presetSelect.value = "";
    const activeTab = document.querySelector(".tab-nav button.active")?.dataset.tab;
    if (activeTab && tabCharState[activeTab]) {
      tabCharState[activeTab].preset = "";
      tabCharState[activeTab].sourceText = sourceText;
      tabCharState[activeTab].jsonLabel = file.name;
    }
    scheduleRender();
  } catch (err) {
    charSourceInfo.textContent = `JSON parse error: ${err.message || err}`;
  }
}

charJsonInput.addEventListener("change", (e) => handleCharJsonFile(e.target.files?.[0]));
["dragenter", "dragover"].forEach((ev) =>
  charJsonDrop.addEventListener(ev, (e) => { e.preventDefault(); charJsonDrop.classList.add("dragover"); })
);
["dragleave", "drop"].forEach((ev) =>
  charJsonDrop.addEventListener(ev, (e) => { e.preventDefault(); charJsonDrop.classList.remove("dragover"); })
);
charJsonDrop.addEventListener("drop", (e) => {
  const f = e.dataTransfer?.files?.[0];
  if (f) handleCharJsonFile(f);
});

resetBtn.addEventListener("click", () => {
  for (const group of ["body_params", "bone_lengths", "blendshapes"]) {
    for (const [k, ref] of Object.entries(sliderRefs[group])) {
      settings[group][k] = ref.def.default;
      ref.range.value = String(ref.def.default);
      ref.num.value = String(ref.def.default);
    }
  }
  // Reset is make-tab only (button is inside data-tab-show="make"). Clear
  // the make tab's preset/JSON source too so the Character panel truthfully
  // reflects "no source".
  presetSelect.value = "";
  charSourceInfo.textContent = "";
  charJsonInput.value = "";
  charJsonLabel.textContent =
    window.i18n?.t("character.json_drop") || "Upload character JSON (optional)";
  if (tabCharState.make) {
    tabCharState.make.preset = "";
    tabCharState.make.sourceText = "";
    tabCharState.make.jsonLabel = null;
  }
  scheduleRender();
});

exportFbxBtn.addEventListener("click", async () => {
  if (!currentJobId) { fbxInfo.textContent = "先にポーズを推定してください"; return; }
  exportFbxBtn.disabled = true;
  fbxInfo.textContent = "Blender subprocess 起動中... (初回は数秒かかる)";
  try {
    const t0 = performance.now();
    const r = await fetch("/api/export_fbx", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ job_id: currentJobId, settings }),
    });
    if (!r.ok) throw new Error(`HTTP ${r.status}: ${await r.text()}`);
    const j = await r.json();
    const ms = Math.round(performance.now() - t0);
    // Server always writes to tmp/rigged.fbx; offer a meaningful save name
    // so the user-side Save dialog does not default to "rigged.fbx".
    const stamp = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
    const savedAs = `sam3d_rigged_${stamp}.fbx`;
    const a = document.createElement("a");
    a.href = j.fbx_url;
    a.download = savedAs;
    document.body.appendChild(a);
    a.click();
    a.remove();
    fbxInfo.textContent = `FBX ${j.elapsed_sec}s (wall ${ms}ms) — saved as ${savedAs}`;
  } catch (e) {
    console.error(e);
    fbxInfo.textContent = `FBX export error: ${e.message || e}`;
  } finally {
    exportFbxBtn.disabled = false;
  }
});

// ---------------------------------------------------------------------------
// Inference lock — aborts the in-flight fetch and freezes tab navigation so
// the user can't switch contexts mid-run. Client-side abort drops the
// response; the server keeps grinding on the current request until
// completion. (True server-side cancellation would require threading an
// abort signal through the model forward pass.)
// ---------------------------------------------------------------------------

let currentAbortController = null;
let inferenceLocked = false;

function _lockTabs(lock) {
  document.querySelectorAll(".tab-nav button[data-tab]").forEach((b) => {
    if (!b.classList.contains("active")) b.disabled = lock;
  });
}

function beginInference(cancelBtn) {
  currentAbortController = new AbortController();
  inferenceLocked = true;
  if (cancelBtn) cancelBtn.hidden = false;
  _lockTabs(true);
  return currentAbortController.signal;
}

function endInference(cancelBtn) {
  inferenceLocked = false;
  if (cancelBtn) cancelBtn.hidden = true;
  currentAbortController = null;
  _lockTabs(false);
}

function cancelInference() {
  if (currentAbortController) currentAbortController.abort();
}

runCancelBtn.addEventListener("click", cancelInference);

// ---------------------------------------------------------------------------
// Pipeline run
// ---------------------------------------------------------------------------

runBtn.addEventListener("click", async () => {
  if (!selectedFile) return;
  runBtn.disabled = true;
  statusEl.textContent = "processing…";
  statusEl.classList.add("busy"); statusEl.classList.remove("ok", "err");
  runInfo.textContent = "推論実行中…";

  const signal = beginInference(runCancelBtn);
  const form = new FormData();
  form.append("image", selectedFile);
  try {
    const r = await fetch("/api/process", { method: "POST", body: form, signal });
    if (!r.ok) throw new Error(`HTTP ${r.status}: ${await r.text()}`);
    const j = await r.json();
    currentJobId = j.job_id;
    tabJobIds.image = j.job_id;
    runInfo.textContent = window.i18n?.t("input.done") || "推定終了";
    characterUnlocked = true;
    // Inference landed — unlock the image-tab FBX download and re-render
    // the now-posed body with whatever character the user was viewing.
    exportFbxBtn.hidden = false;
    scheduleRender();

    statusEl.textContent = `done — ${j.elapsed_sec}s`;
    statusEl.classList.add("ok"); statusEl.classList.remove("busy", "err");
  } catch (err) {
    if (err.name === "AbortError") {
      runInfo.textContent = window.i18n?.t("input.cancelled") || "キャンセルしました";
      statusEl.textContent = "cancelled";
      statusEl.classList.remove("busy", "ok", "err");
    } else {
      console.error(err);
      runInfo.textContent = `エラー: ${err.message || err}`;
      statusEl.textContent = "failed";
      statusEl.classList.add("err"); statusEl.classList.remove("busy", "ok");
    }
  } finally {
    runBtn.disabled = false;
    endInference(runCancelBtn);
  }
});

// ---------------------------------------------------------------------------
// Startup
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Preset Pack Admin (Phase 5)
// ---------------------------------------------------------------------------

const packSelect = $("pack-select");
const packSwitchBtn = $("pack-switch-btn");
const packNewName = $("pack-new-name");
const packCloneBtn = $("pack-clone-btn");
const packDeleteBtn = $("pack-delete-btn");
const packActiveLabel = $("pack-active-label");
const fbxStatusEl = $("fbx-status");
const fbxInput = $("fbx-input");
const fbxDrop = $("fbx-drop");
const fbxLabel = $("fbx-label");
const fbxRebuildBtn = $("fbx-rebuild-btn");
const fbxRebuildInfo = $("fbx-rebuild-info");

async function refreshPackList() {
  try {
    const r = await fetch("/api/preset_packs");
    const j = await r.json();
    packSelect.innerHTML = "";
    for (const name of (j.packs || [])) {
      const opt = document.createElement("option");
      opt.value = name; opt.textContent = name;
      if (name === j.active) opt.textContent += "  (active)";
      packSelect.appendChild(opt);
    }
    packSelect.value = j.active;
    packActiveLabel.textContent = `active: ${j.active}`;
  } catch (e) { console.error(e); }
}

async function refreshFbxStatus() {
  try {
    const r = await fetch("/api/fbx_status");
    const j = await r.json();
    const mtime = j.fbx_mtime ? new Date(j.fbx_mtime * 1000).toLocaleString() : "-";
    const size = j.fbx_size ? `${(j.fbx_size / (1024 * 1024)).toFixed(2)} MB` : "-";
    const staleHint = j.stale ? "  ⚠ npz stale, rebuild required" : "";
    fbxStatusEl.textContent = `FBX: ${size} (${mtime})${staleHint}`;
  } catch (_e) {}
}

packSwitchBtn.addEventListener("click", async () => {
  const name = packSelect.value;
  if (!name) return;
  try {
    const r = await fetch("/api/preset_packs/active", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ name }),
    });
    if (!r.ok) throw new Error(await r.text());
    await refreshPackList();
    // Slider schema (and blendshape list) depends on active pack — refresh.
    await refreshSliderSchemaPreservingValues();
  } catch (e) { console.error(e); packActiveLabel.textContent = `switch failed: ${e.message || e}`; }
});

packCloneBtn.addEventListener("click", async () => {
  const target = packNewName.value.trim();
  if (!target) { return; }
  try {
    const r = await fetch("/api/preset_packs/clone", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ source: packSelect.value, target }),
    });
    if (!r.ok) throw new Error(await r.text());
    packNewName.value = "";
    await refreshPackList();
    packSelect.value = target;
  } catch (e) { packActiveLabel.textContent = `clone failed: ${e.message || e}`; }
});

packDeleteBtn.addEventListener("click", async () => {
  const name = packSelect.value;
  if (!name || !confirm(`Delete pack "${name}"? (cannot be undone)`)) return;
  try {
    const r = await fetch(`/api/preset_packs/${encodeURIComponent(name)}`, { method: "DELETE" });
    if (!r.ok) throw new Error(await r.text());
    await refreshPackList();
    await refreshSliderSchemaPreservingValues();
  } catch (e) { packActiveLabel.textContent = `delete failed: ${e.message || e}`; }
});

fbxInput.addEventListener("change", async (e) => {
  const file = e.target.files?.[0];
  if (!file) return;
  fbxLabel.textContent = `uploading ${file.name}...`;
  const form = new FormData();
  form.append("fbx", file);
  try {
    const r = await fetch("/api/fbx_upload", { method: "POST", body: form });
    if (!r.ok) throw new Error(await r.text());
    fbxLabel.textContent = `${file.name} ← uploaded, click Rebuild`;
    await refreshFbxStatus();
  } catch (err) {
    fbxLabel.textContent = `upload failed: ${err.message || err}`;
  }
});

["dragenter", "dragover"].forEach((ev) =>
  fbxDrop.addEventListener(ev, (e) => { e.preventDefault(); fbxDrop.classList.add("dragover"); })
);
["dragleave", "drop"].forEach((ev) =>
  fbxDrop.addEventListener(ev, (e) => { e.preventDefault(); fbxDrop.classList.remove("dragover"); })
);
fbxDrop.addEventListener("drop", (e) => {
  const f = e.dataTransfer.files?.[0];
  if (f) { fbxInput.files = e.dataTransfer.files; fbxInput.dispatchEvent(new Event("change")); }
});

fbxRebuildBtn.addEventListener("click", async () => {
  fbxRebuildBtn.disabled = true;
  fbxRebuildInfo.textContent = "Running Blender (30-60s)…";
  try {
    const r = await fetch("/api/rebuild_blendshapes", {
      method: "POST", headers: { "content-type": "application/json" }, body: "{}",
    });
    if (!r.ok) throw new Error(await r.text());
    const j = await r.json();
    fbxRebuildInfo.textContent =
      `OK: ${j.num_blendshapes} blendshapes, ${j.num_vertex_jsons} vertex JSONs (${j.elapsed_sec}s)`;
    await refreshFbxStatus();
    // Slider list may have grown / shrunk.
    await refreshSliderSchemaPreservingValues();
  } catch (e) {
    fbxRebuildInfo.textContent = `rebuild failed: ${e.message || e}`;
  } finally {
    fbxRebuildBtn.disabled = false;
  }
});

async function refreshSliderSchemaPreservingValues() {
  // Snapshot the in-memory values so shape-key list changes don't wipe user edits.
  const snapshot = JSON.parse(JSON.stringify(settings));
  try {
    const r = await fetch("/api/slider_schema");
    schema = await r.json();
    buildSliders(bodyParamsEl, "body_params", schema.body_params);
    buildSliders(boneLengthsEl, "bone_lengths", schema.bone_lengths);
    buildSliders(blendshapesEl, "blendshapes", schema.blendshapes);
    applySettingsToUi(snapshot);
  } catch (e) { console.error("slider schema refresh failed:", e); }
  if (currentJobId) scheduleRender();
}

// ---------------------------------------------------------------------------
// Video → Animated FBX
// ---------------------------------------------------------------------------

const videoInput = $("video-input");
const videoDrop = $("video-drop");
const videoLabel = $("video-label");
const videoInfo = $("video-info");
const videoRunBtn = $("video-run-btn");
const videoCancelBtn = $("video-cancel-btn");
const videoRunInfo = $("video-run-info");
const videoDownloadBtn = $("video-download-btn");
const videoDownloadInfo = $("video-download-info");
let selectedVideo = null;
// Motion cache id returned by /api/infer_motion. While set, character
// tweaks re-run /api/build_animated_fbx instead of the pose/image pipeline.
let currentMotionId = null;
// Most recent animated-FBX URL (for the Download button).
let currentAnimatedFbxUrl = null;
let videoRebuildInFlight = false;
let videoRebuildDirty = false;

function onVideoChosen(file) {
  if (!file) return;
  selectedVideo = file;
  videoLabel.textContent = file.name;
  videoRunBtn.disabled = false;
  videoInfo.textContent = `${(file.size / (1024 * 1024)).toFixed(1)} MB`;
  // Probe the video so the user sees fps / frame count before kicking off export.
  const form = new FormData();
  form.append("video", file);
  fetch("/api/probe_video", { method: "POST", body: form })
    .then((r) => r.ok ? r.json() : null)
    .then((info) => {
      if (info) {
        videoInfo.textContent =
          `${(file.size / (1024 * 1024)).toFixed(1)} MB · ${info.width}x${info.height} · ${info.fps.toFixed(1)} fps · ${info.frame_count || "?"} frames · ${info.duration_sec.toFixed(1)} s`;
      }
    })
    .catch(() => {});
}

videoInput.addEventListener("change", (e) => onVideoChosen(e.target.files?.[0]));
["dragenter", "dragover"].forEach((ev) =>
  videoDrop.addEventListener(ev, (e) => {
    e.preventDefault(); videoDrop.classList.add("dragover");
  })
);
["dragleave", "drop"].forEach((ev) =>
  videoDrop.addEventListener(ev, (e) => {
    e.preventDefault(); videoDrop.classList.remove("dragover");
  })
);
videoDrop.addEventListener("drop", (e) => {
  const f = e.dataTransfer.files?.[0];
  if (f) onVideoChosen(f);
});

// Phase 1: "モーションを推定" — runs only the slow SAM3 + SAM3DBody pass
// and caches the raw per-frame params. Phase 2 (FBX build) is triggered
// immediately afterward with the currently-selected character settings
// so the user sees the rig animate right away; subsequent preset/JSON
// changes call only Phase 2.
videoCancelBtn.addEventListener("click", cancelInference);

videoRunBtn.addEventListener("click", async () => {
  if (!selectedVideo) return;
  videoRunBtn.disabled = true;
  // Button is shown again only when rebuildAnimatedFbx finishes successfully.
  videoDownloadBtn.hidden = true;
  videoRunInfo.textContent = "Running motion inference (minutes for long clips)…";
  const signal = beginInference(videoCancelBtn);
  const form = new FormData();
  form.append("video", selectedVideo);
  form.append("fps", $("video-fps").value || "0");
  const maxF = Number($("video-max-frames").value || "0");
  if (maxF > 0) form.append("max_frames", String(maxF));
  form.append("stride", $("video-stride").value || "1");
  form.append("bbox_threshold", $("video-bbox-thr").value || "0.8");
  try {
    const t0 = performance.now();
    const r = await fetch("/api/infer_motion", { method: "POST", body: form, signal });
    if (!r.ok) throw new Error(`HTTP ${r.status}: ${await r.text()}`);
    const j = await r.json();
    currentMotionId = j.motion_id;
    videoRunInfo.textContent = window.i18n?.t("video.done") || "推定終了";
    // Motion is cached — immediately bake and loop the animation on top of
    // the character the user was already viewing (default MHR body before
    // any preset change, or their chosen preset / uploaded JSON).
    await rebuildAnimatedFbx(signal);
  } catch (e) {
    if (e.name === "AbortError") {
      videoRunInfo.textContent = window.i18n?.t("video.cancelled") || "キャンセルしました";
    } else {
      console.error(e);
      videoRunInfo.textContent = `video FBX error: ${e.message || e}`;
    }
  } finally {
    videoRunBtn.disabled = false;
    endInference(videoCancelBtn);
  }
});

// Phase 2: (re)build the animated FBX for the cached motion using the
// current Character settings. Called after motion inference completes and
// again whenever the user swaps preset/JSON while on the video tab. An
// optional AbortSignal plumbs the main-run cancel button through to Phase 2.
async function rebuildAnimatedFbx(signal = null) {
  if (!currentMotionId) return;
  if (videoRebuildInFlight) { videoRebuildDirty = true; return; }
  videoRebuildInFlight = true;
  videoRebuildDirty = false;
  const label0 = videoRunInfo.textContent;
  try {
    const t0 = performance.now();
    const r = await fetch("/api/build_animated_fbx", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        motion_id: currentMotionId,
        // Always bake the VIDEO tab's cached character — not whichever tab
        // happens to be active when the recursion in `finally` fires.
        settings: tabSettings.video,
        root_motion_mode: $("video-root-mode").value,
      }),
      signal,
    });
    if (!r.ok) throw new Error(`HTTP ${r.status}: ${await r.text()}`);
    const j = await r.json();
    // A newer settings change (e.g. preset Load) was queued while this
    // rebuild was in flight — skip swapping the stale result into the
    // viewer so the user doesn't see a flash of the default body before
    // the queued preset-aware rebuild catches up.
    if (videoRebuildDirty) return;
    currentAnimatedFbxUrl = j.fbx_url;
    videoDownloadBtn.hidden = false;
    const ms = Math.round(performance.now() - t0);
    const name = j.fbx_url.split("/").pop();
    videoRunInfo.innerHTML =
      `motion ${j.num_frames} frames · FBX build ${Math.round(ms/1000)}s: ${name}`;
    try {
      await viewer.loadFbxAnimated(j.fbx_url, `video-${Date.now()}`);
      renderAvailable = true;
      const savePngBtn = document.getElementById("save-render-btn");
      if (savePngBtn) savePngBtn.disabled = false;
      if (overlay.textContent) overlay.textContent = "";
    } catch (err) {
      console.warn("FBX playback failed:", err);
    }
  } catch (e) {
    if (e.name === "AbortError") {
      // Propagate — the videoRunBtn handler reports the cancellation label.
      throw e;
    }
    console.error(e);
    videoRunInfo.textContent = `FBX build error: ${e.message || e}`;
  } finally {
    videoRebuildInFlight = false;
    if (videoRebuildDirty) rebuildAnimatedFbx();
  }
}

// "FBX をダウンロード" — save the currently-playing animation to disk.
// The server re-uses tmp/animated.fbx so we tag the download with a
// timestamped filename; browsers honour the `download` attribute.
videoDownloadBtn.addEventListener("click", () => {
  if (!currentAnimatedFbxUrl) return;
  const stamp = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
  const savedAs = `sam3d_animated_${stamp}.fbx`;
  const a = document.createElement("a");
  a.href = currentAnimatedFbxUrl;
  a.download = savedAs;
  document.body.appendChild(a);
  a.click();
  a.remove();
  if (videoDownloadInfo) videoDownloadInfo.textContent = `saved as ${savedAs}`;
});

// ---------------------------------------------------------------------------

// Wire the PNG save button on the 3D viewer overlay. Stays disabled until a
// mesh has been rendered at least once (otherwise you get a blank viewport PNG).
document.getElementById("save-render-btn")?.addEventListener("click", async () => {
  if (!renderAvailable) return;
  const base = currentJobId ? `render_${currentJobId}` : `render_${Date.now()}`;
  try {
    await viewer.savePng(`${base}.png`);
  } catch (e) {
    console.error("save PNG failed:", e);
  }
});

// Character Make tab: download the current slider values as a standalone
// character JSON (same schema as chara_settings_presets/*.json, drop-in
// compatible with Preset Pack's Load menu).
document.getElementById("make-download-btn")?.addEventListener("click", () => {
  // Download the make tab's cached parameters explicitly — settings still
  // points there while the make tab is active, but pinning the slot is
  // safer if this ever runs from another callsite.
  const payload = JSON.stringify(tabSettings.make, null, 2);
  const blob = new Blob([payload], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const stamp = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
  const a = document.createElement("a");
  a.href = url;
  a.download = `character_${stamp}.json`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 5_000);
  const info = document.getElementById("make-download-info");
  if (info) info.textContent = window.i18n?.t("make.downloaded") || "JSON saved";
});

async function boot() {
  // Pull feature flags first so the tab nav can reflect the server's config.ini.
  try {
    const r = await fetch("/api/features");
    if (r.ok) {
      const f = await r.json();
      featureFlags.preset_pack_admin = !!f.preset_pack_admin;
      featureFlags.debug = !!f.debug;
    }
  } catch (_e) {}
  // Hide the Preset Admin tab button entirely when the flag is off.
  const adminBtn = document.querySelector('.tab-nav button[data-tab="admin"]');
  if (adminBtn) {
    adminBtn.hidden = !featureFlags.preset_pack_admin;
    if (!featureFlags.preset_pack_admin) {
      adminBtn.title = "Disabled in config.ini ([features] preset_pack_admin)";
    }
  }
  // Health panel is a debug-only surface. Drop health polling entirely when
  // it isn't visible so we don't stream CUDA info to an invisible <pre>.
  const healthSection = document.getElementById("health-section");
  if (healthSection) healthSection.hidden = !featureFlags.debug;
  initTabs();
  try {
    const r = await fetch("/api/slider_schema");
    schema = await r.json();
    buildSliders(bodyParamsEl, "body_params", schema.body_params);
    buildSliders(boneLengthsEl, "bone_lengths", schema.bone_lengths);
    buildSliders(blendshapesEl, "blendshapes", schema.blendshapes);
  } catch (e) { console.error("slider schema load failed:", e); }
  await refreshPresets();
  await refreshPackList();
  await refreshFbxStatus();
  // Still poll in debug mode so the Health panel reflects the live state;
  // in non-debug mode we skip polling to keep the network quiet.
  if (featureFlags.debug) {
    pollHealth();
    setInterval(pollHealth, 15_000);
  }
}

boot();
