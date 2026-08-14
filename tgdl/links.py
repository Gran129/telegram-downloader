from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import unquote, urlparse

from tgdl.downloader import ANIM_EXTS, IMAGE_EXTS, VIDEO_EXTS, kind_from_name_and_mime

URL_RE = re.compile(r"""(?i)\b((?:https?://[^\s<>"'）】\]]+|magnet:\?[^\s<>"']+))""")

CLOUD_HOSTS = {
    "pan.baidu.com": "baidu-pan",
    "yun.baidu.com": "baidu-pan",
    "pan.quark.cn": "quark",
    "quark.cn": "quark",
    "alipan.com": "aliyun-drive",
    "aliyundrive.com": "aliyun-drive",
    "www.aliyundrive.com": "aliyun-drive",
    "115.com": "115",
    "115cdn.com": "115",
    "mega.nz": "mega",
    "drive.google.com": "google-drive",
    "docs.google.com": "google-drive",
    "dropbox.com": "dropbox",
    "www.dropbox.com": "dropbox",
    "mediafire.com": "mediafire",
    "www.mediafire.com": "mediafire",
    "www.123pan.com": "123pan",
    "123pan.com": "123pan",
    "lanzou.com": "lanzou",
    "lanzoui.com": "lanzou",
    "lanzoux.com": "lanzou",
}


@dataclass(frozen=True)
class ParsedLink:
    url: str
    category: str
    hint: str


def strip_url(url: str) -> str:
    return url.rstrip(").,;，。]")


def extract_raw_urls(text: str) -> list[str]:
    if not text:
        return []
    found: list[str] = []
    seen: set[str] = set()
    for match in URL_RE.findall(text):
        url = strip_url(match)
        if url not in seen:
            seen.add(url)
            found.append(url)
    return found


def classify_url(url: str) -> ParsedLink:
    raw = strip_url(url.strip())
    if raw.lower().startswith("magnet:"):
        return ParsedLink(url=raw, category="magnet", hint="magnet")

    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    path = unquote(parsed.path or "")
    suffix = ""
    if "." in path.rsplit("/", 1)[-1]:
        suffix = "." + path.rsplit(".", 1)[-1].lower()

    if host in {"t.me", "telegram.me", "telegram.dog"}:
        return ParsedLink(url=raw, category="telegram", hint="t.me")

    if suffix == ".torrent":
        return ParsedLink(url=raw, category="torrent", hint="torrent-file")

    for cloud_host, name in CLOUD_HOSTS.items():
        if host == cloud_host or host.endswith("." + cloud_host):
            return ParsedLink(url=raw, category="cloud", hint=name)

    media_kind = kind_from_name_and_mime(path, "")
    if media_kind or suffix in IMAGE_EXTS | VIDEO_EXTS | ANIM_EXTS:
        return ParsedLink(url=raw, category="direct-media", hint=media_kind or suffix)

    if parsed.scheme in {"http", "https"}:
        return ParsedLink(url=raw, category="webpage", hint=host or "http")
    return ParsedLink(url=raw, category="other", hint="unknown")
