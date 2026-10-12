"""The web page's Python (web/glue.py in Pyodide, run with node) gives the same answers as the desktop program:
the same filter file byte for byte, the same settings after the same edits, the same messages when a file is
opened, a zip with what the filter names. Needs node + `npm i` in tests/web_parity (skipped without)."""
from __future__ import annotations
import base64
import gzip
import hashlib
import io
import json
import re
import shutil
import subprocess
import zipfile
from pathlib import Path
from unittest import mock

import pytest

from poe_price_trade import __version__, filter_service, filter_style, wl_embed, wl_session
from poe_price_trade.wl_model import WlModel
from tests.test_wl_import import _drop, old_text
from tests.test_wl_phase3b import _generate, data, model

HERE = Path(__file__).parent
PARITY = HERE / "web_parity"
SAMPLE = HERE / "sample_data"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(not NODE or not (PARITY / "node_modules" / "pyodide").is_dir(),
                                reason="node + tests/web_parity/node_modules (npm i) needed")


def web(program: list, tmp_path: Path) -> dict:
    prog = tmp_path / "program.json"
    prog.write_text(json.dumps(program), encoding="utf-8")
    run = subprocess.run([NODE, str(PARITY / "run.mjs"), str(prog)], capture_output=True, text=True, timeout=300,
                         encoding="utf-8")
    assert run.returncode == 0, run.stderr[-2000:]
    return json.loads(run.stdout.strip().splitlines()[-1])


def fixture_files(game: str, tmp_path: Path) -> dict:
    """The data the desktop tests mock in, as files the node script can read (same objects)."""
    hub, base, extra = data(game)
    hub_f = tmp_path / f"hub_{game}.json"
    hub_f.write_text(json.dumps(hub), encoding="utf-8")
    names_f = tmp_path / f"names_{game}.json"
    names_f.write_text(json.dumps(sorted(extra)), encoding="utf-8")
    return {"hub": f"$file:{hub_f}", "base": f"$file:{SAMPLE / f'neversink_{game}_s2.filter'}",
            "names": f"$file:{names_f}"}


def desktop_file(fg: dict, game: str, tmp_path: Path, name: str, mode: str) -> Path:
    hub, base, extra = data(game)
    cfg = dict(fg, whitelist_enabled=(mode == "whitelist"), **{f"game_dir_{game}": str(tmp_path / "game"),
                                                              "filter_name_whitelist": name, "filter_name_tier": name})
    holder = type("C", (), {"get": lambda self, k, d=None: dict(cfg) if k == "filter_gen" else d,
                            "app_dir": lambda self: tmp_path / "app"})()
    with mock.patch.object(filter_service.neversink_source, "fetch_base_filter", return_value=(base, "t")), \
         mock.patch.object(filter_service.hub_client, "get_prices", return_value=hub), \
         mock.patch.object(filter_service.trade_names, "get_names", return_value=extra):
        return filter_service.generate_filter(holder, game, "p", mode=mode)["path"]


def to_crlf(text: str) -> str:
    """The page's toCrlf: what the desktop programs write on Windows."""
    return re.sub(r"\r?\n", "\r\n", text)


def body_of(text: str) -> str:
    """The filter without the comment lines that carry the settings."""
    return text.split("\n\n# settings of this filter")[0]


def configs(game: str) -> dict:
    out = {"defaults": model(game).to_config({})}
    m = model(game)
    m.set_row("Currency", "Chaos Orb", "S")
    m.set_category("Fragment", "C")
    m.set_tier_stack("B", 4)
    m.set_stack(["Divine Orb"], 6)
    m.gold, m.gold_min, m.map_on, m.map_tier, m.map_rarity = True, 12, True, 7, "Rare"
    m.set_style_from_editor("A", dict(m.effective_style("A"), text=None, size=36))
    m.set_style_from_editor("B", dict(m.effective_style("B"), bg=[1, 2, 3, 0]))
    m.set_flask_custom("Flask", True)
    m.set_flask_rarity("Flask", "Magic", "C")
    m.set_flask_rarity("Flask", "Normal", "B")
    m.custom = [{"name": "heavy belt", "rarities": ["Magic", "Rare"], "tier": "A"}]
    out["edited"] = m.to_config({})
    return out


@pytest.mark.parametrize("game", ["poe1", "poe2"])
def test_the_whitelist_file_is_the_same_byte_for_byte(game, tmp_path):
    files = fixture_files(game, tmp_path)
    for key, fg in configs(game).items():
        want = desktop_file(fg, game, tmp_path / key, f"wl-{key}", "whitelist").read_bytes()
        cfg = dict(fg, whitelist_enabled=True)
        res = web([{"fn": "generate", "args": [json.dumps(cfg), game, files["hub"], files["base"], "t", "$log", "{}",
                                                files["names"]]}], tmp_path)["results"][0]
        got = json.loads(res)
        assert got["status"] == "ok"
        # the file is the same byte for byte; only the embedded settings differ in the program version they record
        web_text, want_text = got["text"], want.decode("utf-8").replace("\r\n", "\n")
        assert body_of(web_text) == body_of(want_text), (game, key)
        a, b = wl_embed.extract(web_text), wl_embed.extract(want_text)
        assert a["app"] == "web-" + __version__ and b["app"] == __version__ and a["cfg"] == b["cfg"] and a["game"] == b["game"]
        assert wl_embed.embed_lines(a["cfg"], game, __version__) == wl_embed.embed_lines(b["cfg"], game, __version__)


@pytest.mark.parametrize("game", ["poe1", "poe2"])
def test_the_neversink_tab_file_is_the_same_byte_for_byte(game, tmp_path):
    files = fixture_files(game, tmp_path)
    fg = {"strictness_" + game: 2, "style_q": filter_style.default_quest_style()}
    want = desktop_file(fg, game, tmp_path / "t", "ns-tab", "tier").read_bytes()
    res = json.loads(web([{"fn": "generate", "args": [json.dumps(dict(fg, whitelist_enabled=False)), game, None,
                                                       files["base"], "t", "$log", "{}"]}], tmp_path)["results"][0])
    assert res["status"] == "ok"
    assert to_crlf(res["text"]).encode("utf-8") == want          # what the page downloads == what the desktop writes


def test_sound_file_names_and_the_filter_that_names_them_are_the_same(tmp_path):
    src = tmp_path / "snd"
    src.mkdir()
    for n in ("my#sound.mp3", "b-sound.mp3"):
        (src / n).write_bytes(n.encode())
    game = "poe2"
    snd = lambda path: {"sound": {"kind": "file", "file": str(path), "id": 1, "volume": 300}}
    fg = dict(model(game).to_config({}), wl_tier_style={"S": snd(src / "my#sound.mp3"), "B": snd(src / "b-sound.mp3")},
              style_q=dict(filter_style.default_quest_style(), sound={"kind": "file", "file": str(src / "b-sound.mp3"),
                                                                       "id": 1, "volume": 300}))
    path = desktop_file(fg, game, tmp_path / "d", "snd", "whitelist")
    desktop_names = sorted(p.name for p in path.parent.glob("*.mp3"))
    files = fixture_files(game, tmp_path)
    web_cfg = dict(fg, whitelist_enabled=True,
                   wl_tier_style={"S": snd("my#sound.mp3"), "B": snd("b-sound.mp3")},
                   style_q=dict(fg["style_q"], sound={"kind": "file", "file": "b-sound.mp3", "id": 1, "volume": 300}))
    hashes = {k: hashlib.sha256((src / n).read_bytes()).hexdigest() for k, n in (("S", "my#sound.mp3"), ("B", "b-sound.mp3"),
                                                                                  ("Q", "b-sound.mp3"))}
    res = json.loads(web([{"fn": "generate", "args": [json.dumps(web_cfg), game, files["hub"], files["base"], "t", "$log",
                                                       json.dumps(hashes), files["names"]]}], tmp_path)["results"][0])
    assert res["status"] == "ok"
    assert sorted({d for d in res["sounds"].values()}) == desktop_names == ["b-sound.mp3", "my_sound.mp3"]   # "#" -> "_"
    assert body_of(res["text"]) == body_of(path.read_bytes().decode("utf-8").replace("\r\n", "\n"))
    # the game folder already has a different file of that name: the page asks, then writes -2 / overwrites
    existing = json.dumps({"b-sound.mp3": "0" * 64, "my_sound.mp3": hashes["S"]})
    prog = lambda dec: [{"fn": "generate", "args": [json.dumps(web_cfg), game, files["hub"], files["base"], "t", "$log",
                                                    json.dumps(hashes), files["names"], existing, json.dumps(dec)]}]
    ask = json.loads(web(prog({}), tmp_path)["results"][0])
    assert ask["status"] == "ask" and ask["conflicts"][0]["name"] == "b-sound.mp3"
    keep = json.loads(web(prog({"b-sound.mp3": "keep"}), tmp_path)["results"][0])
    assert keep["sounds"]["B"] == "b-sound-2.mp3" and ["B", "b-sound-2.mp3"] in keep["copies"] or \
        any(c[1] == "b-sound-2.mp3" for c in keep["copies"])
    over = json.loads(web(prog({"b-sound.mp3": "overwrite"}), tmp_path)["results"][0])
    assert over["sounds"]["B"] == "b-sound.mp3" and any(c[1] == "b-sound.mp3" for c in over["copies"])
    assert not any(c[1] == "my_sound.mp3" for c in over["copies"])      # same content is not copied again


@pytest.mark.parametrize("game", ["poe1", "poe2"])
def test_the_same_edits_give_the_same_settings_and_rows(game, tmp_path):
    files = fixture_files(game, tmp_path)
    steps = [("set_category", {"cat": "Fragment", "tier": "C"}), ("move", {"cat": "Currency", "keys": ["Chaos Orb"], "tier": "S"}),
             ("toggle", {"cat": "Currency", "key": "Divine Orb", "active": "A"}),
             ("set_tier_stack", {"tier": "B", "n": 5}), ("set_stack", {"cat": "Currency", "keys": ["Chaos Orb"], "n": 3}),
             ("set_flask_custom", {"row": "Flask", "custom": True}),
             ("set_flask_rarity", {"row": "Flask", "rarity": "Magic", "tier": "C"}),
             ("reset_rows", {"cat": "Currency", "keys": ["Chaos Orb"]})]
    prog = [{"fn": "wl_init", "args": [game, "{}"]}, {"fn": "wl_load", "args": [files["hub"], files["base"], files["names"]]}]
    prog += [{"fn": "wl_do", "args": [a, json.dumps(args)]} for a, args in steps]
    prog += [{"fn": "wl_set_parts", "args": [json.dumps({"gold": True, "gold_min": "30", "map_on": True, "map_tier": 99})]},
             {"fn": "wl_custom_add", "args": ["Heavy Belt", json.dumps(["Rare"]), "A"]},
             {"fn": "wl_set_style", "args": ["A", json.dumps(dict(filter_style.normalize_style({}), size=33))]},
             {"fn": "wl_config", "args": []}, {"fn": "wl_categories", "args": []},
             {"fn": "wl_rows", "args": ["Currency", ""]}, {"fn": "wl_rows", "args": ["flaskcharm", ""]},
             {"fn": "wl_rows", "args": ["Relic", "relic"]}, {"fn": "wl_parts", "args": []}]
    res = web(prog, tmp_path)["results"]
    # desktop twin
    m = model(game)
    m.set_category("Fragment", "C"); m.set_row("Currency", "Chaos Orb", "S"); m.toggle_row("Currency", "Divine Orb", "A")
    m.set_tier_stack("B", 5)
    m.set_stack([r.key for r in m.rows("Currency") if r.stackable and r.key == "Chaos Orb"], 3)
    m.set_flask_custom("Flask", True); m.set_flask_rarity("Flask", "Magic", "C"); m.reset_row("Currency", "Chaos Orb")
    m.gold, m.gold_min, m.map_on, m.map_tier = True, 30, True, 16
    m.custom.append({"name": "Heavy Belt", "rarities": ["Rare"], "tier": "A"})
    m.set_style_from_editor("A", dict(filter_style.normalize_style({}), size=33))
    assert json.loads(res[-6]) == json.loads(json.dumps(m.to_config({})))
    assert json.loads(res[-5]) == [{"id": c, "label": l} for c, l in m.categories()]
    assert json.loads(res[-3])["flask"] == m.flask_rows()                  # the Flask / Charm rows with their controls
    for key, cat, q in ((-4, "Currency", ""), (-2, "Relic", "relic")):
        rows = json.loads(res[key])["rows"]
        assert [(r["key"], r["label"], r["tier"], r["user_set"], r["stack"]) for r in rows] == \
            [(r.key, r.label, r.tier, r.user_set, r.stack) for r in m.rows(cat, q)]
    assert json.loads(res[-1])["gold_min"] == 30


def test_opening_a_file_says_and_does_the_same(tmp_path):
    cases = [("v2_poe2_checker_whitelist", "poe2"), ("v2_poe2_bus", "poe2"), ("v1_poe1_checker_whitelist", "poe1"),
             ("v2_poe1_wl_sample", "poe1")]
    emb = {}
    for game in ("poe1", "poe2"):
        m = model(game)
        m.set_row("Currency", "Chaos Orb", "S")
        emb[game] = _generate(m.to_config({}), game, tmp_path / game, name="emb")["path"]
    cases = [(c, g, None) for c, g in cases] + [("emb", g, emb[g]) for g in ("poe1", "poe2")]
    for name, game, path in cases:
        text = path.read_text(encoding="utf-8") if path else old_text(name)
        filename = (path.name if path else f"{name}.filter")
        cur = WlModel(game)
        cur.set_data(*data(game))
        want = wl_session.open_text(text, filename, game, cur, data(game),
                                    current_sound=lambda l: "", sound_file=lambda n: n if n in ("sound-S.mp3", "sound-A.mp3") else None)
        files = fixture_files(game, tmp_path)
        tf = tmp_path / f"{name}.txt"
        tf.write_text(text, encoding="utf-8")
        res = web([{"fn": "wl_init", "args": [game, "{}"]},
                   {"fn": "wl_load", "args": [files["hub"], files["base"], files["names"]]},
                   {"fn": "wl_open", "args": [f"$file:{tf}", filename, game, "{}",
                                              json.dumps(["sound-S.mp3", "sound-A.mp3"])]}], tmp_path)["results"][2]
        got = json.loads(res)
        assert got["ok"] == want.ok and [tuple(m) for m in got["messages"]] == [tuple(m) for m in want.messages], name
        assert got["name"] == want.name and got["sounds"] == want.sounds and got["kind"] == want.kind
        if want.ok:
            assert got["cfg"] == json.loads(json.dumps(want.model.to_config({}))), name


def test_the_zip_holds_the_filter_and_the_sound_files_byte_for_byte(tmp_path):
    payload = b"RIFF-not-really-audio"
    res = web([{"fn": "make_zip", "args": ["Show\n", "my-filter", ["a.mp3"], [{"$bytes": base64.b64encode(payload).decode()}]]}],
              tmp_path)["results"][0]
    z = zipfile.ZipFile(io.BytesIO(base64.b64decode(res["$bytes"])))
    assert sorted(z.namelist()) == ["a.mp3", "my-filter.filter"]
    assert z.read("a.mp3") == payload and z.read("my-filter.filter") == b"Show\n"
