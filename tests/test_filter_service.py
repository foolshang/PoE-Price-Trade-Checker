"""filter_service.generate_filter — checker-independent core (no Tk, no app state)."""
from __future__ import annotations
import types
from unittest import mock

from poe_price_trade import filter_service


def _cfg(tmp_path, fg):
    return types.SimpleNamespace(
        get=lambda k, d=None: dict(fg, game_dir_poe2=str(tmp_path / "game")) if k == "filter_gen" else d,
        app_dir=lambda: tmp_path / "app")


def test_whitelist_writes_file_returns_result_and_logs(tmp_path):
    logs = []
    cfg = _cfg(tmp_path, {"whitelist_enabled": True, "whitelist_selected_poe2": ["Divine Orb"],
                          "whitelist_gold": True})
    with mock.patch.object(filter_service.hub_client, "get_prices",
                           side_effect=AssertionError("hub must not be used")):
        res = filter_service.generate_filter(cfg, "poe2", "poe2/prices/latest.json",
                                             log=lambda m, t="info": logs.append((t, m)))
    assert res["mode"] == "whitelist" and res["count"] == 2
    text = (tmp_path / "game" / "poe-checker.filter").read_text(encoding="utf-8")
    assert '"Divine Orb"' in text and '"Gold"' in text and text.rstrip().endswith("Hide")
    assert res["path"] == tmp_path / "game" / "poe-checker.filter"
    assert [t for t, _ in logs] == ["ok", "ok"] and "Filter updated" in logs[-1][1]


def test_whitelist_nothing_selected_returns_none_and_writes_nothing(tmp_path):
    logs = []
    cfg = _cfg(tmp_path, {"whitelist_enabled": True})
    res = filter_service.generate_filter(cfg, "poe2", "p", log=lambda m, t="info": logs.append((t, m)))
    assert res is None
    assert not (tmp_path / "game").exists()
    assert len(logs) == 1 and logs[0][0] == "warn"


def test_whitelist_category_needs_hub_and_degrades_when_it_is_down(tmp_path):
    logs = []
    cfg = _cfg(tmp_path, {"whitelist_enabled": True, "whitelist_selected_poe2": ["Divine Orb"],
                          "whitelist_cats_poe2": ["Rune"]})
    with mock.patch.object(filter_service.hub_client, "get_prices", side_effect=RuntimeError("down")):
        res = filter_service.generate_filter(cfg, "poe2", "p", log=lambda m, t="info": logs.append((t, m)))
    assert res["mode"] == "whitelist" and res["count"] == 1      # static part still generated
    assert logs[0][0] == "warn"


def test_default_log_is_a_noop(tmp_path):
    cfg = _cfg(tmp_path, {"whitelist_enabled": True, "whitelist_gold": True})
    assert filter_service.generate_filter(cfg, "poe2", "p")["mode"] == "whitelist"


def test_tier_mode_returns_state_for_the_caller_and_does_not_save_it(tmp_path):
    cfg = _cfg(tmp_path, {})
    hub = {"currency": [], "items": [], "generated_at": "2000-01-01T00:00:00Z"}
    with mock.patch.object(filter_service.neversink_source, "fetch_base_filter",
                           return_value=("Show\n\tBaseType \"X\"\n", "tag1")), \
         mock.patch.object(filter_service.hub_client, "get_prices", return_value=hub):
        res = filter_service.generate_filter(cfg, "poe2", "p")
    assert res["mode"] == "tier" and res["base_tag"] == "tag1" and res["path"].exists()
    assert not list((tmp_path / "app").glob("filter_state_*.json"))   # caller persists state


def _raise(errno_, winerror=None):
    err = OSError(errno_, "boom")
    if winerror is not None:
        err.winerror = winerror
    return err


def test_write_fail_msg_names_controlled_folder_access_for_blocked_errors(tmp_path):
    for e in (_raise(9), _raise(13), _raise(2), _raise(22, winerror=5)):
        msg = filter_service._write_fail_msg(e, tmp_path)
        assert "Controlled Folder Access" in msg and str(tmp_path) in msg and "boom" in msg
        assert "Game folder override" in msg


def test_write_fail_msg_does_not_blame_cfa_for_unrelated_errors(tmp_path):
    msg = filter_service._write_fail_msg(_raise(28), tmp_path)          # ENOSPC
    assert "Controlled Folder Access" not in msg and "boom" in msg


def test_whitelist_write_blocked_logs_friendly_message_and_returns_none(tmp_path):
    logs = []
    cfg = _cfg(tmp_path, {"whitelist_enabled": True, "whitelist_gold": True})
    with mock.patch.object(filter_service.filter_output, "write_filter", side_effect=_raise(9)):
        res = filter_service.generate_filter(cfg, "poe2", "p", log=lambda m, t="info": logs.append((t, m)))
    assert res is None
    assert logs[-1][0] == "err" and "Controlled Folder Access" in logs[-1][1]


def test_tier_write_blocked_logs_friendly_message_and_returns_none(tmp_path):
    logs = []
    cfg = _cfg(tmp_path, {})
    hub = {"currency": [], "items": [], "generated_at": "2000-01-01T00:00:00Z"}
    with mock.patch.object(filter_service.neversink_source, "fetch_base_filter", return_value=("Show\n", "t")), \
         mock.patch.object(filter_service.hub_client, "get_prices", return_value=hub), \
         mock.patch.object(filter_service.filter_output, "write_filter", side_effect=_raise(9)):
        res = filter_service.generate_filter(cfg, "poe2", "p", log=lambda m, t="info": logs.append((t, m)))
    assert res is None
    assert logs[-1][0] == "err" and "Controlled Folder Access" in logs[-1][1]
