"""Environment-backed service configuration."""

from dataclasses import dataclass
import os
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv(
        "FASTAPI_DATABASE_URL", f"sqlite:///{SERVICE_ROOT / 'filemanager.db'}"
    )
    upload_dir: Path = Path(
        os.getenv("FASTAPI_UPLOAD_DIR", str(SERVICE_ROOT / "uploads"))
    )
    secret_key: str = os.getenv(
        "FASTAPI_SECRET_KEY", "development-only-change-me-before-production"
    )
    access_token_minutes: int = int(os.getenv("FASTAPI_ACCESS_TOKEN_MINUTES", "15"))
    refresh_token_days: int = int(os.getenv("FASTAPI_REFRESH_TOKEN_DAYS", "7"))
    max_file_size: int = int(os.getenv("FASTAPI_MAX_FILE_SIZE", str(50 * 1024 * 1024)))

    def validate(self) -> None:
        if self.access_token_minutes <= 0 or self.refresh_token_days <= 0:
            raise RuntimeError("Token lifetimes must be positive.")
        if self.max_file_size <= 0:
            raise RuntimeError("FASTAPI_MAX_FILE_SIZE must be positive.")
        if (
            os.getenv("FASTAPI_ENV", "development").lower() == "production"
            and self.secret_key == "development-only-change-me-before-production"
        ):
            raise RuntimeError("Production requires FASTAPI_SECRET_KEY.")
