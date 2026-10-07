/* PoE Filter Generator - web UI.
 *
 * JS does UI, fetching, persistence and the download only. Every filter decision
 * (what to fetch, the whitelist/tier text, categories, rules) is the shared Python
 * (poe_price_trade/filter_gen.py + filter_core.py) running in Pyodide, called
 * through web/glue.py. Config uses the same keys as the desktop config["filter_gen"]. */
"use strict";
(() => {
const PYODIDE_VERSION = "0.27.7";
const HUB = "https://storage.googleapis.com/poe-data-hub";
const RARITIES = ["Normal", "Magic", "Rare", "Unique"];
const RAR_ABBR = { Normal: "N", Magic: "M", Rare: "R", Unique: "U" };
const NS_CHECK_HOURS = 24;
const KEY_CFG = "poeFilterGen.cfg", KEY_GAME = "poeFilterGen.game";
const KEY_NS = "poeFilterGen.ns.";
const SOUND_TIERS = ["S", "A", "B"];                 // C is always silent
const BIG_SOUND = 5 * 1024 * 1024;
const DIRS = { poe1: "Documents\\My Games\\Path of Exile", poe2: "Documents\\My Games\\Path of Exile 2" };

const $ = (s, r = document) => r.querySelector(s);
const clone = (o) => JSON.parse(JSON.stringify(o));

// ---- storage: every access guarded (private mode / storage blocked -> memory only) ----
const mem = new Map();
const store = {
  get(k) {
    try { const v = localStorage.getItem(k); if (v !== null) return v; } catch (e) { /* blocked */ }
    return mem.has(k) ? mem.get(k) : null;
  },
  set(k, v, keepInMemory = true) {
    if (keepInMemory) mem.set(k, v);
    try { localStorage.setItem(k, v); return true; } catch (e) { return false; }
  },
  del(k) { mem.delete(k); try { localStorage.removeItem(k); } catch (e) { /* blocked */ } },
  keys() { try { return Object.keys(localStorage); } catch (e) { return []; } },
};
function readJson(key, fallback) {
  try { const v = JSON.parse(store.get(key)); return v && typeof v === "object" ? v : fallback; }
  catch (e) { return fallback; }
}
const loadCfg = () => readJson(KEY_CFG, {});
const saveCfg = (cfg) => store.set(KEY_CFG, JSON.stringify(cfg));

// ---- state ----
let py = null, glue = null, K = null;           // Pyodide, glue module, constants from Python
let game = "poe2";
let custom = [];                                // [{name, rarities}] = source of truth for typed names
let catExclude = {};                            // {category: [excluded names]}
let gemNames = [];                              // poe1 chosen gems
let gemAll = null;                              // poe1 autocomplete list (lazy)
let lastResult = null;                          // filter text (CRLF) of the last Generate
let lastDownload = null;                        // {kind, filename, mime, bytes}
const soundMem = {};                            // tier -> {name, type, bytes: Uint8Array} (this session)
let idbOk = true;                               // false -> sounds live in memory only
const hubCache = {};                            // game -> {text, at}

// ---- sounds: IndexedDB ("poe-filter-gen" / "sounds", key S|A|B), memory fallback ----
function idbOpen() {
  return new Promise((resolve, reject) => {
    try {
      const req = indexedDB.open("poe-filter-gen", 1);
      req.onupgradeneeded = () => req.result.createObjectStore("sounds");
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error || new Error("indexedDB error"));
      req.onblocked = () => reject(new Error("indexedDB blocked"));
    } catch (e) { reject(e); }
  });
}
async function idbDo(mode, fn) {
  const db = await idbOpen();
  try {
    return await new Promise((resolve, reject) => {
      const tx = db.transaction("sounds", mode);
      const out = fn(tx.objectStore("sounds"));
      tx.oncomplete = () => resolve(out && out.result);
      tx.onerror = () => reject(tx.error);
      tx.onabort = () => reject(tx.error || new Error("aborted"));
    });
  } finally { db.close(); }
}
async function loadSounds() {
  try {
    for (const t of SOUND_TIERS) {
      const v = await idbDo("readonly", (s) => s.get(t));
      if (v && v.bytes) {
        const bytes = new Uint8Array(v.bytes);
        soundMem[t] = { name: v.name, type: v.type || "", bytes, hash: await sha256Hex(bytes) };
      }
    }
  } catch (e) { idbOk = false; }
}
async function sha256Hex(bytes) {
  try {
    const d = await crypto.subtle.digest("SHA-256", bytes);
    return [...new Uint8Array(d)].map((b) => b.toString(16).padStart(2, "0")).join("");
  } catch (e) { return ""; }                      // no crypto.subtle: names alone decide "same file"
}
async function putSound(tier, name, type, bytes) {
  soundMem[tier] = { name, type: type || "", bytes, hash: await sha256Hex(bytes) };
  if (!idbOk) return;
  try {
    const copy = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
    await idbDo("readwrite", (s) => s.put({ name, type: type || "", bytes: copy }, tier));
  } catch (e) { idbOk = false; }
}
async function clearSound(tier) {
  delete soundMem[tier];
  if (!idbOk) return;
  try { await idbDo("readwrite", (s) => s.delete(tier)); } catch (e) { idbOk = false; }
}

// ---- log ----
function addLog(msg, tag = "info") {
  const box = $("#log");
  if (!box) return;
  const line = document.createElement("div");
  line.className = tag;
  line.textContent = msg;
  box.appendChild(line);
  box.scrollTop = box.scrollHeight;
}

// ---- fetching ----
async function fetchText(url, label) {
  let resp;
  try { resp = await fetch(url); } catch (e) { throw new Error(`${label} fetch failed (${url}): ${e.message || e}`); }
  if (!resp.ok) throw new Error(`${label} HTTP ${resp.status}: ${url}`);
  return resp.text();
}
async function getHub(g) {
  const c = hubCache[g];
  if (c && Date.now() - c.at < 5 * 60 * 1000) return c.text;
  const url = `${HUB}/${g}/prices/latest.json`;
  const text = await fetchText(url, "hub");
  try { JSON.parse(text); } catch (e) { throw new Error(`hub fetch failed (${url}): ${e.message}`); }
  hubCache[g] = { text, at: Date.now() };
  return text;
}

// NeverSink base: same flow as neversink_source.fetch_base_filter, cache = localStorage.
const nsLast = (g) => readJson(`${KEY_NS}last.${g}`, {});
const nsTextKey = (g, tag, s) => `${KEY_NS}text.${g}|${tag}|${s}`;
async function nsLatestTag(g) {
  try {
    const resp = await fetch(glue.ns_latest_url(g), { headers: { Accept: "application/vnd.github+json" } });
    if (!resp.ok) return null;
    return (await resp.json()).tag_name || null;
  } catch (e) { return null; }
}
function nsCachePut(g, tag, s, text) {
  const prefix = `${KEY_NS}text.${g}|`;
  const drop = () => store.keys().filter((k) => k.startsWith(prefix) && !k.startsWith(`${prefix}${tag}|`))
    .forEach((k) => store.del(k));
  drop();                                        // older tags of this game are dead weight
  if (!store.set(nsTextKey(g, tag, s), text, false)) {
    store.keys().filter((k) => k.startsWith(KEY_NS + "text.")).forEach((k) => store.del(k));   // quota: start over
    store.set(nsTextKey(g, tag, s), text, false);      // still too big -> simply not cached
  }
}
async function fetchBase(g, strictness, force) {
  const last = nsLast(g);
  let stale = true;
  if (last.checked_at) {
    const hrs = (Date.now() - Date.parse(last.checked_at)) / 3600000;
    stale = !(hrs <= NS_CHECK_HOURS);            // NaN (bad date) -> stale
  }
  let tag = last.tag || null;
  if (force || stale || !tag) {
    const fresh = await nsLatestTag(g);
    if (fresh) {
      tag = fresh;
      store.set(`${KEY_NS}last.${g}`, JSON.stringify({ tag, checked_at: new Date().toISOString() }));
    }
  }
  if (tag) {
    const key = nsTextKey(g, tag, strictness);
    const cached = store.get(key);
    if (cached && !force) return [cached, tag];
    try {
      const text = await fetchText(glue.ns_file_url(g, tag, strictness), "neversink");
      nsCachePut(g, tag, strictness, text);
      return [text, tag];
    } catch (e) {
      if (cached) return [cached, tag];
    }
  }
  const suffix = `|${strictness}`;               // last resort: any cached tag for this game+strictness
  const keys = store.keys().filter((k) => k.startsWith(`${KEY_NS}text.${g}|`) && k.endsWith(suffix)).sort();
  if (keys.length) {
    const k = keys[keys.length - 1];
    const t = store.get(k);
    if (t) return [t, k.slice(`${KEY_NS}text.${g}|`.length, -suffix.length)];
  }
  return [null, null];
}

// ---- generate ----
async function runGenerate(cfg, g, refresh) {
  const cfgJson = JSON.stringify(cfg);
  const plan = JSON.parse(glue.plan(cfgJson, g));
  const logs = [];
  const log = (m, t = "info") => { logs.push([t, m]); addLog(m, t); };
  let hubText = null, baseText = null, baseTag = null;
  if (plan.mode === "whitelist") {
    if (plan.hub) {
      try { hubText = await getHub(g); }
      catch (e) { log(`⚠ ดึง hub ไม่ได้ ใช้เฉพาะ currency/ชื่อที่ติ๊ก: ${e.message}`, "warn"); }
    }
  } else {
    log(`⟳ ดึง NeverSink base filter (${g})…`, "info");
    const s = cfg[`strictness_${g}`];
    [baseText, baseTag] = await fetchBase(g, Number.isInteger(s) ? s : 2, !!refresh);
    if (baseText === null) log("⚠ ไม่มี NeverSink base filter ให้ใช้ (GitHub ล่ม + ไม่มี cache)", "warn");
    else log(`✓ NeverSink base filter พร้อม (tag=${baseTag})`, "ok");
  }
  const hashes = {};
  for (const t of SOUND_TIERS) if (soundMem[t] && soundMem[t].hash) hashes[t] = soundMem[t].hash;
  const res = JSON.parse(glue.generate(cfgJson, g, hubText, baseText, baseTag, log, JSON.stringify(hashes)));
  if (res.status === "error") { log(`✗ ${res.message}`, "err"); return { status: "error", logs }; }
  if (res.status === "none") return { status: "none", logs };
  if (res.mode === "whitelist") log(`✓ filter โหมดโชว์เฉพาะ (${res.count} รายการ)`, "ok");
  else log("✓ สร้าง filter แล้ว", "ok");
  log("Filter ready — ดาวน์โหลดแล้ววางในโฟลเดอร์เกม", "ok");
  return { status: "ok", text: res.text, mode: res.mode, baseTag: res.base_tag, sounds: res.sounds || {}, logs };
}
const toCrlf = (t) => t.replace(/\r?\n/g, "\r\n");    // same bytes as the desktop apps write on Windows

// ---- form ----
function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
const rarTag = (rs) => {
  const x = RARITIES.filter((r) => rs.includes(r));
  return x.length ? x.map((r) => RAR_ABBR[r]).join("/") : "N";
};

function renderForm() {
  const cfg = loadCfg();
  const cats = K.categories[game] || [];
  const uncut = K.gem_uncut[game] || [];
  const savedCats = new Set(cfg[`whitelist_cats_${game}`] || []);
  const rawS = cfg[`strictness_${game}`];
  const strictness = Number.isInteger(rawS) && rawS >= 0 && rawS < K.levels.length ? rawS : 2;

  catExclude = {};
  for (const [c, v] of Object.entries(cfg[`whitelist_cat_exclude_${game}`] || {})) if (Array.isArray(v) && v.length) catExclude[c] = [...v];
  custom = [];
  for (const it of cfg[`whitelist_custom_${game}`] || []) {
    if (typeof it === "string") custom.push({ name: it, rarities: [...RARITIES] });
    else if (it && it.name) {
      const rs = RARITIES.filter((r) => (it.rarities || []).includes(r));
      custom.push({ name: it.name, rarities: rs.length ? rs : ["Normal"] });
    }
  }
  gemNames = [...(cfg[`whitelist_gem_names_${game}`] || [])];
  const savedGems = cfg[`whitelist_gem_uncut_${game}`] || {};

  const catBoxes = cats.map((c) =>
    `<label><input type="checkbox" class="cat" data-cat="${esc(c)}" ${savedCats.has(c) ? "checked" : ""}> ${esc(c)}</label>`).join("");
  const gemHtml = uncut.length
    ? uncut.map((b) => `<div class="row"><label><input type="checkbox" class="gem-on" data-base="${esc(b)}" ${b in savedGems ? "checked" : ""}> ${esc(b)}</label>
        <label>level ≥ <input type="text" inputmode="numeric" class="lv gem-lv" data-base="${esc(b)}" value="${esc(b in savedGems ? savedGems[b] : 1)}"></label></div>`).join("")
    : `<div class="row"><input type="text" id="gem-name" size="24" placeholder="ชื่อ gem"><button type="button" id="gem-add">เพิ่ม</button><button type="button" id="gem-del">ลบที่เลือก</button></div>
       <select id="gem-sugg" size="5"></select>
       <select id="gem-list" size="4" multiple></select>`;

  $("#form").innerHTML = `
    <fieldset><legend>Tier mode (NeverSink)</legend>
      <div class="row"><label>NeverSink Strictness:
        <select id="f-strictness">${K.levels.map((l, i) => `<option value="${i}" ${i === strictness ? "selected" : ""}>${i} - ${esc(l)}</option>`).join("")}</select></label></div>
      <div class="muted">Alert sounds (S/A/B — C is always silent):</div>
      <p class="muted">(เสียง S/A/B = tier สูงสุด/รอง/กลาง ของ NeverSink)</p>
      ${SOUND_TIERS.map((t) => `<div class="row snd-row" data-tier="${t}">Tier ${t} sound:
        <input type="file" class="snd-file" data-tier="${t}" accept="audio/*,.mp3,.wav,.ogg" hidden>
        <button type="button" class="secondary snd-pick" data-tier="${t}">เลือกไฟล์…</button>
        <span class="snd-name muted" data-tier="${t}"></span>
        <button type="button" class="secondary snd-clear" data-tier="${t}">Clear</button></div>`).join("")}
      <p class="muted snd-note" id="snd-note" hidden>เบราว์เซอร์ไม่ให้จำไฟล์ ต้องเลือกใหม่เมื่อเปิดหน้าใหม่</p>
      <p class="muted">(มีเสียง = ดาวน์โหลดเป็น zip: แตกไฟล์ทั้งหมดลงโฟลเดอร์ filter ของเกม)</p>
    </fieldset>
    <fieldset><legend>Whitelist mode (show only)</legend>
      <div class="row"><label><input type="checkbox" id="wl-enabled" ${cfg.whitelist_enabled ? "checked" : ""}> โหมดโชว์เฉพาะ (whitelist) — ซ่อนที่เหลือ</label></div>
      <div class="row"><label><input type="checkbox" id="wl-gold" ${cfg.whitelist_gold ? "checked" : ""}> Gold</label>
        <label>จำนวน ≥ <input type="text" inputmode="numeric" id="wl-gold-min" size="6" value="${esc(cfg.whitelist_gold_min ?? 0)}"></label></div>
      <div class="muted">หมวด (โชว์ทั้งหมวด):</div>
      <div class="grid3">${catBoxes}
        <label><input type="checkbox" id="wl-unique" ${cfg.whitelist_unique_all ? "checked" : ""}> Unique (ทุกตัว)</label></div>
      <div class="row"><button type="button" id="btn-refine" class="secondary">ปรับรายการในหมวด…</button></div>
      <div class="muted">ชื่อที่พิมพ์เอง (contains) + เลือก rarity:</div>
      <div class="row"><input type="text" id="cust-name" size="24"><button type="button" id="cust-add">เพิ่ม</button><button type="button" id="cust-del">ลบที่เลือก</button></div>
      <div class="row">${RARITIES.map((r) => `<label><input type="checkbox" class="rar" data-rar="${r}" ${r === "Normal" ? "checked" : ""}> ${r}</label>`).join("")}
        <button type="button" id="cust-setrar" class="secondary">ตั้ง rarity ที่เลือก</button></div>
      <select id="cust-list" size="4" multiple></select>
      <p class="muted">(เปิดโหมดนี้ = ข้าม filter ปกติ, generate เฉพาะที่เลือก)</p>
      <div class="muted">Gem:</div>${gemHtml}
    </fieldset>`;
  renderCustom();
  renderGemList();
  renderSounds();
}

function renderSounds() {
  for (const t of SOUND_TIERS) {
    const s = soundMem[t], span = $(`.snd-name[data-tier="${t}"]`);
    if (!span) continue;
    span.textContent = s ? `${s.name} (${Math.max(1, Math.round(s.bytes.length / 1024))} KB)` +
      (s.bytes.length > BIG_SOUND ? " — ไฟล์ใหญ่กว่า 5 MB" : "") : "";
  }
  const note = $("#snd-note");
  if (note) note.hidden = idbOk;
}

function renderCustom() {
  const sel = $("#cust-list");
  sel.innerHTML = "";
  custom.forEach((e, i) => {
    const o = document.createElement("option");
    o.value = i;
    o.textContent = `${e.name}   [${rarTag(e.rarities)}]`;
    sel.appendChild(o);
  });
}
function renderGemList() {
  const sel = $("#gem-list");
  if (!sel) return;
  sel.innerHTML = "";
  gemNames.forEach((n) => { const o = document.createElement("option"); o.textContent = n; o.value = n; sel.appendChild(o); });
}
const currentRarities = () => {
  const rs = RARITIES.filter((r) => $(`.rar[data-rar="${r}"]`).checked);
  return rs.length ? rs : ["Normal"];
};
const selected = (sel) => [...sel.selectedOptions].map((o) => o.index);

function collect() {
  const cfg = loadCfg();
  const g = game;
  cfg[`strictness_${g}`] = parseInt($("#f-strictness").value, 10);
  for (const t of SOUND_TIERS) cfg[`sound_${t.toLowerCase()}`] = soundMem[t] ? soundMem[t].name : "";
  cfg.whitelist_enabled = $("#wl-enabled").checked;
  cfg.whitelist_gold = $("#wl-gold").checked;
  cfg.whitelist_unique_all = $("#wl-unique").checked;
  const gm = $("#wl-gold-min").value.trim();
  cfg.whitelist_gold_min = /^[+-]?\d+$/.test(gm) ? Math.max(0, parseInt(gm, 10)) : 0;
  if ((K.gem_uncut[g] || []).length) {
    const out = {};
    document.querySelectorAll(".gem-on").forEach((cb) => {
      if (!cb.checked) return;
      const v = $(`.gem-lv[data-base="${cb.dataset.base}"]`).value.trim();
      out[cb.dataset.base] = /^[+-]?\d+$/.test(v) ? Math.max(1, parseInt(v, 10)) : 1;
    });
    cfg[`whitelist_gem_uncut_${g}`] = out;
  } else {
    cfg[`whitelist_gem_names_${g}`] = [...gemNames];
  }
  const ex = {};
  for (const [c, v] of Object.entries(catExclude)) if (v.length) ex[c] = [...v].sort();
  cfg[`whitelist_cat_exclude_${g}`] = ex;
  cfg[`whitelist_cats_${g}`] = [...document.querySelectorAll(".cat")].filter((c) => c.checked).map((c) => c.dataset.cat);
  cfg[`whitelist_custom_${g}`] = custom.map((e) => ({ name: e.name, rarities: [...e.rarities] }));
  return cfg;
}
const persist = () => { if (K) saveCfg(collect()); };

function wireForm() {
  const addCustom = () => {
    const inp = $("#cust-name"), text = inp.value.trim();
    if (!text) return;
    if (!custom.some((e) => e.name.toLowerCase() === text.toLowerCase())) custom.push({ name: text, rarities: currentRarities() });
    inp.value = "";
    renderCustom(); persist();
  };
  $("#cust-add").addEventListener("click", addCustom);
  $("#cust-name").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); addCustom(); } });
  $("#cust-del").addEventListener("click", () => {
    selected($("#cust-list")).sort((a, b) => b - a).forEach((i) => custom.splice(i, 1));
    renderCustom(); persist();
  });
  $("#cust-list").addEventListener("change", () => {            // selecting a name loads its rarities back
    const s = selected($("#cust-list"));
    if (!s.length || !custom[s[0]]) return;
    RARITIES.forEach((r) => { $(`.rar[data-rar="${r}"]`).checked = custom[s[0]].rarities.includes(r); });
  });
  $("#cust-setrar").addEventListener("click", () => {
    const s = selected($("#cust-list"));
    if (!s.length) return;
    const rs = currentRarities();
    s.forEach((i) => { if (custom[i]) custom[i].rarities = [...rs]; });
    renderCustom();
    s.forEach((i) => { $("#cust-list").options[i].selected = true; });
    persist();
  });
  $("#btn-refine").addEventListener("click", openRefine);
  document.querySelectorAll(".snd-pick").forEach((b) => b.addEventListener("click", () => $(`.snd-file[data-tier="${b.dataset.tier}"]`).click()));
  document.querySelectorAll(".snd-file").forEach((inp) => inp.addEventListener("change", async () => {
    const f = inp.files && inp.files[0];
    if (!f) return;
    await putSound(inp.dataset.tier, f.name, f.type, new Uint8Array(await f.arrayBuffer()));
    inp.value = "";
    renderSounds(); persist();
    if (f.size > BIG_SOUND) addLog(`⚠ ไฟล์เสียง ${f.name} ใหญ่กว่า 5 MB (ยังใช้ได้)`, "warn");
  }));
  document.querySelectorAll(".snd-clear").forEach((b) => b.addEventListener("click", async () => {
    await clearSound(b.dataset.tier);
    renderSounds(); persist();
  }));

  if ($("#gem-name")) wireGems();
}

// poe1 gem autocomplete: click = fill the box, double-click = add
async function ensureGemNames() {
  if (gemAll) return;
  try { gemAll = JSON.parse(glue.gem_names(await fetchText(`${HUB}/${game}/gems.json`, "hub"))); }
  catch (e) { addLog(`⚠ โหลดรายชื่อ gem ไม่ได้ (พิมพ์เองได้): ${e.message}`, "warn"); gemAll = []; }
}
function wireGems() {
  const name = $("#gem-name"), sugg = $("#gem-sugg");
  const add = () => {
    const nm = name.value.trim();
    if (!nm) return;
    if (!gemNames.some((x) => x.toLowerCase() === nm.toLowerCase())) gemNames.push(nm);
    name.value = ""; sugg.innerHTML = "";
    renderGemList(); persist();
  };
  name.addEventListener("input", async () => {
    await ensureGemNames();
    const kw = name.value.trim().toLowerCase();
    sugg.innerHTML = "";
    if (!kw) return;
    for (const n of gemAll) {
      if (!n.toLowerCase().includes(kw)) continue;
      const o = document.createElement("option"); o.textContent = n; o.value = n; sugg.appendChild(o);
      if (sugg.options.length >= 20) break;
    }
  });
  name.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); add(); } });
  sugg.addEventListener("change", () => { if (sugg.value) name.value = sugg.value; });
  sugg.addEventListener("dblclick", add);
  $("#gem-add").addEventListener("click", add);
  $("#gem-del").addEventListener("click", () => {
    selected($("#gem-list")).sort((a, b) => b - a).forEach((i) => gemNames.splice(i, 1));
    renderGemList(); persist();
  });
}

// ---- refine popup ----
async function openRefine() {
  const cats = [...document.querySelectorAll(".cat")].filter((c) => c.checked).map((c) => c.dataset.cat);
  if (!cats.length) { addLog("ติ๊กหมวดก่อน แล้วค่อยปรับรายการ", "warn"); return; }
  let hubText;
  try { hubText = await getHub(game); }
  catch (e) { addLog(`ต้องต่อ hub เพื่อดูรายการ: ${e.message}`, "warn"); return; }
  const dlg = $("#refine"), sel = $("#refine-cat"), q = $("#refine-q"), list = $("#refine-list");
  sel.innerHTML = cats.map((c) => `<option>${esc(c)}</option>`).join("");
  q.value = "";
  const names = (cat) => JSON.parse(glue.category_names(hubText, cat));
  const rebuild = () => {
    const cat = sel.value, ex = new Set(catExclude[cat] || []), kw = q.value.trim().toLowerCase();
    list.innerHTML = "";
    for (const nm of names(cat)) {
      if (kw && !nm.toLowerCase().includes(kw)) continue;
      const lab = document.createElement("label"), cb = document.createElement("input");
      cb.type = "checkbox"; cb.checked = !ex.has(nm);
      cb.addEventListener("change", () => {
        const s = new Set(catExclude[cat] || []);
        if (cb.checked) s.delete(nm); else s.add(nm);
        if (s.size) catExclude[cat] = [...s].sort(); else delete catExclude[cat];
        persist();
      });
      lab.append(cb, document.createTextNode(" " + nm));
      list.appendChild(lab);
    }
    list.scrollTop = 0;
  };
  sel.onchange = rebuild; q.oninput = rebuild;
  $("#refine-all").onclick = () => { delete catExclude[sel.value]; persist(); rebuild(); };
  $("#refine-none").onclick = () => { catExclude[sel.value] = names(sel.value); persist(); rebuild(); };
  $("#refine-close").onclick = () => dlg.close();
  rebuild();
  dlg.showModal();
}

// ---- page ----
function setGame(g) {
  if (K && $("#f-strictness")) persist();       // keep the game we are leaving (nothing to save before the first render)
  game = g;
  store.set(KEY_GAME, g);
  document.querySelectorAll(".game-toggle button").forEach((b) => b.classList.toggle("active", b.dataset.game === g));
  gemAll = null;
  renderForm(); wireForm();
  $("#result").hidden = true; lastResult = null; lastDownload = null;
}

async function onGenerate(refresh) {
  const btns = [$("#btn-generate"), $("#btn-refresh")];
  btns.forEach((b) => { b.disabled = true; });
  $("#result").hidden = true;
  try {
    const cfg = collect(); saveCfg(cfg);
    const r = await runGenerate(cfg, game, refresh);
    if (r.status === "ok") await showResult(r);
  } catch (e) {
    addLog(`✗ generate ล้มเหลว: ${e.message || e}`, "err");
  } finally { btns.forEach((b) => { b.disabled = false; }); }
}
// Single .filter, or a zip (filter + the sounds the filter was built with) when any sound is in use.
async function makeDownload(r) {
  const text = toCrlf(r.text);
  const tiers = SOUND_TIERS.filter((t) => r.sounds && r.sounds[t] && soundMem[t]);
  if (!tiers.length) {
    return { kind: "filter", filename: "poe-checker.filter", mime: "text/plain;charset=utf-8",
             bytes: new TextEncoder().encode(text), names: [] };
  }
  const seen = new Set(), names = [], datas = [];             // one zip entry per distinct file name
  for (const t of tiers) {
    if (seen.has(r.sounds[t])) continue;
    seen.add(r.sounds[t]); names.push(r.sounds[t]); datas.push(soundMem[t].bytes);
  }
  const proxy = glue.make_zip(text, names, datas);
  const bytes = proxy.toJs();
  if (proxy.destroy) proxy.destroy();
  return { kind: "zip", filename: "poe-checker-filter.zip", mime: "application/zip", bytes, names };
}
async function showResult(r) {
  lastResult = toCrlf(r.text);
  lastDownload = await makeDownload(r);
  const zip = lastDownload.kind === "zip";
  $("#btn-download").textContent = `ดาวน์โหลด ${lastDownload.filename}`;
  $("#result-info").textContent = `${r.mode === "whitelist" ? "โหมดโชว์เฉพาะ" : "Tier mode" + (r.baseTag ? ` (NeverSink ${r.baseTag})` : "")} · ${lastResult.length.toLocaleString()} ตัวอักษร` +
    (zip ? ` · เสียง ${lastDownload.names.join(", ")}` : "");
  $("#result-steps").innerHTML = zip
    ? `<li>กด “ดาวน์โหลด” แล้วเก็บไฟล์ <code>poe-checker-filter.zip</code></li>
    <li>แตกไฟล์ทั้งหมดลงโฟลเดอร์ <code>${esc(DIRS[game])}</code> (ทับไฟล์เดิม)</li>
    <li>ในเกม: Options → Game → เลือก filter “poe-checker” (หรือกด reload filter)</li>
    <li class="muted">ปุ่ม Copy คัดลอกเฉพาะข้อความ filter — ไฟล์เสียงต้องได้จาก zip</li>`
    : `<li>กด “ดาวน์โหลด” แล้วเก็บไฟล์ <code>poe-checker.filter</code></li>
    <li>วางไฟล์ไว้ใน <code>${esc(DIRS[game])}</code></li>
    <li>ในเกม: Options → Game → เลือก filter “poe-checker” (หรือกด reload filter)</li>`;
  $("#result").hidden = false;
}
function download() {
  if (!lastDownload) return;
  const url = URL.createObjectURL(new Blob([lastDownload.bytes], { type: lastDownload.mime }));
  const a = document.createElement("a");
  a.href = url; a.download = lastDownload.filename;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}
async function copy() {
  if (lastResult === null) return;
  try { await navigator.clipboard.writeText(lastResult); addLog("✓ คัดลอกแล้ว (เฉพาะข้อความ filter — เสียงต้องได้จาก zip)", "ok"); }
  catch (e) { addLog("คัดลอกไม่ได้ — ใช้ปุ่มดาวน์โหลดแทน", "warn"); }
}

async function boot() {
  const t0 = performance.now();
  py = await loadPyodide({ indexURL: `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/` });
  py.FS.mkdirTree("/home/pyodide/poe_price_trade");
  const get = async (p) => {
    const r = await fetch(p);
    if (!r.ok) throw new Error(`${p}: HTTP ${r.status}`);
    return r.text();
  };
  py.FS.writeFile("/home/pyodide/poe_price_trade/__init__.py", "");
  py.FS.writeFile("/home/pyodide/poe_price_trade/filter_gen.py", await get("py/filter_gen.py"));
  py.FS.writeFile("/home/pyodide/poe_price_trade/filter_core.py", await get("py/filter_core.py"));
  py.FS.writeFile("/home/pyodide/poe_price_trade/filter_style.py", await get("py/filter_style.py"));
  py.FS.writeFile("/home/pyodide/poe_price_trade/filter_whitelist.py", await get("py/filter_whitelist.py"));
  py.FS.writeFile("/home/pyodide/glue.py", await get("glue.py"));
  py.runPython("import sys; sys.path.insert(0, '/home/pyodide')");
  glue = py.pyimport("glue");
  K = JSON.parse(glue.constants());
  await loadSounds();
  const saved = store.get(KEY_GAME);
  game = saved === "poe1" || saved === "poe2" ? saved : "poe2";
  document.querySelectorAll(".game-toggle button").forEach((b) => b.addEventListener("click", () => setGame(b.dataset.game)));
  $("#form").addEventListener("input", persist);      // once: the form element outlives every re-render
  $("#form").addEventListener("change", persist);
  $("#btn-generate").addEventListener("click", () => onGenerate(false));
  $("#btn-refresh").addEventListener("click", () => onGenerate(true));
  $("#btn-download").addEventListener("click", download);
  $("#btn-copy").addEventListener("click", copy);
  $("#btn-reset").addEventListener("click", async () => {
    [KEY_CFG].forEach((k) => store.del(k));
    for (const t of SOUND_TIERS) await clearSound(t);
    store.keys().filter((k) => k.startsWith(KEY_NS)).forEach((k) => store.del(k));
    setGame(game);
    addLog("ล้างค่าแล้ว — กลับเป็นค่าเริ่มต้น", "info");
  });
  setGame(game);
  $("#loading").hidden = true;
  $("#app").hidden = false;
  $("#btn-generate").disabled = false;
  $("#btn-refresh").disabled = false;
  return Math.round(performance.now() - t0);
}

const ready = boot().then((ms) => { window.PoeFilterWeb.bootMs = ms; }).catch((e) => {
  $("#loading").hidden = true;
  const box = $("#fatal");
  box.hidden = false;
  box.textContent = `โหลดไม่สำเร็จ: ${e.message || e} — ลอง refresh หน้านี้ หรือดาวน์โหลดโปรแกรม exe แทน`;
  throw e;
});
// hooks for tests / debugging
window.PoeFilterWeb = { ready, runGenerate, collect: () => collect(), setGame, toCrlf,
  rerender: () => { renderForm(); wireForm(); },
  setSound: async (tier, name, bytes) => { await putSound(tier, name, "", Uint8Array.from(bytes)); renderSounds(); },
  clearSound: async (tier) => { await clearSound(tier); renderSounds(); },
  clearAllSounds: async () => { for (const t of SOUND_TIERS) await clearSound(t); renderSounds(); },
  makeDownload,
  soundNames: () => Object.fromEntries(Object.entries(soundMem).map(([t, s]) => [t, s.name])),
  get idbOk() { return idbOk; },       // re-read storage into the form (no save first)
  clearStorage: () => { mem.clear(); try { localStorage.clear(); } catch (e) { /* blocked */ } },
  resetCaches: () => { for (const k of Object.keys(hubCache)) delete hubCache[k]; },
  get game() { return game; }, bootMs: null };
})();
