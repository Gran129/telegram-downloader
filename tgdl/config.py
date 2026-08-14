from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
SESSION_PATH = ROOT / "tgdl_session"


@dataclass(frozen=True)
class Settings:
    api_id: int
    api_hash: str
    phone: str | None
    download_dir: Path


def load_settings() -> Settings:
    load_dotenv(ROOT / ".env")
    api_id_raw = os.getenv("TELEGRAM_API_ID", "").strip()
    api_hash = os.getenv("TELEGRAM_API_HASH", "").strip()
    phone = os.getenv("TELEGRAM_PHONE", "").strip() or None
    download_dir = Path(os.getenv("DOWNLOAD_DIR", "./downloads")).expanduser()
    if not download_dir.is_absolute():
        download_dir = ROOT / download_dir

    if not api_id_raw or not api_hash:
        raise SystemExit(
            "Missing TELEGRAM_API_ID / TELEGRAM_API_HASH.\n"
            "1. Copy .env.example to .env\n"
            "2. Open https://my.telegram.org -> API development tools\n"
            "3. Paste api_id and api_hash into .env"
        )
    try:
        api_id = int(api_id_raw)
    except ValueError as exc:
        raise SystemExit("TELEGRAM_API_ID must be a number.") from exc

    return Settings(
        api_id=api_id,
        api_hash=api_hash,
        phone=phone,
        download_dir=download_dir,
    )
