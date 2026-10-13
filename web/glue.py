"""Thin Python entry points the web page calls through Pyodide.

No filter logic lives here: it keeps the Whitelist tab's state (a `WlModel`, the same class the desktop
window uses), converts JSON in / out and calls the shared poe_price_trade modules (copied into the Pyodide FS from
web/py/ by app.js). Everything crosses the JS boundary as JSON strings. The messages the tab shows come from
poe_price_trade.wl_session, so the page says what the desktop window says."""
from __future__ import annotations
import io
import json
import zipfile
from pathlib import PurePath

from poe_price_trade import __version__, filter_core, filter_gen, filter_style, filter_whitelist as w, wl_embed, wl_session
from poe_price_trade.wl_model import ALL_CHOICES, EQUIP_CATEGORY, FLASK_CATEGORY, RARITIES, TIER_CHOICES, WlModel

APP_VERSION = "web-" + __version__          # recorded in the embedded settings; the page shows it too (bug reports)
_S: dict = {"game": "poe2", "model": None, "data": None}


def _j(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)


def _model() -> WlModel:
    return _S["model"]


# ---------------------------------------------------------------------------------------------- constants / urls

def constants() -> str:
    return _j({
        "categories": filter_gen.WHITELIST_CATEGORIES,
        "gem_uncut": filter_gen.WHITELIST_GEM_UNCUT,
        "levels": filter_core.LEVELS,
        "tiers": list(TIER_CHOICES), "all_tiers": list(ALL_CHOICES), "rarities": list(RARITIES),
        "rarity_choices": list(w.RARITY_CHOICES),
        "style": {"colors": list(filter_style.COLORS), "shapes": list(filter_style.SHAPES),
                  "sound_ids": list(filter_style.SOUND_IDS), "font_min": filter_style.FONT_MIN,
                  "font_max": filter_style.FONT_MAX, "volume_max": filter_style.VOLUME_MAX,
                  "default_volume": filter_style.DEFAULT_VOLUME,
                  "default_quest": filter_style.default_quest_style()},
        "default_names": {"tier": filter_core.DEFAULT_TIER_NAME, "whitelist": filter_core.DEFAULT_WHITELIST_NAME},
        "app": APP_VERSION,
    })


def plan(cfg_json: str, game: str) -> str:
    return _j(filter_core.plan_fetch(json.loads(cfg_json), game))


def ns_latest_url(game: str) -> str:
    return filter_core.neversink_latest_api_url(game)


def ns_file_url(game: str, tag: str, strictness: int) -> str:
    return filter_core.neversink_file_url(game, tag, int(strictness))


def validate_name(name: str) -> str:
    n, err = filter_core.validate_filter_name(name)
    return _j({"name": n, "error": err or ""})


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
    return _j(sorted(out))


# ---------------------------------------------------------------------------------------------- the whitelist model

def wl_init(game: str, cfg_json: str) -> str:
    """A fresh model from the saved settings (an old-style whitelist config is converted, like the desktop window).
    Returns {"updates": keys to merge into the saved config, "notes": [str]}."""
    fg = json.loads(cfg_json or "{}")
    updates, notes = WlModel.convert_legacy(fg, game)
    fg.update(updates)
    # sounds: a saved config with sound_s / sound_a / sound_b becomes sound_1 / 2 / 3 (NeverSink tab) and the tier sounds of
    # the Whitelist tab, once; `moved` = the old sound slot -> its new NeverSink-tab slot (the page copies the file)
    moved: dict = {}
    if fg.get("sound_format") != filter_core.SOUND_FORMAT:
        moved = {t: n for t, n in (("S", "1"), ("A", "2"), ("B", "3")) if fg.get(f"sound_{t.lower()}")}
        migrated, _sound_notes = filter_core.migrate_sounds(fg)
        keys = ["sound_format", "sound_1", "sound_2", "sound_3", "wl_tier_style", "sound_s", "sound_a", "sound_b", "sound_c"]
        updates.update({k: migrated.get(k, "") for k in keys})
    _S.update(game=game, model=WlModel.from_config(fg, game), data=None)
    return _j({"updates": updates, "notes": notes, "moved": moved})


def wl_load(hub_json, base_text: str, names_json) -> str:
    """The item lists arrived: give them to the model. Returns the messages for the Status."""
    hub = json.loads(hub_json) if hub_json else None
    names = set(json.loads(names_json)) if names_json else set()
    _S["data"] = (hub, base_text or "", names)
    _model().set_data(*_S["data"])
    return _j(wl_session.data_loaded_messages(_model(), base_text or ""))


def wl_config() -> str:
    """Every wl_* / whitelist_* key of the model (merge into the saved config before generating / saving)."""
    return _j(_model().to_config({}))


def wl_categories() -> str:
    return _j([{"id": c, "label": l} for c, l in _model().categories()])


def _row(r) -> dict:
    return {"key": r.key, "label": r.label, "tier": r.tier, "default": r.default, "user_set": r.user_set,
            "note": r.note, "stackable": r.stackable, "stack": r.stack, "stack_set": r.stack_set}


def wl_rows(cat: str, query: str = "") -> str:
    m = _model()
    if not m.loaded:
        return _j({"loading": True, "rows": [], "info": {}})
    rows = m.rows(cat, query)
    info = {"count": len(rows), "changed": m.changed_count(cat), "cat_tier": m.category_tier(cat),
            "flask": cat == FLASK_CATEGORY, "equip": cat == EQUIP_CATEGORY}
    out = {"loading": False, "rows": [_row(r) for r in rows], "info": info, "warn": sorted({r.note for r in rows if r.note})}
    if cat == FLASK_CATEGORY:                                   # no list: the Flask / Charm (Tincture) rows with their controls
        out["flask"] = m.flask_rows()
    if cat == EQUIP_CATEGORY:                                   # no list: classes by group, each with its own controls
        out["equip"] = m.equip_groups()
    return _j(out)


def wl_do(action: str, args_json: str = "{}") -> str:
    """One edit of the model (what the desktop panel's buttons do). Returns {} (the page re-reads the rows)."""
    a = json.loads(args_json or "{}")
    m = _model()
    cat = a.get("cat", "")
    if action == "toggle":
        m.toggle_row(cat, a["key"], a["active"])
    elif action == "move":                                   # selected rows -> the active tier
        for k in a["keys"]:
            m.set_row(cat, k, a["tier"])
    elif action == "reset_rows":
        for k in a["keys"]:
            m.reset_row(cat, k)
    elif action == "set_category":
        m.set_category(cat, a["tier"])
    elif action == "reset_category":
        m.reset_category(cat)
    elif action == "set_stack":                              # only names that can stack
        ok = {r.key for r in m.rows(cat) if r.stackable}
        m.set_stack([k for k in a["keys"] if k in ok], max(1, int(a.get("n") or 1)))
    elif action == "set_tier_stack":
        m.set_tier_stack(a["tier"], max(1, int(a.get("n") or 1)))
    elif action == "set_flask_custom":                       # Flask / Charm (Tincture) row: default <-> set myself
        m.set_flask_custom(a["row"], bool(a["custom"]))
    elif action == "set_flask_rarity":
        m.set_flask_rarity(a["row"], a["rarity"], a.get("tier") if a.get("tier") in ALL_CHOICES else None)
    elif action == "set_equip_custom":                       # equipment class row: default <-> set myself
        m.set_equip_custom(a["cls"], bool(a["custom"]))
    elif action == "set_equip_rarity":
        m.set_equip_rarity(a["cls"], a["rarity"], a.get("tier") if a.get("tier") in ALL_CHOICES else None)
    elif action == "set_equip_group":                        # one rarity of every class of the group
        m.set_equip_group(a["group"], a["rarity"], a.get("tier") if a.get("tier") in ALL_CHOICES else None)
    else:
        raise ValueError("unknown action " + action)
    return "{}"


def wl_style(label: str) -> str:
    m = _model()
    return _j({"effective": m.effective_style(label), "base": m.base_style(label)})


def wl_set_style(label: str, style_json: str) -> str:
    _model().set_style_from_editor(label, json.loads(style_json))
    return "{}"


def wl_clear_style(label: str) -> str:
    _model().set_style(label, None)
    return "{}"


def wl_parts() -> str:
    m = _model()
    return _j({"gold": m.gold, "gold_min": m.gold_min, "map_on": m.map_on, "map_tier": m.map_tier,
               "map_rarity": m.map_rarity, "gem_uncut": m.gem_uncut, "gem_names": m.gem_names, "gem_tier": m.gem_tier,
               "custom": m.custom, "tier_stack": m.tier_stack, "game": m.game,
               "gem_uncut_bases": filter_gen.WHITELIST_GEM_UNCUT.get(m.game, []),
               "unique_conflicts": [[b, t] for b, t in m.unique_conflicts()]})


def wl_set_parts(parts_json: str) -> str:
    """The 'ส่วนแยก' fields (same coercions as the desktop panel's read_parts)."""
    p = json.loads(parts_json)
    m = _model()
    if "gold" in p:
        m.gold = bool(p["gold"])
    if "gold_min" in p:
        try:
            m.gold_min = max(0, int(p["gold_min"] or 0))
        except (TypeError, ValueError):
            m.gold_min = 0
    if "map_on" in p:
        m.map_on = bool(p["map_on"])
    if "map_tier" in p:
        try:
            m.map_tier = max(1, min(16, int(p["map_tier"] or 1)))
        except (TypeError, ValueError):
            m.map_tier = 1
    if "map_rarity" in p:
        m.map_rarity = p["map_rarity"] if p["map_rarity"] in RARITIES else "Normal"
    if "gem_tier" in p:
        m.gem_tier = p["gem_tier"] if p["gem_tier"] in ALL_CHOICES else "B"
    if "gem_uncut" in p:
        out = {}
        for base, lv in (p["gem_uncut"] or {}).items():
            try:
                out[str(base)] = max(1, int(lv or 1))
            except (TypeError, ValueError):
                out[str(base)] = 1
        m.gem_uncut = out
    if "gem_names" in p:
        m.gem_names = [str(n) for n in p["gem_names"] if n]
    return "{}"


def wl_custom_add(name: str, rarities_json: str, tier: str) -> str:
    nm = (name or "").strip()
    m = _model()
    if nm and not any(e["name"].lower() == nm.lower() for e in m.custom):
        rs = [r for r in RARITIES if r in set(json.loads(rarities_json))] or ["Normal"]
        m.custom.append({"name": nm, "rarities": rs, "tier": tier if tier in ALL_CHOICES else "B"})
    return "{}"


def wl_custom_remove(index: int) -> str:
    m = _model()
    if 0 <= int(index) < len(m.custom):
        del m.custom[int(index)]
    return "{}"


def filter_kind(head: str) -> str:
    """"whitelist" (made by the Whitelist tab - the tab can open and edit it) | "tier" (the NeverSink tab's) | "other",
    from the first lines of a .filter file (the header comment each of our files starts with)."""
    head = (head or "")[:600]
    if wl_embed.WL_HEADER in head:
        return "whitelist"
    if wl_embed.TIER_HEADER_START in head:
        return "tier"
    return "other"


def wl_open(text: str, filename: str, game: str, current_sounds_json: str, folder_files_json: str) -> str:
    """Open the text of a whitelist filter file (settings embedded, or an older file read back block by block).
    `current_sounds` = {S|A|B: file name now}; `folder_files` = the names of the files next to it (when the page can
    see that folder). On success the model is replaced; the page applies `cfg` and the sound names it gets back."""
    cur = json.loads(current_sounds_json or "{}")
    files = set(json.loads(folder_files_json or "[]"))
    out = wl_session.open_text(text, filename, game, _model(), _S.get("data"),
                               current_sound=lambda label: cur.get(label, ""),
                               sound_file=lambda name: name if name in files else None)
    if out.ok:
        _S["model"] = out.model
    return _j({"ok": out.ok, "messages": out.messages, "name": out.name, "sounds": out.sounds, "kind": out.kind,
               "app": out.app, "cfg": out.model.to_config({}) if out.ok else {}})


# ---------------------------------------------------------------------------------------------- generate / files

def _copy_sounds_fn(used: dict, hashes: dict, existing, decisions: dict, conflicts: list, copies: list, log):
    """Web twin of filter_output.copy_sounds: nothing is copied here (the page owns the files); it plans the
    destination names exactly like desktop does - the file's own name, "#" / ";" become "_", a name that is already
    in the folder with other content asks (overwrite / keep -> "-2"), the same content is reused - and records which
    sounds must be written. `existing` = {file name: content hash or None} of the game folder when the page can
    see it, else {} (a zip: every name is new). `hashes` = content hash per label from the page."""
    def fn(sound_map: dict) -> dict:
        requests = [(label, PurePath(src).name, hashes.get(label) or PurePath(src).name)
                    for label, src in (sound_map or {}).items() if src]

        def decide(name, new_name):
            conflicts.append({"name": name, "new_name": new_name})
            return decisions.get(name, "keep")
        dest, cps, msgs = filter_core.resolve_sound_plan(filter_core.plan_sound_files(requests, existing or {}), decide)
        for m in msgs:
            log(m, "info")
        used.update(dest)
        copies.extend(cps)
        return dest
    return fn


def generate(cfg_json: str, game: str, hub_json, base_text, base_tag, log, hashes_json=None, names_json=None,
             existing_json=None, decisions_json=None) -> str:
    cfg = json.loads(cfg_json)
    hashes = json.loads(hashes_json) if hashes_json else {}
    hub_data = json.loads(hub_json) if hub_json else None
    names = set(json.loads(names_json)) if names_json else None
    existing = json.loads(existing_json) if existing_json else None
    decisions = json.loads(decisions_json) if decisions_json else {}
    used: dict = {}
    conflicts: list = []
    copies: list = []
    try:
        res = filter_core.build_filter_text(
            cfg, game, hub_data=hub_data, base_text=base_text or None, base_tag=base_tag or None,
            extra_names=names, copy_sounds_fn=_copy_sounds_fn(used, hashes, existing, decisions, conflicts, copies, log),
            app_version=APP_VERSION, log=log)
        if res is None:
            return _j({"status": "none"})
        text = filter_core.compose_filter_body(res["generated_section"], res["base_text"])
    except ValueError as e:
        return _j({"status": "error", "message": str(e)})
    undecided = [c for c in conflicts if c["name"] not in decisions]
    if undecided:
        return _j({"status": "ask", "conflicts": undecided})
    return _j({"status": "ok", "mode": res["mode"], "text": text, "count": res.get("count"),
               "base_tag": res.get("base_tag"), "sounds": used, "copies": [list(c) for c in copies]})


def make_zip(filter_text: str, filter_name: str, names, datas) -> bytes:
    """<filter name>.filter + the sound files, ready to unpack into the game's filter folder."""
    names = names.to_py() if hasattr(names, "to_py") else list(names)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(filter_name + ".filter", filter_text.encode("utf-8"))
        for name, data in zip(names, datas):
            z.writestr(name, bytes(data.to_py()) if hasattr(data, "to_py") else bytes(data))
    return buf.getvalue()


def safe_name(name: str) -> str:
    """The file name the game can play (a "#" or ";" becomes "_"), what the sound planner uses."""
    return filter_core.safe_sound_name(name)[0]


def embed_check(text: str) -> str:
    """{"kind", "game", "app"} of a filter file's text (what the open button can do with it)."""
    emb = wl_embed.extract(text)
    return _j({"kind": wl_embed.classify(text), "game": emb["game"] if emb else "", "app": emb.get("app", "") if emb else ""})
