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


def _src(tmp_path, name, data):
    d = tmp_path / "src"
    d.mkdir(exist_ok=True)
    p = d / name
    p.write_bytes(data)
    return str(p)


def test_copy_sounds_keeps_the_original_file_name(tmp_path):
    out_dir = tmp_path / "out"
    msgs = []
    written = filter_output.copy_sounds(out_dir, {"S": _src(tmp_path, "airhorn.mp3", b"fake mp3 data"), "A": None},
                                        notify=msgs.append)
    assert written == {"S": "airhorn.mp3"} and msgs == []
    assert (out_dir / "airhorn.mp3").read_bytes() == b"fake mp3 data"
    assert not list(out_dir.glob("poe-checker-*"))


def test_copy_sounds_same_content_is_reused_not_copied_again(tmp_path):
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "ping.mp3").write_bytes(b"same")
    before = (out_dir / "ping.mp3").stat().st_mtime_ns
    msgs = []
    written = filter_output.copy_sounds(out_dir, {"S": _src(tmp_path, "ping.mp3", b"same")}, notify=msgs.append)
    assert written == {"S": "ping.mp3"} and (out_dir / "ping.mp3").stat().st_mtime_ns == before
    assert any("ใช้ไฟล์เดิม" in m for m in msgs)


def test_copy_sounds_different_content_asks_and_obeys(tmp_path):
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "ping.mp3").write_bytes(b"old")
    src = _src(tmp_path, "ping.mp3", b"new")
    asked = []
    keep = filter_output.copy_sounds(out_dir, {"S": src}, decide=lambda n, alt: asked.append((n, alt)) or "keep")
    assert asked == [("ping.mp3", "ping-2.mp3")] and keep == {"S": "ping-2.mp3"}
    assert (out_dir / "ping.mp3").read_bytes() == b"old" and (out_dir / "ping-2.mp3").read_bytes() == b"new"
    over = filter_output.copy_sounds(out_dir, {"S": src}, decide=lambda n, alt: "overwrite")
    assert over == {"S": "ping.mp3"} and (out_dir / "ping.mp3").read_bytes() == b"new"
    # no decide callback = keep the old file; the free name skips ones already taken
    again = filter_output.copy_sounds(out_dir, {"S": _src(tmp_path, "ping.mp3", b"third")})
    assert again == {"S": "ping-3.mp3"}


def test_copy_sounds_one_file_for_several_slots_is_copied_once_and_bad_names_are_fixed(tmp_path):
    out_dir = tmp_path / "out"
    a = _src(tmp_path, "a#b;c.mp3", b"x")
    msgs = []
    written = filter_output.copy_sounds(out_dir, {"S": a, "A": a, "Q": a}, notify=msgs.append)
    assert written == {"S": "a_b_c.mp3", "A": "a_b_c.mp3", "Q": "a_b_c.mp3"}
    assert [p.name for p in out_dir.iterdir()] == ["a_b_c.mp3"]
    assert len(msgs) == 1 and "#" in msgs[0] and ";" in msgs[0]


def test_copy_sounds_two_different_files_with_one_name_are_told_apart_without_asking(tmp_path):
    out_dir = tmp_path / "out"
    d1 = tmp_path / "d1"
    d2 = tmp_path / "d2"
    d1.mkdir()
    d2.mkdir()
    (d1 / "x.mp3").write_bytes(b"1")
    (d2 / "x.mp3").write_bytes(b"2")
    asked = []
    written = filter_output.copy_sounds(out_dir, {"S": str(d1 / "x.mp3"), "A": str(d2 / "x.mp3")},
                                        decide=lambda *a: asked.append(a) or "overwrite")
    assert asked == [] and written == {"S": "x.mp3", "A": "x-2.mp3"}
    assert (out_dir / "x.mp3").read_bytes() == b"1" and (out_dir / "x-2.mp3").read_bytes() == b"2"


def test_write_filter_uses_the_given_name_and_rejects_bad_ones(tmp_path):
    p = filter_output.write_filter(tmp_path, "G", "B", name="my filter")
    assert p.name == "my filter.filter" and p.read_text(encoding="utf-8").endswith("B")
    assert filter_output.write_filter(tmp_path, "G", None).name == "poe-checker.filter"
    for bad in ("a/b", "CON", "x.", "", "q?"):
        with pytest.raises(ValueError):
            filter_output.write_filter(tmp_path, "G", "B", name=bad)


def test_copy_sounds_missing_source_is_skipped_not_raised(tmp_path):
    out_dir = tmp_path / "out"
    written = filter_output.copy_sounds(out_dir, {"S": str(tmp_path / "missing.mp3")})
    assert written == {}


def test_copy_sounds_empty_map_returns_empty(tmp_path):
    assert filter_output.copy_sounds(tmp_path, {}) == {}
