from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
SESSION_PATH = ROOT / "tgdl_session"
ENV_PATH = ROOT / ".env"

_ENV_KEYS = {
    "TELEGRAM_API_ID": "api_id",
    "TELEGRAM_API_HASH": "api_hash",
    "TELEGRAM_PHONE": "phone",
    "DOWNLOAD_DIR": "download_dir",
}


@dataclass(frozen=True)
class Settings:
    api_id: int
    api_hash: str
    phone: str | None
    download_dir: Path


def read_env_values() -> dict[str, str]:
    """Read raw .env values for pre-filling the GUI (no validation)."""
    values = {"api_id": "", "api_hash": "", "phone": "", "download_dir": "./downloads"}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in line:
                continue
            key, _, raw = line.partition("=")
            field = _ENV_KEYS.get(key.strip())
            value = raw.strip()
            if field and value:
                values[field] = value
    return values


def update_env(values: dict[str, str]) -> Path:
    """Create/update .env with the given values, preserving other lines."""
    desired = {
        "TELEGRAM_API_ID": values.get("api_id", ""),
        "TELEGRAM_API_HASH": values.get("api_hash", ""),
        "TELEGRAM_PHONE": values.get("phone", ""),
        "DOWNLOAD_DIR": values.get("download_dir", "") or "./downloads",
    }
    existing_lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    seen: set[str] = set()
    out: list[str] = []
    for line in existing_lines:
        key = line.partition("=")[0].strip()
        if key in desired:
            out.append(f"{key}={desired[key]}")
            seen.add(key)
        else:
            out.append(line)
    for key, value in desired.items():
        if key not in seen:
            out.append(f"{key}={value}")
    ENV_PATH.write_text("\n".join(out) + "\n", encoding="utf-8")
    return ENV_PATH


def load_settings() -> Settings:
    load_dotenv(ROOT / ".env", override=True)
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
