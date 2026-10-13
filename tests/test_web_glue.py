"""web/glue.py - the thin Pyodide entry points. Same filter_core underneath, so the
browser build can't drift from desktop; these just guard the JSON plumbing."""
from __future__ import annotations
import importlib.util
import io
import json
import zipfile
from pathlib import Path

from poe_price_trade import filter_core, filter_gen

_ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("web_glue", _ROOT / "web" / "glue.py")
glue = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(glue)

_LOG = lambda m, t="info": None
_BASE = ('Show # $type->currency $tier->t1\n\tBaseType == "Divine Orb"\n\tPlayAlertSound 6 300\n\n'
         'Show # $type->currency $tier->t2\n\tBaseType == "Exalted Orb"\n\tPlayAlertSound 1 300\n')


def test_constants_come_from_the_shared_python():
    k = json.loads(glue.constants())
    assert k["categories"] == filter_gen.WHITELIST_CATEGORIES
    assert k["gem_uncut"] == filter_gen.WHITELIST_GEM_UNCUT
    assert k["levels"] == filter_core.LEVELS
    assert k["tiers"] == ["S", "A", "B", "C"] and k["all_tiers"] == ["S", "A", "B", "C", "D"] and k["app"] == "web-" + __import__("poe_price_trade").__version__           # no price thresholds; the page names itself
    assert k["style"]["default_quest"] and "Red" in k["style"]["colors"]


def test_generate_whitelist_matches_core_directly():
    cfg = {"whitelist_enabled": True, "whitelist_gold": True, "whitelist_gold_min": 25}
    res = json.loads(glue.generate(json.dumps(cfg), "poe2", None, None, None, _LOG))
    core = filter_core.build_filter_text(cfg, "poe2")
    assert res["status"] == "ok" and res["text"] == core["generated_section"] and res["count"] == 1


def test_generate_tier_is_base_plus_header_and_ignores_any_hub_payload():
    plain = json.loads(glue.generate("{}", "poe2", None, _BASE, "t", _LOG))
    assert plain["status"] == "ok" and plain["sounds"] == {}
    assert plain["text"] == filter_core.compose_filter_body(filter_core.TIER_HEADER, _BASE)
    with_hub = json.loads(glue.generate("{}", "poe2", json.dumps({"currency": [{"name": "x"}]}), _BASE, "t", _LOG))
    assert with_hub["text"] == plain["text"]


def test_generate_statuses():
    none = glue.generate(json.dumps({"whitelist_enabled": True}), "poe2", None, None, None, _LOG)
    assert json.loads(none) == {"status": "none"}
    err = json.loads(glue.generate("{}", "poe2", None, None, None, _LOG))
    assert err["status"] == "error" and "nothing to write" in err["message"]


def test_category_and_gem_helpers():
    hub = {"currency": [], "items": [{"category": "Rune", "name": "B Rune"}, {"category": "Rune", "name": "A Rune"},
                                     {"category": "Fragment", "name": "F"}]}
    json.loads(glue.wl_init("poe2", "{}"))
    msgs = json.loads(glue.wl_load(json.dumps(hub), "", json.dumps(["A Rune", "B Rune", "F"])))
    assert msgs[-1][0] == "warn" and "NeverSink base filter" in msgs[-1][1]             # no base filter: said so
    assert [r["key"] for r in json.loads(glue.wl_rows("Rune", ""))["rows"]] == ["A Rune", "B Rune"]
    assert json.loads(glue.validate_name("a/b"))["error"] and json.loads(glue.validate_name("ok"))["error"] == ""
    assert glue.safe_name("a#b;c.mp3") == "a_b_c.mp3"
    gems = {"gems": [{"display_name": "Fireball"}, {"display_name": "fireball"}, {"display_name": "..."},
                     {"display_name": " Vaal Grace "}, {}]}
    assert json.loads(glue.gem_names(json.dumps(gems))) == ["Fireball", "Vaal Grace"]


def test_neversink_urls_exposed():
    assert glue.ns_latest_url("poe1").startswith("https://api.github.com/repos/")
    assert "NeverSink-Filter-for-PoE2" in glue.ns_file_url("poe2", "t", "2")


def test_generate_reports_sound_destinations_only_for_tiers_that_have_a_file():
    logs = []
    cfg = {"sound_1": "My Ping.MP3", "sound_2": "", "sound_3": "x.wav"}
    out = json.loads(glue.generate(json.dumps(cfg), "poe2", None, _BASE, "t", _LOG))
    assert out["status"] == "ok" and out["sounds"] == {"1": "My Ping.MP3", "3": "x.wav"}      # the file's own names
    assert 'CustomAlertSoundOptional "My Ping.MP3" 300' in out["text"]                        # Divine's block (sound 6)
    assert "poe-checker-S" not in out["text"] and "x.wav" not in out["text"]                  # no block uses sound 2 here
    bad = json.loads(glue.generate(json.dumps({"sound_1": "a#b.mp3", "sound_2": "a#b.mp3"}), "poe2", None, _BASE, "t", lambda m, t="info": logs.append(m)))
    assert bad["sounds"] == {"1": "a_b.mp3", "2": "a_b.mp3"} and any("เพราะเกมเล่นไฟล์ที่ชื่อมี #" in m for m in logs)
    twin = json.loads(glue.generate(json.dumps({"sound_1": "x.mp3", "sound_2": "x.mp3"}), "poe2", None, _BASE, "t", _LOG,
                                    json.dumps({"1": "h1", "2": "h2"})))
    assert twin["sounds"] == {"1": "x.mp3", "2": "x-2.mp3"}                                    # different files, one name


def test_legacy_whitelist_uses_the_numbered_sound_and_missing_base_errors():
    cfg = {"whitelist_enabled": True, "whitelist_gold": True, "sound_s": "a.mp3"}
    wl = json.loads(glue.generate(json.dumps(cfg), "poe2", None, None, None, _LOG))
    assert wl["sounds"] == {"1": "a.mp3"}      # the legacy whitelist reads the NeverSink tab's numbered sounds (old sound_s = 1)
    nobase = json.loads(glue.generate(json.dumps({"sound_s": "a.mp3"}), "poe2", None, None, None, _LOG))
    assert nobase["status"] == "error"


def test_make_zip_contains_filter_and_untouched_sound_bytes():
    snd = bytes(range(256)) * 4
    raw = glue.make_zip("a\r\nb\r\n", "my-filter", ["poe-checker-S.mp3"], [snd])
    z = zipfile.ZipFile(io.BytesIO(raw))
    assert z.namelist() == ["my-filter.filter", "poe-checker-S.mp3"]
    assert z.read("my-filter.filter") == b"a\r\nb\r\n" and z.read("poe-checker-S.mp3") == snd


def test_filter_kind_tells_who_made_a_file_from_its_first_lines():
    from poe_price_trade import wl_embed
    wl = "# === PoE Checker - Whitelist (own tiers, starting tiers from NeverSink strictness 2) ===\n\n# tier S\n"
    assert glue.filter_kind(wl) == "whitelist"
    assert glue.filter_kind(wl_embed.WL_HEADER + " (show only) ===") == "whitelist"          # an older file of the tab too
    assert glue.filter_kind(filter_core.TIER_HEADER + "\n# ===== base filter below =====") == "tier"
    assert glue.filter_kind('Show\n    Class "Gems"\n') == "other" and glue.filter_kind("") == "other"


def test_the_pages_own_files_carry_the_program_version_in_index_html():
    """A static server sends no Cache-Control, so a browser may keep an older copy of one script next to a new one: every own
    script / stylesheet in index.html is stamped `?v=<version>` by tools/sync_web_py.py."""
    import re
    from pathlib import Path
    from poe_price_trade import __version__
    html = (Path(__file__).resolve().parent.parent / "web" / "index.html").read_text(encoding="utf-8")
    own = re.findall(r'(?:src|href)="((?:js/\w+\.js)|app\.js|style\.css)(\?v=[^"]*)?"', html)
    assert len(own) >= 9 and all(v == f"?v={__version__}" for _f, v in own), own
