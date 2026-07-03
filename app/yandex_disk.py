import json
import os
from pathlib import Path
from typing import BinaryIO, List, Optional

import requests


class YandexDiskStorage:
    """Клиент для работы с Яндекс.Диском через REST API."""

    def __init__(self, oauth_token: str, backup_path: str = "ARMory/backups"):
        self.oauth_token = oauth_token
        self.backup_path = backup_path.lstrip("/")
        self.base_url = "https://cloud-api.yandex.net/v1/disk"
        self.headers = {
            "Authorization": f"OAuth {oauth_token}",
            "Accept": "application/json",
        }
        self.is_reloader = os.environ.get("WERKZEUG_RUN_MAIN") == "true"

    def _log(self, msg: str):
        if not self.is_reloader:
            print(msg)

    def test_connection(self) -> dict:
        """Проверяет подключение. Возвращает {"ok": bool, "info": str, "used": str, "total": str}."""
        try:
            resp = requests.get(
                f"{self.base_url}/",
                headers=self.headers,
                timeout=10,
            )
            if resp.status_code == 200:
                info = resp.json()
                user = info.get("user", {}).get("display_name", "Unknown")
                used = info.get("used_space", 0)
                total = info.get("total_space", 0)
                return {
                    "ok": True,
                    "info": user,
                    "used": f"{used / (1024 ** 3):.2f} GB",
                    "total": f"{total / (1024 ** 3):.2f} GB",
                }
            elif resp.status_code == 401:
                return {"ok": False, "info": "Недействительный токен"}
            else:
                return {"ok": False, "info": f"HTTP {resp.status_code}"}
        except requests.exceptions.RequestException as e:
            return {"ok": False, "info": str(e)}

    def file_exists(self, remote_path: str) -> bool:
        """Проверяет существование файла/папки на диске."""
        try:
            resp = requests.get(
                f"{self.base_url}/resources",
                headers=self.headers,
                params={"path": f"/{remote_path}"},
                timeout=10,
            )
            return resp.status_code == 200
        except requests.exceptions.RequestException:
            return False

    def create_folder(self, remote_path: str) -> bool:
        """Создаёт папку (включая промежуточные)."""
        try:
            resp = requests.put(
                f"{self.base_url}/resources",
                headers=self.headers,
                params={"path": f"/{remote_path}"},
                timeout=10,
            )
            return resp.status_code in (201, 409)
        except requests.exceptions.RequestException:
            return False

    def ensure_folders(self, remote_path: str) -> bool:
        """Создаёт всю цепочку папок для указанного пути."""
        parts = remote_path.strip("/").split("/")
        current = ""
        for part in parts[:-1]:
            current = f"{current}/{part}" if current else part
            if not self.create_folder(current):
                return False
        return True

    def upload_file_with_progress(
        self,
        local_path: str | Path,
        remote_path: str,
        overwrite: bool = True,
        progress_callback=None,
    ) -> bool:
        """Загружает файл с вызовом progress_callback(bytes_uploaded, total_bytes)."""
        local_path = Path(local_path)
        if not local_path.exists():
            self._log(f"❌ Локальный файл не найден: {local_path}")
            return False

        if not self.ensure_folders(remote_path):
            self._log(f"❌ Не удалось создать папки для {remote_path}")
            return False

        total_size = local_path.stat().st_size

        try:
            resp = requests.get(
                f"{self.base_url}/resources/upload",
                headers=self.headers,
                params={"path": f"/{remote_path}", "overwrite": str(overwrite).lower()},
                timeout=10,
            )
            if resp.status_code != 200:
                self._log(f"❌ Ошибка получения upload_url: {resp.status_code} - {resp.text}")
                return False

            upload_url = resp.json().get("href")
            if not upload_url:
                return False

            uploaded = 0
            with open(local_path, "rb") as f:
                if progress_callback:

                    def _generator():
                        nonlocal uploaded
                        while True:
                            chunk = f.read(8192)
                            if not chunk:
                                break
                            uploaded += len(chunk)
                            progress_callback(uploaded, total_size)
                            yield chunk

                    upload_resp = requests.put(upload_url, data=_generator(), timeout=120)
                else:
                    upload_resp = requests.put(upload_url, data=f, timeout=120)

            if upload_resp.status_code in (200, 201, 202):
                return True
            else:
                self._log(f"❌ Ошибка загрузки: {upload_resp.status_code}")
                return False
        except requests.exceptions.RequestException as e:
            self._log(f"❌ Ошибка сети при загрузке: {e}")
            return False

    def upload_file(self, local_path: str | Path, remote_path: str, overwrite: bool = True) -> bool:
        """Загружает локальный файл на Яндекс.Диск (без колбека прогресса)."""
        return self.upload_file_with_progress(local_path, remote_path, overwrite, progress_callback=None)

    def download_file(self, remote_path: str, local_path: str | Path) -> bool:
        """Скачивает файл с Яндекс.Диска."""
        local_path = Path(local_path)
        try:
            resp = requests.get(
                f"{self.base_url}/resources/download",
                headers=self.headers,
                params={"path": f"/{remote_path}"},
                timeout=10,
            )
            if resp.status_code != 200:
                return False

            download_url = resp.json().get("href")
            if not download_url:
                return False

            file_resp = requests.get(download_url, stream=True, timeout=60)
            if file_resp.status_code != 200:
                return False

            local_path.parent.mkdir(parents=True, exist_ok=True)
            with open(local_path, "wb") as f:
                for chunk in file_resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            return True
        except requests.exceptions.RequestException as e:
            self._log(f"❌ Ошибка сети при скачивании: {e}")
            return False

    def list_files(self, remote_folder: str) -> List[dict]:
        """Возвращает список файлов и папок в папке на Яндекс.Диске."""
        try:
            resp = requests.get(
                f"{self.base_url}/resources",
                headers=self.headers,
                params={"path": f"/{remote_folder}", "limit": 100},
                timeout=10,
            )
            if resp.status_code != 200:
                return []

            data = resp.json()
            items = data.get("_embedded", {}).get("items", [])
            result = []
            for item in items:
                result.append({
                    "name": item.get("name"),
                    "path": item.get("path"),
                    "type": item.get("type"),
                    "size": item.get("size", 0),
                    "modified": item.get("modified"),
                })
            return result
        except requests.exceptions.RequestException:
            return []

    def list_all_files(self, remote_folder: str, prefix: str = "") -> List[dict]:
        """Рекурсивно возвращает все файлы в папке и подпапках."""
        result = []
        try:
            items = self.list_files(remote_folder)
            for item in items:
                rel = f"{prefix}{item['name']}" if not prefix else f"{prefix}/{item['name']}"
                if item.get("type") == "dir":
                    sub_folder = item["path"]
                    if sub_folder.startswith("disk:/"):
                        sub_folder = sub_folder[6:]
                    result.extend(self.list_all_files(sub_folder, rel))
                else:
                    result.append({
                        "name": item["name"],
                        "path": item["path"],
                        "rel": rel,
                        "size": item.get("size", 0),
                        "modified": item.get("modified"),
                    })
            return result
        except requests.exceptions.RequestException:
            return result

    def delete(self, remote_path: str) -> bool:
        """Удаляет файл/папку на Яндекс.Диске."""
        try:
            resp = requests.delete(
                f"{self.base_url}/resources",
                headers=self.headers,
                params={"path": f"/{remote_path}", "permanently": "true"},
                timeout=10,
            )
            return resp.status_code in (200, 202, 204)
        except requests.exceptions.RequestException:
            return False
