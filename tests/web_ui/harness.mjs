// Shared by the browser tests: a static server for web/, and routes that answer the page's network calls from local
// files (Pyodide from node_modules, NeverSink / hub from tests/sample_data), so the tests are fast and offline.
import http from "http";
import fs from "fs";
import path from "path";
import zlib from "zlib";
import { fileURLToPath } from "url";

export const HERE = path.dirname(fileURLToPath(import.meta.url));
export const REPO = path.resolve(HERE, "..", "..");
export const WEB = path.join(REPO, "web");
const SAMPLE = path.join(REPO, "tests", "sample_data");
const MIME = { ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".py": "text/plain; charset=utf-8",
  ".wasm": "application/wasm", ".zip": "application/zip", ".mjs": "text/javascript" };

export function startServer(port = 0) {
  return new Promise((resolve) => {
    const srv = http.createServer((req, res) => {
      let p = decodeURIComponent(new URL(req.url, "http://x").pathname);
      if (p.endsWith("/")) p += "index.html";
      const file = path.join(WEB, p);
      if (!file.startsWith(WEB) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) { res.writeHead(404); res.end("not found"); return; }
      res.writeHead(200, { "Content-Type": MIME[path.extname(file)] || "application/octet-stream", "Cache-Control": "no-store" });
      fs.createReadStream(file).pipe(res);
    });
    srv.listen(port, "127.0.0.1", () => resolve({ srv, url: `http://127.0.0.1:${srv.address().port}` }));
  });
}

const gz = (f) => zlib.gunzipSync(fs.readFileSync(path.join(SAMPLE, f))).toString("utf-8");

/** Answer every call to another site from local fixtures. `calls` collects what the page asked for. */
export async function routeNetwork(context, calls = []) {
  const pyodideDir = path.join(HERE, "node_modules", "pyodide");
  await context.route(/^https:\/\/cdn\.jsdelivr\.net\/pyodide\//, (route) => {
    const name = new URL(route.request().url()).pathname.split("/").pop();
    const f = path.join(pyodideDir, name);
    calls.push("pyodide:" + name);
    if (!fs.existsSync(f)) return route.fulfill({ status: 404, body: "no" });
    route.fulfill({ status: 200, body: fs.readFileSync(f), contentType: MIME[path.extname(f)] || "application/octet-stream",
      headers: { "Access-Control-Allow-Origin": "*" } });
  });
  await context.route(/^https:\/\/api\.github\.com\//, (route) => {
    calls.push("ns-api");
    route.fulfill({ status: 200, contentType: "application/json", headers: { "Access-Control-Allow-Origin": "*" }, body: JSON.stringify({ tag_name: "v-test" }) });
  });
  await context.route(/^https:\/\/raw\.githubusercontent\.com\//, (route) => {
    const url = route.request().url();
    const g = /PoE2/i.test(url) ? "poe2" : "poe1";
    calls.push("ns-file:" + g);
    route.fulfill({ status: 200, contentType: "text/plain; charset=utf-8", headers: { "Access-Control-Allow-Origin": "*" },
      body: fs.readFileSync(path.join(SAMPLE, `neversink_${g}_s2.filter`), "utf-8") });
  });
  await context.route(/^https:\/\/storage\.googleapis\.com\/poe-data-hub\//, (route) => {
    const url = route.request().url();
    const m = url.match(/poe-data-hub\/(poe[12])\/(.*)$/);
    calls.push("hub:" + (m ? m[1] + "/" + m[2] : url));
    if (m && m[2] === "prices/latest.json") {
      return route.fulfill({ status: 200, contentType: "application/json", headers: { "Access-Control-Allow-Origin": "*" }, body: gz(`hub_${m[1]}.json.gz`) });
    }
    route.fulfill({ status: 404, contentType: "text/plain", headers: { "Access-Control-Allow-Origin": "*" }, body: "not found" });
  });
}

export const wait = (ms) => new Promise((r) => setTimeout(r, ms));
