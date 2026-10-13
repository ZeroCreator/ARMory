import json

import pytest

from app.routers import backup


def test_sync_state_records_each_application_timestamp(tmp_path, monkeypatch):
    state_path = tmp_path / "sync_state.json"
    monkeypatch.setattr(backup, "SYNC_STATE_PATH", state_path)

    armory_timestamp = backup._record_sync("armory_last_sync_at")
    alexandrite_timestamp = backup._record_sync("alexandrite_last_sync_at")

    assert json.loads(state_path.read_text(encoding="utf-8")) == {
        "armory_last_sync_at": armory_timestamp,
        "alexandrite_last_sync_at": alexandrite_timestamp,
    }
    assert backup._sync_state_payload() == {
        "last_sync_at": armory_timestamp,
        "last_sync": backup._format_dt(armory_timestamp),
        "alexandrite_last_sync_at": alexandrite_timestamp,
        "alexandrite_last_sync": backup._format_dt(alexandrite_timestamp),
    }


def test_sync_state_rejects_unknown_timestamp_key(tmp_path, monkeypatch):
    monkeypatch.setattr(backup, "SYNC_STATE_PATH", tmp_path / "sync_state.json")

    with pytest.raises(ValueError):
        backup._record_sync("unknown_last_sync_at")
