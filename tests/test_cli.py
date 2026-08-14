from pathlib import Path

import pytest

from telegram_downloader.cli import main
from telegram_downloader.config import Config, ConfigError


def test_cli_demo_downloads_files(tmp_path: Path, capsys) -> None:
    out = tmp_path / "downloads"
    exit_code = main(["download", "demo-chat", "--demo", "--out", str(out)])

    assert exit_code == 0
    files = sorted(out.iterdir())
    assert len(files) == 4  # 4 media messages in the sample
    captured = capsys.readouterr().out
    assert "Downloaded 4 file(s)" in captured


def test_cli_demo_with_type_filter(tmp_path: Path) -> None:
    out = tmp_path / "downloads"
    exit_code = main(
        ["download", "demo-chat", "--demo", "--out", str(out), "--type", "video"]
    )

    assert exit_code == 0
    files = list(out.iterdir())
    assert len(files) == 1
    assert files[0].suffix == ".mp4"


def test_cli_real_mode_without_credentials_errors(tmp_path: Path, monkeypatch) -> None:
    for var in ("TELEGRAM_API_ID", "TELEGRAM_API_HASH", "TELEGRAM_SESSION"):
        monkeypatch.delenv(var, raising=False)

    exit_code = main(["download", "some-chat", "--out", str(tmp_path)])
    assert exit_code == 2  # ConfigError -> exit code 2


def test_config_from_env_parses_values() -> None:
    config = Config.from_env(
        {"TELEGRAM_API_ID": "12345", "TELEGRAM_API_HASH": "abcdef"}
    )
    assert config.api_id == 12345
    assert config.api_hash == "abcdef"


def test_config_from_env_missing_raises() -> None:
    with pytest.raises(ConfigError):
        Config.from_env({"TELEGRAM_API_ID": "12345"})
