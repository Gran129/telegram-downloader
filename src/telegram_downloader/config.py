"""Configuration loading for telegram-downloader.

Credentials are read from environment variables so that no secrets are ever
committed to the repository. Obtain ``api_id`` / ``api_hash`` from
https://my.telegram.org and generate a ``StringSession`` for reusable logins.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


class ConfigError(RuntimeError):
    """Raised when required Telegram credentials are missing or invalid."""


@dataclass(frozen=True)
class Config:
    """Telegram API credentials used to authenticate a real client."""

    api_id: int
    api_hash: str
    session: str = ""

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "Config":
        """Build a :class:`Config` from environment variables.

        Recognised variables:
            TELEGRAM_API_ID    - numeric API id from my.telegram.org
            TELEGRAM_API_HASH  - API hash from my.telegram.org
            TELEGRAM_SESSION   - optional Telethon StringSession string
        """
        source = os.environ if env is None else env

        raw_api_id = source.get("TELEGRAM_API_ID", "").strip()
        api_hash = source.get("TELEGRAM_API_HASH", "").strip()
        session = source.get("TELEGRAM_SESSION", "").strip()

        missing = [
            name
            for name, value in (
                ("TELEGRAM_API_ID", raw_api_id),
                ("TELEGRAM_API_HASH", api_hash),
            )
            if not value
        ]
        if missing:
            raise ConfigError(
                "Missing required environment variable(s): "
                + ", ".join(missing)
                + ". Set them (see README) or use --demo for an offline run."
            )

        try:
            api_id = int(raw_api_id)
        except ValueError as exc:
            raise ConfigError("TELEGRAM_API_ID must be an integer") from exc

        return cls(api_id=api_id, api_hash=api_hash, session=session)
