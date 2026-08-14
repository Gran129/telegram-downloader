"""Command-line interface for telegram-downloader."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from .config import Config, ConfigError
from .downloader import MEDIA_TYPES, MediaDownloader


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="telegram-downloader",
        description="Download media from a Telegram chat or channel.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    dl = sub.add_parser("download", help="Download media from a chat")
    dl.add_argument("chat", help="Chat/channel username, id, or invite link")
    dl.add_argument(
        "-o",
        "--out",
        default="./downloads",
        help="Output directory (default: ./downloads)",
    )
    dl.add_argument(
        "-l",
        "--limit",
        type=int,
        default=None,
        help="Maximum number of messages to inspect",
    )
    dl.add_argument(
        "-t",
        "--type",
        dest="types",
        action="append",
        choices=MEDIA_TYPES,
        help="Restrict to a media type (repeatable)",
    )
    dl.add_argument(
        "--demo",
        action="store_true",
        help="Run offline against synthetic sample data (no credentials needed)",
    )
    return parser


def _print_progress(path: str, index: int) -> None:
    print(f"  [{index}] downloaded {path}")


async def _download(args: argparse.Namespace) -> int:
    if args.demo:
        from .testing import build_sample_client

        client = build_sample_client()
        print(f"Running in DEMO mode (synthetic data) for chat '{args.chat}'.")
        downloader = MediaDownloader(client)
        result = await downloader.download_chat(
            args.chat,
            args.out,
            limit=args.limit,
            media_types=args.types,
            progress=_print_progress,
        )
    else:
        try:
            config = Config.from_env()
        except ConfigError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

        from telethon import TelegramClient
        from telethon.sessions import StringSession

        client = TelegramClient(
            StringSession(config.session), config.api_id, config.api_hash
        )
        print(f"Connecting to Telegram for chat '{args.chat}'...")
        async with client:
            downloader = MediaDownloader(client)
            result = await downloader.download_chat(
                args.chat,
                args.out,
                limit=args.limit,
                media_types=args.types,
                progress=_print_progress,
            )

    print(
        f"Done. Downloaded {result.downloaded} file(s), "
        f"skipped {result.skipped} message(s). Output: {Path(args.out).resolve()}"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "download":
        return asyncio.run(_download(args))
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
