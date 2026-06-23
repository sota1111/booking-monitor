"""Tests for the sample-data seeder (SOT-1152)."""

import json
import os
from datetime import datetime, timezone

import pytest

from booking_monitor import sample_data
from booking_monitor.config import load_config
from booking_monitor.history import History
from booking_monitor.services.config_loader import resolve_config_path, sample_mode_enabled
from booking_monitor.slots import build_slot_grid

FIXED_NOW = datetime(2026, 6, 23, 12, 0, 0, tzinfo=timezone.utc)


def test_build_sample_targets_variety():
    targets = sample_data.build_sample_targets(FIXED_NOW)
    assert len(targets) >= 4
    # At least two range-based targets.
    range_based = [
        t for t in targets if (t.get("conditions") or {}).get("date_range")
    ]
    assert len(range_based) >= 2
    # At least one notify-off and a mix of site types.
    assert any(t["notify"] is False for t in targets)
    assert {t["site_type"] for t in targets} >= {"tablecheck", "generic"}


def test_sample_config_loads_via_config_loader(tmp_path):
    path = tmp_path / "config.sample.json"
    sample_data.write_sample_config(str(path), FIXED_NOW)
    assert path.exists()
    # The written config must load cleanly through the real loader.
    config = load_config(str(path))
    assert len(config.targets) >= 4


def test_build_sample_slots_produces_grid():
    targets = sample_data.build_sample_targets(FIXED_NOW)
    range_target = next(t for t in targets if (t["conditions"]).get("date_range"))
    slots = sample_data.build_sample_slots(range_target)
    assert slots, "range target should expand into slots"
    grid = build_slot_grid(slots)
    assert grid is not None
    states = {
        cell for row in grid["cells"].values() for cell in row.values()
    }
    # Grid should exhibit a mix of states for a meaningful dashboard.
    assert "available" in states
    assert "unavailable" in states
    # Non-range target yields no slots.
    legacy = next(t for t in targets if not (t["conditions"]).get("date_range"))
    assert sample_data.build_sample_slots(legacy) == []


def test_seed_history_writes_all_three_files(tmp_path):
    summary = sample_data.seed_history(history_dir=str(tmp_path), now=FIXED_NOW)
    assert summary["latest"] >= 4
    assert summary["checks"] >= 30
    assert summary["notifications"] >= 1

    for name in ("history.jsonl", "check_history.jsonl", "notification_history.jsonl"):
        p = tmp_path / name
        assert p.exists()
        lines = [json.loads(line) for line in p.read_text().splitlines() if line.strip()]
        assert lines
        assert all(entry.get("sample") is True for entry in lines)


def test_seed_history_is_idempotent_and_preserves_real_records(tmp_path):
    history_dir = str(tmp_path)
    history_path = tmp_path / "history.jsonl"

    # A pre-existing real (non-sample) record must survive re-seeding.
    real = {"target_name": "REAL", "url": "http://x", "available": True, "notified": False}
    history_path.write_text(json.dumps(real) + "\n")

    sample_data.seed_history(history_dir=history_dir, now=FIXED_NOW)
    sample_data.seed_history(history_dir=history_dir, now=FIXED_NOW)  # second pass

    lines = [json.loads(line) for line in history_path.read_text().splitlines() if line.strip()]
    real_lines = [line for line in lines if not line.get("sample")]
    sample_lines = [line for line in lines if line.get("sample")]
    assert len(real_lines) == 1
    assert real_lines[0]["target_name"] == "REAL"
    # Idempotent: sample records not duplicated across two passes.
    targets = sample_data.build_sample_targets(FIXED_NOW)
    assert len(sample_lines) == len(targets)


def test_seeded_history_is_consumable_by_history_reader(tmp_path):
    sample_data.seed_history(history_dir=str(tmp_path), now=FIXED_NOW)
    hist = History(path=str(tmp_path / "history.jsonl"))
    states = hist.get_all_latest_states()
    assert states
    # Dashboard expects at least one available and one error state.
    assert any(s.get("available") is True for s in states)
    assert any(s.get("error") for s in states)


def test_seed_all_writes_config_when_missing(tmp_path):
    config_path = tmp_path / "config.sample.json"
    summary = sample_data.seed_all(
        config_path=str(config_path), history_dir=str(tmp_path), now=FIXED_NOW
    )
    assert config_path.exists()
    assert summary["config_targets"] >= 4


def test_seed_all_does_not_overwrite_existing_config_without_force(tmp_path):
    config_path = tmp_path / "config.sample.json"
    config_path.write_text('{"sentinel": true}')
    sample_data.seed_all(
        config_path=str(config_path), history_dir=str(tmp_path), now=FIXED_NOW
    )
    assert json.loads(config_path.read_text()) == {"sentinel": True}
    # With force, it is regenerated.
    sample_data.seed_all(
        config_path=str(config_path), history_dir=str(tmp_path), now=FIXED_NOW, force=True
    )
    assert "targets" in json.loads(config_path.read_text())


@pytest.mark.parametrize("value,expected", [
    ("1", True), ("true", True), ("YES", True), ("on", True),
    ("0", False), ("", False), ("off", False),
])
def test_sample_mode_enabled_flag(monkeypatch, value, expected):
    monkeypatch.setenv("SEED_SAMPLE_DATA", value)
    assert sample_mode_enabled() is expected


def test_resolve_config_path_prefers_sample_when_enabled(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SEED_SAMPLE_DATA", "1")
    path = resolve_config_path()
    assert path == "config.sample.json"
    assert os.path.exists(path)


def test_resolve_config_path_unchanged_when_disabled(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SEED_SAMPLE_DATA", raising=False)
    (tmp_path / "config.json").write_text("{}")
    assert resolve_config_path() == "config.json"
