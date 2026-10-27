from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    admin_password: str = "change-me"
    data_dir: Path = Path("./data")
    frontend_dist: Path = Path("./frontend/dist")
    cookie_secure: bool = False
    session_days: int = 30
    pixabay_api_key: str = ""

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.data_dir / 'vacabyrock.sqlite3'}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
