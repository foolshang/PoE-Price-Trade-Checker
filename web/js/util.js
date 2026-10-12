/* Small helpers shared by every part of the page. Everything lives on window.PFG (no bundler). */
"use strict";
window.PFG = window.PFG || {};
(() => {
const P = window.PFG;
P.$ = (s, r = document) => r.querySelector(s);
P.$$ = (s, r = document) => [...r.querySelectorAll(s)];
P.clone = (o) => JSON.parse(JSON.stringify(o));
P.esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

/** h("div", {class: "x", onclick: fn, dataset: {a: 1}}, child, "text", ...) */
P.h = (tag, attrs, ...kids) => {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "dataset") Object.assign(el.dataset, v);
    else if (k === "style" && typeof v === "object") Object.assign(el.style, v);
    else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
    else if (k === "value") el.value = v;
    else if (k === "checked" || k === "disabled" || k === "hidden" || k === "selected") el[k] = !!v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) {
    if (kid === null || kid === undefined || kid === false) continue;
    el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  return el;
};

P.debounce = (fn, ms = 120) => {
  let t = null;
  return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
};

/** text with LF -> CRLF, same bytes the desktop programs write on Windows */
P.toCrlf = (t) => t.replace(/\r?\n/g, "\r\n");

P.saveBlob = (bytes, filename, mime) => {
  const url = URL.createObjectURL(new Blob([bytes], { type: mime || "application/octet-stream" }));
  const a = document.createElement("a");
  a.href = url; a.download = filename;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
};

P.log = (msg, tag = "info") => {
  const box = P.$("#log");
  if (!box) return;
  const line = document.createElement("div");
  line.className = tag;
  line.textContent = msg;
  box.appendChild(line);
  box.scrollTop = box.scrollHeight;
};

/** a Python-side message list [[tag, text], ...] -> the Status */
P.logAll = (msgs) => { for (const [tag, text] of msgs || []) P.log(text, tag); };

P.rgba = (c, fallback) => (c ? `rgba(${c[0]},${c[1]},${c[2]},${(c[3] === undefined ? 255 : c[3]) / 255})` : fallback);
P.hex = (c) => "#" + (c || [0, 0, 0]).slice(0, 3).map((x) => Math.max(0, Math.min(255, x | 0)).toString(16).padStart(2, "0")).join("");
P.unhex = (s) => [1, 3, 5].map((i) => parseInt(s.slice(i, i + 2), 16));
})();
