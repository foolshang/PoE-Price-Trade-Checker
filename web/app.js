/* PoE Filter Generator - web page (v0.11.x feature set of the desktop program).
 *
 * JS does UI, fetching, storage and files only. Every filter decision (tiers, categories, the filter text, what the
 * Status says) is the shared Python (poe_price_trade/*, web/glue.py) running in Pyodide. Settings use the same keys
 * as the desktop config["filter_gen"], kept in localStorage. */
"use strict";
(() => {
const P = window.PFG;
const { $, h } = P;
const PYODIDE_VERSION = "0.27.7";
const DIRS = { poe1: "Documents\\My Games\\Path of Exile", poe2: "Documents\\My Games\\Path of Exile 2" };
const J = (s) => JSON.parse(s);

let py = null;
let game = "poe2";
let tab = "tier";
P.cfg = {};
P.data = { hub: null, base: null, baseTag: null, names: null, namesFrom: "" };
let lastDownload = null, lastText = "";
let loadingLists = false;

// ---------------------------------------------------------------- settings
const collectCfg = (mode) => {
  const cfg = P.cfg;
  P.tabNs.collect(cfg, game);
  P.tabWl.collect(cfg);
  Object.assign(cfg, J(P.glue.wl_config()));                    // wl_v2 + every wl_* / whitelist_* key of the model
  cfg.whitelist_enabled = (mode || tab) === "whitelist";
  cfg.last_tab = mode || tab;
  return cfg;
};
const persist = P.debounce(() => { if (P.glue) P.saveCfg(collectCfg()); }, 250);
const changed = () => { P.tabNs.refreshQ(P.cfg); P.tabNs.refreshSounds(); P.tabWl.refreshSounds(); persist(); };

// ---------------------------------------------------------------- lists (hub + NeverSink s2 + real names)
async function loadLists(force) {
  if (loadingLists) return;
  loadingLists = true;
  const g = game;
  P.log("⟳ โหลดรายการ whitelist (hub + NeverSink)…", "info");
  P.tabWl.setLoading(true);
  let hub = null, base = null, tag = null, names = null, from = "";
  try { hub = await P.getHub(g); } catch (e) { P.log(`⚠ ดึง hub ไม่ได้: ${e.message}`, "warn"); }
  try { [base, tag] = await P.fetchBase(g, 2, !!force); } catch (e) { P.log(`⚠ ดึง NeverSink base filter ไม่ได้: ${e.message}`, "warn"); }
  if (!base) P.log("⚠ ไม่มี NeverSink base filter (GitHub ล่ม + ไม่มี cache) — รายการ tier เริ่มต้นไม่ครบ", "warn");
  const n = await P.getNames(g);
  if (n) { names = n.text; from = n.from; } else P.log("⚠ ไม่มีรายชื่อไอเท็มจริง (hub และ snapshot ใช้ไม่ได้) — ชื่อที่ NeverSink ไม่มีจะไม่ถูกเขียน", "warn");
  loadingLists = false;
  if (g !== game) return;                                        // the game was switched while loading
  P.data = { hub, base, baseTag: tag, names, namesFrom: from };
  P.logAll(J(P.glue.wl_load(hub, base || "", names)));
  if (from) P.log(`รายชื่อไอเท็มจริง: จาก snapshot ที่มากับหน้านี้${tag ? ` · NeverSink ${tag}` : ""}`, "info");
  P.tabWl.reload();
  P.tabNs.showTag(game);
}

// ---------------------------------------------------------------- generate
const soundNamesInUse = (cfg) => {
  const out = [];
  for (const n of ["1", "2", "3", "4", "5", "6"]) if (cfg[`sound_${n}`]) out.push(cfg[`sound_${n}`]);
  const q = cfg.style_q && cfg.style_q.sound;
  if (q && q.kind === "file" && q.file) out.push(q.file);
  for (const s of Object.values(cfg.wl_tier_style || {})) if (s && s.sound && s.sound.kind === "file" && s.sound.file) out.push(s.sound.file);
  return out;
};

function askConflicts(conflicts) {
  return new Promise((resolve) => {
    const dlg = $("#dlg-ask");
    const decisions = {};
    const rows = conflicts.map((c) => {
      const sel = h("select", { "aria-label": `ไฟล์ ${c.name}` },
        h("option", { value: "keep" }, `เก็บไฟล์เดิมไว้ แล้วใช้ชื่อ "${c.new_name}" สำหรับไฟล์ใหม่`),
        h("option", { value: "overwrite" }, "ทับไฟล์เดิม"));
      decisions[c.name] = sel;
      return h("div", { class: "row" }, h("div", {}, `ในโฟลเดอร์ filter มีไฟล์ "${c.name}" อยู่แล้ว แต่เป็นคนละไฟล์กับที่เลือก`), sel);
    });
    dlg.replaceChildren(h("h3", {}, "ไฟล์เสียงชื่อซ้ำ"), ...rows,
      h("div", { class: "actions" }, h("button", { type: "button", id: "ask-ok", onclick: () => {
        const out = {}; for (const [k, s] of Object.entries(decisions)) out[k] = s.value;
        dlg.close(); resolve(out);
      } }, "ตกลง")));
    dlg.addEventListener("cancel", (e) => e.preventDefault(), { once: true });
    dlg.showModal();
  });
}

async function generate(mode, refresh) {
  const cfg = collectCfg(mode);
  P.saveCfg(cfg);
  const key = mode === "whitelist" ? "filter_name_whitelist" : "filter_name_tier";
  const v = J(P.glue.validate_name(cfg[key]));
  if (v.error) { P.log(`✗ ชื่อ filter ใช้ไม่ได้: ${v.error}`, "err"); return; }
  const name = v.name || cfg[key];
  setBusy(true);
  try {
    let hub = null, base = null, tag = null, names = null;
    if (mode === "whitelist") {
      if (refresh) await loadLists(true);
      ({ hub, base, baseTag: tag, names } = P.data);
      if (!base) { P.log("⚠ ไม่มี NeverSink base filter — whitelist ไม่มี tier เริ่มต้น ไม่ generate", "warn"); return; }
    } else {
      P.log(`⟳ ดึง NeverSink base filter (${game})…`, "info");
      const s = cfg[`strictness_${game}`];
      [base, tag] = await P.fetchBase(game, Number.isInteger(s) ? s : 2, !!refresh);
      if (base === null) { P.log("⚠ ไม่มี NeverSink base filter ให้ใช้ (GitHub ล่ม + ไม่มี cache)", "warn"); return; }
      P.log(`✓ NeverSink base filter พร้อม (tag=${tag})`, "ok");
      P.tabNs.showTag(game);
    }
    const logFn = (m, t = "info") => P.log(m, t);
    let existing = null;
    if (P.FS.ready) {
      try {
        const wanted = new Set(soundNamesInUse(cfg).map((n) => P.glue.safe_name(n)));
        existing = JSON.stringify(await P.FS.existingFor(wanted));
      } catch (e) { P.log(`⚠ อ่านโฟลเดอร์เกมไม่ได้: ${e.message}`, "warn"); existing = null; }
    }
    let decisions = {};
    let res = null;
    for (let round = 0; round < 3; round++) {
      res = J(P.glue.generate(JSON.stringify(cfg), game, hub, base, tag, logFn, JSON.stringify(P.sounds.hashes()), names, existing, JSON.stringify(decisions)));
      if (res.status !== "ask") break;
      decisions = await askConflicts(res.conflicts);
    }
    if (res.status === "error") { P.log(`✗ ${res.message}`, "err"); return; }
    if (res.status === "none") { P.log("⚠ ยังไม่ได้เลือกอะไร — ไม่ generate", "warn"); return; }
    if (res.status !== "ok") { P.log("✗ สร้าง filter ไม่สำเร็จ", "err"); return; }
    P.log(res.mode === "whitelist" ? `✓ filter โหมดโชว์เฉพาะ (${res.count} รายการ)` : "✓ สร้าง filter แล้ว", "ok");
    await deliver(res, name);
  } catch (e) {
    P.log(`✗ ${e.message || e}`, "err");
  } finally { setBusy(false); }
}

async function deliver(res, name) {
  lastText = res.text;
  const fileName = `${name}.filter`;
  if (P.FS.ready) {
    try {
      if (await P.FS.exists(fileName) && !window.confirm(`จะเขียนทับไฟล์ ${fileName} ในโฟลเดอร์ ${P.FS.name}\nด้วยค่าที่ตั้งอยู่ตอนนี้ — ต้องการต่อหรือไม่?`)) {
        P.log("ยกเลิกการเขียนทับ — ไม่ได้เขียนไฟล์", "warn"); return;
      }
      const written = await P.writeToFolder(res, name);
      P.log(`✓ เขียนลงโฟลเดอร์ ${P.FS.name}: ${written.join(", ")}`, "ok");
      P.log("Filter updated — reload in game (Options → Game)", "ok");
      showResult(null, `เขียนลงโฟลเดอร์ "${P.FS.name}" แล้ว: ${written.join(", ")}`);
      return;
    } catch (e) {
      P.log(`⚠ เขียนลงโฟลเดอร์ไม่ได้ (${e.message || e}) — ใช้ดาวน์โหลดแทน`, "warn");
    }
  }
  lastDownload = P.packDownload(res.text, name, res.sounds);
  P.log("Filter ready — ดาวน์โหลดแล้ววางในโฟลเดอร์เกม", "ok");
  showResult(lastDownload, null);
}

function showResult(dl, written) {
  $("#result").hidden = false;
  const btn = $("#btn-download");
  btn.hidden = !dl;
  if (dl) btn.textContent = dl.kind === "zip" ? `ดาวน์โหลด ${dl.filename} (filter + เสียง)` : `ดาวน์โหลด ${dl.filename}`;
  $("#btn-copy").hidden = !!written && false;
  $("#result-info").textContent = written || (dl.kind === "zip"
    ? `zip มี ${dl.names.length} ไฟล์เสียงที่ filter อ้างถึง — แตกลงโฟลเดอร์ filter ของเกม (Windows จะถามถ้าชื่อไฟล์ซ้ำ)`
    : "ไฟล์เดียว — วางในโฟลเดอร์ filter ของเกม");
  $("#result-steps").replaceChildren(...(written ? [] : [
    `วางไฟล์ใน ${DIRS[game]}`, "ในเกม: Options → Game → เลือก filter แล้ว reload"].map((t) => h("li", {}, t))));
}

function setBusy(on) {
  for (const b of P.$$("#btn-generate-tier, #btn-refresh, #btn-generate-wl, #btn-reload")) b.disabled = on;
}

// ---------------------------------------------------------------- open a filter file
async function openFile(file) {
  const text = await file.text();
  const cur = {};
  let folderFiles = [];
  if (P.FS.ready) { try { folderFiles = await P.FS.names(); } catch (e) { folderFiles = []; } }
  const res = J(P.glue.wl_open(text, file.name, game, JSON.stringify(cur), JSON.stringify(folderFiles)));
  P.logAll(res.messages);
  if (!res.ok) return;
  Object.assign(P.cfg, res.cfg);
  P.cfg.filter_name_whitelist = res.name;
  for (const [label, name] of Object.entries(res.sounds || {})) {      // the sound file sits in the connected folder
    try { await P.sounds.setBytes(label, name, "", await P.FS.read(name)); }       // the tier's own slot (the style already names it)
    catch (e) { P.log(`⚠ อ่านไฟล์เสียง ${name} จากโฟลเดอร์ไม่ได้`, "warn"); }
  }
  P.tabWl.load(P.cfg);
  P.tabWl.reload();
  P.tabNs.refreshSounds();
  showTab("whitelist");
  persist();
}

// ---------------------------------------------------------------- folder (File System Access)
/** The folder of the game picked now: the picker (called straight from the click), then the name check - PoE1 expects
 *  "Path of Exile", PoE2 "Path of Exile 2". Another name is asked about: pick again, or keep it (a player's own folder).
 *  Returns true when a folder was adopted for the game. */
async function chooseFolder() {
  const g = game;
  for (;;) {
    let handle;
    try { handle = await P.FS.choose(g); }
    catch (e) {
      if (!(e && e.name === "AbortError")) P.log(`⚠ เลือกโฟลเดอร์ไม่ได้: ${e && e.message ? e.message : e}`, "warn");
      return false;
    }
    let keep = P.FS.nameOk(g, handle.name);
    if (!keep) {
      const answer = await askFolderName(g, handle.name);
      if (answer === "again") continue;                 // (the picker is called from the click of that button)
      keep = answer === "keep";
    }
    if (!keep) return false;
    await P.FS.adopt(g, handle);
    if (g === game) refreshFolder();
    return true;
  }
}

function askFolderName(g, picked) {
  return new Promise((resolve) => {
    const dlg = $("#dlg-folder");
    const done = (v) => { dlg.close(); resolve(v); };
    dlg.replaceChildren(
      h("h3", {}, "ชื่อโฟลเดอร์ไม่ตรงกับเกม"),
      h("p", {}, `โฟลเดอร์ที่เลือกชื่อ "${picked}" แต่โฟลเดอร์ของ ${g === "poe2" ? "PoE2" : "PoE1"} ปกติชื่อ "${P.FS.folderName(g)}" `
        + `(${DIRS[g]})`),
      h("p", { class: "hint" }, "ถ้าตั้งใจใช้โฟลเดอร์ชื่อนี้ (เช่น ใช้โฟลเดอร์ของตัวเอง) เลือก \"ใช้โฟลเดอร์นี้ต่อ\""),
      h("div", { class: "actions" },
        h("button", { type: "button", id: "btn-folder-again", onclick: () => done("again") }, "เลือกใหม่"),
        h("button", { type: "button", id: "btn-folder-keep", class: "secondary", onclick: () => done("keep") }, "ใช้โฟลเดอร์นี้ต่อ"),
        h("button", { type: "button", id: "btn-folder-cancel", class: "secondary", onclick: () => done("cancel") }, "ยกเลิก")));
    dlg.addEventListener("cancel", () => resolve("cancel"), { once: true });
    dlg.showModal();
  });
}

function refreshFolder() {
  const box = $("#folder-box");
  box.hidden = !P.FS.supported;
  if (!P.FS.supported) return;
  const name = $("#folder-name");
  if (P.FS.state === "granted") { name.textContent = `${P.FS.name} — เขียนไฟล์ลงที่นี่โดยตรง`; name.className = "ok-text"; }
  else if (P.FS.state === "prompt") { name.textContent = `${P.FS.name} — ต้องยืนยันสิทธิ์อีกครั้ง`; name.className = "muted"; }
  else { name.textContent = "ยังไม่ได้เลือก — จะดาวน์โหลดเป็นไฟล์แทน"; name.className = "muted"; }
  $("#btn-folder-grant").hidden = P.FS.state !== "prompt";
  $("#btn-folder-forget").hidden = P.FS.state === "none";
  const odd = P.FS.state !== "none" && !P.FS.nameOk(game, P.FS.name);
  $("#folder-hint").textContent = `Chrome / Edge: เลือกโฟลเดอร์ ${DIRS[game]} แล้วโปรแกรมเขียน .filter และไฟล์เสียงลงไปให้เลย`
    + (odd ? ` · โฟลเดอร์ที่ใช้อยู่ชื่อ "${P.FS.name}" ไม่ใช่ "${P.FS.folderName(game)}" (ใช้ต่อได้)` : "");
}

// ---------------------------------------------------------------- tabs / game
function showTab(t) {
  tab = t;
  for (const b of P.$$(".tabs button")) b.setAttribute("aria-selected", String(b.dataset.tab === t));
  $("#pane-tier").hidden = t !== "tier";
  $("#pane-whitelist").hidden = t !== "whitelist";
  persist();
}

async function setGame(g) {
  game = g;
  P.store.set(P.KEY_GAME, g);
  for (const b of P.$$(".game-toggle button")) b.setAttribute("aria-pressed", String(b.dataset.game === g));
  const init = J(P.glue.wl_init(g, JSON.stringify(P.cfg)));
  Object.assign(P.cfg, init.updates);
  for (const n of init.notes) P.log("ℹ " + n, "warn");
  for (const [from, to] of Object.entries(init.moved || {})) await P.sounds.copy(from, to);     // the old S / A / B files -> sounds 1 / 2 / 3
  P.data = { hub: null, base: null, baseTag: null, names: null, namesFrom: "" };
  P.tabNs.load(P.cfg, g);
  P.tabWl.load(P.cfg);
  P.tabWl.reload();
  await P.FS.init(g);
  refreshFolder();
  loadLists(false);
}

// ---------------------------------------------------------------- boot
async function boot() {
  const fatal = (msg) => { $("#loading").hidden = true; const f = $("#fatal"); f.hidden = false; f.textContent = msg; };
  try {
    if (typeof loadPyodide !== "function") throw new Error("โหลด Pyodide ไม่ได้ (ต้องต่ออินเทอร์เน็ต)");
    py = await loadPyodide({ indexURL: `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/` });
    py.FS.mkdirTree("/home/pyodide/poe_price_trade");
    const get = async (p) => { const r = await fetch(p, { cache: "no-cache" }); if (!r.ok) throw new Error(`โหลด ${p} ไม่ได้ (HTTP ${r.status})`); return r.text(); };
    const manifest = JSON.parse(await get("py/manifest.json"));
    for (const f of manifest.files) py.FS.writeFile(`/home/pyodide/poe_price_trade/${f}`, await get(`py/${f}`));
    py.FS.writeFile("/home/pyodide/glue.py", await get("glue.py"));
    py.runPython("import sys; sys.path.insert(0, '/home/pyodide')");
    P.glue = py.pyimport("glue");
    P.K = J(P.glue.constants());
    $("#ver").textContent = `เวอร์ชัน ${P.K.app}`;
  } catch (e) { fatal(String(e.message || e)); return; }

  await P.sounds.load();
  P.cfg = P.loadCfg();
  const ctx = {
    cfg: P.cfg, changed, generate, openFile, gotoNsTab: () => showTab("tier"), reloadLists: () => loadLists(true), game: () => game,
    // "เปิด filter…": the folder's list / the file picker; `fallback` is the plain file input. Nothing may fail silently here:
    // a page whose files come from the browser cache in two versions has no P.openFilter - say so and use the plain input
    // (called straight from the click, so the browser lets it open)
    openFilter: async (fallback) => {
      if (typeof P.openFilter !== "function" || P.openFilterBroken) {
        if (typeof P.openFilter !== "function") P.log("⚠ หน้านี้ยังเป็นรุ่นเก่าที่ค้างใน cache (ไม่มีตัวเปิดรายการไฟล์) — กด Ctrl+F5 เพื่อโหลดใหม่ · ตอนนี้ใช้ช่องเลือกไฟล์แทน", "warn");
        return fallback();
      }
      try { await P.openFilter({ game, openFile, fallback, log: P.log, chooseFolder, dirHint: DIRS[game] }); }
      catch (e) {
        P.openFilterBroken = true;                // the next click goes straight to the plain input (it needs the click itself)
        P.log(`⚠ เปิดรายการไฟล์ไม่ได้: ${e && e.message ? e.message : e} — กด "เปิด filter…" อีกครั้งเพื่อเลือกไฟล์ด้วยช่องเลือกไฟล์`, "err");
      }
    },
  };
  P.ctx = ctx;
  P.tabNs.mount($("#pane-tier"), ctx);
  P.tabWl.mount($("#pane-whitelist"), ctx);
  for (const b of P.$$(".tabs button")) b.addEventListener("click", () => showTab(b.dataset.tab));
  for (const b of P.$$(".game-toggle button")) b.addEventListener("click", () => { if (b.dataset.game !== game) { persist(); P.saveCfg(collectCfg()); setGame(b.dataset.game); } });
  $("#btn-download").addEventListener("click", () => { if (lastDownload) P.saveBlob(lastDownload.bytes, lastDownload.filename, lastDownload.mime); });
  $("#btn-copy").addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(lastText); P.log("คัดลอกแล้ว", "ok"); } catch (e) { P.log("คัดลอกไม่ได้ (เบราว์เซอร์ไม่อนุญาต)", "warn"); }
  });
  $("#btn-folder").addEventListener("click", async () => { await chooseFolder(); refreshFolder(); });
  $("#btn-folder-grant").addEventListener("click", async () => {
    try { if (!(await P.FS.grant())) P.log("⚠ ไม่ได้รับสิทธิ์เขียนโฟลเดอร์", "warn"); } catch (e) { P.log(`⚠ ${e.message || e}`, "warn"); }
    refreshFolder();
  });
  $("#btn-folder-forget").addEventListener("click", async () => { await P.FS.forget(game); refreshFolder(); });

  $("#loading").hidden = true;
  $("#app").hidden = false;
  const g = P.store.get(P.KEY_GAME);
  showTab(P.cfg.last_tab === "whitelist" ? "whitelist" : "tier");
  await setGame(g === "poe1" || g === "poe2" ? g : "poe2");
}

P.boot = boot;
document.addEventListener("DOMContentLoaded", boot);
})();
