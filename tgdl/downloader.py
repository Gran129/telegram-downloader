from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from telethon import TelegramClient
from telethon.errors import (
    ChannelPrivateError,
    FloodWaitError,
    UserAlreadyParticipantError,
    UsernameNotOccupiedError,
)
from telethon.tl.functions.messages import CheckChatInviteRequest, ImportChatInviteRequest
from telethon.tl.types import (
    DocumentAttributeFilename,
    Message,
    MessageMediaDocument,
    MessageMediaPhoto,
    MessageMediaWebPage,
)
from tqdm import tqdm

PHOTO_TYPES = {"photo"}
VIDEO_TYPES = {"video", "animation"}
ALL_TYPES = PHOTO_TYPES | VIDEO_TYPES

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".heic", ".tif", ".tiff"}
VIDEO_EXTS = {".mp4", ".mkv", ".mov", ".webm", ".avi", ".m4v", ".ts", ".flv"}
ANIM_EXTS = {".gif"}

INVITE_RE = re.compile(
    r"(?:https?://)?t\.me/(?:\+|joinchat/)([A-Za-z0-9_\-]+)",
    re.IGNORECASE,
)
USERNAME_RE = re.compile(
    r"(?:https?://)?t\.me/([A-Za-z0-9_]+)/?$",
    re.IGNORECASE,
)


def document_filename(document: object) -> str:
    for attr in getattr(document, "attributes", None) or []:
        if isinstance(attr, DocumentAttributeFilename):
            return attr.file_name or ""
    return ""


def kind_from_name_and_mime(filename: str, mime: str) -> str | None:
    mime = (mime or "").lower()
    suffix = Path(filename or "").suffix.lower()
    if mime.startswith("image/") or suffix in IMAGE_EXTS:
        if mime == "image/gif" or suffix in ANIM_EXTS:
            return "animation"
        return "photo"
    if mime.startswith("video/") or suffix in VIDEO_EXTS:
        return "video"
    if suffix in ANIM_EXTS:
        return "animation"
    return None


def kind_from_document(document: object) -> str | None:
    if document is None:
        return None
    return kind_from_name_and_mime(
        document_filename(document),
        getattr(document, "mime_type", "") or "",
    )


def classify_message(message: Message) -> str | None:
    if message.sticker or message.voice or message.audio:
        return None

    media = message.media
    if isinstance(media, MessageMediaWebPage):
        web = getattr(media, "webpage", None)
        if web is None:
            return None
        doc_kind = kind_from_document(getattr(web, "document", None))
        if doc_kind:
            return doc_kind
        if getattr(web, "photo", None) is not None:
            return "photo"
        return None

    if isinstance(media, MessageMediaPhoto):
        return "photo"
    if message.video:
        return "video"
    if message.gif:
        return "animation"
    if isinstance(media, MessageMediaDocument) and media.document:
        return kind_from_document(media.document)
    if message.photo:
        return "photo"
    return None


def download_target(message: Message):
    media = message.media
    if isinstance(media, MessageMediaWebPage):
        web = getattr(media, "webpage", None)
        if web is None:
            return message
        document = getattr(web, "document", None)
        if document is not None and kind_from_document(document) in {"video", "animation"}:
            return document
        photo = getattr(web, "photo", None)
        if photo is not None:
            return photo
        if document is not None:
            return document
    return message


def media_origin(message: Message) -> str:
    if isinstance(message.media, MessageMediaWebPage):
        return "link-preview"
    sender = getattr(message, "sender", None)
    if getattr(sender, "bot", False):
        return "bot"
    return "attachment"


def safe_name(text: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*]', "_", text).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned[:80] or "channel"


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    for i in range(1, 10_000):
        candidate = path.with_name(f"{stem}_{i}{suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Cannot find a free filename for {path}")


async def resolve_channel(client: TelegramClient, target: str):
    target = target.strip()
    invite = INVITE_RE.search(target)
    if invite:
        invite_hash = invite.group(1)
        try:
            result = await client(ImportChatInviteRequest(invite_hash))
            chats = getattr(result, "chats", None)
            if chats:
                return chats[0]
        except UserAlreadyParticipantError:
            checked = await client(CheckChatInviteRequest(invite_hash))
            chat = getattr(checked, "chat", None)
            if chat is not None:
                return chat
        except Exception:
            pass

    username_match = USERNAME_RE.search(target)
    if username_match:
        target = username_match.group(1)

    if target.startswith("@"):
        target = target[1:]

    try:
        return await client.get_entity(int(target) if _looks_like_id(target) else target)
    except (ChannelPrivateError, UsernameNotOccupiedError, ValueError) as exc:
        raise SystemExit(
            f"Cannot access '{target}'. Join the private channel with this account first, "
            "then pass the numeric id from `python -m tgdl list`."
        ) from exc


def _looks_like_id(value: str) -> bool:
    return value.lstrip("-").isdigit()


class DownloadStats:
    def __init__(self) -> None:
        self.saved = 0
        self.skipped = 0
        self.failed = 0


async def download_channel(
    client: TelegramClient,
    *,
    target: str,
    download_dir: Path,
    types: set[str],
    limit: int | None,
    since: datetime | None,
    until: datetime | None,
    skip_existing: bool = True,
    dry_run: bool = False,
) -> DownloadStats:
    entity = await resolve_channel(client, target)
    title = getattr(entity, "title", None) or getattr(entity, "username", None) or str(entity.id)
    folder = download_dir / safe_name(str(title))
    photos_dir = folder / "photos"
    videos_dir = folder / "videos"
    if not dry_run:
        photos_dir.mkdir(parents=True, exist_ok=True)
        videos_dir.mkdir(parents=True, exist_ok=True)

    print(f"Channel: {title}")
    if dry_run:
        print("Mode:    list only (no download)")
    else:
        print(f"Save to: {folder}")
    print(f"Types:   {', '.join(sorted(types))}")

    stats = DownloadStats()
    offset_date = until
    scanned = 0

    async for message in client.iter_messages(entity, offset_date=offset_date):
        if limit is not None and scanned >= limit:
            break
        if not isinstance(message, Message) or message.date is None:
            continue
        msg_date = message.date if message.date.tzinfo else message.date.replace(tzinfo=timezone.utc)
        if since is not None and msg_date < since:
            break

        kind = classify_message(message)
        if kind is None or kind not in types:
            continue

        scanned += 1
        origin = media_origin(message)
        date_prefix = msg_date.strftime("%Y%m%d")
        base = f"{date_prefix}_{message.id}"
        if dry_run:
            sender = getattr(message, "sender", None)
            sender_name = getattr(sender, "username", None) or getattr(sender, "first_name", None) or "-"
            preview = (message.raw_text or "").replace("\n", " ")[:60]
            print(f"{base}  {kind:<10}  {origin:<13}  @{sender_name}  {preview}")
            stats.saved += 1
            continue

        dest_dir = photos_dir if kind == "photo" else videos_dir
        try:
            await _download_one(
                client,
                message,
                dest_dir,
                base,
                skip_existing=skip_existing,
                stats=stats,
            )
        except FloodWaitError as exc:
            print(f"\nRate limited. Wait {exc.seconds}s then retry this channel.")
            raise
        except Exception as exc:
            stats.failed += 1
            print(f"\nFailed message {message.id}: {exc}")

    print(
        f"\nDone. saved={stats.saved} skipped={stats.skipped} failed={stats.failed} matched={scanned}"
    )
    return stats


async def _download_one(
    client: TelegramClient,
    message: Message,
    dest_dir: Path,
    base: str,
    *,
    skip_existing: bool,
    stats: DownloadStats,
) -> None:
    existing = list(dest_dir.glob(f"{base}.*"))
    if skip_existing and existing:
        stats.skipped += 1
        return

    with tqdm(unit="B", unit_scale=True, desc=base, leave=False) as bar:
        def progress(current: int, total: int) -> None:
            bar.total = total or bar.total
            bar.n = current
            bar.refresh()

        saved = await client.download_media(
            download_target(message),
            file=str(dest_dir),
            progress_callback=progress,
        )

    if not saved:
        stats.failed += 1
        return

    saved_path = Path(saved)
    suffix = saved_path.suffix or ".bin"
    final_path = dest_dir / f"{base}{suffix}"
    if skip_existing and final_path.exists() and saved_path != final_path:
        saved_path.unlink(missing_ok=True)
        stats.skipped += 1
        return
    if final_path.exists() and final_path != saved_path:
        final_path = unique_path(final_path)
    if saved_path != final_path:
        saved_path.replace(final_path)
    stats.saved += 1
