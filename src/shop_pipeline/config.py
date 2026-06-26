"""Centralized configuration loader.

All environment access goes through this module — never read os.environ elsewhere.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values


class ConfigError(ValueError):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True)
class Config:
    """Application configuration. Immutable."""

    dashscope_api_key: str | None
    kling_api_key: str | None
    kling_api_secret: str | None

    @classmethod
    def load(
        cls,
        env_file: Path | None = None,
        require_dashscope: bool = False,
        require_kling: bool = False,
    ) -> Config:
        """Load config from .env file + process env.

        - env_file: defaults to <project root>/.env
        - Process env vars override file values
        - Raises ConfigError if a required key is missing
        """
        values: dict[str, str] = {}
        if env_file is not None and env_file.exists():
            values.update({k: v for k, v in dotenv_values(env_file).items() if v is not None})
        # Process env overrides
        for key in ("DASHSCOPE_API_KEY", "KLING_API_KEY", "KLING_API_SECRET"):
            env_val = os.environ.get(key)
            if env_val:
                values[key] = env_val

        dashscope = values.get("DASHSCOPE_API_KEY") or None
        kling_key = values.get("KLING_API_KEY") or None
        kling_secret = values.get("KLING_API_SECRET") or None

        if require_dashscope and not dashscope:
            raise ConfigError("DASHSCOPE_API_KEY is required but not set")
        if require_kling and not (kling_key and kling_secret):
            raise ConfigError("KLING_API_KEY and KLING_API_SECRET are required but not set")

        return cls(
            dashscope_api_key=dashscope,
            kling_api_key=kling_key,
            kling_api_secret=kling_secret,
        )

    def has_dashscope(self) -> bool:
        return bool(self.dashscope_api_key)

    def has_kling(self) -> bool:
        return bool(self.kling_api_key and self.kling_api_secret)
