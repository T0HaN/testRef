from pathlib import Path
from typing import Optional

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# ============================================================
# === ПУТИ ПРОЕКТА ===
# ============================================================
BASE_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    """Конфигурация приложения.

    Все секреты (SECRET_KEY, DB_PASSWORD, S3_SECRET_KEY) НЕ имеют значений
    по умолчанию: при их отсутствии в .env / переменных окружения приложение
    падает на старте (fail-fast), а не работает со слабыми вшитыми паролями.

    Сгенерировать новый SECRET_KEY:
        python -c "import secrets; print(secrets.token_urlsafe(50))"
    """

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",  # абсолютный путь — не зависит от CWD
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # === JWT / AUTH ===
    # 🔒 Ключ подписи сессий: обязателен, задаётся в .env
    SECRET_KEY: SecretStr = Field(..., min_length=32)
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 часа
    # Secure-флаг для session-cookie и доп. Origin для WebSocket (CSWSH)
    SESSION_COOKIE_SECURE: bool = True  # отключайте только при отладке по HTTP
    WS_ALLOWED_ORIGINS: str = ""  # CSV дополнительных Origin, если не совпадают с Host

    # === DIRECTORIES ===
    DATA_DIR: Path = BASE_DIR / "data"
    TEMPLATES_DIR: Path = BASE_DIR / "templates"
    STATIC_DIR: Path = BASE_DIR / "static"

    # === STATIC DATA ===
    CLASSES_DIR: Path = BASE_DIR / "data" / "classes"
    EQUIPMENT_FILE: Path = BASE_DIR / "data" / "equipment.json"
    SPELLS_FILE: Path = BASE_DIR / "data" / "spells.json"

    # === POSTGRESQL DATABASE ===
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_NAME: str = "dnd"
    DB_USER: str = "dndapp"
    DB_PASSWORD: SecretStr = Field(..., min_length=8)

    # === REDIS ===
    REDIS_HOST: str = "127.0.0.1"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: Optional[str] = None

    # === S3 / MinIO ===
    S3_ENDPOINT: str = "http://127.0.0.1:9000"
    S3_ACCESS_KEY: str = "admin"
    S3_SECRET_KEY: SecretStr = Field(..., min_length=8)
    S3_BUCKET: str = "folio-maps"


    # === SMTP / EMAIL ===
    SMTP_HOST: str = "smtp.mail.ru"  # или smtp.yandex.ru / smtp.gmail.com
    SMTP_PORT: int = 465             # 465 (SSL) или 587 (STARTTLS)
    SMTP_USER: str = ""
    SMTP_PASSWORD: Optional[SecretStr] = None
    SMTP_FROM_NAME: str = "Folio VTT"


settings = Settings()

settings.DATA_DIR.mkdir(exist_ok=True)
(settings.DATA_DIR / "user_data").mkdir(exist_ok=True)