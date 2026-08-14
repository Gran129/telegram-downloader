import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from tgdl import parser


class FakeMessage:
    def __init__(self, msg_id: int, text: str) -> None:
        self.id = msg_id
        self.message = text
        self.raw_text = text
        self.date = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.entities = None
        self.media = None
        self.web_preview = None
        self.sticker = None
        self.voice = None
        self.audio = None
        self.video = None
        self.gif = None
        self.photo = None

    def get_entities_text(self):
        return []


class FakeEntity:
    id = 123
    title = "TestChannel"
    username = None


class FakeClient:
    def __init__(self, messages):
        self._messages = messages

    async def iter_messages(self, entity, offset_date=None):
        for message in self._messages:
            yield message


def test_parse_channel_schedules_and_catalogs(monkeypatch, tmp_path: Path) -> None:
    async def fake_resolve(client, target):
        return FakeEntity()

    async def fake_http(session, url, media_dir, torrent_dir, basename):
        if "fail" in url:
            raise RuntimeError("boom")
        Path(media_dir).mkdir(parents=True, exist_ok=True)
        dest = Path(media_dir) / f"{basename}.mp4"
        dest.write_bytes(b"x")
        return "media", dest

    async def fake_torrent(source, dest_dir, *args, **kwargs):
        Path(dest_dir).mkdir(parents=True, exist_ok=True)
        return Path(dest_dir)

    monkeypatch.setattr(parser, "Message", object)  # accept our fake messages
    monkeypatch.setattr(parser, "resolve_channel", fake_resolve)
    monkeypatch.setattr(parser, "download_http_asset", fake_http)
    monkeypatch.setattr(parser, "download_torrent", fake_torrent)
    monkeypatch.setattr(parser, "bt_engine_available", lambda: True)

    messages = [
        FakeMessage(1, "grab http://host/a.mp4"),
        FakeMessage(2, "magnet:?xt=urn:btih:deadbeef"),
        FakeMessage(3, "broken http://host/fail.mp4"),
        FakeMessage(4, "just text, no links here"),
    ]
    client = FakeClient(messages)

    stats = asyncio.run(
        parser.parse_channel(
            client,
            target="123",
            download_dir=tmp_path,
            limit=None,
            since=None,
            until=None,
        )
    )

    assert stats.links == 3
    assert stats.direct == 1
    assert stats.torrents == 1
    assert stats.failed == 1

    folder = tmp_path / "TestChannel" / "parsed"
    catalog = folder / "links.jsonl"
    failures = folder / "failures.jsonl"
    assert catalog.exists()
    rows = [json.loads(line) for line in catalog.read_text().splitlines()]
    assert len(rows) == 3
    assert any(r["downloaded"] and r["category"] == "direct-media" for r in rows)
    assert any(r.get("error") for r in rows)

    assert failures.exists()
    failure_rows = [json.loads(line) for line in failures.read_text().splitlines()]
    assert len(failure_rows) == 1
    assert "fail.mp4" in failure_rows[0]["url"]


def test_parse_channel_dry_run_writes_nothing(monkeypatch, tmp_path: Path) -> None:
    async def fake_resolve(client, target):
        return FakeEntity()

    monkeypatch.setattr(parser, "Message", object)  # accept our fake messages
    monkeypatch.setattr(parser, "resolve_channel", fake_resolve)

    client = FakeClient([FakeMessage(1, "http://host/a.mp4")])
    stats = asyncio.run(
        parser.parse_channel(
            client,
            target="123",
            download_dir=tmp_path,
            limit=None,
            since=None,
            until=None,
            dry_run=True,
        )
    )
    assert stats.catalogued == 1
    assert not (tmp_path / "TestChannel" / "parsed" / "links.jsonl").exists()
