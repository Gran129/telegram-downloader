from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone

from tgdl.channels import format_dialog, list_media_dialogs
from tgdl.client import build_client, ensure_login
from tgdl.config import load_settings
from tgdl.downloader import ALL_TYPES, PHOTO_TYPES, download_channel
from tgdl.parser import (
    DEFAULT_BT_CONCURRENCY,
    DEFAULT_HTTP_CONCURRENCY,
    parse_channel,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tgdl",
        description="Download photos and videos from Telegram channels you already joined.",
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("login", help="Log in with phone + verification code")
    sub.add_parser("list", help="List channels and groups on this account")

    download = sub.add_parser("download", help="Download media from one channel")
    download.add_argument(
        "--channel",
        "-c",
        required=True,
        help="Channel id from `list`, @username, t.me link, or private invite link",
    )
    download.add_argument(
        "--type",
        "-t",
        default="photo,video",
        help="photo, video, animation — comma separated (default: photo,video)",
    )
    download.add_argument("--limit", "-n", type=int, default=None, help="Max files to save")
    download.add_argument("--since", help="Only media on/after this date, YYYY-MM-DD")
    download.add_argument("--until", help="Only media on/before this date, YYYY-MM-DD")
    download.add_argument(
        "--no-skip",
        action="store_true",
        help="Re-download even if the file already exists",
    )
    download.add_argument(
        "--dry-run",
        action="store_true",
        help="List matching photos/videos only, do not download",
    )

    parse = sub.add_parser(
        "parse",
        help="Parse links in messages, keep previews, download direct media URLs",
    )
    parse.add_argument("--channel", "-c", required=True, help="Channel id, @username, or invite")
    parse.add_argument("--limit", "-n", type=int, default=None, help="Max messages to scan")
    parse.add_argument("--since", help="Only on/after YYYY-MM-DD")
    parse.add_argument("--until", help="Only on/before YYYY-MM-DD")
    parse.add_argument(
        "--no-previews",
        action="store_true",
        help="Do not save Telegram link-preview images/videos",
    )
    parse.add_argument(
        "--catalog-only",
        action="store_true",
        help="Save all links but do not download files/torrents",
    )
    parse.add_argument(
        "--no-bt",
        action="store_true",
        help="Do not download magnet or .torrent payloads",
    )
    parse.add_argument(
        "--http-concurrency",
        type=int,
        default=DEFAULT_HTTP_CONCURRENCY,
        help=f"Parallel HTTP downloads (default: {DEFAULT_HTTP_CONCURRENCY})",
    )
    parse.add_argument(
        "--bt-concurrency",
        type=int,
        default=DEFAULT_BT_CONCURRENCY,
        help=f"Parallel torrent downloads (default: {DEFAULT_BT_CONCURRENCY})",
    )
    parse.add_argument(
        "--dry-run",
        action="store_true",
        help="Print parsed links only, do not write files",
    )
    return parser


def parse_types(raw: str) -> set[str]:
    mapping = {
        "photo": PHOTO_TYPES,
        "photos": PHOTO_TYPES,
        "image": PHOTO_TYPES,
        "images": PHOTO_TYPES,
        "video": {"video"},
        "videos": {"video"},
        "animation": {"animation"},
        "gif": {"animation"},
        "all": ALL_TYPES,
    }
    selected: set[str] = set()
    for part in raw.split(","):
        key = part.strip().lower()
        if not key:
            continue
        if key not in mapping:
            raise SystemExit(f"Unknown type '{part}'. Use photo, video, animation, or all.")
        selected |= mapping[key]
    if not selected:
        raise SystemExit("Choose at least one media type.")
    return selected


def parse_day(raw: str | None, end_of_day: bool = False) -> datetime | None:
    if not raw:
        return None
    try:
        day = datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise SystemExit("Dates must be YYYY-MM-DD") from exc
    if end_of_day:
        return day.replace(hour=23, minute=59, second=59)
    return day


async def cmd_login() -> None:
    settings = load_settings()
    client = build_client(settings)
    async with client:
        await ensure_login(client, settings.phone)
        print("Session saved. Next: python -m tgdl list")


async def cmd_list() -> None:
    settings = load_settings()
    client = build_client(settings)
    async with client:
        await ensure_login(client, settings.phone)
        items = await list_media_dialogs(client)
        if not items:
            print("No channels or groups found.")
            return
        print(f"{'ID':>14}  {'KIND':<12}  {'ACCESS':<22}  TITLE")
        print("-" * 80)
        for item in items:
            print(format_dialog(item))
        print("\nPrivate channels show no @username. Copy the ID into --channel.")


async def cmd_download(args: argparse.Namespace) -> None:
    settings = load_settings()
    client = build_client(settings)
    async with client:
        await ensure_login(client, settings.phone)
        await download_channel(
            client,
            target=args.channel,
            download_dir=settings.download_dir,
            types=parse_types(args.type),
            limit=args.limit,
            since=parse_day(args.since),
            until=parse_day(args.until, end_of_day=True),
            skip_existing=not args.no_skip,
            dry_run=args.dry_run,
        )


async def cmd_parse(args: argparse.Namespace) -> None:
    settings = load_settings()
    client = build_client(settings)
    async with client:
        await ensure_login(client, settings.phone)
        await parse_channel(
            client,
            target=args.channel,
            download_dir=settings.download_dir,
            limit=args.limit,
            since=parse_day(args.since),
            until=parse_day(args.until, end_of_day=True),
            keep_previews=not args.no_previews,
            download_direct=not args.catalog_only,
            download_torrents=not args.catalog_only and not args.no_bt,
            dry_run=args.dry_run,
            http_concurrency=args.http_concurrency,
            bt_concurrency=args.bt_concurrency,
        )


async def cmd_menu() -> None:
    print("Telegram media downloader")
    print("1) Login")
    print("2) List my channels / groups")
    print("3) Download from a channel")
    print("4) Parse links (previews, direct, magnet, torrent)")
    print("0) Exit")
    choice = input("Choose: ").strip()
    if choice == "1":
        await cmd_login()
    elif choice == "2":
        await cmd_list()
    elif choice == "3":
        channel = input("Channel id / @username / invite link: ").strip()
        if not channel:
            raise SystemExit("Channel is required.")
        media_type = input("Types [photo,video]: ").strip() or "photo,video"
        limit_raw = input("Limit empty=all: ").strip()
        args = argparse.Namespace(
            channel=channel,
            type=media_type,
            limit=int(limit_raw) if limit_raw else None,
            since=None,
            until=None,
            no_skip=False,
            dry_run=False,
        )
        await cmd_download(args)
    elif choice == "4":
        channel = input("Channel id / @username / invite link: ").strip()
        if not channel:
            raise SystemExit("Channel is required.")
        limit_raw = input("Max messages empty=all: ").strip()
        args = argparse.Namespace(
            channel=channel,
            limit=int(limit_raw) if limit_raw else None,
            since=None,
            until=None,
            no_previews=False,
            catalog_only=False,
            no_bt=False,
            http_concurrency=DEFAULT_HTTP_CONCURRENCY,
            bt_concurrency=DEFAULT_BT_CONCURRENCY,
            dry_run=False,
        )
        await cmd_parse(args)
    elif choice in {"0", ""}:
        return
    else:
        raise SystemExit("Unknown choice.")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "login":
        asyncio.run(cmd_login())
    elif args.command == "list":
        asyncio.run(cmd_list())
    elif args.command == "download":
        asyncio.run(cmd_download(args))
    elif args.command == "parse":
        asyncio.run(cmd_parse(args))
    else:
        try:
            asyncio.run(cmd_menu())
        except EOFError:
            parser.print_help()
