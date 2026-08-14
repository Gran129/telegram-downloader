"""telegram-downloader: download media from Telegram chats and channels."""

from .config import Config
from .downloader import DownloadResult, MediaDownloader

__all__ = ["Config", "MediaDownloader", "DownloadResult"]
__version__ = "0.1.0"
