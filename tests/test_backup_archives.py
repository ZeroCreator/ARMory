import io
import tarfile
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.responses import FileResponse

from app.routers import backup


class FakeYandexDisk:
    def __init__(self):
        self.uploaded = []

    def ensure_folders(self, remote_path):
        return True

    def upload_file_with_progress(self, local_path, remote_path, overwrite=True, progress_callback=None):
        self.uploaded.append((Path(local_path).read_bytes(), remote_path, overwrite))
        if progress_callback:
            progress_callback(len(self.uploaded[-1][0]), len(self.uploaded[-1][0]))
        return True


def _prepare_sources(tmp_path):
    db_path = tmp_path / "armory.db"
    db_path.write_bytes(b"database")
    uploads_path = tmp_path / "uploads"
    (uploads_path / "nested").mkdir(parents=True)
    (uploads_path / "nested" / "document.txt").write_bytes(b"document")
    return db_path, uploads_path


@pytest.mark.asyncio
async def test_local_archive_job_keeps_archive_and_records_local_target(tmp_path, monkeypatch):
    db_path, uploads_path = _prepare_sources(tmp_path)
    local_backups = tmp_path / "backups"
    monkeypatch.setattr(backup, "LOCAL_BACKUPS", local_backups)
    job_id = "local-job"
    archive_name = "armory_backup_20261013_120000.tar.gz"
    archive_path = local_backups / archive_name
    backup._backup_jobs[job_id] = {"status": "starting"}

    await backup._run_create_archive_async(
        None,
        db_path,
        uploads_path,
        archive_path,
        archive_name,
        job_id,
        "local",
        None,
    )

    assert archive_path.is_file()
    assert backup._backup_jobs[job_id]["status"] == "completed"
    assert backup._backup_jobs[job_id]["local_saved"] is True
    assert backup._backup_jobs[job_id]["yandex_saved"] is False
    with tarfile.open(archive_path, "r:gz") as archive:
        assert archive.getnames() == ["armory.db", "uploads/nested/document.txt"]
    backup._backup_jobs.pop(job_id, None)


@pytest.mark.asyncio
async def test_both_archive_job_uploads_and_keeps_local_copy(tmp_path, monkeypatch):
    db_path, uploads_path = _prepare_sources(tmp_path)
    local_backups = tmp_path / "backups"
    monkeypatch.setattr(backup, "LOCAL_BACKUPS", local_backups)
    fake_yandex = FakeYandexDisk()
    job_id = "both-job"
    archive_name = "armory_backup_20261013_120001.tar.gz"
    archive_path = local_backups / archive_name
    backup._backup_jobs[job_id] = {"status": "starting"}

    await backup._run_create_archive_async(
        fake_yandex,
        db_path,
        uploads_path,
        archive_path,
        archive_name,
        job_id,
        "both",
        None,
    )

    assert archive_path.is_file()
    assert fake_yandex.uploaded[0][1] == f"{backup.REMOTE_BACKUPS}/{archive_name}"
    assert backup._backup_jobs[job_id]["local_saved"] is True
    assert backup._backup_jobs[job_id]["yandex_saved"] is True
    backup._backup_jobs.pop(job_id, None)


@pytest.mark.asyncio
async def test_archives_are_listed_locally_without_yandex(tmp_path, monkeypatch):
    local_backups = tmp_path / "backups"
    local_backups.mkdir()
    archive_path = local_backups / "armory_backup_20261013_120002.tar.gz"
    archive_path.write_bytes(b"archive")
    monkeypatch.setattr(backup, "LOCAL_BACKUPS", local_backups)
    monkeypatch.setattr(backup, "_get_yandex", lambda: None)

    result = await backup.list_archives()

    assert len(result["archives"]) == 1
    listed = result["archives"][0]
    assert listed["name"] == archive_path.name
    assert listed["size"] == len(b"archive")
    assert listed["source"] == "local"
    assert listed["modified"]
    assert listed["modified_at"]


@pytest.mark.asyncio
async def test_local_archive_download_returns_file_response(tmp_path, monkeypatch):
    local_backups = tmp_path / "backups"
    local_backups.mkdir()
    archive_name = "armory_backup_20261013_120003.tar.gz"
    (local_backups / archive_name).write_bytes(b"archive")
    monkeypatch.setattr(backup, "LOCAL_BACKUPS", local_backups)

    response = await backup.download_archive(archive_name, "local")

    assert isinstance(response, FileResponse)
    assert response.path == local_backups / archive_name


def test_archive_name_validation_rejects_path_traversal():
    with pytest.raises(HTTPException) as error:
        backup._validate_archive_name("../armory_backup_20261013_120004.tar.gz")

    assert error.value.status_code == 400


def test_archive_extraction_rejects_path_traversal(tmp_path):
    archive_path = tmp_path / "malicious.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        payload = b"outside"
        member = tarfile.TarInfo("uploads/../../outside.txt")
        member.size = len(payload)
        archive.addfile(member, io.BytesIO(payload))

    with pytest.raises(RuntimeError):
        backup._extract_tarball(
            archive_path,
            tmp_path / "armory.db",
            tmp_path / "uploads",
        )

    assert not (tmp_path / "outside.txt").exists()
