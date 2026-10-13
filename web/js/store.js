/* Storage: localStorage for settings (same key as before, same keys as the desktop config), IndexedDB for the
 * sound files (key = slot label S/A/B/Q/G/Tablet/Map) and for the game folder handles (key = game). Every access is
 * guarded: private mode / blocked storage -> the page keeps working from memory only. */
"use strict";
(() => {
const P = window.PFG;
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
P.store = store;
P.readJson = (key, fallback) => {
  try { const v = JSON.parse(store.get(key)); return v && typeof v === "object" ? v : fallback; }
  catch (e) { return fallback; }
};
P.KEY_CFG = "poeFilterGen.cfg";
P.KEY_GAME = "poeFilterGen.game";
P.loadCfg = () => P.readJson(P.KEY_CFG, {});
P.saveCfg = (cfg) => store.set(P.KEY_CFG, JSON.stringify(cfg));

// ---- IndexedDB: "sounds" (label -> {name,type,bytes}) and "handles" (game -> FileSystemDirectoryHandle) ----
let idbOk = true;
const memIdb = { sounds: new Map(), handles: new Map() };
function idbOpen() {
  return new Promise((resolve, reject) => {
    try {
      const req = indexedDB.open("poe-filter-gen", 2);
      req.onupgradeneeded = () => {
        const db = req.result;
        if (!db.objectStoreNames.contains("sounds")) db.createObjectStore("sounds");
        if (!db.objectStoreNames.contains("handles")) db.createObjectStore("handles");
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error || new Error("indexedDB error"));
      req.onblocked = () => reject(new Error("indexedDB blocked"));
    } catch (e) { reject(e); }
  });
}
async function idbDo(storeName, mode, fn) {
  const db = await idbOpen();
  try {
    return await new Promise((resolve, reject) => {
      const tx = db.transaction(storeName, mode);
      const out = fn(tx.objectStore(storeName));
      tx.oncomplete = () => resolve(out && out.result);
      tx.onerror = () => reject(tx.error);
      tx.onabort = () => reject(tx.error || new Error("aborted"));
    });
  } finally { db.close(); }
}
P.idb = {
  async get(storeName, key) {
    if (idbOk) { try { const v = await idbDo(storeName, "readonly", (s) => s.get(key)); if (v !== undefined) return v; } catch (e) { idbOk = false; } }
    return memIdb[storeName].get(key);
  },
  async put(storeName, key, value) {
    memIdb[storeName].set(key, value);
    if (!idbOk) return false;
    try { await idbDo(storeName, "readwrite", (s) => s.put(value, key)); return true; } catch (e) { idbOk = false; return false; }
  },
  async del(storeName, key) {
    memIdb[storeName].delete(key);
    if (!idbOk) return;
    try { await idbDo(storeName, "readwrite", (s) => s.delete(key)); } catch (e) { idbOk = false; }
  },
  /** every key of a store (the in-memory fallback included) */
  async keys(storeName) {
    const out = new Set(memIdb[storeName].keys());
    if (idbOk) {
      try { (await idbDo(storeName, "readonly", (s) => s.getAllKeys())).forEach((k) => out.add(k)); } catch (e) { idbOk = false; }
    }
    return [...out];
  },
  get ok() { return idbOk; },
};
})();
