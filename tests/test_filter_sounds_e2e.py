"""Every sound slot x both tabs x both games, through filter_service with the real NeverSink s2 filters and
real hub snapshots: the NeverSink tab's six numbered sounds land on every Show block of their NeverSink number (counted
per number), the Whitelist tab's tier / Gold / Map / Tablet / Gem sounds land in its own blocks, Q is the one shared
sound, the files are in the game folder and nothing is there twice."""
import gzip
import json
import re
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

from poe_price_trade import filter_gen, filter_service

SAMPLE = Path(__file__).parent / "sample_data"
NS_SLOTS = ["1", "2", "3", "4", "5", "6"]
WL_SLOTS = ["S", "A", "B", "C", "G", "Tablet", "Map", "Gem"]


def _load(game):
    base = (SAMPLE / f"neversink_{game}_s2.filter").read_text(encoding="utf-8")
    with gzip.open(SAMPLE / f"hub_{game}.json.gz", "rt", encoding="utf-8") as fh:
        hub = {"currency": [], "items": json.load(fh)["items"]}
    return base, hub


def _refs(text):
    return re.findall(r'^\s*CustomAlertSoundOptional "([^"]+)"', text, re.M)


def _run(tmp_path, game, v2, ns_slots=NS_SLOTS):
    src = tmp_path / "src"
    src.mkdir()
    files = {}
    for s in ns_slots + WL_SLOTS + ["Q"]:
        files[s] = src / f"snd_{s}.mp3"
        files[s].write_bytes(s.encode() * 10)         # different content per slot
    style = lambda k: {"sound": {"kind": "file", "file": str(files[k]), "volume": 300}}
    fg = {f"sound_{n}": str(files[n]) for n in ns_slots}
    fg.update({"style_q": {"text": [1, 2, 3, 255], **style("Q")},
               "wl_tier_style": {k: style(k) for k in WL_SLOTS},
               "whitelist_gold": True, "whitelist_gold_min": 10, "wl_map_on": True, "wl_map_tier_min": 5,
               f"whitelist_custom_{game}": ["Divine Orb", {"name": "Chaos Orb", "rarities": ["Normal"], "tier": "C"}],
               "whitelist_gem_tier": "A", "wl_v2": v2, "sound_format": 2})
    if game == "poe2":
        fg["whitelist_gem_uncut_poe2"] = {"Uncut Skill Gem": 3}
    else:
        fg["whitelist_gem_names_poe1"] = ["Fireball"]
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
            sorted(p.name for p in game_dir.glob("*.mp3")), base)


@pytest.mark.parametrize("game", ["poe1", "poe2"])
def test_the_six_numbered_sounds_land_on_every_block_of_their_number(tmp_path, game):
    tier, _wl, _folder, base = _run(tmp_path, game, True)
    counts = filter_gen.sound_block_counts(base)
    assert set(counts) <= set("123456")                         # no NeverSink number outside 1-6: nothing left alone
    lines = tier.split("\n")
    got = {n: 0 for n in NS_SLOTS}
    for b in filter_gen._parse_blocks(lines):
        body = lines[b.start + 1:b.end]
        have = _refs("\n".join(body))
        num = filter_gen.sound_id_of(body)
        if b.block_type == "Show" and num in filter_gen.SOUND_SLOT_OF_ID:
            slot = filter_gen.SOUND_SLOT_OF_ID[num]
            assert have == [f"snd_{slot}.mp3"], (num, have)    # the right slot, once
            got[slot] += 1
        elif "snd_Q" not in "".join(have):
            assert not have
    for num, slot in filter_gen.SOUND_SLOT_OF_ID.items():
        assert got[slot] == counts.get(num, 0), (num, slot)    # block count per number matches NeverSink's own
    assert sum(got.values()) == sum(counts.values()) and sum(got.values()) > 100


@pytest.mark.parametrize("game", ["poe1", "poe2"])
@pytest.mark.parametrize("v2", [False, True], ids=["legacy-whitelist", "wl_v2"])
def test_every_sound_reaches_its_own_file_and_nothing_is_shared_but_q(tmp_path, game, v2):
    tier, wl, folder, _base = _run(tmp_path, game, v2)
    rt, rw = set(_refs(tier)), set(_refs(wl))
    name = lambda s: f"snd_{s}.mp3"
    for s in NS_SLOTS + ["Q"]:                              # NeverSink tab: the six numbered sounds + Q
        assert name(s) in rt, s
    assert not rt & {name(s) for s in WL_SLOTS}              # ... and nothing of the Whitelist tab's sounds
    if v2:
        for s in ["S", "A", "B", "C", "Q", "G", "Map", "Gem"] + (["Tablet"] if game == "poe2" else []):
            assert name(s) in rw, s
        assert not rw & {name(s) for s in NS_SLOTS}          # the tabs share no sound but Q
    else:                                                    # the old whitelist reads the NeverSink tab's numbers
        assert name("1") in rw and name("Q") in rw
    assert "-2" not in "".join(folder + sorted(rt | rw))
    assert (rt | rw) <= set(folder)                          # every file that is referenced is in the folder ...
    assert len(folder) == len(set(folder)) and set(folder) <= (rt | rw | {name(s) for s in WL_SLOTS if s not in ("Tablet",) or game == "poe2"})


def test_an_empty_slot_writes_nothing_and_leaves_neversinks_own_sound(tmp_path):
    tier, _wl, folder, base = _run(tmp_path, "poe2", True, ns_slots=["2", "5"])
    assert set(_refs(tier)) == {"snd_2.mp3", "snd_5.mp3", "snd_Q.mp3"}
    counts = filter_gen.sound_block_counts(base)
    assert tier.count('CustomAlertSoundOptional "snd_2.mp3"') == counts["1"]        # slot 2 <- id 1
    assert tier.count('CustomAlertSoundOptional "snd_5.mp3"') == counts["4"]        # slot 5 <- id 4
    assert tier.count("PlayAlertSound") == base.count("PlayAlertSound")               # NeverSink's own sounds all stay
