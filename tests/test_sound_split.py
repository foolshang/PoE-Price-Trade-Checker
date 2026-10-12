"""Sounds are split per tab (v0.13.0): the NeverSink tab has six numbered sounds (sound 1 <- NeverSink's PlayAlertSound 6,
2 <- 1, 3 <- 2, 4 <- 3, 5 <- 4, 6 <- 5), the Whitelist tab has its own sound per tier / Gold / Map / Tablet / Gem, Q is the
only shared one. A config from before (sound_s / sound_a / sound_b, v0.12.0's sound_c) is converted once."""
from __future__ import annotations
import json

import pytest

from poe_price_trade import filter_core, filter_gen, filter_style
from poe_price_trade.wl_model import WlModel
from tests.test_wl_phase3b import cfg, data, make_window, root       # noqa: F401  (fixtures)

OLD = {"sound_s": "C:/snd/top.mp3", "sound_a": "C:/snd/second.wav", "sound_b": "", "sound_c": "C:/snd/faint.ogg"}


def test_an_old_config_gives_its_files_to_sounds_1_to_3_and_to_the_tier_sounds_once():
    out, notes = filter_core.migrate_sounds(dict(OLD))
    assert (out["sound_1"], out["sound_2"], out.get("sound_3", "")) == ("C:/snd/top.mp3", "C:/snd/second.wav", "")
    assert not any(out.get(f"sound_{n}") for n in "456")
    assert not any(k in out for k in ("sound_s", "sound_a", "sound_b", "sound_c")) and out["sound_format"] == 2
    st = out["wl_tier_style"]
    assert st["S"]["sound"]["file"] == "C:/snd/top.mp3" and st["A"]["sound"]["file"] == "C:/snd/second.wav"
    assert st["C"]["sound"]["file"] == "C:/snd/faint.ogg" and "B" not in st
    assert len(notes) == 1 and "เสียง 1 / 2 / 3" in notes[0] and "top.mp3" in notes[0]
    again, notes2 = filter_core.migrate_sounds(out)               # a converted config: nothing again
    assert again == out and notes2 == []


def test_a_tier_that_already_has_its_own_sound_keeps_it_and_nothing_to_convert_says_nothing():
    fg = {"sound_s": "C:/snd/top.mp3", "wl_tier_style": {"S": {"sound": {"kind": "file", "file": "own.mp3", "volume": 100}}}}
    out, _n = filter_core.migrate_sounds(fg)
    assert out["wl_tier_style"]["S"]["sound"]["file"] == "own.mp3" and out["sound_1"] == "C:/snd/top.mp3"
    out, notes = filter_core.migrate_sounds({})
    assert notes == [] and out["sound_format"] == 2 and "wl_tier_style" not in out


def test_the_model_reads_the_old_files_as_tier_sounds_and_saves_without_the_old_keys():
    m = WlModel.from_config(dict(OLD), "poe2")
    m.set_data(*data("poe2"))
    assert m.tier_style["S"]["sound"] == {"kind": "file", "id": 1, "file": "C:/snd/top.mp3", "volume": 300}
    assert any("เสียงเดิม" in n for n in m.take_notes())
    fg = m.to_config(dict(OLD))
    assert not any(k in fg for k in ("sound_s", "sound_a", "sound_b", "sound_c")) and fg["sound_format"] == 2
    assert fg["wl_tier_style"]["S"]["sound"]["file"] == "C:/snd/top.mp3"
    back = WlModel.from_config(json.loads(json.dumps(fg)), "poe2")          # opened again: no second conversion, no note
    assert back.take_notes() == [] and back.tier_style["S"] == m.tier_style["S"]


def test_the_window_shows_the_old_files_as_sounds_1_to_3_saves_them_and_converts_only_once(root, cfg):
    fg = dict(cfg.get("filter_gen", {}) or {})
    fg.update(OLD)
    cfg.set("filter_gen", fg)
    win = make_window(root, cfg, "poe2")
    assert [win._vars[f"sound_{n}"].get() for n in "123456"] == ["C:/snd/top.mp3", "C:/snd/second.wav", "", "", "", ""]
    assert "sound_s" not in win._vars and win._model.tier_style["A"]["sound"]["file"] == "C:/snd/second.wav"
    saved = win._save("whitelist")
    assert saved["sound_1"] == "C:/snd/top.mp3" and saved["sound_format"] == 2 and not any(k in saved for k in OLD)
    win2 = make_window(root, cfg, "poe2")
    assert win2._vars["sound_1"].get() == "C:/snd/top.mp3" and win2._model.take_notes() == []


def test_the_neversink_tab_has_six_labelled_rows_and_nothing_else_about_sounds(root, cfg):
    win = make_window(root, cfg, "poe1")
    import tkinter as tk

    def texts(w):
        out = []
        for c in w.winfo_children():
            if isinstance(c, tk.Label):
                out.append(c.cget("text"))
            out += texts(c)
        return out
    t = texts(win._win)
    assert {f"เสียง {n}" for n in "123456"} <= set(t)
    assert not any(x.startswith("Tier ") and x.endswith("sound:") for x in t)
    assert [n for n in "123456" if f"sound_{n}" in win._vars] == list("123456")


def test_web_init_reports_the_old_files_to_move_and_the_converted_keys():
    from web import glue
    out = json.loads(glue.wl_init("poe2", json.dumps({"sound_s": "My Ping.MP3", "sound_b": "x.wav"})))
    assert out["moved"] == {"S": "1", "B": "3"}
    up = out["updates"]
    assert up["sound_1"] == "My Ping.MP3" and up["sound_3"] == "x.wav" and up["sound_format"] == 2
    assert up["sound_s"] == "" and up["wl_tier_style"]["S"]["sound"]["file"] == "My Ping.MP3"
    again = json.loads(glue.wl_init("poe2", json.dumps(dict(up))))
    assert again["moved"] == {} and "sound_1" not in again["updates"]


def test_glue_labels_for_the_numbered_sounds_are_the_slot_numbers():
    assert filter_gen.SOUND_SLOTS == ("1", "2", "3", "4", "5", "6")
    assert set(filter_core.tier_sound_requests({"sound_4": "d.mp3"})) == set("123456") | {"Q"}
    assert filter_core.tier_sound_requests({"sound_4": "d.mp3"})["4"] == "d.mp3"
    assert filter_style.uses_sound_file({"sound": {"kind": "file", "file": "q.mp3"}}) == "q.mp3"
