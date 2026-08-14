from pathlib import Path

import pytest

from telegram_downloader.downloader import MediaDownloader, media_type
from telegram_downloader.testing import (
    FakeMessage,
    FakeTelegramClient,
    build_sample_client,
)


@pytest.mark.asyncio
async def test_downloads_only_messages_with_media(tmp_path: Path) -> None:
    client = build_sample_client()
    downloader = MediaDownloader(client)

    result = await downloader.download_chat("demo", tmp_path)

    # Sample data has 4 media messages and 1 text-only message.
    assert result.downloaded == 4
    assert result.skipped == 1
    for path in result.files:
        assert path.exists()
        assert path.read_bytes()  # non-empty


@pytest.mark.asyncio
async def test_limit_is_respected(tmp_path: Path) -> None:
    downloader = MediaDownloader(build_sample_client())

    result = await downloader.download_chat("demo", tmp_path, limit=2)

    # First two sample messages are a photo and a video.
    assert result.downloaded == 2


@pytest.mark.asyncio
async def test_media_type_filter(tmp_path: Path) -> None:
    downloader = MediaDownloader(build_sample_client())

    result = await downloader.download_chat("demo", tmp_path, media_types=["photo"])

    assert result.downloaded == 2  # two photos in the sample
    assert all(p.suffix == ".jpg" for p in result.files)


@pytest.mark.asyncio
async def test_progress_callback_invoked(tmp_path: Path) -> None:
    events: list[tuple[str, int]] = []
    downloader = MediaDownloader(build_sample_client())

    await downloader.download_chat(
        "demo", tmp_path, progress=lambda path, i: events.append((path, i))
    )

    assert [i for _, i in events] == [1, 2, 3, 4]


@pytest.mark.asyncio
async def test_creates_output_directory(tmp_path: Path) -> None:
    nested = tmp_path / "a" / "b" / "c"
    client = FakeTelegramClient([FakeMessage(id=1, kind="document", content=b"x")])

    result = await MediaDownloader(client).download_chat("demo", nested)

    assert nested.is_dir()
    assert result.downloaded == 1


def test_media_type_classification() -> None:
    assert media_type(FakeMessage(id=1, kind="photo")) == "photo"
    assert media_type(FakeMessage(id=2, kind="video")) == "video"
    assert media_type(FakeMessage(id=3, kind="document")) == "document"
    assert media_type(FakeMessage(id=4, kind=None)) is None
