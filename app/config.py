from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    app_name: str = "ARMory"
    database_url: str = "sqlite+aiosqlite:///./projectdocs.db"
    
    # Storage: "local" or "s3"
    storage_type: str = "local"
    local_storage_path: str = "./data/uploads"
    
    # S3 settings (optional)
    s3_endpoint_url: str | None = None
    s3_bucket_name: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    s3_region: str = "us-east-1"
    
    # S3 advanced
    s3_force_path_style: bool = False  # True for MinIO / some self-hosted S3
    s3_presigned_expires: int = 3600   # presigned URL lifetime in seconds

    # Yandex Disk sync
    yandex_disk_token: str | None = None
    yandex_disk_path: str = "ARMory/data"
    yandex_disk_backups_path: str = "ARMory/backups"
    timezone: str = "Europe/Moscow"

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
