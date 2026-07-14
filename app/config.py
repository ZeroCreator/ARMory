from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    app_name: str = "ARMory"
    database_url: str = "sqlite+aiosqlite:///./projectdocs.db"
    
    # Хранилище: "local" или "s3"
    storage_type: str = "local"
    local_storage_path: str = "./data/uploads"
    
    # Настройки S3 (опционально)
    s3_endpoint_url: str | None = None
    s3_bucket_name: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    s3_region: str = "us-east-1"
    
    # S3 расширенные
    s3_force_path_style: bool = False  # True for MinIO / some self-hosted S3
    s3_presigned_expires: int = 3600   # presigned URL lifetime in seconds

    # Синхронизация с Яндекс.Диском
    yandex_disk_token: str | None = None
    yandex_disk_path: str = "ARMory/data"
    yandex_disk_backups_path: str = "ARMory/backups"
    timezone: str = "Europe/Moscow"

    # alexandrite — папка для файлового хранилища заметок
    alexandrite_vault_path: str = "./data/alexandrite"

    # Путь к папке Alexandrite на Яндекс.Диске (для синхронизации и архивов)
    yandex_disk_alexandrite_path: str = "ARMory/alexandrite"

    # Ограничение просмотра Яндекс.Диска в Alexandrite указанной папкой.
    # Если не задано — доступен весь диск. Например: ARMory
    alexandrite_yandex_root_path: str | None = None

    # Отключение планировщика (вкладка не отображается на главной странице)
    scheduler_enabled: bool = True

    # Telegram-уведомления о событиях календаря
    telegram_reminder_enabled: bool = False
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None

    # Публичный URL ARMory (используется для WOPI / Collabora)
    armory_public_url: str = "https://armory.team-73.ru"

    # Collabora Online — редактирование документов в Alexandrite
    collabora_enabled: bool = False
    collabora_domain: str = "armory.team-73.ru"
    collabora_internal_url: str = "http://collabora:9980"
    collabora_public_url: str = "https://armory.team-73.ru/collabora"
    # Внутренний URL ARMory, по которому контейнер Collabora обращается к WOPI-эндпоинтам.
    # Collabora и app — в одной docker-сети; публичный адрес изнутри недоступен (hairpin),
    # поэтому WOPI-callback идёт напрямую в приложение.
    collabora_wopi_internal_url: str = "http://app:8088"
    collabora_service_root: str = "/collabora"
    collabora_wopi_secret: str = ""
    collabora_admin_user: str = "admin"
    collabora_admin_password: str = "changeme"

    # PocketBase — встроенный инструмент для управления схемами данных
    pocketbase_internal_url: str = "http://pocketbase:8090"
    pocketbase_public_path: str = "/pocketbase/"

    @property
    def pocketbase_public_url(self) -> str:
        return self.pocketbase_public_path + "_/"

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
