"""Tests for application configuration."""

from pathlib import Path

import pytest

from invoiceflow.config import Settings


def test_default_settings() -> None:
    """Verify default settings values."""
    settings = Settings()
    assert settings.data_dir == Path("data")
    assert settings.raw_dir == Path("data/raw")
    assert "sqlite" in settings.database_url
    assert settings.log_level == "INFO"
    assert settings.default_currency == "INR"
    assert settings.default_locale == "IN"


def test_env_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Verify environment variables override defaults."""
    custom_data = tmp_path / "custom_data"
    monkeypatch.setenv("INVOICEFLOW_DATA_DIR", str(custom_data))
    monkeypatch.setenv("INVOICEFLOW_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("INVOICEFLOW_DEFAULT_CURRENCY", "USD")

    settings = Settings()
    assert settings.data_dir == custom_data
    assert settings.log_level == "DEBUG"
    assert settings.default_currency == "USD"


def test_ensure_directories(tmp_path: Path) -> None:
    """Verify ensure_directories creates data directories."""
    data_dir = tmp_path / "test_data"
    raw_dir = data_dir / "raw"
    settings = Settings(data_dir=data_dir, raw_dir=raw_dir)

    assert not data_dir.exists()
    settings.ensure_directories()
    assert data_dir.is_dir()
    assert raw_dir.is_dir()
