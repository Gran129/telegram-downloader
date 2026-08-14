"""In-memory Telegram client used for offline demos and tests.

This lets the full download pipeline run end-to-end without real Telegram API
credentials, producing genuine files on disk.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

_EXTENSIONS = {"photo": "jpg", "video": "mp4", "document": "pdf"}


@dataclass
class FakeMessage:
    """A synthetic Telegram message carrying fake media bytes."""

    id: int
    kind: str | None
    content: bytes = b""

    def __post_init__(self) -> None:
        # Mirror the attribute shape Telethon messages expose so that
        # downloader.media_type() classifies them identically.
        self.photo = object() if self.kind == "photo" else None
        self.video = object() if self.kind == "video" else None
        self.document = object() if self.kind == "document" else None
        self.media = object() if self.kind else None

    @property
    def extension(self) -> str:
        return _EXTENSIONS.get(self.kind or "", "bin")


@dataclass
class FakeTelegramClient:
    """Implements the subset of the Telethon client the pipeline needs."""

    messages: list[FakeMessage] = field(default_factory=list)

    async def iter_messages(self, entity, limit=None):  # noqa: ARG002 - entity unused
        count = 0
        for message in self.messages:
            if limit is not None and count >= limit:
                break
            count += 1
            yield message

    async def download_media(self, message, file):
        target = Path(file)
        if target.suffix:
            dest = target
            dest.parent.mkdir(parents=True, exist_ok=True)
        else:
            target.mkdir(parents=True, exist_ok=True)
            dest = target / f"{message.id}.{message.extension}"
        dest.write_bytes(message.content or f"fake-{message.id}".encode())
        return str(dest)

    async def __aenter__(self) -> "FakeTelegramClient":
        return self

    async def __aexit__(self, *exc) -> bool:
        return False


def build_sample_client() -> FakeTelegramClient:
    """Return a client pre-loaded with a representative mix of messages."""
    return FakeTelegramClient(
        messages=[
            FakeMessage(id=101, kind="photo", content=b"\xff\xd8\xff sample-photo"),
            FakeMessage(id=102, kind="video", content=b"\x00\x00\x00 sample-video"),
            FakeMessage(id=103, kind=None, content=b""),  # text-only, skipped
            FakeMessage(id=104, kind="document", content=b"%PDF-1.4 sample-doc"),
            FakeMessage(id=105, kind="photo", content=b"\xff\xd8\xff another-photo"),
        ]
    )
