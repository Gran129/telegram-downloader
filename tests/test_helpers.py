from datetime import timezone

from tgdl.cli import parse_day, parse_types
from tgdl.downloader import safe_name


def test_parse_types_default_parts() -> None:
    assert parse_types("photo,video") == {"photo", "video"}
    assert parse_types("all") == {"photo", "video", "animation"}
    assert parse_types("gif") == {"animation"}


def test_parse_day() -> None:
    value = parse_day("2026-08-14")
    assert value is not None
    assert value.tzinfo == timezone.utc
    assert value.day == 14


def test_kind_from_name_and_mime() -> None:
    from tgdl.downloader import kind_from_name_and_mime

    assert kind_from_name_and_mime("a.jpg", "") == "photo"
    assert kind_from_name_and_mime("clip.mp4", "application/octet-stream") == "video"
    assert kind_from_name_and_mime("x.bin", "video/mp4") == "video"
    assert kind_from_name_and_mime("loop.gif", "") == "animation"
    assert kind_from_name_and_mime("pack.zip", "application/zip") is None


def test_classify_url() -> None:
    from tgdl.links import classify_url, extract_raw_urls

    assert classify_url("https://cdn.example.com/a.mp4").category == "direct-media"
    assert classify_url("https://cdn.example.com/file.torrent").category == "torrent"
    assert classify_url("https://t.me/foo/12").category == "telegram"
    assert classify_url("https://pan.baidu.com/s/1abc").category == "cloud"
    assert classify_url("magnet:?xt=urn:btih:abc").category == "magnet"
    assert classify_url("https://example.com/page").category == "webpage"

    text = "see https://cdn.example.com/v.mp4 and https://pan.quark.cn/s/xx"
    urls = extract_raw_urls(text)
    assert len(urls) == 2


def test_safe_name() -> None:
    assert ":" not in safe_name("a:b/c?*")
    assert safe_name("   ") == "channel"
