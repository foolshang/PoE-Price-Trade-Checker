// Real-site check: the deployed page, no network stubs. Usage: node live.mjs <url>
import { chromium } from "playwright";
import fs from "fs";
import os from "os";
import path from "path";
const url = process.argv[2];
function findChrome() {
  if (process.env.PW_CHROME) return process.env.PW_CHROME;
  const base = path.join(process.env.LOCALAPPDATA || os.homedir(), "ms-playwright");
  const dirs = fs.readdirSync(base).filter((d) => /^chromium-\d+$/.test(d)).sort().reverse();
  for (const d of dirs) for (const s of ["chrome-win64/chrome.exe", "chrome-win/chrome.exe"]) {
    const f = path.join(base, d, s); if (fs.existsSync(f)) return f;
  }
}
const browser = await chromium.launch({ executablePath: findChrome(), headless: true });
const ctx = await browser.newContext({ acceptDownloads: true });
const page = await ctx.newPage();
const errors = [], failed = [], bad = [];
page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
page.on("pageerror", (e) => errors.push(String(e)));
page.on("requestfailed", (r) => failed.push(r.url() + " " + (r.failure() || {}).errorText));
page.on("response", (r) => { if (r.status() >= 400) bad.push(r.status() + " " + r.url()); });
await page.goto(url, { waitUntil: "load" });
await page.waitForSelector("#app:not([hidden])", { timeout: 180000 });
const out = { ver: await page.locator("#ver").innerText() };
await page.waitForFunction(() => document.querySelectorAll("select option").length > 3, null, { timeout: 60000 }).catch(() => {});
await page.click("#btn-generate-tier");
await page.waitForSelector("#btn-download", { timeout: 120000 });
const [dl] = await Promise.all([page.waitForEvent("download", { timeout: 60000 }), page.click("#btn-download")]);
const f = await dl.path();
const text = fs.readFileSync(f, "utf-8");
out.download = { name: dl.suggestedFilename(), bytes: text.length, shows: (text.match(/^Show/gm) || []).length };
out.status = (await page.locator("#log").innerText().catch(() => "")).slice(-400);
await page.click("#tab-wl");
await page.click("#game-poe1");
await page.waitForTimeout(3000);
out.poe1ver = await page.locator("#ver").innerText();
out.errors = errors; out.failed = failed; out.bad = bad;
console.log(JSON.stringify(out, null, 1));
await browser.close();
