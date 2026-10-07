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
    assert "tiers" not in k                                              # no price thresholds any more


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
    hub = {"currency": [{"category": "Rune", "name": "B Rune"}, {"category": "Rune", "name": "A Rune"},
                        {"category": "Fragment", "name": "F"}], "items": []}
    assert json.loads(glue.category_names(json.dumps(hub), "Rune")) == ["A Rune", "B Rune"]
    gems = {"gems": [{"display_name": "Fireball"}, {"display_name": "fireball"}, {"display_name": "..."},
                     {"display_name": " Vaal Grace "}, {}]}
    assert json.loads(glue.gem_names(json.dumps(gems))) == ["Fireball", "Vaal Grace"]


def test_neversink_urls_exposed():
    assert glue.ns_latest_url("poe1").startswith("https://api.github.com/repos/")
    assert "NeverSink-Filter-for-PoE2" in glue.ns_file_url("poe2", "t", "2")


def test_generate_reports_sound_destinations_only_for_tiers_that_have_a_file():
    logs = []
    cfg = {"sound_s": "My Ping.MP3", "sound_a": "", "sound_b": "x.wav"}
    out = json.loads(glue.generate(json.dumps(cfg), "poe2", None, _BASE, "t", _LOG))
    assert out["status"] == "ok" and out["sounds"] == {"S": "My Ping.MP3", "B": "x.wav"}      # the file's own names
    assert 'CustomAlertSoundOptional "My Ping.MP3" 300' in out["text"]                        # Divine's block (sound 6)
    assert "poe-checker-S" not in out["text"] and "x.wav" not in out["text"]                  # no block uses sound 2 here
    bad = json.loads(glue.generate(json.dumps({"sound_s": "a#b.mp3", "sound_a": "a#b.mp3"}), "poe2", None, _BASE, "t", lambda m, t="info": logs.append(m)))
    assert bad["sounds"] == {"S": "a_b.mp3", "A": "a_b.mp3"} and any("เพราะเกมเล่นไฟล์ที่ชื่อมี #" in m for m in logs)
    twin = json.loads(glue.generate(json.dumps({"sound_s": "x.mp3", "sound_a": "x.mp3"}), "poe2", None, _BASE, "t", _LOG,
                                    json.dumps({"S": "h1", "A": "h2"})))
    assert twin["sounds"] == {"S": "x.mp3", "A": "x-2.mp3"}                                    # different files, one name


def test_no_sounds_for_whitelist_or_missing_base():
    cfg = {"whitelist_enabled": True, "whitelist_gold": True, "sound_s": "a.mp3"}
    wl = json.loads(glue.generate(json.dumps(cfg), "poe2", None, None, None, _LOG))
    assert wl["sounds"] == {}
    nobase = json.loads(glue.generate(json.dumps({"sound_s": "a.mp3"}), "poe2", None, None, None, _LOG))
    assert nobase["status"] == "error"


def test_make_zip_contains_filter_and_untouched_sound_bytes():
    snd = bytes(range(256)) * 4
    raw = glue.make_zip("a\r\nb\r\n", ["poe-checker-S.mp3"], [snd])
    z = zipfile.ZipFile(io.BytesIO(raw))
    assert z.namelist() == ["poe-checker.filter", "poe-checker-S.mp3"]
    assert z.read("poe-checker.filter") == b"a\r\nb\r\n" and z.read("poe-checker-S.mp3") == snd
