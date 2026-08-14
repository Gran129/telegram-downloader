from pathlib import Path

from tgdl import config


def test_update_and_read_env_roundtrip(monkeypatch, tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    monkeypatch.setattr(config, "ENV_PATH", env_path)

    config.update_env(
        {
            "api_id": "12345",
            "api_hash": "deadbeef",
            "phone": "+15551234567",
            "download_dir": "./downloads",
        }
    )
    assert env_path.exists()

    values = config.read_env_values()
    assert values["api_id"] == "12345"
    assert values["api_hash"] == "deadbeef"
    assert values["phone"] == "+15551234567"
    assert values["download_dir"] == "./downloads"


def test_update_env_preserves_comments(monkeypatch, tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("# my comment\nTELEGRAM_API_ID=old\nCUSTOM=keep\n", encoding="utf-8")
    monkeypatch.setattr(config, "ENV_PATH", env_path)

    config.update_env({"api_id": "new", "api_hash": "h", "phone": "", "download_dir": "./d"})
    text = env_path.read_text(encoding="utf-8")
    assert "# my comment" in text
    assert "CUSTOM=keep" in text
    assert "TELEGRAM_API_ID=new" in text
    assert "TELEGRAM_API_ID=old" not in text


def test_resolve_credentials_from_env_dict() -> None:
    assert config.resolve_api_credentials(
        {"TELEGRAM_API_ID": "111", "TELEGRAM_API_HASH": "abc"}
    ) == ("111", "abc")


def test_resolve_credentials_none_when_missing(monkeypatch) -> None:
    monkeypatch.setattr(config, "_bundled_defaults", lambda: None)
    assert config.resolve_api_credentials({}) is None


def test_resolve_credentials_bundled_fallback(monkeypatch) -> None:
    monkeypatch.setattr(config, "_bundled_defaults", lambda: ("999", "deadbeef"))
    assert config.resolve_api_credentials({}) == ("999", "deadbeef")


def test_default_download_dir_name() -> None:
    assert config.default_download_dir().name == "TelegramDownloader"
