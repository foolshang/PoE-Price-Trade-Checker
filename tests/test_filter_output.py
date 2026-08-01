"""Tests for filter_output.py — write_filter/copy_sounds/state round-trip
using tmp_path."""
import pytest

from poe_price_trade import filter_output


def test_game_filter_dir_uses_override_when_set(tmp_path):
    override = str(tmp_path / "custom")
    d = filter_output.game_filter_dir("poe2", override)
    assert d == tmp_path / "custom"


def test_game_filter_dir_falls_back_to_documents_my_games():
    d = filter_output.game_filter_dir("poe1", "")
    assert d.parts[-2:] == ("My Games", "Path of Exile")
    d2 = filter_output.game_filter_dir("poe2", "")
    assert d2.parts[-2:] == ("My Games", "Path of Exile 2")


def test_write_filter_writes_generated_and_base(tmp_path):
    path = filter_output.write_filter(tmp_path, "GENERATED", "BASE")
    text = path.read_text(encoding="utf-8")
    assert "GENERATED" in text
    assert "BASE" in text
    assert text.index("GENERATED") < text.index("BASE")


def test_write_filter_generated_only_when_base_none(tmp_path):
    path = filter_output.write_filter(tmp_path, "GENERATED", None)
    text = path.read_text(encoding="utf-8")
    assert text.strip() == "GENERATED"


def test_write_filter_raises_when_both_sources_empty(tmp_path):
    with pytest.raises(ValueError):
        filter_output.write_filter(tmp_path, "", None)


def test_write_filter_overwrites_existing(tmp_path):
    filter_output.write_filter(tmp_path, "FIRST", None)
    path = filter_output.write_filter(tmp_path, "SECOND", None)
    assert path.read_text(encoding="utf-8").strip() == "SECOND"


def test_copy_sounds_uses_tier_prefixed_fixed_names(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    sound_file = src / "airhorn.mp3"
    sound_file.write_bytes(b"fake mp3 data")
    out_dir = tmp_path / "out"

    written = filter_output.copy_sounds(out_dir, {"S": str(sound_file), "A": None})

    assert written == {"S": "poe-checker-S.mp3"}
    assert (out_dir / "poe-checker-S.mp3").read_bytes() == b"fake mp3 data"
    assert not (out_dir / "poe-checker-A.mp3").exists()


def test_copy_sounds_missing_source_is_skipped_not_raised(tmp_path):
    out_dir = tmp_path / "out"
    written = filter_output.copy_sounds(out_dir, {"S": str(tmp_path / "missing.mp3")})
    assert written == {}


def test_copy_sounds_empty_map_returns_empty(tmp_path):
    assert filter_output.copy_sounds(tmp_path, {}) == {}


def test_state_round_trip(tmp_path):
    filter_output.save_state(tmp_path, "poe2", last_signature="abc123", base_tag="1.0.0")
    state = filter_output.load_state(tmp_path, "poe2")
    assert state["last_signature"] == "abc123"
    assert state["base_tag"] == "1.0.0"


def test_state_missing_file_returns_empty_dict(tmp_path):
    assert filter_output.load_state(tmp_path, "poe1") == {}


def test_state_save_merges_not_replaces(tmp_path):
    filter_output.save_state(tmp_path, "poe2", last_signature="abc")
    filter_output.save_state(tmp_path, "poe2", base_tag="1.0.0")
    state = filter_output.load_state(tmp_path, "poe2")
    assert state["last_signature"] == "abc"
    assert state["base_tag"] == "1.0.0"


def test_state_isolated_per_game(tmp_path):
    filter_output.save_state(tmp_path, "poe1", last_signature="one")
    filter_output.save_state(tmp_path, "poe2", last_signature="two")
    assert filter_output.load_state(tmp_path, "poe1")["last_signature"] == "one"
    assert filter_output.load_state(tmp_path, "poe2")["last_signature"] == "two"


def test_state_round_trip_last_mapping(tmp_path):
    mapping = {"c:Divine Orb": "S", "u:Headhunter": "S"}
    filter_output.save_state(tmp_path, "poe2", last_signature="abc123", last_mapping=mapping)
    state = filter_output.load_state(tmp_path, "poe2")
    assert state["last_mapping"] == mapping
