import os
from pathlib import Path
from typing import Any

import requests


class YandexDiskError(RuntimeError):
    """Ошибка обращения к REST API Яндекс.Диска."""


class YandexDiskStorage:
    """Клиент для работы с Яндекс.Диском через REST API."""

    BASE_URL = "https://cloud-api.yandex.net/v1/disk"

    def __init__(self, oauth_token: str, backup_path: str = "ARMory/backups", request_timeout: int = 15):
        token = (oauth_token or "").strip()
        if not token:
            raise ValueError("Не задан OAuth-токен Яндекс.Диска")

        self.oauth_token = token
        self.backup_path = backup_path.strip("/")
        self.base_url = self.BASE_URL
        self.request_timeout = request_timeout
        self.headers = {
            "Authorization": f"OAuth {token}",
            "Accept": "application/json",
        }
        self.is_reloader = os.environ.get("WERKZEUG_RUN_MAIN") == "true"

    def _log(self, msg: str) -> None:
        if not self.is_reloader:
            print(msg)

    @staticmethod
    def _api_path(remote_path: str) -> str:
        normalized = str(remote_path or "").strip().strip("/")
        if not normalized:
            raise YandexDiskError("Не задан путь к объекту на Яндекс.Диске")
        return f"/{normalized}"

    @staticmethod
    def _error_message(response: requests.Response) -> str:
        messages = {
            401: "Недействительный токен Яндекс.Диска (HTTP 401)",
            403: "Нет прав доступа к Яндекс.Диску (HTTP 403)",
            404: "Файл или папка не найдены на Яндекс.Диске (HTTP 404)",
            507: "На Яндекс.Диске недостаточно места (HTTP 507)",
        }
        return messages.get(
            response.status_code,
            f"Яндекс.Диск вернул HTTP {response.status_code}",
        )

    def _request(self, method: str, endpoint: str, **kwargs: Any) -> requests.Response:
        kwargs.setdefault("timeout", self.request_timeout)
        try:
            return requests.request(
                method,
                f"{self.base_url}{endpoint}",
                headers=self.headers,
                **kwargs,
            )
        except requests.RequestException as exc:
            raise YandexDiskError("Не удалось подключиться к Яндекс.Диску") from exc

    def test_connection(self) -> dict[str, Any]:
        """Проверяет токен и возвращает безопасную для интерфейса информацию."""
        try:
            response = self._request("GET", "/")
        except YandexDiskError as exc:
            return {"ok": False, "info": str(exc)}

        if response.status_code != 200:
            return {"ok": False, "info": self._error_message(response)}

        try:
            data = response.json()
        except ValueError:
            return {"ok": False, "info": "Яндекс.Диск вернул некорректный ответ"}

        user = data.get("user", {})
        if not isinstance(user, dict):
            user = {}
        try:
            used = int(data.get("used_space") or 0)
            total = int(data.get("total_space") or 0)
        except (TypeError, ValueError):
            return {"ok": False, "info": "Яндекс.Диск вернул некорректную статистику"}

        return {
            "ok": True,
            "info": user.get("display_name") or "Подключено",
            "used": f"{used / (1024 ** 3):.2f} GB",
            "total": f"{total / (1024 ** 3):.2f} GB",
        }

    def file_exists(self, remote_path: str) -> bool:
        """Проверяет существование файла или папки на Яндекс.Диске."""
        response = self._request(
            "GET",
            "/resources",
            params={"path": self._api_path(remote_path)},
        )
        if response.status_code == 404:
            return False
        if response.status_code != 200:
            raise YandexDiskError(self._error_message(response))
        return True

    def create_folder(self, remote_path: str) -> bool:
        """Создаёт папку на Яндекс.Диске."""
        response = self._request(
            "PUT",
            "/resources",
            params={"path": self._api_path(remote_path)},
        )
        if response.status_code not in (201, 202, 409):
            raise YandexDiskError(self._error_message(response))
        return True

    def ensure_folders(self, remote_path: str) -> bool:
        """Создаёт всю цепочку папок для указанного пути."""
        parts = remote_path.strip("/").split("/")
        current = ""
        for part in parts[:-1]:
            if not part:
                continue
            current = f"{current}/{part}" if current else part
            self.create_folder(current)
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
        if not local_path.is_file():
            self._log(f"❌ Локальный файл не найден: {local_path}")
            return False

        self.ensure_folders(remote_path)
        total_size = local_path.stat().st_size
        response = self._request(
            "GET",
            "/resources/upload",
            params={
                "path": self._api_path(remote_path),
                "overwrite": str(overwrite).lower(),
            },
        )
        if response.status_code != 200:
            raise YandexDiskError(self._error_message(response))

        try:
            upload_url = response.json().get("href")
        except ValueError as exc:
            raise YandexDiskError("Яндекс.Диск не вернул ссылку для загрузки") from exc
        if not upload_url:
            raise YandexDiskError("Яндекс.Диск не вернул ссылку для загрузки")

        try:
            with local_path.open("rb") as file_obj:
                if progress_callback:
                    class _UploadStream:
                        """Файловый поток с прогрессом и известной длиной."""

                        def __init__(self, source, size: int):
                            self.source = source
                            self.size = size
                            self.uploaded = 0

                        def __len__(self):
                            return self.size

                        def read(self, size=-1):
                            chunk = self.source.read(size)
                            if chunk:
                                self.uploaded += len(chunk)
                                progress_callback(self.uploaded, self.size)
                            return chunk

                    upload_response = requests.put(
                        upload_url,
                        data=_UploadStream(file_obj, total_size),
                        headers={"Content-Type": "application/octet-stream"},
                        timeout=(self.request_timeout, 600),
                    )
                else:
                    upload_response = requests.put(
                        upload_url,
                        data=file_obj,
                        headers={"Content-Type": "application/octet-stream"},
                        timeout=(self.request_timeout, 600),
                    )
        except requests.RequestException as exc:
            raise YandexDiskError("Не удалось загрузить файл на Яндекс.Диск") from exc

        if upload_response.status_code not in (200, 201, 202):
            raise YandexDiskError(self._error_message(upload_response))
        return True

    def upload_file(self, local_path: str | Path, remote_path: str, overwrite: bool = True) -> bool:
        """Загружает локальный файл на Яндекс.Диск без отслеживания прогресса."""
        return self.upload_file_with_progress(
            local_path,
            remote_path,
            overwrite,
            progress_callback=None,
        )

    def download_file(self, remote_path: str, local_path: str | Path) -> bool:
        """Скачивает файл на локальный путь без сохранения частичного результата."""
        destination = Path(local_path)
        response = self._request(
            "GET",
            "/resources/download",
            params={"path": self._api_path(remote_path)},
        )
        if response.status_code != 200:
            raise YandexDiskError(self._error_message(response))

        try:
            download_url = response.json().get("href")
        except ValueError as exc:
            raise YandexDiskError("Яндекс.Диск не вернул ссылку для скачивания") from exc
        if not download_url:
            raise YandexDiskError("Яндекс.Диск не вернул ссылку для скачивания")

        destination.parent.mkdir(parents=True, exist_ok=True)
        partial = destination.with_name(f".{destination.name}.part")
        try:
            with requests.get(
                download_url,
                stream=True,
                timeout=(self.request_timeout, 600),
            ) as file_response:
                if file_response.status_code != 200:
                    raise YandexDiskError(self._error_message(file_response))
                with partial.open("wb") as output:
                    for chunk in file_response.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            output.write(chunk)
            os.replace(partial, destination)
        except YandexDiskError:
            partial.unlink(missing_ok=True)
            raise
        except requests.RequestException as exc:
            partial.unlink(missing_ok=True)
            raise YandexDiskError("Не удалось скачать файл с Яндекс.Диска") from exc
        except OSError as exc:
            partial.unlink(missing_ok=True)
            raise YandexDiskError("Не удалось сохранить скачанный файл") from exc
        return True

    def list_files(self, remote_folder: str) -> list[dict]:
        """Возвращает список файлов и папок в указанной папке."""
        response = self._request(
            "GET",
            "/resources",
            params={"path": self._api_path(remote_folder), "limit": 100},
        )
        if response.status_code == 404:
            return []
        if response.status_code != 200:
            raise YandexDiskError(self._error_message(response))

        try:
            items = response.json().get("_embedded", {}).get("items", [])
        except (AttributeError, ValueError) as exc:
            raise YandexDiskError("Яндекс.Диск вернул некорректный список файлов") from exc
        if not isinstance(items, list):
            raise YandexDiskError("Яндекс.Диск вернул некорректный список файлов")

        return [
            {
                "name": item.get("name"),
                "path": item.get("path"),
                "type": item.get("type"),
                "size": item.get("size", 0),
                "modified": item.get("modified"),
            }
            for item in items
            if isinstance(item, dict)
        ]

    def list_all_files(self, remote_folder: str, prefix: str = "") -> list[dict]:
        """Рекурсивно возвращает все файлы в папке и подпапках."""
        result = []
        for item in self.list_files(remote_folder):
            name = item.get("name") or ""
            rel = f"{prefix}{name}" if not prefix else f"{prefix}/{name}"
            if item.get("type") == "dir":
                sub_folder = item.get("path") or ""
                if sub_folder.startswith("disk:/"):
                    sub_folder = sub_folder[6:]
                result.extend(self.list_all_files(sub_folder, rel))
            else:
                result.append({
                    "name": name,
                    "path": item.get("path"),
                    "rel": rel,
                    "size": item.get("size", 0),
                    "modified": item.get("modified"),
                })
        return result

    def delete(self, remote_path: str) -> bool:
        """Удаляет файл или папку с Яндекс.Диска."""
        response = self._request(
            "DELETE",
            "/resources",
            params={
                "path": self._api_path(remote_path),
                "permanently": "true",
            },
        )
        if response.status_code not in (200, 202, 204):
            raise YandexDiskError(self._error_message(response))
        return True
