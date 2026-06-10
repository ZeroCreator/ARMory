import os
import re
import shutil
import uuid
from pathlib import Path
from typing import BinaryIO
from app.config import get_settings, Settings

settings = get_settings()


def slugify(name: str) -> str:
    """Make a filesystem-safe slug from a name."""
    if not name:
        return "untitled"
    # Заменить пробелы и дефисы на подчёркивания
    slug = re.sub(r"[-\s]+", "_", name.strip())
    # Удалить опасные символы файловой системы
    slug = re.sub(r'[\\/:*?"<>|]', "", slug)
    # Ограничить длину, чтобы избежать слишком длинных путей
    slug = slug[:80]
    return slug or "untitled"


class StorageBackend:
    async def save(self, file_obj: BinaryIO, filename: str, content_type: str | None = None, subfolder: str | None = None) -> dict:
        """Save file and return metadata dict with url/path"""
        raise NotImplementedError

    async def delete(self, identifier: str) -> bool:
        """Delete file by identifier (path or key)"""
        raise NotImplementedError

    async def rename_subfolder(self, old_subfolder: str, new_subfolder: str) -> bool:
        """Rename/move a subfolder on the filesystem."""
        raise NotImplementedError

    async def get_local_path(self, identifier: str) -> str | None:
        """Get local filesystem path for reading, or None if not local"""
        raise NotImplementedError

    def get_download_url(self, identifier: str, filename: str | None = None) -> str | None:
        """Get a URL that can be used to download the file"""
        raise NotImplementedError

    def get_preview_url(self, identifier: str) -> str | None:
        """Get a URL for inline preview (no Content-Disposition: attachment)"""
        raise NotImplementedError

    def get_public_url(self, identifier: str) -> str | None:
        """Get public URL if available"""
        raise NotImplementedError


class LocalStorage(StorageBackend):
    def __init__(self, base_path: str):
        self.base_path = Path(base_path).resolve()
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _unique_filename(self, original: str) -> str:
        ext = Path(original).suffix
        return f"{uuid.uuid4().hex}{ext}"

    def _resolve_path(self, identifier: str) -> Path:
        """Resolve identifier to actual filesystem path with fallback."""
        if not identifier:
            return self.base_path
        path = Path(identifier)
        # Если абсолютный и существует, использовать как есть
        if path.is_absolute() and path.exists():
            return path
        # Попробовать относительно base_path
        rel = self.base_path / identifier
        if rel.exists():
            return rel
        # Попробовать только имя файла (fallback для мигрированных БД со старыми абсолютными путями)
        basename = path.name
        if basename:
            fallback = self.base_path / basename
            if fallback.exists():
                return fallback
        return rel

    async def save(self, file_obj: BinaryIO, filename: str, content_type: str | None = None, subfolder: str | None = None) -> dict:
        unique_name = self._unique_filename(filename)
        dest_dir = self.base_path
        if subfolder:
            dest_dir = self.base_path / subfolder
            dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / unique_name
        with open(dest, "wb") as f:
            shutil.copyfileobj(file_obj, f)
        rel_path = str(Path(subfolder) / unique_name) if subfolder else unique_name
        return {
            "file_path": rel_path,
            "url": None,
        }

    async def delete(self, identifier: str) -> bool:
        path = self._resolve_path(identifier)
        if path.exists():
            path.unlink()
            return True
        return False

    async def rename_subfolder(self, old_subfolder: str, new_subfolder: str) -> bool:
        old_path = self.base_path / old_subfolder
        new_path = self.base_path / new_subfolder
        if not old_path.exists():
            return False
        if new_path.exists():
            return False
        new_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(old_path), str(new_path))
        return True

    async def get_local_path(self, identifier: str) -> str | None:
        path = self._resolve_path(identifier)
        return str(path) if path.exists() else None

    def get_download_url(self, identifier: str, filename: str | None = None) -> str | None:
        return None  # served via FileResponse

    def get_preview_url(self, identifier: str) -> str | None:
        return None  # served via FileResponse without attachment

    def get_public_url(self, identifier: str) -> str | None:
        return None


class S3Storage(StorageBackend):
    def __init__(self, settings: Settings):
        import boto3
        from botocore.config import Config as BotoConfig
        self.settings = settings
        self.bucket = settings.s3_bucket_name
        
        boto_config = BotoConfig(
            signature_version="s3v4",
            s3={"addressing_style": "path" if settings.s3_force_path_style else "auto"},
        )
        
        self.s3 = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key_id,
            aws_secret_access_key=settings.s3_secret_access_key,
            region_name=settings.s3_region,
            config=boto_config,
        )

    def _key(self, filename: str, subfolder: str | None = None) -> str:
        ext = Path(filename).suffix
        prefix = f"uploads/{subfolder}/" if subfolder else "uploads/"
        return f"{prefix}{uuid.uuid4().hex}{ext}"

    async def save(self, file_obj: BinaryIO, filename: str, content_type: str | None = None, subfolder: str | None = None) -> dict:
        key = self._key(filename, subfolder)
        extra_args = {}
        if content_type:
            extra_args["ContentType"] = content_type
        self.s3.upload_fileobj(file_obj, self.bucket, key, ExtraArgs=extra_args)
        url = self.get_public_url(key)
        return {
            "file_path": key,
            "url": url,
        }

    async def delete(self, identifier: str) -> bool:
        try:
            self.s3.delete_object(Bucket=self.bucket, Key=identifier)
            return True
        except Exception:
            return False

    async def rename_subfolder(self, old_subfolder: str, new_subfolder: str) -> bool:
        # У S3 нет настоящих папок; переименование ключей потребует copy+delete.
        # Пока не реализовано.
        return False

    async def get_local_path(self, identifier: str) -> str | None:
        return None

    def get_public_url(self, identifier: str) -> str | None:
        """Direct/public URL if bucket is public. For private buckets use get_download_url."""
        if self.settings.s3_endpoint_url:
            return f"{self.settings.s3_endpoint_url}/{self.bucket}/{identifier}"
        # Стандартный URL AWS S3
        return f"https://{self.bucket}.s3.{self.settings.s3_region}.amazonaws.com/{identifier}"

    def get_download_url(self, identifier: str, filename: str | None = None) -> str | None:
        """Generate a presigned URL for temporary access (works for private buckets)."""
        extra = {}
        if filename:
            extra["ResponseContentDisposition"] = f'attachment; filename="{filename}"'
        try:
            url = self.s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": identifier, **extra},
                ExpiresIn=self.settings.s3_presigned_expires,
            )
            return url
        except Exception:
            return None

    def get_preview_url(self, identifier: str) -> str | None:
        """Presigned URL without Content-Disposition for inline preview."""
        try:
            url = self.s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": identifier},
                ExpiresIn=self.settings.s3_presigned_expires,
            )
            return url
        except Exception:
            return None


def get_storage() -> StorageBackend:
    if settings.storage_type == "s3":
        return S3Storage(settings)
    return LocalStorage(settings.local_storage_path)
