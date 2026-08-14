from __future__ import annotations

from telethon import TelegramClient

from tgdl.config import SESSION_PATH, Settings


def build_client(settings: Settings) -> TelegramClient:
    return TelegramClient(
        str(SESSION_PATH),
        settings.api_id,
        settings.api_hash,
        device_model="TG Media Downloader",
        app_version="1.0.0",
        system_version="Windows",
    )


async def ensure_login(client: TelegramClient, phone: str | None) -> None:
    await client.start(phone=phone)
    me = await client.get_me()
    if me is None:
        raise SystemExit("Login failed.")
    name = " ".join(part for part in (me.first_name, me.last_name) if part)
    username = f"@{me.username}" if me.username else ""
    print(f"Logged in as {name} {username} (id={me.id})".strip())
