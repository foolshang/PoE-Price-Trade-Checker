// Browser test of the web page (Chromium via Playwright): drives every part of the UI, writes screenshots, prints one
// JSON summary line. Usage: node ui.mjs <screenshot dir>
import { chromium } from "playwright";
import fs from "fs";
import os from "os";
import path from "path";
import zlib from "zlib";
import { HERE, REPO, startServer, routeNetwork, wait } from "./harness.mjs";

const OUT = path.resolve(process.argv[2] || path.join(os.tmpdir(), "web-ui-shots"));
fs.mkdirSync(OUT, { recursive: true });
const results = [];
const check = (name, ok, detail = "") => { results.push({ name, ok: !!ok, detail: ok ? "" : String(detail).slice(0, 300) }); };
const { srv, url } = await startServer();
const calls = [];
const consoleErrors = [];

// the Chromium Playwright downloaded (any version: the page only needs a current Chrome); PW_CHROME overrides
function findChrome() {
  if (process.env.PW_CHROME) return process.env.PW_CHROME;
  const base = path.join(process.env.LOCALAPPDATA || os.homedir(), "ms-playwright");
  if (!fs.existsSync(base)) return undefined;
  const dirs = fs.readdirSync(base).filter((d) => /^chromium-\d+$/.test(d)).sort().reverse();
  for (const d of dirs) {
    for (const sub of ["chrome-win64/chrome.exe", "chrome-win/chrome.exe"]) {
      const f = path.join(base, d, sub);
      if (fs.existsSync(f)) return f;
    }
  }
  return undefined;
}
const browser = await chromium.launch({ executablePath: findChrome(), headless: true });
const context = await browser.newContext({ viewport: { width: 900, height: 1100 }, acceptDownloads: true });
await routeNetwork(context, calls);
await context.addInitScript(() => {            // a real directory handle (origin private file system) stands in for the folder picker
  // the folder picker: a real handle of the origin private file system, named like the game's folder unless a test says otherwise
  window.__dirPicks = [];
  window.__dirName = null;
  window.__dirAbort = false;
  window.showDirectoryPicker = async (o) => {
    window.__dirPicks.push({ startIn: typeof o.startIn === "string" ? o.startIn : (o.startIn && o.startIn.name), id: o.id });
    if (window.__dirAbort) throw new DOMException("closed", "AbortError");
    const name = window.__dirName || (String(o.id).endsWith("poe1") ? "Path of Exile" : "Path of Exile 2");
    return (await navigator.storage.getDirectory()).getDirectoryHandle(name, { create: true });
  };
  // the file picker: remembers how it was asked (startIn) and hands back a file of the same origin private folder
  window.__picks = [];
  window.__pickName = "wl-made.filter";
  window.showOpenFilePicker = window.__stubPick = async (o) => {
    window.__picks.push({ startIn: typeof o.startIn === "string" ? o.startIn : (o.startIn && o.startIn.name), id: o.id, multiple: o.multiple });
    const d = await (await navigator.storage.getDirectory()).getDirectoryHandle("Path of Exile 2", { create: true });
    return [await d.getFileHandle(window.__pickName, { create: true })];
  };
});
const page = await context.newPage();
page.on("console", (m) => { if (m.type() === "error" && !/favicon|Failed to load resource/.test(m.text())) consoleErrors.push(m.text()); });
page.on("pageerror", (e) => consoleErrors.push("pageerror: " + e.message));
page.on("dialog", (d) => d.accept());

const shot = (name) => page.screenshot({ path: path.join(OUT, name + ".png"), fullPage: true });
const logText = () => page.locator("#log").innerText();
const waitFor = async (fn, ms = 10000) => {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) { if (await fn()) return true; await wait(100); }
  return false;
};
const waitLog = async (needle, ms = 60000) => {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) { if ((await logText()).includes(needle)) return true; await wait(150); }
  return false;
};
const model = (fn, ...args) => page.evaluate(([f, a]) => JSON.parse(window.PFG.glue[f](...a)), [fn, args]);
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "webui-"));

// ---------------------------------------------------------------- boot + the NeverSink tab
await page.goto(url + "/");
await page.waitForSelector("#app:not([hidden])", { timeout: 120000 });
check("page boots (Pyodide + glue)", true);
check("lists load (hub + NeverSink + names)", await waitLog("โหลดรายการ whitelist แล้ว"), await logText());
check("names come from the snapshot while the hub has no file", (await logText()).includes("snapshot"), await logText());
check("the hub is never asked for a names file (snapshot only)", !calls.some((c) => c.includes("trade_names")));
check("the version is shown for bug reports", /^เวอร์ชัน web-\d+\.\d+\.\d+$/.test(await page.locator("#ver").innerText()), await page.locator("#ver").innerText());
await shot("01_neversink_tab");
check("strictness has 7 levels", (await page.locator("#pane-tier select option").count()) === 7);
check("six numbered sound rows on the NeverSink tab", (await page.locator("#pane-tier label.l").evaluateAll((l) => l.map((x) => x.textContent).filter((t) => /^เสียง \d$/.test(t)).join("|"))) === "เสียง 1|เสียง 2|เสียง 3|เสียง 4|เสียง 5|เสียง 6" && !(await page.locator("#pane-tier").innerText()).includes("Tier S sound"));

// ---------------------------------------------------------------- the Whitelist tab
await page.click("#tab-wl");
await shot("02_whitelist_start");
check("nothing works before a tier is picked", await page.locator("#tier-style").isHidden() && await page.locator("#btn-move").isDisabled());
await page.click(".tier-btns button[data-t=B]");
check("picking a tier shows its style right there (no pop-up) and enables the rest", await page.locator("#tier-style-editor").isVisible() && !(await page.locator("#btn-move").isDisabled()) && !(await page.locator("#dlg-style[open]").count()));
await page.selectOption("#pane-whitelist select[aria-label=หมวด]", { label: "Currency" });
const chaos = page.locator('table.items tr[data-key="Chaos Orb"]');
await chaos.waitFor();
const tierOf = async (key) => page.locator(`table.items tr[data-key="${key}"]`).getAttribute("data-tier");
const before = await tierOf("Chaos Orb");
await chaos.locator("input[type=checkbox]").click();
const after = await tierOf("Chaos Orb");
check("ticking a row off hides it (D)", before !== "D" && after === "D", `${before} -> ${after}`);
await chaos.locator("input[type=checkbox]").click();
check("ticking it again puts it in the active tier", (await tierOf("Chaos Orb")) === "B", await tierOf("Chaos Orb"));
// select two rows, move them to tier A
await page.click(".tier-btns button[data-t=A]");
await page.locator('table.items tr[data-key="Divine Orb"] td.name .txt').click();
await page.keyboard.down("Control");
await chaos.locator("td.name .txt").click();
await page.keyboard.up("Control");
await page.click("#btn-move");
check("move selected rows to the active tier", (await tierOf("Divine Orb")) === "A" && (await tierOf("Chaos Orb")) === "A",
  `${await tierOf("Divine Orb")} ${await tierOf("Chaos Orb")}`);
check("rows moved by hand are marked", (await chaos.locator("td.mark").innerText()).includes("ตั้งเอง"));
// tier C is a shown tier of its own, D hides
check("four tier buttons: S A B C", (await page.locator(".tier-btns button").evaluateAll((b) => b.map((x) => x.dataset.t).join(""))) === "SABC");
check("the whole-category hide button says D", (await page.locator("#btn-cat-d").innerText()).includes("D (ซ่อน)"));
await page.click(".tier-btns button[data-t=C]");
check("tier C has its own inline style editor with its sample", (await page.locator("#tier-style-editor .style-preview").innerText()).includes("ตัวอย่าง C"));
await chaos.locator("td.name .txt").click();
await page.click("#btn-move");
check("a row moved to tier C is shown (ticked) as C", (await tierOf("Chaos Orb")) === "C" && (await chaos.locator("input[type=checkbox]").isChecked()));
await chaos.locator("input[type=checkbox]").click();
check("ticking a C row off hides it as D", (await tierOf("Chaos Orb")) === "D");
await chaos.locator("input[type=checkbox]").click();
check("ticking it on again puts it in the active tier C", (await tierOf("Chaos Orb")) === "C");
await page.click(".tier-btns button[data-t=A]");
await chaos.locator("td.name .txt").click();
await page.click("#btn-move");
check("back to A for the rest of the run", (await tierOf("Chaos Orb")) === "A");
await page.fill("#pane-whitelist input[type=search]", "chaos");
await wait(400);
check("search narrows the list", (await page.locator("table.items tbody tr").count()) < 10);
await page.fill("#pane-whitelist input[type=search]", "");
await wait(300);
await shot("03_currency_list");

// the tier's style editor, inline, with opacity: every edit reaches the model at once
await page.click(".tier-btns button[data-t=B]");
await page.waitForSelector("#tier-style-editor");
await page.locator('#tier-style-editor input[aria-label="ความทึบ พื้นหลัง"]').fill("120");
await page.locator('#tier-style-editor input[aria-label="ความทึบ พื้นหลัง"]').dispatchEvent("input");
check("opacity slider follows the number", (await page.locator('#tier-style-editor input[aria-label="แถบความทึบ พื้นหลัง"]').inputValue()) === "120");
await page.locator('#tier-style-editor input[aria-label="โปร่งใส ตัวอักษร"]').check();
check("'โปร่งใส' sets opacity 0", (await page.locator('#tier-style-editor input[aria-label="ความทึบ ตัวอักษร"]').inputValue()) === "0");
await page.locator('#tier-style-editor input[aria-label="โปร่งใส ตัวอักษร"]').uncheck();
check("un-ticking restores the old opacity", (await page.locator('#tier-style-editor input[aria-label="ความทึบ ตัวอักษร"]').inputValue()) !== "0");
await shot("04_tier_style_inline_opacity");
const effB = (await model("wl_style", "B")).effective;
check("style reached the model with the opacity (no save button)", effB.bg && effB.bg[3] === 120, JSON.stringify(effB.bg));
check("the tier editor has a sound field of its own", (await page.locator('#tier-style-editor select[aria-label="ชนิดเสียง"]').count()) === 1);
// round trip: pick the tier again, the value is still there
await page.click(".tier-btns button[data-t=A]");
await page.click(".tier-btns button[data-t=B]");
check("style shows the saved opacity again", (await page.locator('#tier-style-editor input[aria-label="ความทึบ พื้นหลัง"]').inputValue()) === "120");
await page.locator('#tier-style-editor input[type=checkbox][aria-label="ใช้ส่วนนี้"]').nth(2).uncheck();      // bg off
await page.click(".tier-btns button[data-t=A]");
await page.click(".tier-btns button[data-t=B]");
check("an unticked part stays unticked after re-picking the tier", !(await page.locator('#tier-style-editor input[type=checkbox][aria-label="ใช้ส่วนนี้"]').nth(2).isChecked()));
await page.click("#btn-style-reset-B");
check("reset gives NeverSink's look back", ((await model("wl_style", "B")).effective.bg || [0, 0, 0, 0])[3] === 255 && !(((await model("wl_config")).wl_tier_style || {}).B));

// stack minimum + rarity
await page.fill('#pane-whitelist input[aria-label="โชว์เมื่อจำนวน ≥ (tier)"]', "5");
await page.locator('#pane-whitelist input[aria-label="โชว์เมื่อจำนวน ≥ (tier)"]').dispatchEvent("input");
check("tier stack minimum reaches the model", ((await model("wl_parts")).tier_stack || {}).B === 5);
// the categories the page still offers: no equipment block lists, no keys / special classes, no Jewel
const catsNow = await page.locator("#pane-whitelist select[aria-label=หมวด] option").allInnerTexts();
check("the cut categories are gone", !catsNow.some((c) => /เนื้อเรื่อง|6-link|Heist|Influenced|Gem ทั่วไป|กุญแจ|Jewel|เครื่องประดับ|Craft|Exotic|Salvage|AlwaysShow|Rare ตาม|Magic\/Rare/.test(c)), catsNow.join("|"));
check("PoE2 ends with the Flask / Charm and the equipment-by-class categories", catsNow[catsNow.length - 2] === "Flask / Charm" && catsNow[catsNow.length - 1] === "อุปกรณ์ตาม class", catsNow.join("|"));
await page.selectOption("#pane-whitelist select[aria-label=หมวด]", { label: "Flask / Charm" });
await page.waitForSelector("#flask-box:not([hidden])");
check("no block list under Flask / Charm", await page.locator("#list-box").isHidden());
check("two rows: Flask and Charm, both default", (await page.locator("#flask-box .rarity-box").count()) === 2 &&
  (await page.locator('#flask-box input[type=radio][value=default]:checked').count()) === 2);
check("no rarity boxes before 'set myself'", (await page.locator("#flask-box select").count()) === 0);
await page.locator('input[aria-label="Flask ตั้งค่าเอง"]').check();
check("'set myself' shows Normal / Magic (no Rare), S / A / B / C / D only, all start at B", (await page.locator('#flask-box [data-row=Flask] select').count()) === 2 &&
  (await page.locator('#flask-box [data-row=Flask] select').evaluateAll((els) => els.every((e) => e.value === "B" &&
    JSON.stringify([...e.options].map((o) => o.value)) === JSON.stringify(["S", "A", "B", "C", "D"])))));
check("the warning is shown with the rarity boxes", (await page.locator("#flask-box .rarity-warning").innerText()).includes("ตั้ง D = ซ่อนทุกชิ้นของ rarity นั้น"));
await page.selectOption('select[aria-label="Flask rarity Magic"]', "D");
await page.selectOption('select[aria-label="Flask rarity Normal"]', "B");
check("rarity D / B reach the model", JSON.stringify(((await model("wl_config")).wl_rarity_rows_poe2 || {}).Flask) === JSON.stringify({ custom: true, tiers: { Normal: "B", Magic: "D" } }));
await shot("05_flask_charm_rows");
await page.locator('input[aria-label="Flask ค่าเริ่มต้น (block ของ NeverSink ทั้งหมดของแถวนี้)"]').check();
check("back to the default keeps the values but writes nothing", ((await model("wl_config")).wl_rarity_rows_poe2.Flask.custom === false) &&
  ((await model("wl_config")).wl_rarity_rows_poe2.Flask.tiers.Magic === "D"));
await page.locator('input[aria-label="Flask ตั้งค่าเอง"]').check();       // custom again for the generated file below
// ---- equipment by class
await page.selectOption("#pane-whitelist select[aria-label=หมวด]", { label: "อุปกรณ์ตาม class" });
await page.waitForSelector("#equip-box:not([hidden])");
check("equipment: no block list, flask box hidden", await page.locator("#list-box").isHidden() && await page.locator("#flask-box").isHidden());
check("equipment: one sub tab per group, in order", JSON.stringify(await page.locator("#equip-box .equip-tabs button").allInnerTexts()) === JSON.stringify(["อาวุธ", "เกราะ", "เครื่องประดับ", "อื่นๆ"]));
check("equipment: only the first group's rows are shown, each has the whole-group boxes on top",
  (await page.locator("#equip-box .equip-group:not([hidden])").count()) === 1 && (await page.locator("#equip-pane-weapon .equip-head").count()) === 1);
check("equipment: what D means is said once, above the tabs", (await page.locator("#equip-box").innerText()).split("D = ซ่อนทั้งหมด").length === 2 && (await page.locator("#equip-box .equip-warning").count()) === 0);
check("equipment: Foci is shown as Focus", (await page.locator('#equip-box [data-class=Foci] .cls').innerText()) === "Focus" && (await page.locator('input[aria-label="Focus ตั้งค่าเอง"]').count()) === 1);
const eqClasses = await page.locator("#equip-box .equip-row .cls").allInnerTexts();
check("equipment: Quivers are in the weapons group, 22 classes in poe2", eqClasses.length === 22 && (await page.locator('#equip-box [data-group=weapon] [data-class=Quivers]').count()) === 1, String(eqClasses.length));
check("equipment: every row starts as the default", (await page.locator('#equip-box input[type=radio][value=default]:checked').count()) === 22 &&
  (await page.locator('#equip-box .equip-row select:not([disabled])').count()) === 0);
check("equipment: the row boxes offer S / A / B / C / D only", await page.locator('#equip-box .equip-row select').first().evaluate((e) => JSON.stringify([...e.options].map((o) => o.value)) === JSON.stringify(["S", "A", "B", "C", "D"])));
await page.click("#equip-tab-armour");
check("equipment: the armour tab shows only the armour group", (await page.locator("#equip-box .equip-group:not([hidden])").count()) === 1 && await page.locator("#equip-pane-armour").isVisible() && await page.locator("#equip-pane-weapon").isHidden());
await page.locator('input[aria-label="Boots ตั้งค่าเอง"]').check();
check("equipment: set myself starts every rarity at B", (await page.locator('#equip-box [data-class=Boots] select').evaluateAll((els) => els.length === 3 && els.every((e) => e.value === "B" && !e.disabled))));
await page.selectOption('select[aria-label="Boots rarity Rare"]', "D");
check("equipment: Boots Rare D reaches the model", JSON.stringify(((await model("wl_config")).wl_equip_rows_poe2 || {}).Boots) === JSON.stringify({ custom: true, tiers: { Normal: "B", Magic: "B", Rare: "D" } }));
await page.selectOption('select[aria-label="เกราะ ตั้งทั้งกลุ่ม Magic"]', "A");
const eqCfg = (await model("wl_config")).wl_equip_rows_poe2 || {};
const ARMOUR = ["Body Armours", "Boots", "Gloves", "Helmets", "Shields", "Bucklers", "Foci"];
check("equipment: the group select makes each armour row 'set myself' with that tier (no separate group value)", ARMOUR.every((c) => eqCfg[c] && eqCfg[c].custom && eqCfg[c].tiers.Magic === "A") &&
  eqCfg.Boots.tiers.Rare === "D" && !eqCfg.Wands);
check("equipment: the header select goes back to its prompt, the rows show the value", (await page.locator('select[aria-label="เกราะ ตั้งทั้งกลุ่ม Magic"]').inputValue()) === "ทั้งกลุ่ม…" &&
  (await page.locator('select[aria-label="Gloves rarity Magic"]').inputValue()) === "A" && await page.locator('input[aria-label="Gloves ตั้งค่าเอง"]').isChecked());
const hdrWidths = await page.locator('#equip-box [data-group=armour] .equip-head select').evaluateAll((els) => els.map((e) => Math.round(e.getBoundingClientRect().width)));
const rowWidths = await page.locator('#equip-box [data-class=Boots] .tier-grid select').evaluateAll((els) => els.map((e) => Math.round(e.getBoundingClientRect().width)));
check("equipment: Normal / Magic / Rare boxes have one width (header and row)", new Set(hdrWidths).size === 1 && new Set(rowWidths).size === 1 && rowWidths[0] >= 40, JSON.stringify([hdrWidths, rowWidths]));
await shot("05b_equipment_by_class");
await page.selectOption('select[aria-label="เกราะ ตั้งทั้งกลุ่ม Normal"]', "ค่าเริ่มต้น");
const eqCfg2 = (await model("wl_config")).wl_equip_rows_poe2 || {};
check("equipment: 'ค่าเริ่มต้น' at the header puts every armour row back to the default (values kept)", ARMOUR.every((c) => eqCfg2[c] && eqCfg2[c].custom === false) &&
  (await page.locator('#equip-box [data-group=armour] input[type=radio][value=default]:checked').count()) === 7);
await page.locator('input[aria-label="Boots ตั้งค่าเอง"]').check();
await page.locator('input[aria-label="Boots ค่าเริ่มต้น"]').check();
check("equipment: back to the default keeps the values", (await model("wl_config")).wl_equip_rows_poe2.Boots.custom === false && (await model("wl_config")).wl_equip_rows_poe2.Boots.tiers.Rare === "D");
await page.locator('input[aria-label="Boots ตั้งค่าเอง"]').check();
await page.selectOption("#pane-whitelist select[aria-label=หมวด]", { label: "Currency" });
check("the list is back for Currency", await page.locator("#list-box").isVisible() && await page.locator("#flask-box").isHidden());
await shot("06_currency_after_flask");

// the other parts: one sub tab each, each with its own style editor (no pop-up)
check("PoE2 sub tabs: items, Gold, Waystone, Tablet, Gem, typed names", JSON.stringify(await page.locator("#pane-whitelist > .subtabs button").allInnerTexts()) ===
  JSON.stringify(["ไอเท็ม / หมวด", "Gold", "Waystone", "Tablet", "Gem", "พิมพ์เอง"]));
await page.click("#subtab-gem");
{
  const labels = await page.locator("#pane-sub-gem .box label:has(input[type=checkbox])").allInnerTexts();
  const uncut = labels.map((t) => t.trim()).filter((t) => t.startsWith("Uncut"));
  check("PoE2 uncut gem rows: Skill, Spirit, Support", JSON.stringify(uncut) === JSON.stringify(["Uncut Skill Gem", "Uncut Spirit Gem", "Uncut Support Gem"]), uncut.join("|"));
  check("the Gem sub tab shows its own style editor", await page.locator('#pane-sub-gem [data-style="Gem"] .style-grid').isVisible());
}
await page.click("#subtab-gold");
await page.check("#chk-gold");
await page.locator('input[aria-label="จำนวนขั้นต่ำของ Gold"]').fill("25");
await page.locator('input[aria-label="จำนวนขั้นต่ำของ Gold"]').dispatchEvent("input");
check("gold style editor is inline with a sound field", (await page.locator('#pane-sub-gold [data-style="G"] select[aria-label="ชนิดเสียง"]').count()) === 1 && !(await page.locator("#dlg-style[open]").count()));
await shot("07_parts_gold_style");
await page.click("#subtab-map");
await page.check("#chk-map");
await page.click("#subtab-tablet");
check("the Tablet sub tab has its own editor", await page.locator('#pane-sub-tablet [data-style="Tablet"] .style-grid').isVisible());
await page.click("#subtab-custom");
await page.fill("#custom-input", "heavy belt");
await page.click("#custom-add");
check("typed name added", (await page.locator("#custom-chips li").count()) === 1);
check("gold + map in the model", (await model("wl_parts")).gold === true && (await model("wl_parts")).map_on === true && (await model("wl_parts")).gold_min === 25);
await shot("08_parts");

// ---------------------------------------------------------------- generate: whitelist -> download
await page.fill('#pane-whitelist input[aria-label="ชื่อ filter"]', "my-wl");
await page.click("#btn-generate-wl");
await page.waitForSelector("#result:not([hidden])", { timeout: 60000 });
check("whitelist generate says how many", (await logText()).includes("โหมดโชว์เฉพาะ"), await logText());
const [dl] = await Promise.all([page.waitForEvent("download"), page.click("#btn-download")]);
const wlFile = path.join(tmp, dl.suggestedFilename());
await dl.saveAs(wlFile);
const wlText = fs.readFileSync(wlFile, "utf-8");
// kept for the desktop parity test: the file the page made and the settings it made it from
fs.mkdirSync(path.join(OUT, "parity"), { recursive: true });
fs.copyFileSync(wlFile, path.join(OUT, "parity", "wl.filter"));
fs.writeFileSync(path.join(OUT, "parity", "wl_cfg.json"), await page.evaluate(() => localStorage.getItem("poeFilterGen.cfg")));
check("download is <name>.filter with CRLF", dl.suggestedFilename() === "my-wl.filter" && wlText.includes("\r\n"), dl.suggestedFilename());
check("file has the embedded settings, version 'web'", wlText.includes("# poe-checker-config:"));
check("file has the rarity block, NeverSink's copied blocks and the Q block", wlText.includes("# rarity: Flask - Magic - tier D") && wlText.includes("# neversink (") && wlText.includes("# quest items"));
check("file has the typed name and the gold stack", wlText.includes('"heavy belt"') && wlText.includes("StackSize >= 25") && wlText.includes("# gold (stack >= 25)"));
await shot("09_result");

// ---------------------------------------------------------------- sounds: zip
await page.click("#tab-ns");
const mp3 = Buffer.from("ID3-fake-sound-bytes");
await page.locator('#pane-tier input[type=file]').first().setInputFiles({ name: "snd#1.mp3", mimeType: "audio/mpeg", buffer: mp3 });
await wait(300);
check("sound name shown", (await page.locator("#pane-tier").innerText()).includes("snd#1.mp3"));
await page.fill('#pane-tier input[aria-label="ชื่อ filter"]', "my-ns");
await page.selectOption('#pane-tier select[aria-label="NeverSink Strictness"]', "3");
await page.click("#btn-generate-tier");
await page.waitForFunction(() => document.querySelector("#btn-download") && /zip/.test(document.querySelector("#btn-download").textContent), null, { timeout: 60000 });
const [dl2] = await Promise.all([page.waitForEvent("download"), page.click("#btn-download")]);
const zipFile = path.join(tmp, dl2.suggestedFilename());
await dl2.saveAs(zipFile);
const zbytes = fs.readFileSync(zipFile);
check("sounds -> a zip named after the filter", dl2.suggestedFilename() === "my-ns.zip");
check("zip holds the filter and the renamed sound (# -> _)", zbytes.includes(Buffer.from("my-ns.filter")) && zbytes.includes(Buffer.from("snd_1.mp3")));
check("the log says why the name changed", (await logText()).includes("#"), await logText());
await shot("10_ns_zip");

// ---------------------------------------------------------------- open a filter
await page.click("#tab-wl");
await page.setInputFiles("#open-filter-input", wlFile);
check("opening our own file loads the settings", await waitLog("ค่าฝังจากรุ่น web"), await logText());
check("the name follows the file", (await page.inputValue('#pane-whitelist input[aria-label="ชื่อ filter"]')) === "my-wl");
check("opened settings keep the Flask rarity rows", ((await model("wl_config")).wl_rarity_rows_poe2 || {}).Flask?.tiers?.Magic === "D");
const oldTxt = zlib.gunzipSync(fs.readFileSync(path.join(REPO, "tests", "sample_data", "old_filters", "v2_poe2_bus.filter.gz")));
const oldFile = path.join(tmp, "old-bus.filter");
fs.writeFileSync(oldFile, oldTxt);
await page.setInputFiles("#open-filter-input", oldFile);
check("an old file without settings is read back", await waitLog("ไฟล์รุ่น v2"), await logText());
check("what was guessed is named", (await logText()).includes("เดา/ปรับ"));
const foreign = path.join(tmp, "foreign.filter");
fs.writeFileSync(foreign, 'Show\n    Class "Gems"\n');
await page.setInputFiles("#open-filter-input", foreign);
check("a foreign file is refused", await waitLog("ไม่ได้สร้างจากแท็บ Whitelist"));
await shot("11_after_open");

// ---------------------------------------------------------------- the game folder (File System Access)
check("folder box is shown (browser supports it)", await page.locator("#folder-box").isVisible());
await page.click("#btn-folder");
await wait(500);
check("folder connected", (await page.locator("#folder-name").innerText()).includes("Path of Exile 2"), await page.locator("#folder-name").innerText());
await page.evaluate(async () => {               // the folder already holds a DIFFERENT file with the sound's name
  const d = await (await navigator.storage.getDirectory()).getDirectoryHandle("Path of Exile 2", { create: true });
  const w = await (await d.getFileHandle("snd_1.mp3", { create: true })).createWritable();
  await w.write(new Uint8Array([1, 2, 3])); await w.close();
});
await page.click("#tab-ns");
await page.fill('#pane-tier input[aria-label="ชื่อ filter"]', "my-ns");
await page.click("#btn-generate-tier");
await page.waitForSelector("#dlg-ask[open]", { timeout: 60000 });
check("same name, other content -> asks", (await page.locator("#dlg-ask").innerText()).includes("snd_1.mp3"));
await shot("12_ask_conflict");
await page.click("#ask-ok");                    // default: keep the old file, new one gets -2
await waitLog("เขียนลงโฟลเดอร์");
const listing = await page.evaluate(async () => {
  const d = await (await navigator.storage.getDirectory()).getDirectoryHandle("Path of Exile 2");
  const out = {};
  for await (const [n, h] of d.entries()) out[n] = (await (await h.getFile()).size);
  return out;
});
check("filter written straight into the folder", "my-ns.filter" in listing, JSON.stringify(listing));
check("old sound kept, new one saved as -2", listing["snd_1.mp3"] === 3 && "snd_1-2.mp3" in listing, JSON.stringify(listing));
check("no download offered when written", await page.locator("#btn-download").isHidden());
await page.click("#btn-generate-tier");         // second run: the same sounds are reused, the filter is asked about (confirm accepted)
await waitLog("เขียนลงโฟลเดอร์");
await shot("13_written");
// the folder is remembered after a reload
await page.reload();
await page.waitForSelector("#app:not([hidden])", { timeout: 120000 });
check("folder remembered after reload", (await page.locator("#folder-name").innerText()).includes("Path of Exile 2"), await page.locator("#folder-name").innerText());
// open the file from the folder's content: sound found next to it
await page.click("#tab-wl");
const written = await page.evaluate(async () => {
  const d = await (await navigator.storage.getDirectory()).getDirectoryHandle("Path of Exile 2");
  return await (await (await d.getFileHandle("my-ns.filter")).getFile()).text();
});
check("the file written to the folder is a complete filter", written.length > 100000 && written.includes("\r\n"));

// ---------------------------------------------------------------- "เปิด filter…" with the folder connected
await page.evaluate(async (text) => {
  const d = await (await navigator.storage.getDirectory()).getDirectoryHandle("Path of Exile 2", { create: true });
  const put = async (name, body) => { const w = await (await d.getFileHandle(name, { create: true })).createWritable(); await w.write(body); await w.close(); };
  await put("wl-made.filter", text);
  await put("foreign.filter", 'Show\n    Class "Gems"\n');
  await put("not-a-filter.txt", "x");
}, wlText);
await page.click("#btn-open");
await page.waitForSelector("#dlg-open[open]");
const rowsOpen = await page.locator("#open-list li").evaluateAll((li) => li.map((x) => ({ f: x.dataset.file, k: x.dataset.kind, dis: x.querySelector("button").disabled })));
check("the folder's .filter files are listed (no other files), editable ones first",
  rowsOpen.map((r) => r.f).join("|") === "wl-made.filter|foreign.filter|my-ns.filter" && rowsOpen[0].k === "whitelist", JSON.stringify(rowsOpen));
check("only the file made by the Whitelist tab can be opened", rowsOpen[0].dis === false && rowsOpen[1].dis === true && rowsOpen[2].k === "tier" && rowsOpen[2].dis === true, JSON.stringify(rowsOpen));
check("the list says which ones can be edited", (await page.locator("#dlg-open").innerText()).includes("เปิดแก้ได้") && (await page.locator("#dlg-open").innerText()).includes("เปิดแก้ไม่ได้"));
await shot("11b_open_list");
await page.locator('#open-list li[data-file="wl-made.filter"] button').click();
check("a file of the list opens at once, no picker", await page.locator("#dlg-open").evaluate((d) => !d.open) &&
  (await page.inputValue('#pane-whitelist input[aria-label="ชื่อ filter"]')) === "wl-made" && (await page.evaluate(() => window.__picks.length)) === 0);
// "เลือกไฟล์อื่น…": showOpenFilePicker starting in the game folder
await page.click("#btn-open");
await page.waitForSelector("#dlg-open[open]");
await page.click("#btn-open-other");
check("'เลือกไฟล์อื่น…' starts the picker in the game folder", await waitFor(() => page.evaluate(() => window.__picks.length === 1)) &&
  (await page.evaluate(() => window.__picks[0])).startIn === "Path of Exile 2", JSON.stringify(await page.evaluate(() => window.__picks)));
// the permission expired after a reload: one button first, then the list
await page.evaluate(() => { window.PFG.FS.state = "prompt"; });
await page.click("#btn-open");
await page.waitForSelector("#dlg-open[open]");
check("an expired folder permission asks once, before any list", await page.locator("#btn-open-grant").isVisible() && (await page.locator("#open-list").count()) === 0);
await page.click("#btn-open-grant");
await page.waitForSelector("#open-list");
check("after the permission the list is shown", (await page.locator("#open-list li").count()) === 3);
await page.click("#btn-open-close");
// ---- a folder for each game
const folderText = () => page.locator("#folder-name").innerText();
const dirPicks = () => page.evaluate(() => window.__dirPicks);
// no folder for this game: the folder picker opens at once (Documents), the Status says which folder, then the list follows
await page.click("#btn-folder-forget");
await page.evaluate(() => { window.__dirPicks = []; });
await page.click("#btn-open");
await page.waitForSelector("#open-list");
check("no folder: the folder picker opens at once, starting in Documents (one per game)", JSON.stringify(await dirPicks()) ===
  JSON.stringify([{ startIn: "documents", id: "poe-filter-poe2" }]), JSON.stringify(await dirPicks()));
check("the Status names the folder to choose", (await logText()).includes("เลือกโฟลเดอร์ Documents\\My Games\\Path of Exile 2"));
check("what was picked is listed at once and adopted", (await page.locator("#open-list li").count()) === 3 && (await folderText()).includes("Path of Exile 2"));
await page.click("#btn-open-close");
// a name that is not the game's: asked, "again" opens the picker again
await page.click("#btn-folder-forget");
await page.evaluate(() => { window.__dirName = "My Own Folder"; window.__dirPicks = []; });
await page.click("#btn-open");
await page.waitForSelector("#dlg-folder[open]");
check("another folder name is asked about (both names shown)", (await page.locator("#dlg-folder").innerText()).includes("My Own Folder") &&
  (await page.locator("#dlg-folder").innerText()).includes("Path of Exile 2") && (await folderText()).includes("ยังไม่ได้เลือก"));
await page.evaluate(() => { window.__dirName = "Path of Exile 2"; });
await page.click("#btn-folder-again");
await page.waitForSelector("#open-list");
check("'เลือกใหม่' opens the picker again and the right folder is adopted", (await dirPicks()).length === 2 && (await folderText()).includes("Path of Exile 2"));
await page.click("#btn-open-close");
// ... "keep" uses the player's own folder
await page.click("#btn-folder-forget");
await page.evaluate(() => { window.__dirName = "My Own Folder"; });
await page.click("#btn-open");
await page.waitForSelector("#dlg-folder[open]");
await page.click("#btn-folder-keep");
await page.waitForSelector("#dlg-open[open]");                 // (the folder is empty: the list says so)
check("'ใช้โฟลเดอร์นี้ต่อ' keeps the own folder and says the name is odd", (await folderText()).includes("My Own Folder") &&
  (await page.locator("#folder-hint").innerText()).includes("ไม่ใช่"));
await page.click("#btn-open-close");
// ... "cancel" adopts nothing; a picker closed by the player says nothing
await page.click("#btn-folder-forget");
await page.click("#btn-open");
await page.waitForSelector("#dlg-folder[open]");
await page.click("#btn-folder-cancel");
check("'ยกเลิก' adopts nothing", (await folderText()).includes("ยังไม่ได้เลือก") && (await page.locator("#dlg-open").evaluate((d) => !d.open)));
await page.evaluate(() => { window.__dirAbort = true; });
await page.click("#btn-open");
await wait(400);
check("a picker the player closed leaves everything as it was", (await folderText()).includes("ยังไม่ได้เลือก") &&
  (await page.locator("#dlg-open").evaluate((d) => !d.open)) && (await page.locator("#dlg-folder").evaluate((d) => !d.open)));
await page.evaluate(() => { window.__dirAbort = false; window.__dirName = null; });
// the button "เลือกโฟลเดอร์เกม" checks the name the same way
await page.evaluate(() => { window.__dirName = "Wrong"; });
await page.click("#btn-folder");
await page.waitForSelector("#dlg-folder[open]");
await page.click("#btn-folder-cancel");
check("'เลือกโฟลเดอร์เกม' asks about a wrong name too", (await folderText()).includes("ยังไม่ได้เลือก"));
await page.evaluate(() => { window.__dirName = null; });
await page.click("#btn-folder");
await page.waitForFunction(() => document.querySelector("#folder-name").textContent.includes("Path of Exile 2"));
// each game has its own folder: PoE1 has none yet, PoE2 keeps its own
await page.evaluate(() => { window.__dirPicks = []; });
await page.click("#game-poe1");
await page.waitForFunction(() => document.querySelector("#folder-name").textContent.includes("ยังไม่ได้เลือก"));
check("another game has its own folder (PoE1 has none yet)", true);
await page.click("#btn-open");
await page.waitForSelector("#dlg-open[open]");
check("PoE1's picker is PoE1's (folder 'Path of Exile', empty), PoE2's folder was not touched", (await dirPicks())[0].id === "poe-filter-poe1" &&
  (await folderText()).includes("Path of Exile") && !(await folderText()).includes("Exile 2") && (await page.locator("#dlg-open").innerText()).includes("ไม่มีไฟล์ .filter"));
await page.click("#btn-open-close");
await page.click("#game-poe2");
await page.waitForFunction(() => document.querySelector("#folder-name").textContent.includes("Path of Exile 2"));
await page.click("#btn-open");
await page.waitForSelector("#open-list");
check("back to PoE2: its own folder is used at once, no picker", (await page.locator("#open-list li").count()) >= 3 && (await dirPicks()).length === 1);
await page.click("#btn-open-close");
// a handle an older page kept without a game (key "folder"): moved to the game its folder name says
await page.evaluate(async () => {
  const root = await navigator.storage.getDirectory();
  const d = await root.getDirectoryHandle("Path of Exile", { create: true });
  await new Promise((res, rej) => {
    const rq = indexedDB.open("poe-filter-gen", 2);
    rq.onsuccess = () => {
      const db = rq.result;
      const tx = db.transaction("handles", "readwrite");
      const st = tx.objectStore("handles");
      st.delete("poe1");
      st.put(d, "folder");
      tx.oncomplete = () => { db.close(); res(); };
      tx.onerror = () => rej(tx.error);
    };
    rq.onerror = () => rej(rq.error);
  });
});
await page.reload();
await page.waitForSelector("#app:not([hidden])", { timeout: 120000 });
await page.click("#game-poe1");
await page.waitForFunction(() => document.querySelector("#folder-name").textContent.includes("Path of Exile"));
const keysNow = await page.evaluate(() => new Promise((res) => {
  const rq = indexedDB.open("poe-filter-gen", 2);
  rq.onsuccess = () => { const db = rq.result; const q = db.transaction("handles").objectStore("handles").getAllKeys();
    q.onsuccess = () => { db.close(); res(q.result); }; };
}));
check("an older single handle goes to the game its folder name says (and its old key is gone)", !(await folderText()).includes("ยังไม่ได้เลือก") &&
  JSON.stringify([...keysNow].sort()) === JSON.stringify(["poe1", "poe2"]), JSON.stringify(keysNow));
await page.click("#game-poe2");
await page.waitForFunction(() => document.querySelector("#folder-name").textContent.includes("Path of Exile 2"));
await page.click("#tab-wl");
// no showDirectoryPicker (Firefox / Safari): the old way - showOpenFilePicker, or the plain file input
await page.click("#btn-folder-forget");
await page.waitForFunction(() => document.querySelector("#folder-name").textContent.includes("ยังไม่ได้เลือก"));
await page.evaluate(() => { window.PFG.FS.supported = false; window.showOpenFilePicker = undefined; });
const [chooser] = await Promise.all([page.waitForEvent("filechooser"), page.click("#btn-open")]);
check("no folder API: the plain file chooser opens", !!chooser);
await page.evaluate(() => { window.PFG.FS.supported = true; window.showOpenFilePicker = window.__stubPick; });
await page.click("#btn-folder");
await page.waitForFunction(() => document.querySelector("#folder-name").textContent.includes("Path of Exile 2"));
// a page whose files came from the browser cache in two versions (no P.openFilter) / a list that throws: never silent
await page.evaluate(() => { window.__keepOpen = window.PFG.openFilter; window.PFG.openFilter = undefined; });
const [stale] = await Promise.all([page.waitForEvent("filechooser"), page.click("#btn-open")]);
check("a stale page (no list code) says so and still opens the file chooser", !!stale && (await logText()).includes("รุ่นเก่าที่ค้างใน cache"));
await page.evaluate(() => { window.PFG.openFilter = async () => { throw new Error("boom"); }; });
await page.click("#btn-open");
await wait(300);
check("a list that fails says why in the Status", (await logText()).includes("เปิดรายการไฟล์ไม่ได้: boom"));
const [afterFail] = await Promise.all([page.waitForEvent("filechooser"), page.click("#btn-open")]);
check("... and the next click goes straight to the plain file chooser", !!afterFail);
await page.evaluate(() => { window.PFG.openFilter = window.__keepOpen; window.PFG.openFilterBroken = false; });
await page.click("#btn-folder");                // the folder is back for what follows
await wait(500);

// ---------------------------------------------------------------- PoE1
await page.click("#game-poe1");
check("lists load for PoE1", await waitLog("โหลดรายการ whitelist แล้ว"));
await page.click("#tab-wl");
const cats = await page.locator("#pane-whitelist select[aria-label=หมวด] option").allInnerTexts();
check("PoE1 has the name lists and Flask / Tincture, no gem group", ["Runegraft", "Vial", "Corpse", "Wombgift", "Relic", "Flask / Tincture"].every((c) => cats.includes(c)) && !cats.some((c) => c.startsWith("Gem ทั่วไป")), cats.join("|"));
await page.click(".tier-btns button[data-t=S]");
await page.selectOption("#pane-whitelist select[aria-label=หมวด]", { label: "Runegraft" });
check("Runegraft rows start at NeverSink's tiers", (await page.locator('table.items tr[data-key="Runegraft of Gemcraft"]').getAttribute("data-tier")) === "S");
await page.selectOption("#pane-whitelist select[aria-label=หมวด]", { label: "Unique" });
check("Unique list is big and renders", (await page.locator("table.items tbody tr").count()) > 1000);
check("PoE1 has no Tablet sub tab", JSON.stringify(await page.locator("#pane-whitelist > .subtabs button").allInnerTexts()) ===
  JSON.stringify(["ไอเท็ม / หมวด", "Gold", "Map", "Gem", "พิมพ์เอง"]));
await page.click("#subtab-gem");
check("PoE1 gem names input + autocomplete", await page.locator("#gem-input").isVisible());
await shot("14_poe1_parts");
await page.click("#subtab-items");
await shot("15_poe1_unique");

// ---------------------------------------------------------------- a phone-sized screen
await page.setViewportSize({ width: 360, height: 780 });
await page.click("#tab-wl");
await shot("16_mobile_whitelist");
await page.selectOption("#pane-whitelist select[aria-label=หมวด]", { label: "อุปกรณ์ตาม class" });
await page.waitForSelector("#equip-box:not([hidden])");
await page.click("#equip-tab-armour");
await page.locator('input[aria-label="Boots ตั้งค่าเอง"]').check();
await page.selectOption('select[aria-label="Boots rarity Rare"]', "D");
await page.locator('#equip-box [data-class=Boots]').scrollIntoViewIfNeeded();
await shot("16b_mobile_equipment");
const eqOver = await page.evaluate(() => {
  const box = document.querySelector("#equip-box");
  const wide = [...box.querySelectorAll("*")].filter((e) => e.getBoundingClientRect().right > window.innerWidth + 1 || e.getBoundingClientRect().left < -1);
  return { boxScroll: box.scrollWidth > box.clientWidth + 1, page: document.documentElement.scrollWidth > window.innerWidth + 1, wide: wide.length };
});
check("equipment at 360 px: no row wider than the screen, no sideways scroll", !eqOver.boxScroll && !eqOver.page && eqOver.wide === 0, JSON.stringify(eqOver));
const mw = await page.locator('#equip-box [data-class=Boots] .tier-grid select').evaluateAll((els) => els.map((e) => Math.round(e.getBoundingClientRect().width)));
check("equipment at 360 px: Normal / Magic / Rare boxes one width", new Set(mw).size === 1 && mw[0] >= 60, JSON.stringify(mw));
await page.selectOption("#pane-whitelist select[aria-label=หมวด]", { index: 0 });
await page.click("#tab-ns");
await shot("17_mobile_neversink");
const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
check("no sideways scroll on a phone", !overflow);

check("no console errors", consoleErrors.length === 0, consoleErrors.join(" | "));
await browser.close();
srv.close();
console.log(JSON.stringify({ results, calls: calls.filter((c) => !c.startsWith("pyodide")), out: OUT }));
