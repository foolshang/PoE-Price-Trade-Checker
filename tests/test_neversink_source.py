"""Tests for neversink_source.py — mock urllib, same patch style as
test_hub_client.py."""
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from poe_price_trade import neversink_source


def test_fetch_base_filter_totally_unreachable_returns_none(tmp_path):
    with patch("urllib.request.urlopen", side_effect=RuntimeError("network down")):
        text, tag = neversink_source.fetch_base_filter("poe2", 2, tmp_path)
    assert text is None
    assert tag is None


def _mock_urlopen(payload_bytes):
    class _Resp:
        def __enter__(self_inner):
            return self_inner

        def __exit__(self_inner, *a):
            return False

        def read(self_inner):
            return payload_bytes

    return _Resp()


def test_get_latest_tag_parses_tag_name():
    body = json.dumps({"tag_name": "0.10.3", "assets": []}).encode()
    with patch("urllib.request.urlopen", return_value=_mock_urlopen(body)):
        tag = neversink_source.get_latest_tag("poe2")
    assert tag == "0.10.3"


def test_get_latest_tag_unknown_game_returns_none():
    assert neversink_source.get_latest_tag("poe3") is None


def test_get_latest_tag_network_failure_returns_none():
    with patch("urllib.request.urlopen", side_effect=RuntimeError("boom")):
        assert neversink_source.get_latest_tag("poe1") is None


def test_fetch_base_filter_downloads_and_caches(tmp_path):
    filter_bytes = b"Show\n    BaseType == \"Chaos Orb\"\n"
    tag_body = json.dumps({"tag_name": "1.0.0"}).encode()

    call_count = {"n": 0}

    def _fake_urlopen(req, timeout=None):
        call_count["n"] += 1
        url = req.full_url if hasattr(req, "full_url") else req
        if "api.github.com" in url:
            return _mock_urlopen(tag_body)
        return _mock_urlopen(filter_bytes)

    with patch("urllib.request.urlopen", side_effect=_fake_urlopen):
        text, tag = neversink_source.fetch_base_filter("poe2", 2, tmp_path)

    assert tag == "1.0.0"
    assert "Chaos Orb" in text
    cached = tmp_path / "neversink" / "poe2" / "1.0.0_2.filter"
    assert cached.exists()


def test_fetch_base_filter_skips_github_check_within_a_day(tmp_path):
    game_dir = tmp_path / "neversink" / "poe2"
    game_dir.mkdir(parents=True)
    (game_dir / "last_check.json").write_text(json.dumps({
        "tag": "1.0.0",
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }), encoding="utf-8")
    (game_dir / "1.0.0_2.filter").write_text("cached text", encoding="utf-8")

    with patch("urllib.request.urlopen") as mock_urlopen:
        text, tag = neversink_source.fetch_base_filter("poe2", 2, tmp_path)

    mock_urlopen.assert_not_called()
    assert text == "cached text"
    assert tag == "1.0.0"


def test_fetch_base_filter_force_bypasses_daily_cache(tmp_path):
    game_dir = tmp_path / "neversink" / "poe2"
    game_dir.mkdir(parents=True)
    (game_dir / "last_check.json").write_text(json.dumps({
        "tag": "1.0.0",
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }), encoding="utf-8")
    (game_dir / "1.0.0_2.filter").write_text("old text", encoding="utf-8")

    tag_body = json.dumps({"tag_name": "2.0.0"}).encode()
    filter_bytes = b"new text"

    def _fake_urlopen(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else req
        if "api.github.com" in url:
            return _mock_urlopen(tag_body)
        return _mock_urlopen(filter_bytes)

    with patch("urllib.request.urlopen", side_effect=_fake_urlopen):
        text, tag = neversink_source.fetch_base_filter("poe2", 2, tmp_path, force=True)

    assert tag == "2.0.0"
    assert text == "new text"


def test_fetch_base_filter_falls_back_to_disk_cache_on_network_failure(tmp_path):
    game_dir = tmp_path / "neversink" / "poe1"
    game_dir.mkdir(parents=True)
    stale_check = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    (game_dir / "last_check.json").write_text(json.dumps({
        "tag": "8.19.2",
        "checked_at": stale_check,
    }), encoding="utf-8")
    (game_dir / "8.19.2_2.filter").write_text("previously cached", encoding="utf-8")

    with patch("urllib.request.urlopen", side_effect=RuntimeError("network down")):
        text, tag = neversink_source.fetch_base_filter("poe1", 2, tmp_path)

    assert text == "previously cached"
    assert tag == "8.19.2"
