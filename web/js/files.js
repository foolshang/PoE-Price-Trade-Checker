/* Files: the sound files the player picked (kept in IndexedDB, one per slot label: 1-6 = the NeverSink tab's numbered
 * sounds, S/A/B/C/G/Tablet/Map/Gem = the Whitelist tab's, Q = the quest style, shared), the game
 * folder (File System Access API: Chrome / Edge, the handle is remembered in IndexedDB) and the download / zip. */
"use strict";
(() => {
const P = window.PFG;

P.sha256Hex = async (bytes) => {
  try {
    const d = await crypto.subtle.digest("SHA-256", bytes);
    return [...new Uint8Array(d)].map((b) => b.toString(16).padStart(2, "0")).join("");
  } catch (e) { return ""; }                      // no crypto.subtle: names alone decide "same file"
};

// ---- sound slots ----
const SLOTS = ["1", "2", "3", "4", "5", "6", "S", "A", "B", "C", "Q", "G", "Tablet", "Map", "Gem"];
P.sounds = {
  mem: {},
  async load() {
    for (const label of SLOTS) {
      const v = await P.idb.get("sounds", label);
      if (v && v.bytes) {
        const bytes = new Uint8Array(v.bytes);
        this.mem[label] = { name: v.name, type: v.type || "", bytes, hash: await P.sha256Hex(bytes) };
      }
    }
  },
  async setBytes(label, name, type, bytes) {
    this.mem[label] = { name, type: type || "", bytes, hash: await P.sha256Hex(bytes) };
    const copy = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
    await P.idb.put("sounds", label, { name, type: type || "", bytes: copy });
  },
  async setFile(label, file) {
    await this.setBytes(label, file.name, file.type, new Uint8Array(await file.arrayBuffer()));
    return file.name;
  },
  async clear(label) { delete this.mem[label]; await P.idb.del("sounds", label); },
  /** the file of one slot into another (an old S / A / B file becomes sound 1 / 2 / 3 as well) */
  async copy(from, to) {
    const v = this.mem[from];
    if (v && !this.mem[to]) await this.setBytes(to, v.name, v.type, v.bytes);
  },
  name(label) { return this.mem[label] ? this.mem[label].name : ""; },
  hashes() {
    const out = {};
    for (const [k, v] of Object.entries(this.mem)) if (v.hash) out[k] = v.hash;
    return out;
  },
};

// ---- the game folder (File System Access API) ----
// The folder of each game has its own handle (IndexedDB key = "poe1" / "poe2") and its own name in Documents\My Games.
const FOLDER_NAME = { poe1: "Path of Exile", poe2: "Path of Exile 2" };
const sameName = (a, b) => String(a || "").trim().toLowerCase() === String(b || "").trim().toLowerCase();

const FS = {
  supported: typeof window.showDirectoryPicker === "function",
  handle: null,
  state: "none",                                   // none | granted | prompt (remembered, permission must be confirmed)
  folderName(game) { return FOLDER_NAME[game] || ""; },
  /** true when the picked folder is called what the game's own folder is called (a player's own folder name is allowed too,
   *  after a question - see app.js chooseFolder) */
  nameOk(game, name) { return sameName(name, FOLDER_NAME[game]); },
  /** A handle kept under another key (an older page kept one handle for both games) goes to the game its folder name says;
   *  one with another name stays where it is (it is not guessed). A game that already has its own handle keeps it. */
  async migrateLegacy() {
    let keys = [];
    try { keys = await P.idb.keys("handles"); } catch (e) { return; }
    for (const k of keys) {
      if (k === "poe1" || k === "poe2") continue;
      const h = await P.idb.get("handles", k);
      const target = h && Object.keys(FOLDER_NAME).find((g) => sameName(h.name, FOLDER_NAME[g]));
      if (!target) continue;
      if (!(await P.idb.get("handles", target))) await P.idb.put("handles", target, h);
      await P.idb.del("handles", k);
    }
  },
  async init(game) {
    this.handle = null; this.state = "none";
    if (!this.supported) return this.state;
    await this.migrateLegacy();
    const h = await P.idb.get("handles", game);
    if (h && typeof h.queryPermission === "function") {
      this.handle = h;
      try { this.state = (await h.queryPermission({ mode: "readwrite" })) === "granted" ? "granted" : "prompt"; }
      catch (e) { this.state = "prompt"; }
    }
    return this.state;
  },
  /** the folder picker of a game (starts in Documents, remembers where it was per game); returns the handle, stores nothing */
  choose(game) {
    return window.showDirectoryPicker({ id: `poe-filter-${game}`, mode: "readwrite", startIn: "documents" });
  },
  /** make `h` the folder of `game` (this one is the current one) */
  async adopt(game, h) {
    this.handle = h; this.state = "granted";
    await P.idb.put("handles", game, h);
  },
  async pick(game) { await this.adopt(game, await this.choose(game)); },
  async grant() {                                  // must run from a click
    if (!this.handle) return false;
    this.state = (await this.handle.requestPermission({ mode: "readwrite" })) === "granted" ? "granted" : "prompt";
    return this.state === "granted";
  },
  async forget(game) { this.handle = null; this.state = "none"; await P.idb.del("handles", game); },
  get ready() { return this.state === "granted" && !!this.handle; },
  get name() { return this.handle ? this.handle.name : ""; },
  async names() {
    const out = [];
    for await (const [name, h] of this.handle.entries()) if (h.kind === "file") out.push(name);
    return out;
  },
  /** the .filter files of the folder: [{name, size, head}] (head = the first 600 characters, enough to tell who made it) */
  async list() {
    const out = [];
    for await (const [name, h] of this.handle.entries()) {
      if (h.kind !== "file" || !/\.filter$/i.test(name)) continue;
      const f = await h.getFile();
      out.push({ name, size: f.size, head: await f.slice(0, 600).text() });
    }
    return out;
  },
  async getFile(name) { return (await this.handle.getFileHandle(name)).getFile(); },
  async exists(name) {
    try { await this.handle.getFileHandle(name); return true; } catch (e) { return false; }
  },
  async read(name) {
    const fh = await this.handle.getFileHandle(name);
    return new Uint8Array(await (await fh.getFile()).arrayBuffer());
  },
  async write(name, data) {
    const fh = await this.handle.getFileHandle(name, { create: true });
    const w = await fh.createWritable();
    try { await w.write(data); } finally { await w.close(); }
  },
  /** {file name: content hash or null} for what the sound planner needs: every file of the folder is listed, the
   *  content is hashed only for the names the sounds will use (like the desktop copy_sounds). */
  async existingFor(wanted) {
    const out = {};
    for (const name of await this.names()) {
      out[name] = wanted.has(name) ? await P.sha256Hex(await this.read(name)) : null;
    }
    return out;
  },
};
P.FS = FS;

// ---- download (when no folder is connected, or the browser cannot write to one) ----
/** Bytes of what to hand to the player: the .filter alone, or a zip with the sound files the filter names. */
P.packDownload = (filterText, filterName, soundsByLabel) => {
  const dest = {};                                  // file name -> bytes (one file once, even for several slots)
  for (const [label, name] of Object.entries(soundsByLabel || {})) {
    const s = P.sounds.mem[label];
    if (s && !dest[name]) dest[name] = s.bytes;
  }
  const names = Object.keys(dest);
  if (!names.length) {
    return { kind: "filter", filename: `${filterName}.filter`, mime: "text/plain;charset=utf-8",
             bytes: new TextEncoder().encode(P.toCrlf(filterText)) };
  }
  const zipBytes = P.glue.make_zip(P.toCrlf(filterText), filterName, names, names.map((n) => dest[n])).toJs();
  return { kind: "zip", filename: `${filterName}.zip`, mime: "application/zip", bytes: zipBytes, names };
};

/** Write the filter + the sounds that have to be written into the connected folder. `res` = glue.generate result. */
P.writeToFolder = async (res, filterName) => {
  const written = [];
  for (const [label, final] of res.copies || []) {
    const s = P.sounds.mem[label];
    if (!s) continue;
    await FS.write(final, s.bytes);
    written.push(final);
  }
  await FS.write(`${filterName}.filter`, new TextEncoder().encode(P.toCrlf(res.text)));
  written.push(`${filterName}.filter`);
  return written;
};
})();
