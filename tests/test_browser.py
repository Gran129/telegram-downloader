import asyncio
import base64
from datetime import datetime, timezone
from pathlib import Path

from tgdl import browser

# a tiny valid 1x1 PNG so Pillow/Tk could decode it if needed
PNG_1x1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


class FakeMessage:
    def __init__(self, msg_id: int, kind: str | None) -> None:
        self.id = msg_id
        self.date = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.media = None
        self.sticker = None
        self.voice = None
        self.audio = None
        self.video = object() if kind == "video" else None
        self.gif = None
        self.photo = object() if kind == "photo" else None


class FakeClient:
    def __init__(self, messages):
        self._messages = messages

    async def iter_messages(self, entity):
        for message in self._messages:
            yield message

    async def download_media(self, message, file=None, thumb=None, progress_callback=None):
        if file is bytes:  # thumbnail request
            return PNG_1x1
        directory = Path(file)
        directory.mkdir(parents=True, exist_ok=True)
        dest = directory / f"{message.id}.jpg"
        dest.write_bytes(b"full-media")
        return str(dest)


def _messages():
    return [
        FakeMessage(1, "photo"),
        FakeMessage(2, "video"),
        FakeMessage(3, None),  # text only -> skipped
        FakeMessage(4, "photo"),
    ]


def test_list_media_returns_items_with_thumbs() -> None:
    client = FakeClient(_messages())
    items = asyncio.run(browser.list_media(client, "chat", limit=10))
    assert len(items) == 3  # 2 photos + 1 video, text skipped
    assert all(i.thumb == PNG_1x1 for i in items)
    assert {i.kind for i in items} == {"photo", "video"}


def test_list_media_type_filter() -> None:
    client = FakeClient(_messages())
    items = asyncio.run(browser.list_media(client, "chat", limit=10, types={"photo"}))
    assert len(items) == 2
    assert all(i.kind == "photo" for i in items)


def test_list_media_limit() -> None:
    client = FakeClient(_messages())
    items = asyncio.run(browser.list_media(client, "chat", limit=1))
    assert len(items) == 1


def test_save_items_writes_selected(tmp_path: Path) -> None:
    client = FakeClient(_messages())
    items = asyncio.run(browser.list_media(client, "chat", limit=10))
    # select first two
    result = asyncio.run(
        browser.save_items(client, items[:2], download_dir=tmp_path, title="My Chat")
    )
    assert result.saved == 2
    folder = tmp_path / "My Chat"
    saved = list((folder / "photos").glob("*")) + list((folder / "videos").glob("*"))
    assert len(saved) == 2
