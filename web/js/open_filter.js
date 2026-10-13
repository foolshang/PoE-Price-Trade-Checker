/* The "เปิด filter…" button. With the game's folder connected it lists the .filter files of that folder (each marked as
 * editable - made by the Whitelist tab - or not) and opens the one clicked; "เลือกไฟล์อื่น…" is showOpenFilePicker starting
 * in that folder. Without a folder for the game picked now it opens the folder picker at once (starting in Documents, the
 * Status says which folder to choose) and shows the list of what was picked. A browser without showDirectoryPicker
 * (Firefox / Safari) keeps the old way: showOpenFilePicker in Documents, or the plain file input. A folder permission that
 * expired after a reload is asked for again with one button before the list is shown. */
"use strict";
(() => {
const P = window.PFG;
const { h } = P;

const TYPES = [{ description: "Path of Exile filter", accept: { "text/plain": [".filter"] } }];
const KIND = {
  whitelist: { label: "เปิดแก้ได้ — สร้างจากแท็บ Whitelist", ok: true },
  tier: { label: "สร้างจากแท็บ NeverSink — เปิดแก้ไม่ได้", ok: false },
  other: { label: "ไม่ได้สร้างจากโปรแกรมนี้ — เปิดแก้ไม่ได้", ok: false },
};

const canPick = () => typeof window.showOpenFilePicker === "function";
const aborted = (e) => e && e.name === "AbortError";

/** the plain file picker, started in `startIn` ("documents" or the game folder's handle) */
async function pickFile(startIn, id) {
  const [handle] = await window.showOpenFilePicker({ id, startIn, types: TYPES, multiple: false });
  return handle.getFile();
}

/** opts: game, openFile(file), fallback() (the plain input), log(text, tag), chooseFolder() -> Promise<bool> (the folder picker
 *  with the name check; called straight from the click), dirHint (the folder to choose, for the Status) */
P.openFilter = async (opts) => {
  const { game, openFile, fallback, log } = opts;
  const id = `poe-open-${game}`;
  if (!canPick()) return fallback();
  const finish = async (file) => { if (file) await openFile(file); };
  const pick = async (startIn) => {
    try { await finish(await pickFile(startIn, id)); }
    catch (e) {
      if (aborted(e)) return;
      log(`⚠ เปิดตัวเลือกไฟล์ไม่ได้: ${e.message || e}`, "warn");
      fallback();
    }
  };
  if (!P.FS.handle || P.FS.state === "none") {
    if (!(P.FS.supported && opts.chooseFolder)) return pick("documents");     // (no folder API: the old way)
    log(`ℹ เลือกโฟลเดอร์ ${opts.dirHint} ในหน้าต่างที่เปิดขึ้น แล้วรายการไฟล์จะขึ้นให้`, "info");
    if (!(await opts.chooseFolder())) return;                                   // cancelled / not adopted
  }

  const dlg = P.$("#dlg-open");
  const close = () => { if (dlg.open) dlg.close(); };
  const other = h("button", { type: "button", class: "secondary", id: "btn-open-other",
    onclick: async () => { close(); await pick(P.FS.handle); } }, "เลือกไฟล์อื่น…");
  const cancel = h("button", { type: "button", class: "secondary", id: "btn-open-close", onclick: close }, "ปิด");

  const draw = async () => {
    if (P.FS.state !== "granted") {            // the permission of the remembered folder expired: one button, then the list
      const grant = h("button", { type: "button", id: "btn-open-grant", onclick: async () => {
        try { await P.FS.grant(); } catch (e) { log(`⚠ ${e.message || e}`, "warn"); }
        await draw();
      } }, "ให้สิทธิ์โฟลเดอร์อีกครั้ง");
      dlg.replaceChildren(
        h("h3", {}, "เปิด filter"),
        h("p", {}, `ต้องยืนยันสิทธิ์โฟลเดอร์ "${P.FS.name}" อีกครั้งก่อนดูรายการไฟล์`),
        h("div", { class: "actions" }, grant, other, cancel));
      return;
    }
    let files = [];
    try { files = await P.FS.list(); } catch (e) { log(`⚠ อ่านรายการไฟล์ในโฟลเดอร์ไม่ได้: ${e.message || e}`, "warn"); }
    const rows = files.map((f) => ({ ...f, kind: KIND[P.glue.filter_kind(f.head)] ? P.glue.filter_kind(f.head) : "other" }));
    rows.sort((a, b) => (KIND[b.kind].ok - KIND[a.kind].ok) || a.name.localeCompare(b.name));
    const list = rows.length
      ? h("ul", { class: "open-list", id: "open-list" }, ...rows.map((f) => h("li", { "data-file": f.name, "data-kind": f.kind },
          h("span", { class: "nm" }, f.name),
          h("span", { class: KIND[f.kind].ok ? "ok-text" : "muted" }, KIND[f.kind].label),
          h("button", { type: "button", disabled: !KIND[f.kind].ok, "aria-label": `เปิด ${f.name}`,
            onclick: async () => {
              try { const file = await P.FS.getFile(f.name); close(); await finish(file); }
              catch (e) { log(`⚠ เปิด ${f.name} ไม่ได้: ${e.message || e}`, "warn"); }
            } }, "เปิด"))))
      : h("p", { class: "muted" }, `ไม่มีไฟล์ .filter ในโฟลเดอร์ "${P.FS.name}"`);
    dlg.replaceChildren(
      h("h3", {}, `เปิด filter จากโฟลเดอร์ "${P.FS.name}"`),
      list,
      h("div", { class: "actions" }, other, cancel));
  };
  await draw();
  dlg.showModal();
};
})();
