/* Where the data comes from: NeverSink (GitHub: release tag + raw file, cached in localStorage), the hub (item names,
 * Google Cloud Storage, CORS set for this site), the real item names (the snapshot shipped with the page:
 * data/trade_names_<game>.json), the gem list (poe1). */
"use strict";
(() => {
const P = window.PFG;
const HUB = "https://storage.googleapis.com/poe-data-hub";
const KEY_NS = "poeFilterGen.ns.";
const NS_CHECK_HOURS = 24;
const hubCache = {};

async function fetchText(url, label) {
  let resp;
  try { resp = await fetch(url); } catch (e) { throw new Error(`${label} fetch failed (${url}): ${e.message || e}`); }
  if (!resp.ok) throw new Error(`${label} HTTP ${resp.status}: ${url}`);
  return resp.text();
}
P.fetchText = fetchText;

P.getHub = async (g) => {
  const c = hubCache[g];
  if (c && Date.now() - c.at < 5 * 60 * 1000) return c.text;
  const url = `${HUB}/${g}/prices/latest.json`;
  const text = await fetchText(url, "hub");
  try { JSON.parse(text); } catch (e) { throw new Error(`hub fetch failed (${url}): ${e.message}`); }
  hubCache[g] = { text, at: Date.now() };
  return text;
};

/** The real item names (GGG's trade list, which a browser cannot call) = the snapshot shipped with the page
 *  (data/trade_names_<game>.json, made by tools/refresh_web_names.py). Returns {text, from} or null.
 *  (Option kept in history.md: the hub could publish `{game}/trade_names.json` and this would try it first.) */
P.getNames = async (g) => {
  try {
    const list = JSON.parse(await fetchText(`data/trade_names_${g}.json`, "names snapshot"));
    if (!Array.isArray(list) || list.length < 500) throw new Error("too few names");
    return { text: JSON.stringify(list), from: "snapshot" };
  } catch (e) { return null; }
};

let gemAll = null;
P.getGemNames = async (g) => {
  if (g !== "poe1") return [];
  if (gemAll) return gemAll;
  try { gemAll = JSON.parse(P.glue.gem_names(await fetchText(`${HUB}/${g}/gems.json`, "gems"))); } catch (e) { gemAll = []; }
  return gemAll;
};

// ---- NeverSink base filter: same flow as neversink_source.fetch_base_filter, cache = localStorage ----
const nsLast = (g) => P.readJson(`${KEY_NS}last.${g}`, {});
P.nsLast = nsLast;
const nsTextKey = (g, tag, s) => `${KEY_NS}text.${g}|${tag}|${s}`;
async function nsLatestTag(g) {
  try {
    const resp = await fetch(P.glue.ns_latest_url(g), { headers: { Accept: "application/vnd.github+json" } });
    if (!resp.ok) return null;
    return (await resp.json()).tag_name || null;
  } catch (e) { return null; }
}
function nsCachePut(g, tag, s, text) {
  const prefix = `${KEY_NS}text.${g}|`;
  P.store.keys().filter((k) => k.startsWith(prefix) && !k.startsWith(`${prefix}${tag}|`)).forEach((k) => P.store.del(k));
  if (!P.store.set(nsTextKey(g, tag, s), text, false)) {
    P.store.keys().filter((k) => k.startsWith(KEY_NS + "text.")).forEach((k) => P.store.del(k));   // quota: start over
    P.store.set(nsTextKey(g, tag, s), text, false);                                                // still too big -> not cached
  }
}
/** [text, tag] of NeverSink's filter for this strictness ([null, null] when nothing can be had). */
P.fetchBase = async (g, strictness, force) => {
  const last = nsLast(g);
  let stale = true;
  if (last.checked_at) {
    const hrs = (Date.now() - Date.parse(last.checked_at)) / 3600000;
    stale = !(hrs <= NS_CHECK_HOURS);
  }
  let tag = last.tag || null;
  if (force || stale || !tag) {
    const fresh = await nsLatestTag(g);
    if (fresh) {
      tag = fresh;
      P.store.set(`${KEY_NS}last.${g}`, JSON.stringify({ tag, checked_at: new Date().toISOString() }));
    }
  }
  if (tag) {
    const key = nsTextKey(g, tag, strictness);
    const cached = P.store.get(key);
    if (cached && !force) return [cached, tag];
    try {
      const text = await fetchText(P.glue.ns_file_url(g, tag, strictness), "neversink");
      nsCachePut(g, tag, strictness, text);
      return [text, tag];
    } catch (e) { if (cached) return [cached, tag]; }
  }
  const suffix = `|${strictness}`;               // last resort: any cached tag for this game+strictness
  const keys = P.store.keys().filter((k) => k.startsWith(`${KEY_NS}text.${g}|`) && k.endsWith(suffix)).sort();
  if (keys.length) {
    const k = keys[keys.length - 1];
    const t = P.store.get(k);
    if (t) return [t, k.slice(`${KEY_NS}text.${g}|`.length, -suffix.length)];
  }
  return [null, null];
};
})();
