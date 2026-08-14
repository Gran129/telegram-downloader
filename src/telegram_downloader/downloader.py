"""Core media download pipeline.

The pipeline is deliberately decoupled from Telethon: it only requires a
"client" object exposing two awaitables, ``iter_messages`` (an async iterator)
and ``download_media``. The real Telethon ``TelegramClient`` satisfies this
interface, and so does :class:`telegram_downloader.testing.FakeTelegramClient`,
which lets the whole flow be exercised offline and in tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable, Iterable, Protocol

# Recognised logical media categories.
MEDIA_TYPES = ("photo", "video", "document")

ProgressCallback = Callable[[str, int], None]


class SupportsDownload(Protocol):
    """Minimal client interface required by :class:`MediaDownloader`."""

    def iter_messages(self, entity, limit=None):  # pragma: no cover - protocol
        ...

    def download_media(self, message, file) -> Awaitable[str | None]:  # pragma: no cover
        ...


@dataclass
class DownloadResult:
    """Summary of a completed download run."""

    files: list[Path] = field(default_factory=list)
    skipped: int = 0

    @property
    def downloaded(self) -> int:
        return len(self.files)


def media_type(message) -> str | None:
    """Classify a message's media, or return ``None`` when it has none."""
    if getattr(message, "photo", None):
        return "photo"
    if getattr(message, "video", None):
        return "video"
    if getattr(message, "document", None):
        return "document"
    if getattr(message, "media", None):
        return "document"
    return None


class MediaDownloader:
    """Downloads media from a chat using an injected client."""

    def __init__(self, client: SupportsDownload) -> None:
        self.client = client

    async def download_chat(
        self,
        entity,
        out_dir: str | Path,
        *,
        limit: int | None = None,
        media_types: Iterable[str] | None = None,
        progress: ProgressCallback | None = None,
    ) -> DownloadResult:
        """Download media from ``entity`` into ``out_dir``.

        Args:
            entity: Chat/channel identifier understood by the client.
            out_dir: Destination directory (created if needed).
            limit: Maximum number of messages to inspect.
            media_types: Restrict downloads to these logical types.
            progress: Optional callback invoked as ``(path, index)``.
        """
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)

        wanted = set(media_types) if media_types else None
        result = DownloadResult()

        async for message in self.client.iter_messages(entity, limit=limit):
            kind = media_type(message)
            if kind is None:
                result.skipped += 1
                continue
            if wanted is not None and kind not in wanted:
                result.skipped += 1
                continue

            saved = await self.client.download_media(message, file=str(out))
            if not saved:
                result.skipped += 1
                continue

            path = Path(saved)
            result.files.append(path)
            if progress is not None:
                progress(str(path), result.downloaded)

        return result
