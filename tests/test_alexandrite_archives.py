import os
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.responses import FileResponse

from app.routers import backup


class FakeYandexDisk:
    def __init__(self, files=None):
        self.files = files or []
        self.uploaded = []

    def list_files(self, remote_path):
        return self.files

    def ensure_folders(self, remote_path):
        return True

    def upload_file(self, local_path, remote_path, overwrite=True):
        self.uploaded.append((Path(local_path).read_bytes(), remote_path, overwrite))
        return True


@pytest.mark.asyncio
async def test_alexandrite_archive_can_be_created_locally(tmp_path, monkeypatch):
    source = tmp_path / "alexandrite"
    source.mkdir()
    (source / "note.md").write_text("note", encoding="utf-8")
    local_backups = tmp_path / "backups"
    monkeypatch.setattr(backup.settings, "alexandrite_vault_path", str(source))
    monkeypatch.setattr(backup, "LOCAL_BACKUPS", local_backups)
    monkeypatch.setattr(backup, "_get_yandex", lambda: None)

    result = await backup.create_alexandrite_archive({"backup_target": "local"})

    assert result["target"] == "local"
    assert result["local_saved"] is True
    assert result["yandex_saved"] is False
    assert (local_backups / result["archive"]).is_file()


@pytest.mark.asyncio
async def test_alexandrite_archive_can_be_created_in_both_storages(tmp_path, monkeypatch):
    source = tmp_path / "alexandrite"
    source.mkdir()
    (source / "note.md").write_text("note", encoding="utf-8")
    local_backups = tmp_path / "backups"
    yandex = FakeYandexDisk()
    monkeypatch.setattr(backup.settings, "alexandrite_vault_path", str(source))
    monkeypatch.setattr(backup, "LOCAL_BACKUPS", local_backups)
    monkeypatch.setattr(backup, "_get_yandex", lambda: yandex)

    result = await backup.create_alexandrite_archive({"backup_target": "both"})

    assert result["target"] == "both"
    assert result["local_saved"] is True
    assert result["yandex_saved"] is True
    assert (local_backups / result["archive"]).is_file()
    assert yandex.uploaded[0][1] == f"{backup.REMOTE_ALEXANDRITE_BACKUPS}/{result['archive']}"


@pytest.mark.asyncio
async def test_alexandrite_archives_are_sorted_from_early_to_late(tmp_path, monkeypatch):
    local_backups = tmp_path / "backups"
    local_backups.mkdir()
    old_local = local_backups / "alexandrite_backup_20260101_000000.tar.gz"
    new_local = local_backups / "alexandrite_backup_20260103_000000.tar.gz"
    old_local.write_bytes(b"old")
    new_local.write_bytes(b"new")
    old_timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp()
    new_timestamp = datetime(2026, 1, 3, tzinfo=timezone.utc).timestamp()
    os.utime(old_local, (old_timestamp, old_timestamp))
    os.utime(new_local, (new_timestamp, new_timestamp))
    yandex = FakeYandexDisk([
        {
            "type": "file",
            "name": "alexandrite_backup_20260102_000000.tar.gz",
            "size": 4,
            "modified": "2026-01-02T00:00:00Z",
        }
    ])
    monkeypatch.setattr(backup, "LOCAL_BACKUPS", local_backups)
    monkeypatch.setattr(backup, "_get_yandex", lambda: yandex)

    result = await backup.list_alexandrite_archives()

    assert [item["name"] for item in result["archives"]] == [
        old_local.name,
        "alexandrite_backup_20260102_000000.tar.gz",
        new_local.name,
    ]
    assert all(item["source"] in {"local", "yandex"} for item in result["archives"])


@pytest.mark.asyncio
async def test_local_alexandrite_archive_download_returns_file_response(tmp_path, monkeypatch):
    local_backups = tmp_path / "backups"
    local_backups.mkdir()
    archive_name = "alexandrite_backup_20260104_000000.tar.gz"
    (local_backups / archive_name).write_bytes(b"archive")
    monkeypatch.setattr(backup, "LOCAL_BACKUPS", local_backups)

    response = await backup.download_alexandrite_archive(archive_name, "local")

    assert isinstance(response, FileResponse)
    assert response.path == local_backups / archive_name
