from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import aiohttp
from telethon import TelegramClient
from telethon.tl.types import (
    Message,
    MessageEntityTextUrl,
    MessageEntityUrl,
    MessageMediaWebPage,
)

from tgdl.downloader import (
    ALL_TYPES,
    DownloadStats,
    _download_one,
    classify_message,
    resolve_channel,
    safe_name,
)
from tgdl.http_fetch import USER_AGENT, download_http_asset
from tgdl.links import ParsedLink, classify_url, extract_raw_urls
from tgdl.torrent_fetch import download_torrent


@dataclass
class ParserStats:
    messages: int = 0
    links: int = 0
    previews: int = 0
    direct: int = 0
    telegram_posts: int = 0
    torrents: int = 0
    catalogued: int = 0
    failed: int = 0
    by_category: Counter[str] = field(default_factory=Counter)


def urls_from_message(message: Message) -> list[str]:
    text = message.raw_text or message.message or ""
    found = extract_raw_urls(text)
    entities = message.get_entities_text() if message.entities else []
    for ent, inner in entities:
        if isinstance(ent, MessageEntityTextUrl) and ent.url:
            found.append(ent.url)
        elif isinstance(ent, MessageEntityUrl) and inner:
            found.append(inner)
    web = getattr(message, "web_preview", None)
    web_url = getattr(web, "url", None) if web else None
    if web_url:
        found.append(web_url)

    unique: list[str] = []
    seen: set[str] = set()
    for url in found:
        url = url.strip()
        if url and url not in seen:
            seen.add(url)
            unique.append(url)
    return unique


def write_catalog(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    md_path = path.with_suffix(".md")
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        grouped.setdefault(str(row.get("category", "other")), []).append(row)
    lines = ["# Parsed links", ""]
    for category, items in grouped.items():
        lines.append(f"## {category} ({len(items)})")
        lines.append("")
        for item in items:
            title = item.get("preview_title") or item.get("text") or ""
            lines.append(f"- `{item.get('message_id')}` [{title}]({item.get('url')})")
        lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")


async def parse_channel(
    client: TelegramClient,
    *,
    target: str,
    download_dir: Path,
    limit: int | None,
    since: datetime | None,
    until: datetime | None,
    keep_previews: bool = True,
    download_direct: bool = True,
    download_torrents: bool = True,
    dry_run: bool = False,
) -> ParserStats:
    entity = await resolve_channel(client, target)
    title = getattr(entity, "title", None) or getattr(entity, "username", None) or str(entity.id)
    folder = download_dir / safe_name(str(title))
    preview_photos = folder / "photos"
    preview_videos = folder / "videos"
    direct_dir = folder / "parsed" / "direct"
    torrent_dir = folder / "parsed" / "torrents"
    catalog_path = folder / "parsed" / "links.jsonl"

    print("[parser-bot] scanning messages for links + Telegram previews")
    print(f"Channel: {title}")
    print(f"Save to: {folder / 'parsed'}")

    stats = ParserStats()
    rows: list[dict[str, object]] = []
    preview_stats = DownloadStats()

    async with aiohttp.ClientSession(headers={"User-Agent": USER_AGENT}) as session:
        async for message in client.iter_messages(entity, offset_date=until):
            if limit is not None and stats.messages >= limit:
                break
            if not isinstance(message, Message) or message.date is None:
                continue
            msg_date = (
                message.date if message.date.tzinfo else message.date.replace(tzinfo=timezone.utc)
            )
            if since is not None and msg_date < since:
                break

            stats.messages += 1
            urls = urls_from_message(message)
            kind = classify_message(message)
            preview_title = ""
            web = getattr(message, "web_preview", None)
            if web is not None:
                preview_title = getattr(web, "title", None) or getattr(web, "site_name", None) or ""

            has_link = bool(urls) or isinstance(message.media, MessageMediaWebPage)
            if keep_previews and has_link and kind in ALL_TYPES:
                date_prefix = msg_date.strftime("%Y%m%d")
                base = f"{date_prefix}_{message.id}"
                if dry_run:
                    print(f"{base}  preview/{kind}  {(message.raw_text or '')[:50]}")
                    stats.previews += 1
                else:
                    dest = preview_photos if kind == "photo" else preview_videos
                    dest.mkdir(parents=True, exist_ok=True)
                    try:
                        before = preview_stats.saved
                        await _download_one(
                            client,
                            message,
                            dest,
                            base,
                            skip_existing=True,
                            stats=preview_stats,
                        )
                        if preview_stats.saved > before:
                            stats.previews += 1
                    except Exception as exc:
                        stats.failed += 1
                        print(f"preview failed {message.id}: {exc}")

            snippet = (message.raw_text or "").replace("\n", " ")[:180]
            for url in urls:
                parsed = classify_url(url)
                stats.links += 1
                stats.by_category[parsed.category] += 1
                row = {
                    "message_id": message.id,
                    "date": msg_date.isoformat(),
                    "url": parsed.url,
                    "category": parsed.category,
                    "hint": parsed.hint,
                    "preview_title": preview_title,
                    "text": snippet,
                    "downloaded": False,
                }

                if dry_run:
                    print(f"{message.id}  {parsed.category:<13}  {parsed.url}")
                    stats.catalogued += 1
                    rows.append(row)
                    continue

                if parsed.category in {"direct-media", "webpage", "torrent"} and download_direct:
                    try:
                        kind, saved = await download_http_asset(
                            session,
                            parsed.url,
                            direct_dir,
                            torrent_dir,
                            f"{msg_date.strftime('%Y%m%d')}_{message.id}",
                        )
                        if kind == "media" and saved is not None:
                            row["downloaded"] = True
                            row["file"] = str(saved)
                            row["category"] = "direct-media"
                            stats.direct += 1
                        elif kind == "torrent" and saved is not None:
                            row["torrent_file"] = str(saved)
                            if download_torrents:
                                out = await download_torrent(
                                    str(saved),
                                    torrent_dir / f"{msg_date.strftime('%Y%m%d')}_{message.id}",
                                )
                                row["downloaded"] = True
                                row["file"] = str(out)
                                stats.torrents += 1
                    except Exception as exc:
                        stats.failed += 1
                        row["error"] = str(exc)

                elif parsed.category == "magnet" and download_torrents:
                    try:
                        out = await download_torrent(
                            parsed.url,
                            torrent_dir / f"{msg_date.strftime('%Y%m%d')}_{message.id}",
                        )
                        row["downloaded"] = True
                        row["file"] = str(out)
                        stats.torrents += 1
                    except Exception as exc:
                        stats.failed += 1
                        row["error"] = str(exc)

                elif parsed.category == "telegram":
                    extra = await _try_telegram_post(client, parsed, folder, msg_date, message.id)
                    if extra:
                        row["downloaded"] = True
                        row["file"] = extra
                        stats.telegram_posts += 1

                rows.append(row)
                stats.catalogued += 1

    if not dry_run:
        write_catalog(catalog_path, rows)
        print(f"[parser-bot] catalog: {catalog_path}")
        print(f"[parser-bot] markdown: {catalog_path.with_suffix('.md')}")

    print(
        "[parser-bot] "
        f"messages={stats.messages} links={stats.links} "
        f"previews={stats.previews} direct={stats.direct} "
        f"tme={stats.telegram_posts} torrents={stats.torrents} failed={stats.failed}"
    )
    if stats.by_category:
        summary = ", ".join(f"{k}={v}" for k, v in sorted(stats.by_category.items()))
        print(f"[parser-bot] categories: {summary}")
    print("[parser-bot] cloud-disk links stay in the catalog (need official clients).")
    return stats


async def _try_telegram_post(
    client: TelegramClient,
    parsed: ParsedLink,
    folder: Path,
    msg_date: datetime,
    source_id: int,
) -> str | None:
    from urllib.parse import urlparse

    path = urlparse(parsed.url).path.strip("/")
    parts = [p for p in path.split("/") if p]
    try:
        if len(parts) >= 2 and parts[0] == "c" and parts[1].isdigit() and parts[-1].isdigit():
            channel_id = int("-100" + parts[1])
            msg_id = int(parts[-1])
            entity = await client.get_entity(channel_id)
        elif len(parts) >= 2 and parts[-1].isdigit() and parts[0] not in {"+", "joinchat"}:
            entity = await client.get_entity(parts[0])
            msg_id = int(parts[-1])
        else:
            return None
        message = await client.get_messages(entity, ids=msg_id)
        if not isinstance(message, Message) or classify_message(message) is None:
            return None
        kind = classify_message(message)
        dest = folder / ("photos" if kind == "photo" else "videos")
        dest.mkdir(parents=True, exist_ok=True)
        stats = DownloadStats()
        await _download_one(
            client,
            message,
            dest,
            f"{msg_date.strftime('%Y%m%d')}_{source_id}_tme{msg_id}",
            skip_existing=True,
            stats=stats,
        )
        if stats.saved:
            return f"telegram-post:{msg_id}"
    except Exception:
        return None
    return None
