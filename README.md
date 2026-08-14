# telegram-downloader

A small, well-tested command-line tool to download media (photos, videos, and
documents) from Telegram chats and channels, built on
[Telethon](https://docs.telethon.dev/).

The download pipeline is decoupled from the Telegram client, so the full flow
can be exercised **offline** with synthetic data — no API credentials required
for development, tests, or a demo.

## Requirements

- Python 3.10+
- `ffmpeg` (only needed if you later post-process downloaded video)

## Setup

```bash
pip3 install -r requirements-dev.txt   # runtime + test deps
pip3 install -e .                       # editable install
```

> On externally-managed Python installs (e.g. Debian/Ubuntu) add
> `--break-system-packages` to the `pip3` commands, as the Cloud Agent
> environment does.

## Usage

### Offline demo (no credentials)

Runs the real pipeline against built-in synthetic messages and writes actual
files to disk:

```bash
python3 -m telegram_downloader download demo-chat --demo --out ./downloads
```

### Real downloads

1. Get an `api_id` and `api_hash` from https://my.telegram.org.
2. Export credentials (a Telethon `StringSession` is optional but avoids
   re-authenticating):

   ```bash
   export TELEGRAM_API_ID=123456
   export TELEGRAM_API_HASH=your_api_hash
   export TELEGRAM_SESSION=your_string_session   # optional
   ```

3. Download:

   ```bash
   python3 -m telegram_downloader download @somechannel \
       --limit 50 --type photo --type video --out ./downloads
   ```

Options: `--limit N`, `--type {photo,video,document}` (repeatable),
`-o/--out DIR`.

## Development

Run the test suite:

```bash
python3 -m pytest
```

## Project layout

```
src/telegram_downloader/
  config.py       # env-based credential loading
  downloader.py   # client-agnostic download pipeline
  cli.py          # argparse CLI (real + --demo modes)
  testing.py      # in-memory fake client for offline runs & tests
tests/            # pytest suite (pipeline + CLI)
```
