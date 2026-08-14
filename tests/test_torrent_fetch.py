from pathlib import Path

import pytest

from tgdl import torrent_fetch
from tgdl.torrent_fetch import TorrentError, aria2_install_hint, download_torrent_sync


def test_aria2_hint_mentions_engine() -> None:
    hint = aria2_install_hint()
    assert hint.strip()
    assert "aria2" in hint.lower()


def test_no_engine_raises_with_hint(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(torrent_fetch, "bt_engine_available", lambda: False)
    with pytest.raises(TorrentError) as excinfo:
        download_torrent_sync("magnet:?xt=urn:btih:abc", tmp_path)
    assert "aria2" in str(excinfo.value).lower()


def test_retries_then_succeeds(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(torrent_fetch, "bt_engine_available", lambda: True)
    monkeypatch.setattr(torrent_fetch, "_find_aria2", lambda: "/usr/bin/aria2c")

    def failing_libtorrent(*args, **kwargs):
        raise TorrentError("libtorrent not installed")

    monkeypatch.setattr(torrent_fetch, "download_via_libtorrent", failing_libtorrent)

    calls = {"n": 0}

    def flaky_aria2(source, dest_dir, timeout_sec=0):
        calls["n"] += 1
        if calls["n"] == 1:
            raise TorrentError("transient failure")
        Path(dest_dir).mkdir(parents=True, exist_ok=True)
        return Path(dest_dir)

    monkeypatch.setattr(torrent_fetch, "download_via_aria2", flaky_aria2)

    out = download_torrent_sync("magnet:?xt=urn:btih:abc", tmp_path / "t", attempts=2)
    assert out == tmp_path / "t"
    assert calls["n"] == 2  # first attempt failed, second succeeded


def test_gives_up_after_attempts(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(torrent_fetch, "bt_engine_available", lambda: True)
    monkeypatch.setattr(torrent_fetch, "_find_aria2", lambda: "/usr/bin/aria2c")

    def always_fail(*args, **kwargs):
        raise TorrentError("boom")

    monkeypatch.setattr(torrent_fetch, "download_via_aria2", always_fail)
    monkeypatch.setattr(torrent_fetch, "download_via_libtorrent", always_fail)

    with pytest.raises(TorrentError) as excinfo:
        download_torrent_sync("magnet:x", tmp_path, attempts=2)
    assert "2 attempt" in str(excinfo.value)


def test_bt_engine_available_reflects_helpers(monkeypatch) -> None:
    monkeypatch.setattr(torrent_fetch, "_find_aria2", lambda: None)
    monkeypatch.setattr(torrent_fetch, "_has_libtorrent", lambda: False)
    assert torrent_fetch.bt_engine_available() is False

    monkeypatch.setattr(torrent_fetch, "_find_aria2", lambda: "/usr/bin/aria2c")
    assert torrent_fetch.bt_engine_available() is True
