from __future__ import annotations

from dataclasses import dataclass

from telethon import TelegramClient
from telethon.tl.types import Channel, Chat, User


@dataclass(frozen=True)
class DialogInfo:
    entity_id: int
    title: str
    kind: str
    username: str | None
    is_private: bool


def _kind_of(entity: object) -> str:
    if isinstance(entity, Channel):
        return "channel" if entity.broadcast else "supergroup"
    if isinstance(entity, Chat):
        return "group"
    if isinstance(entity, User):
        return "user"
    return type(entity).__name__.lower()


async def list_media_dialogs(client: TelegramClient) -> list[DialogInfo]:
    items: list[DialogInfo] = []
    async for dialog in client.iter_dialogs():
        entity = dialog.entity
        kind = _kind_of(entity)
        if kind not in {"channel", "supergroup", "group"}:
            continue
        username = getattr(entity, "username", None)
        items.append(
            DialogInfo(
                entity_id=dialog.id,
                title=dialog.name or "(untitled)",
                kind=kind,
                username=username,
                is_private=username is None,
            )
        )
    return items


def format_dialog(item: DialogInfo) -> str:
    access = "private" if item.is_private else f"@{item.username}"
    return f"{item.entity_id:>14}  [{item.kind:<10}]  {access:<22}  {item.title}"
