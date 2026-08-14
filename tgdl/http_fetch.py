from __future__ import annotations

import re
from pathlib import Path

import aiohttp
from tqdm import tqdm

from tgdl.downloader import kind_from_name_and_mime, unique_path

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
MAX_BYTES = 3 * 1024 * 1024 * 1024
DISPOSITION_RE = re.compile(r"filename\*?=(?:UTF-8''|\"?)([^\";]+)", re.IGNORECASE)


def filename_from_headers(url: str, content_type: str, disposition: str) -> str:
    if disposition:
        match = DISPOSITION_RE.search(disposition)
        if match:
            name = match.group(1).strip().strip('"')
            if name:
                return Path(name).name
    path_name = Path(url.split("?", 1)[0]).name
    if path_name and "." in path_name:
        return path_name
    kind = kind_from_name_and_mime("", content_type)
    ext = {None: ".bin", "photo": ".jpg", "video": ".mp4", "animation": ".gif"}[kind]
    return f"file{ext}"


def is_html(content_type: str) -> bool:
    return "text/html" in (content_type or "").lower()


def is_media_response(content_type: str, filename: str) -> bool:
    ctype = (content_type or "").lower()
    if ctype.startswith("image/") or ctype.startswith("video/"):
        return True
    return kind_from_name_and_mime(filename, ctype) in {"photo", "video", "animation"}


def is_torrent_response(content_type: str, filename: str) -> bool:
    name = (filename or "").lower()
    ctype = (content_type or "").lower()
    return name.endswith(".torrent") or "bittorrent" in ctype


async def download_http_asset(
    session: aiohttp.ClientSession,
    url: str,
    media_dir: Path,
    torrent_dir: Path,
    basename: str,
) -> tuple[str, Path | None]:
    media_dir.mkdir(parents=True, exist_ok=True)
    torrent_dir.mkdir(parents=True, exist_ok=True)
    timeout = aiohttp.ClientTimeout(total=None, sock_connect=30, sock_read=180)
    headers = {"User-Agent": USER_AGENT}
    async with session.get(url, allow_redirects=True, timeout=timeout, headers=headers) as resp:
        if resp.status >= 400:
            return "error", None
        content_type = resp.content_type or resp.headers.get("Content-Type", "")
        disposition = resp.headers.get("Content-Disposition", "")
        filename = filename_from_headers(str(resp.url), content_type, disposition)
        if is_html(content_type):
            return "html", None

        dest_dir = torrent_dir if is_torrent_response(content_type, filename) else media_dir
        kind = "torrent" if dest_dir == torrent_dir else "media"
        if kind == "media" and not is_media_response(content_type, filename):
            return "other", None

        length = resp.content_length
        if length is not None and length > MAX_BYTES:
            return "too-large", None

        suffix = Path(filename).suffix or (".torrent" if kind == "torrent" else ".bin")
        final_path = unique_path(dest_dir / f"{basename}{suffix}")
        with tqdm(total=length, unit="B", unit_scale=True, desc=basename, leave=False) as bar:
            with final_path.open("wb") as handle:
                async for chunk in resp.content.iter_chunked(1024 * 256):
                    handle.write(chunk)
                    bar.update(len(chunk))
                    if final_path.stat().st_size > MAX_BYTES:
                        handle.close()
                        final_path.unlink(missing_ok=True)
                        return "too-large", None
        return kind, final_path


async def download_direct_url(
    session: aiohttp.ClientSession,
    url: str,
    dest_dir: Path,
    basename: str,
) -> Path | None:
    dummy = dest_dir / "_unused"
    kind, path = await download_http_asset(session, url, dest_dir, dummy, basename)
    if kind == "media":
        return path
    if dummy.exists():
        dummy.unlink(missing_ok=True)
    return None
