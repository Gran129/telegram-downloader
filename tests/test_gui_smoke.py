"""Import-level smoke tests for the GUI module (no display required)."""

from tgdl import gui


def test_gui_exposes_run_gui() -> None:
    assert callable(gui.run_gui)


def test_silent_bar_supports_tqdm_surface() -> None:
    bar = gui._SilentBar(total=100, unit="B")
    # attribute assignment used by the core modules
    bar.total = 10
    bar.n = 5
    bar.update(1)
    bar.refresh()
    bar.set_postfix(peers=3, state="x")
    bar.close()
    with gui._SilentBar() as ctx:
        ctx.update(2)


def test_silence_progress_bars_patches_modules() -> None:
    gui._silence_progress_bars()
    from tgdl import downloader, http_fetch, torrent_fetch

    assert downloader.tqdm is gui._SilentBar
    assert http_fetch.tqdm is gui._SilentBar
    assert torrent_fetch.tqdm is gui._SilentBar
