"""Application configuration management using pydantic-settings."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration settings for InvoiceFlow."""

    model_config = SettingsConfigDict(
        env_prefix="INVOICEFLOW_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    data_dir: Path = Field(default=Path("data"), description="Root data directory")
    raw_dir: Path = Field(default=Path("data/raw"), description="Raw document storage directory")
    database_url: str = Field(
        default="sqlite:///data/invoiceflow.db",
        description="SQLAlchemy database connection URL",
    )
    log_level: str = Field(default="INFO", description="Standard logging level")
    log_json: bool = Field(default=False, description="Whether to format logs as JSON")

    default_currency: str = Field(default="INR", description="Default currency code")
    default_locale: str = Field(default="IN", description="Default locale for parsing rules")

    imap_host: str | None = Field(default=None, description="IMAP server hostname")
    imap_port: int = Field(default=993, description="IMAP server SSL port")
    imap_user: str | None = Field(default=None, description="IMAP account username")
    imap_password: str | None = Field(default=None, description="IMAP account password")
    imap_folder: str = Field(default="INBOX", description="IMAP mailbox folder")

    def ensure_directories(self) -> None:
        """Create necessary data storage directories if they do not exist."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.raw_dir.mkdir(parents=True, exist_ok=True)
