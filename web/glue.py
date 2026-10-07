"""Thin Python entry points the web page calls through Pyodide.

No filter logic lives here - it only converts JSON in/out and calls the shared
poe_price_trade.filter_core / filter_gen (copied into the Pyodide FS from
web/py/ by app.js). Everything crosses the JS boundary as JSON strings. hub_json is only the
item-name list for whitelist categories; tier mode never gets prices."""
from __future__ import annotations
import io
import json
import zipfile
from pathlib import PurePath

from poe_price_trade import filter_core, filter_gen


def constants() -> str:
    return json.dumps({
        "categories": filter_gen.WHITELIST_CATEGORIES,
        "gem_uncut": filter_gen.WHITELIST_GEM_UNCUT,
        "levels": filter_core.LEVELS,
    })


def plan(cfg_json: str, game: str) -> str:
    return json.dumps(filter_core.plan_fetch(json.loads(cfg_json), game))


def ns_latest_url(game: str) -> str:
    return filter_core.neversink_latest_api_url(game)


def ns_file_url(game: str, tag: str, strictness: int) -> str:
    return filter_core.neversink_file_url(game, tag, int(strictness))


def category_names(hub_json: str, category: str) -> str:
    return json.dumps(sorted(set(filter_gen.names_in_categories(json.loads(hub_json), [category]))))


def gem_names(gems_json: str) -> str:
    """Autocomplete list for poe1 (same filtering as the desktop window)."""
    data = json.loads(gems_json) or {}
    seen, out = set(), []
    for g in data.get("gems", []):
        nm = (g.get("display_name") or "").strip()
        if not nm or nm == "..." or nm.lower() in seen:
            continue
        seen.add(nm.lower())
        out.append(nm)
    return json.dumps(sorted(out))


def _copy_sounds_fn(used: dict, hashes: dict, log):
    """Web twin of filter_output.copy_sounds: nothing is copied here (the page owns the files); it
    plans the destination names exactly like desktop does - the file's own name, "#" / ";" become
    "_", two different files with one name get -2 - and records which sounds the zip must contain.
    The browser cannot see the game's folder, so every name counts as new. `hashes` = content hash
    per label from the page (the same file picked for several slots is one file)."""
    def fn(sound_map: dict) -> dict:
        requests = [(label, PurePath(src).name, hashes.get(label) or PurePath(src).name)
                    for label, src in (sound_map or {}).items() if src]
        dest, _copies, msgs = filter_core.resolve_sound_plan(filter_core.plan_sound_files(requests, {}))
        for m in msgs:
            log(m, "info")
        used.update(dest)
        return dest
    return fn


def generate(cfg_json: str, game: str, hub_json, base_text, base_tag, log, hashes_json=None) -> str:
    cfg = json.loads(cfg_json)
    hashes = json.loads(hashes_json) if hashes_json else {}
    hub_data = json.loads(hub_json) if hub_json else None
    used: dict = {}
    try:
        res = filter_core.build_filter_text(
            cfg, game, hub_data=hub_data, base_text=base_text or None, base_tag=base_tag or None,
            copy_sounds_fn=_copy_sounds_fn(used, hashes, log), log=log)
        if res is None:
            return json.dumps({"status": "none"})
        text = filter_core.compose_filter_body(res["generated_section"], res["base_text"])
    except ValueError as e:
        return json.dumps({"status": "error", "message": str(e)})
    return json.dumps({"status": "ok", "mode": res["mode"], "text": text,
                       "count": res.get("count"), "base_tag": res.get("base_tag"), "sounds": used})


def make_zip(filter_text: str, names, datas) -> bytes:
    """poe-checker.filter + the sound files, ready to unpack into the game's filter folder."""
    names = names.to_py() if hasattr(names, "to_py") else list(names)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("poe-checker.filter", filter_text.encode("utf-8"))
        for name, data in zip(names, datas):
            z.writestr(name, bytes(data.to_py()) if hasattr(data, "to_py") else bytes(data))
    return buf.getvalue()
