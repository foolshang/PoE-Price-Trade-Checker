// Runs web/glue.py (the page's Python) in Pyodide, like the browser does, for the parity tests.
//   node run.mjs <program.json>      program = [{"fn": "generate", "args": [...], "log": true?}, ...]
// An argument "$file:<path>" is replaced by the text of that file (".gz" = gunzipped); "$log" by a log collector.
// Prints one JSON line: {"results": [...], "logs": [[tag, msg], ...]}
import { loadPyodide } from "pyodide";
import fs from "fs";
import path from "path";
import zlib from "zlib";

const repo = path.resolve(path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1")), "..", "..");
const program = JSON.parse(fs.readFileSync(process.argv[2], "utf-8"));
const py = await loadPyodide();
py.FS.mkdirTree("/home/pyodide/poe_price_trade");
py.FS.writeFile("/home/pyodide/poe_price_trade/__init__.py", "");
const manifest = JSON.parse(fs.readFileSync(path.join(repo, "web", "py", "manifest.json"), "utf-8"));
for (const f of manifest.files) py.FS.writeFile("/home/pyodide/poe_price_trade/" + f, fs.readFileSync(path.join(repo, "web", "py", f), "utf-8"));
py.FS.writeFile("/home/pyodide/glue.py", fs.readFileSync(path.join(repo, "web", "glue.py"), "utf-8"));
py.runPython("import sys; sys.path.insert(0, '/home/pyodide')");
const glue = py.pyimport("glue");
const logs = [];
const logFn = (m, t = "info") => { logs.push([t, m]); };
const read = (p) => {
  const buf = fs.readFileSync(p);
  return (p.endsWith(".gz") ? zlib.gunzipSync(buf) : buf).toString("utf-8");
};
const results = [];
for (const step of program) {
  const conv = (a) => {
    if (typeof a === "string" && a.startsWith("$file:")) return read(a.slice(6));
    if (a === "$log") return logFn;
    if (Array.isArray(a)) return a.map(conv);
    if (a && typeof a === "object" && a.$bytes) return Uint8Array.from(Buffer.from(a.$bytes, "base64"));
    return a;
  };
  const args = (step.args || []).map(conv);
  let r = glue[step.fn](...args);
  if (r && typeof r.toJs === "function") {
    const js = r.toJs();
    r = js instanceof Uint8Array ? { $bytes: Buffer.from(js).toString("base64") } : js;
  }
  results.push(r);
}
console.log(JSON.stringify({ results, logs }));
