"""Tests for config module."""

from __future__ import annotations

import pytest

from shop_pipeline.config import Config, ConfigError


def test_config_loads_from_env_file(tmp_path, monkeypatch):
    """Config reads .env file from the project root by default."""
    # Clear any env vars from parent shell
    for key in ("DASHSCOPE_API_KEY", "KLING_API_KEY", "KLING_API_SECRET"):
        monkeypatch.delenv(key, raising=False)

    env_file = tmp_path / ".env"
    env_file.write_text(
        "DASHSCOPE_API_KEY=ds-test-123\n"
        "KLING_API_KEY=kl-test-456\n"
        "KLING_API_SECRET=kl-secret-789\n"
    )

    cfg = Config.load(env_file=env_file)
    assert cfg.dashscope_api_key == "ds-test-123"
    assert cfg.kling_api_key == "kl-test-456"
    assert cfg.kling_api_secret == "kl-secret-789"


def test_config_missing_required_key_raises(tmp_path, monkeypatch):
    """ConfigError raised when a required key is missing."""
    for key in ("DASHSCOPE_API_KEY", "KLING_API_KEY", "KLING_API_SECRET"):
        monkeypatch.delenv(key, raising=False)

    env_file = tmp_path / ".env"
    env_file.write_text("DASHSCOPE_API_KEY=\n")  # present but empty

    with pytest.raises(ConfigError, match="DASHSCOPE_API_KEY"):
        Config.load(env_file=env_file, require_dashscope=True)


def test_config_optional_key_not_required(tmp_path, monkeypatch):
    """DashScope key is optional (user might only have Kling)."""
    for key in ("DASHSCOPE_API_KEY", "KLING_API_KEY", "KLING_API_SECRET"):
        monkeypatch.delenv(key, raising=False)

    env_file = tmp_path / ".env"
    env_file.write_text("DASHSCOPE_API_KEY=\nKLING_API_KEY=k1\nKLING_API_SECRET=s1\n")

    cfg = Config.load(env_file=env_file, require_dashscope=False)
    assert cfg.dashscope_api_key is None
    assert cfg.kling_api_key == "k1"


def test_config_env_var_takes_precedence_over_file(tmp_path, monkeypatch):
    """Explicit environment variable overrides .env file."""
    env_file = tmp_path / ".env"
    env_file.write_text("DASHSCOPE_API_KEY=from-file\n")

    monkeypatch.setenv("DASHSCOPE_API_KEY", "from-env")
    cfg = Config.load(env_file=env_file)
    assert cfg.dashscope_api_key == "from-env"
