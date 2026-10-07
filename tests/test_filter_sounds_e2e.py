"""Every sound slot x both tabs x both games, through filter_service with the real NeverSink s2 filters and
real hub snapshots: the filter references the sound file, the file is in the game folder, nothing twice."""
import gzip
import json
import re
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

from poe_price_trade import filter_service

SAMPLE = Path(__file__).parent / "sample_data"
SLOTS = ["S", "A", "B", "Q", "G", "Tablet", "Map"]


def _load(game):
    base = (SAMPLE / f"neversink_{game}_s2.filter").read_text(encoding="utf-8")
    with gzip.open(SAMPLE / f"hub_{game}.json.gz", "rt", encoding="utf-8") as fh:
        hub = {"currency": [], "items": json.load(fh)["items"]}
    return base, hub


def _refs(text):
    return re.findall(r'^\s*CustomAlertSoundOptional "([^"]+)"', text, re.M)


def _run(tmp_path, game, v2):
    src = tmp_path / "src"
    src.mkdir()
    files = {}
    for s in SLOTS:
        files[s] = src / f"snd_{s}.mp3"
        files[s].write_bytes(s.encode() * 10)         # different content per slot
    style = lambda k: {"sound": {"kind": "file", "file": str(files[k]), "volume": 300}}
    fg = {"sound_s": str(files["S"]), "sound_a": str(files["A"]), "sound_b": str(files["B"]),
          "style_q": {"text": [1, 2, 3, 255], **style("Q")},
          "wl_tier_style": {k: style(k) for k in ("G", "Tablet", "Map")},
          "whitelist_gold": True, "whitelist_gold_min": 10, "wl_map_on": True, "wl_map_tier_min": 5,
          f"whitelist_custom_{game}": ["Divine Orb"], "wl_v2": v2}
    game_dir = tmp_path / "game"
    cfg = SimpleNamespace(get=lambda k, d=None: dict(fg, **{f"game_dir_{game}": str(game_dir)}) if k == "filter_gen" else d,
                          app_dir=lambda: tmp_path / "app")
    base, hub = _load(game)
    with mock.patch.object(filter_service.neversink_source, "fetch_base_filter", return_value=(base, "t")), \
         mock.patch.object(filter_service.hub_client, "get_prices", return_value=hub), \
         mock.patch.object(filter_service.trade_names, "get_names", return_value=set()):
        tier = filter_service.generate_filter(cfg, game, "p", mode="tier")
        wl = filter_service.generate_filter(cfg, game, "p", mode="whitelist")
    return (tier["path"].read_text(encoding="utf-8"), wl["path"].read_text(encoding="utf-8"),
            sorted(p.name for p in game_dir.glob("*.mp3")))


@pytest.mark.parametrize("game", ["poe1", "poe2"])
@pytest.mark.parametrize("v2", [False, True], ids=["legacy-whitelist", "wl_v2"])
def test_every_sound_slot_reaches_both_files(tmp_path, game, v2):
    tier, wl, folder = _run(tmp_path, game, v2)
    rt, rw = set(_refs(tier)), set(_refs(wl))
    name = lambda s: f"snd_{s}.mp3"
    for s in ("S", "A", "B", "Q"):                       # NeverSink tab: all four
        assert name(s) in rt, s
    assert not rt & {name("G"), name("Tablet"), name("Map")}
    if v2:
        for s in ("S", "A", "B", "Q", "G", "Map") + (("Tablet",) if game == "poe2" else ()):
            assert name(s) in rw, s
    else:   # old whitelist: S (gold / names), B (typed names) and Q; it has no block with NeverSink sound 1
        for s in ("S", "B", "Q"):
            assert name(s) in rw, s
    assert "-2" not in "".join(folder + sorted(rt | rw))
    assert (rt | rw) <= set(folder)                      # every file that is referenced is in the folder ...
    assert len(folder) == len(set(folder)) and set(folder) <= (rt | rw)    # ... once, and nothing extra
