from __future__ import annotations

import asyncio
import shutil
import subprocess
import sys
import time
from pathlib import Path

from tqdm import tqdm

# Default per-torrent wall-clock cap so a stalled magnet cannot hang forever.
DEFAULT_TIMEOUT_SEC = 30 * 60
# How many times to retry the whole engine chain (aria2 -> libtorrent) per source.
DEFAULT_ATTEMPTS = 2


class TorrentError(RuntimeError):
    pass


def _find_aria2() -> str | None:
    found = shutil.which("aria2c")
    if found:
        return found
    for candidate in (
        Path(r"C:\aria2\aria2c.exe"),
        Path.home() / "aria2" / "aria2c.exe",
        Path(r"C:\Program Files\aria2\aria2c.exe"),
    ):
        if candidate.is_file():
            return str(candidate)
    return None


def _has_libtorrent() -> bool:
    try:
        import libtorrent  # noqa: F401
    except Exception:
        return False
    return True


def bt_engine_available() -> bool:
    """True when at least one torrent engine (aria2 or libtorrent) is usable."""
    return _find_aria2() is not None or _has_libtorrent()


def aria2_install_hint() -> str:
    """Return a short, platform-specific guide for installing a torrent engine."""
    if sys.platform.startswith("win"):
        steps = (
            "  - Download aria2 from https://github.com/aria2/aria2/releases\n"
            "  - Put aria2c.exe on PATH, or at C:\\aria2\\aria2c.exe\n"
            "  - Alternatively: pip install libtorrent (often fails on Windows)"
        )
    elif sys.platform == "darwin":
        steps = (
            "  - brew install aria2\n"
            "  - Alternatively: pip install libtorrent"
        )
    else:
        steps = (
            "  - Debian/Ubuntu: sudo apt-get install -y aria2\n"
            "  - Fedora: sudo dnf install -y aria2\n"
            "  - Alternatively: pip install libtorrent"
        )
    return "To download magnet/.torrent links, install a torrent engine:\n" + steps


def download_via_aria2(source: str, dest_dir: Path, timeout_sec: int = 0) -> Path:
    aria2 = _find_aria2()
    if not aria2:
        raise TorrentError("aria2c not found")
    dest_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        aria2,
        "--seed-time=0",
        "--file-allocation=none",
        "--max-upload-limit=1K",
        "--bt-max-peers=80",
        "--summary-interval=5",
        "--console-log-level=notice",
        "--allow-overwrite=true",
        f"--dir={dest_dir}",
        source,
    ]
    print(f"[bt] aria2c -> {dest_dir}")
    proc = subprocess.run(cmd, cwd=str(dest_dir), timeout=timeout_sec or None, check=False)
    if proc.returncode not in {0, None}:
        raise TorrentError(f"aria2c exited {proc.returncode}")
    files = [p for p in dest_dir.rglob("*") if p.is_file()]
    if not files:
        raise TorrentError("aria2c finished but no files were saved")
    return dest_dir


def download_via_libtorrent(source: str, dest_dir: Path, timeout_sec: int = 0) -> Path:
    try:
        import libtorrent as lt
    except ImportError as exc:
        raise TorrentError("libtorrent is not installed") from exc

    dest_dir.mkdir(parents=True, exist_ok=True)
    session = lt.session()
    try:
        session.listen_on(6881, 6891)
    except Exception:
        pass
    try:
        session.apply_settings({"enable_dht": True, "enable_lsd": True, "enable_natpmp": True})
    except Exception:
        try:
            session.start_dht()
        except Exception:
            pass

    params: dict[str, object] = {"save_path": str(dest_dir)}
    if source.lower().startswith("magnet:"):
        handle = _add_magnet(session, lt, source, dest_dir)
    else:
        info = lt.torrent_info(source)
        params["ti"] = info
        handle = session.add_torrent(params)

    handle.set_upload_limit(1024)
    started = time.time()
    bar = tqdm(total=1000, desc="torrent", unit="‰", leave=False)
    try:
        while True:
            status = handle.status()
            progress = int(status.progress * 1000)
            bar.n = min(progress, 1000)
            bar.set_postfix(peers=status.num_peers, state=str(status.state), refresh=False)
            bar.refresh()
            if status.is_seeding or status.progress >= 1.0:
                break
            if timeout_sec and (time.time() - started) > timeout_sec:
                raise TorrentError("torrent timed out")
            time.sleep(1)
    finally:
        bar.close()
        try:
            session.remove_torrent(handle)
        except Exception:
            pass
    return dest_dir


def _add_magnet(session: object, lt: object, uri: str, dest_dir: Path):
    parse = getattr(lt, "parse_magnet_uri", None)
    if parse is not None:
        try:
            params = parse(uri)
            if hasattr(params, "save_path"):
                params.save_path = str(dest_dir)
                return session.add_torrent(params)
        except Exception:
            pass
    return session.add_torrent({"url": uri, "save_path": str(dest_dir)})


def download_torrent_sync(
    source: str,
    dest_dir: Path,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    attempts: int = DEFAULT_ATTEMPTS,
) -> Path:
    if not bt_engine_available():
        raise TorrentError("No torrent engine available.\n" + aria2_install_hint())

    errors: list[str] = []
    for attempt in range(1, max(1, attempts) + 1):
        if _find_aria2():
            try:
                return download_via_aria2(source, dest_dir, timeout_sec=timeout_sec)
            except Exception as exc:
                errors.append(f"attempt{attempt} aria2: {exc}")
        try:
            return download_via_libtorrent(source, dest_dir, timeout_sec=timeout_sec)
        except Exception as exc:
            errors.append(f"attempt{attempt} libtorrent: {exc}")
        if attempt < attempts:
            print(f"[bt] attempt {attempt} failed, retrying...")

    raise TorrentError(
        f"Torrent failed after {attempts} attempt(s). "
        + " | ".join(errors)
        + "\n"
        + aria2_install_hint()
    )


async def download_torrent(
    source: str,
    dest_dir: Path,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    attempts: int = DEFAULT_ATTEMPTS,
) -> Path:
    return await asyncio.to_thread(
        download_torrent_sync, source, dest_dir, timeout_sec, attempts
    )
