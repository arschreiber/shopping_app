"""Konfiguration (ARCHITECTURE.md §2): pydantic-settings aus `.env` + `data/config.local.toml`.

Marktspezifisches (PLZ, Edeka-Markt-ID) gehört bewusst *nicht* ins Repo, sondern in
`data/config.local.toml` (ARCHITECTURE.md §12).
"""

from __future__ import annotations

import tomllib
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MEALPLAN_",
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    data_dir: Path = Field(default=REPO_ROOT / "data")
    database_url: str | None = None

    # Bring! - eigener Bot-Account (general_plan.md §6 Nr. 2), nie die privaten Konten.
    bring_email: str | None = None
    bring_password: str | None = None
    bring_list_name: str | None = None
    bring_sync: Literal["bring", "text"] = "text"
    catalog_autofetch: bool = True  # Tests setzen False - kein Netz

    # Angebote (Phase 2)
    korbunio_url: str | None = None
    offer_fetch_enabled: bool = False
    offer_fetch_hours: tuple[int, int] = (5, 5)  # Mo, Do

    # Betrieb
    host: str = "0.0.0.0"
    port: int = 8080
    log_level: str = "INFO"
    backup_keep: int = 7

    @property
    def db_path(self) -> Path:
        return self.data_dir / "mealplan.sqlite3"

    @property
    def sqlalchemy_url(self) -> str:
        return self.database_url or f"sqlite+pysqlite:///{self.db_path}"

    @property
    def catalog_dir(self) -> Path:
        return self.data_dir / "catalog"

    @property
    def media_dir(self) -> Path:
        return self.data_dir / "media"

    @property
    def backup_dir(self) -> Path:
        return self.data_dir / "backups"

    @property
    def local_config(self) -> dict[str, Any]:
        """`data/config.local.toml` - PLZ, Markt-IDs. Fehlt im Repo, das ist Absicht."""
        path = self.data_dir / "config.local.toml"
        if not path.exists():
            return {}
        with path.open("rb") as handle:
            return tomllib.load(handle)

    def ensure_dirs(self) -> None:
        for path in (self.data_dir, self.catalog_dir, self.media_dir, self.backup_dir):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
