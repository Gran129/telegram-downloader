"""Tkinter GUI for tgdl.

A point-and-click front end over the existing async functions. The asyncio
event loop runs in a background thread; the UI submits coroutines to it and
receives log output through a thread-safe queue. Telethon's interactive
login (phone code / 2FA password) is wired to modal dialogs.

Tkinter ships with the standard Python installer on Windows, so this needs no
extra runtime dependency and packages cleanly with PyInstaller.
"""

from __future__ import annotations

import asyncio
import queue
import sys
import threading
from pathlib import Path

from tgdl import config
from tgdl.channels import list_media_dialogs
from tgdl.client import build_client
from tgdl.config import Settings, load_settings, read_env_values, update_env
from tgdl.downloader import download_channel

# Patch the progress bars used by the core modules so they do not spam the log
# console with carriage-return redraws. Import the modules and swap `tqdm`.
from tgdl import downloader as _downloader
from tgdl import http_fetch as _http_fetch
from tgdl import parser as _parser
from tgdl import torrent_fetch as _torrent_fetch
from tgdl.cli import parse_day, parse_types
from tgdl.parser import parse_channel


class _SilentBar:
    """Minimal no-op stand-in for tqdm used inside the GUI."""

    def __init__(self, *args, **kwargs) -> None:
        self.n = 0
        self.total = kwargs.get("total")

    def __enter__(self) -> "_SilentBar":
        return self

    def __exit__(self, *exc) -> bool:
        return False

    def update(self, _n: int = 1) -> None:
        pass

    def refresh(self) -> None:
        pass

    def set_postfix(self, *args, **kwargs) -> None:
        pass

    def close(self) -> None:
        pass


def _silence_progress_bars() -> None:
    for module in (_downloader, _http_fetch, _torrent_fetch, _parser):
        if hasattr(module, "tqdm"):
            module.tqdm = _SilentBar  # type: ignore[attr-defined]


class AsyncLoop:
    """Runs an asyncio event loop in a dedicated background thread."""

    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def submit(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self.loop)

    def stop(self) -> None:
        self.loop.call_soon_threadsafe(self.loop.stop)


class _QueueWriter:
    """File-like object that funnels text into a thread-safe queue."""

    def __init__(self, sink: "queue.Queue[str]") -> None:
        self._sink = sink

    def write(self, text: str) -> int:
        if text:
            self._sink.put(text)
        return len(text)

    def flush(self) -> None:
        pass


def run_gui() -> None:
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, scrolledtext, simpledialog, ttk
    except Exception as exc:  # pragma: no cover - depends on platform Tk
        print(
            "Tkinter is not available. On Debian/Ubuntu install it with:\n"
            "  sudo apt-get install -y python3-tk\n"
            f"({exc})"
        )
        raise SystemExit(1)

    _silence_progress_bars()

    app = _App(tk, ttk, scrolledtext, filedialog, messagebox, simpledialog)
    app.run()


class _App:
    def __init__(self, tk, ttk, scrolledtext, filedialog, messagebox, simpledialog) -> None:
        self.tk = tk
        self.ttk = ttk
        self.filedialog = filedialog
        self.messagebox = messagebox
        self.simpledialog = simpledialog

        self.loop = AsyncLoop()
        self.client = None
        self.settings: Settings | None = None
        self.dialog_map: dict[str, int] = {}
        self.log_queue: "queue.Queue[str]" = queue.Queue()

        self.root = tk.Tk()
        self.root.title("Telegram 下载器 (tgdl)")
        self.root.geometry("860x680")
        self.root.minsize(760, 560)

        env = read_env_values()
        self.api_id_var = tk.StringVar(value=env["api_id"])
        self.api_hash_var = tk.StringVar(value=env["api_hash"])
        self.phone_var = tk.StringVar(value=env["phone"])
        self.download_dir_var = tk.StringVar(value=env["download_dir"])
        self.channel_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Not logged in")

        # download options
        self.type_photo = tk.BooleanVar(value=True)
        self.type_video = tk.BooleanVar(value=True)
        self.type_anim = tk.BooleanVar(value=False)
        self.dl_limit = tk.StringVar()
        self.dl_since = tk.StringVar()
        self.dl_until = tk.StringVar()
        self.dl_no_skip = tk.BooleanVar(value=False)
        self.dl_dry = tk.BooleanVar(value=False)

        # parse options
        self.p_limit = tk.StringVar()
        self.p_since = tk.StringVar()
        self.p_until = tk.StringVar()
        self.p_no_previews = tk.BooleanVar(value=False)
        self.p_catalog_only = tk.BooleanVar(value=False)
        self.p_no_bt = tk.BooleanVar(value=False)
        self.p_http = tk.StringVar(value="3")
        self.p_bt = tk.StringVar(value="1")
        self.p_dry = tk.BooleanVar(value=False)

        self._build_ui()

        # redirect stdout/stderr so tgdl's print()s show in the log console
        self._stdout, self._stderr = sys.stdout, sys.stderr
        writer = _QueueWriter(self.log_queue)
        sys.stdout = writer
        sys.stderr = writer

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(100, self._drain_log)

    # ---------- UI construction ----------
    def _build_ui(self) -> None:
        tk, ttk = self.tk, self.ttk
        pad = {"padx": 6, "pady": 3}

        creds = ttk.LabelFrame(self.root, text="Telegram API (from my.telegram.org)")
        creds.pack(fill="x", **pad)
        ttk.Label(creds, text="API ID").grid(row=0, column=0, sticky="w", **pad)
        ttk.Entry(creds, textvariable=self.api_id_var, width=18).grid(row=0, column=1, sticky="w", **pad)
        ttk.Label(creds, text="API HASH").grid(row=0, column=2, sticky="w", **pad)
        ttk.Entry(creds, textvariable=self.api_hash_var, width=40).grid(row=0, column=3, sticky="w", **pad)
        ttk.Label(creds, text="Phone").grid(row=1, column=0, sticky="w", **pad)
        ttk.Entry(creds, textvariable=self.phone_var, width=18).grid(row=1, column=1, sticky="w", **pad)
        ttk.Label(creds, text="Download dir").grid(row=1, column=2, sticky="w", **pad)
        ttk.Entry(creds, textvariable=self.download_dir_var, width=32).grid(row=1, column=3, sticky="w", **pad)
        ttk.Button(creds, text="Browse", command=self._choose_dir).grid(row=1, column=4, **pad)
        self.login_btn = ttk.Button(creds, text="Save & Login", command=self.on_login)
        self.login_btn.grid(row=0, column=4, **pad)

        chan = ttk.LabelFrame(self.root, text="Channel")
        chan.pack(fill="x", **pad)
        ttk.Label(chan, text="Channel / @user / invite / id").grid(row=0, column=0, sticky="w", **pad)
        self.channel_combo = ttk.Combobox(chan, textvariable=self.channel_var, width=52)
        self.channel_combo.grid(row=0, column=1, sticky="we", **pad)
        self.channel_combo.bind("<<ComboboxSelected>>", self._on_channel_pick)
        self.list_btn = ttk.Button(chan, text="List my channels", command=self.on_list)
        self.list_btn.grid(row=0, column=2, **pad)
        chan.columnconfigure(1, weight=1)

        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="x", **pad)
        notebook.add(self._build_download_tab(), text="Download media")
        notebook.add(self._build_parse_tab(), text="Parse links (直链/磁力/种子)")

        status = ttk.Frame(self.root)
        status.pack(fill="x", **pad)
        ttk.Label(status, text="Status:").pack(side="left")
        ttk.Label(status, textvariable=self.status_var, foreground="#0a6").pack(side="left", padx=6)

        logframe = ttk.LabelFrame(self.root, text="Log")
        logframe.pack(fill="both", expand=True, **pad)
        self.log = self.scrolled(logframe)
        self.log.pack(fill="both", expand=True, padx=4, pady=4)

    def scrolled(self, parent):
        from tkinter import scrolledtext

        return scrolledtext.ScrolledText(parent, height=16, wrap="word", state="disabled")

    def _build_download_tab(self):
        tk, ttk = self.tk, self.ttk
        pad = {"padx": 6, "pady": 3}
        frame = ttk.Frame(self.root)
        types = ttk.Frame(frame)
        types.grid(row=0, column=0, columnspan=4, sticky="w", **pad)
        ttk.Label(types, text="Types:").pack(side="left")
        ttk.Checkbutton(types, text="photo", variable=self.type_photo).pack(side="left")
        ttk.Checkbutton(types, text="video", variable=self.type_video).pack(side="left")
        ttk.Checkbutton(types, text="animation", variable=self.type_anim).pack(side="left")
        ttk.Label(frame, text="Limit").grid(row=1, column=0, sticky="w", **pad)
        ttk.Entry(frame, textvariable=self.dl_limit, width=10).grid(row=1, column=1, sticky="w", **pad)
        ttk.Label(frame, text="Since (YYYY-MM-DD)").grid(row=1, column=2, sticky="w", **pad)
        ttk.Entry(frame, textvariable=self.dl_since, width=14).grid(row=1, column=3, sticky="w", **pad)
        ttk.Label(frame, text="Until (YYYY-MM-DD)").grid(row=2, column=2, sticky="w", **pad)
        ttk.Entry(frame, textvariable=self.dl_until, width=14).grid(row=2, column=3, sticky="w", **pad)
        ttk.Checkbutton(frame, text="Re-download existing", variable=self.dl_no_skip).grid(
            row=2, column=0, columnspan=2, sticky="w", **pad
        )
        ttk.Checkbutton(frame, text="Dry run (list only)", variable=self.dl_dry).grid(
            row=3, column=0, columnspan=2, sticky="w", **pad
        )
        self.download_btn = ttk.Button(frame, text="Download", command=self.on_download)
        self.download_btn.grid(row=3, column=3, sticky="e", **pad)
        return frame

    def _build_parse_tab(self):
        tk, ttk = self.tk, self.ttk
        pad = {"padx": 6, "pady": 3}
        frame = ttk.Frame(self.root)
        ttk.Label(frame, text="Limit").grid(row=0, column=0, sticky="w", **pad)
        ttk.Entry(frame, textvariable=self.p_limit, width=10).grid(row=0, column=1, sticky="w", **pad)
        ttk.Label(frame, text="Since").grid(row=0, column=2, sticky="w", **pad)
        ttk.Entry(frame, textvariable=self.p_since, width=14).grid(row=0, column=3, sticky="w", **pad)
        ttk.Label(frame, text="Until").grid(row=1, column=2, sticky="w", **pad)
        ttk.Entry(frame, textvariable=self.p_until, width=14).grid(row=1, column=3, sticky="w", **pad)
        ttk.Label(frame, text="HTTP concurrency").grid(row=1, column=0, sticky="w", **pad)
        ttk.Entry(frame, textvariable=self.p_http, width=6).grid(row=1, column=1, sticky="w", **pad)
        ttk.Label(frame, text="BT concurrency").grid(row=2, column=0, sticky="w", **pad)
        ttk.Entry(frame, textvariable=self.p_bt, width=6).grid(row=2, column=1, sticky="w", **pad)
        ttk.Checkbutton(frame, text="No previews", variable=self.p_no_previews).grid(
            row=3, column=0, sticky="w", **pad
        )
        ttk.Checkbutton(frame, text="Catalog only", variable=self.p_catalog_only).grid(
            row=3, column=1, sticky="w", **pad
        )
        ttk.Checkbutton(frame, text="No BT", variable=self.p_no_bt).grid(row=3, column=2, sticky="w", **pad)
        ttk.Checkbutton(frame, text="Dry run", variable=self.p_dry).grid(row=3, column=3, sticky="w", **pad)
        self.parse_btn = ttk.Button(frame, text="Parse", command=self.on_parse)
        self.parse_btn.grid(row=4, column=3, sticky="e", **pad)
        return frame

    # ---------- helpers ----------
    def _choose_dir(self) -> None:
        chosen = self.filedialog.askdirectory()
        if chosen:
            self.download_dir_var.set(chosen)

    def _on_channel_pick(self, _event=None) -> None:
        label = self.channel_var.get()
        if label in self.dialog_map:
            self.channel_var.set(str(self.dialog_map[label]))

    def _log(self, text: str) -> None:
        self.log_queue.put(text)

    def _drain_log(self) -> None:
        try:
            while True:
                chunk = self.log_queue.get_nowait()
                self.log.configure(state="normal")
                self.log.insert("end", chunk)
                self.log.see("end")
                self.log.configure(state="disabled")
        except queue.Empty:
            pass
        self.root.after(100, self._drain_log)

    def _set_status(self, text: str) -> None:
        self.root.after(0, lambda: self.status_var.set(text))

    def _ask(self, prompt: str, secret: bool = False) -> str:
        """Prompt the user on the Tk thread and block the asyncio thread."""
        answer: dict[str, str | None] = {}
        done = threading.Event()

        def ask_on_ui() -> None:
            show = "*" if secret else ""
            answer["value"] = self.simpledialog.askstring(
                "Telegram", prompt, show=show, parent=self.root
            )
            done.set()

        self.root.after(0, ask_on_ui)
        done.wait()
        value = answer.get("value")
        if value is None:
            raise RuntimeError("Cancelled by user")
        return value.strip()

    def _run_task(self, coro, button) -> None:
        button.config(state="disabled")
        future = self.loop.submit(coro)

        def finished(fut) -> None:
            try:
                fut.result()
            except Exception as exc:  # noqa: BLE001 - surface all errors to the log
                self._log(f"\n[error] {exc}\n")
            finally:
                self.root.after(0, lambda: button.config(state="normal"))

        future.add_done_callback(finished)

    def _save_env_from_fields(self) -> None:
        update_env(
            {
                "api_id": self.api_id_var.get().strip(),
                "api_hash": self.api_hash_var.get().strip(),
                "phone": self.phone_var.get().strip(),
                "download_dir": self.download_dir_var.get().strip(),
            }
        )

    # ---------- async client ----------
    async def _ensure_client(self):
        if self.client is not None:
            return self.client
        settings = load_settings()
        self.settings = settings
        client = build_client(settings)

        def phone_cb():
            return settings.phone or self._ask("Phone number (+countrycode):")

        await client.start(
            phone=phone_cb,
            code_callback=lambda: self._ask("Login code from Telegram:"),
            password=lambda: self._ask("Two-step password:", secret=True),
        )
        me = await client.get_me()
        if me is None:
            raise RuntimeError("Login failed")
        name = " ".join(p for p in (me.first_name, me.last_name) if p)
        handle = f"@{me.username}" if me.username else ""
        print(f"Logged in as {name} {handle} (id={me.id})".strip())
        self._set_status(f"Logged in: {name} {handle}".strip())
        self.client = client
        return client

    # ---------- button handlers ----------
    def on_login(self) -> None:
        if not self.api_id_var.get().strip() or not self.api_hash_var.get().strip():
            self.messagebox.showwarning("Missing", "Please fill API ID and API HASH first.")
            return
        self._save_env_from_fields()
        self._log("Logging in...\n")

        async def coro():
            await self._ensure_client()

        self._run_task(coro(), self.login_btn)

    def on_list(self) -> None:
        async def coro():
            client = await self._ensure_client()
            items = await list_media_dialogs(client)
            labels = [f"{it.entity_id}  {it.title}" for it in items]
            mapping = {label: it.entity_id for label, it in zip(labels, items)}

            def apply():
                self.dialog_map = mapping
                self.channel_combo["values"] = labels

            self.root.after(0, apply)
            print(f"Found {len(items)} channels/groups. Pick one from the dropdown.")

        self._run_task(coro(), self.list_btn)

    def on_download(self) -> None:
        channel = self.channel_var.get().strip()
        if not channel:
            self.messagebox.showwarning("Missing", "Enter or pick a channel first.")
            return
        types_raw = ",".join(
            name
            for name, var in (
                ("photo", self.type_photo),
                ("video", self.type_video),
                ("animation", self.type_anim),
            )
            if var.get()
        )
        if not types_raw:
            self.messagebox.showwarning("Missing", "Select at least one media type.")
            return
        opts = {
            "channel": channel,
            "types": types_raw,
            "limit": self.dl_limit.get().strip(),
            "since": self.dl_since.get().strip(),
            "until": self.dl_until.get().strip(),
            "no_skip": self.dl_no_skip.get(),
            "dry": self.dl_dry.get(),
        }

        async def coro():
            client = await self._ensure_client()
            await download_channel(
                client,
                target=opts["channel"],
                download_dir=self.settings.download_dir,
                types=parse_types(opts["types"]),
                limit=int(opts["limit"]) if opts["limit"] else None,
                since=parse_day(opts["since"] or None),
                until=parse_day(opts["until"] or None, end_of_day=True),
                skip_existing=not opts["no_skip"],
                dry_run=opts["dry"],
            )
            print("Download task finished.\n")

        self._run_task(coro(), self.download_btn)

    def on_parse(self) -> None:
        channel = self.channel_var.get().strip()
        if not channel:
            self.messagebox.showwarning("Missing", "Enter or pick a channel first.")
            return
        opts = {
            "channel": channel,
            "limit": self.p_limit.get().strip(),
            "since": self.p_since.get().strip(),
            "until": self.p_until.get().strip(),
            "no_previews": self.p_no_previews.get(),
            "catalog_only": self.p_catalog_only.get(),
            "no_bt": self.p_no_bt.get(),
            "http": self.p_http.get().strip() or "3",
            "bt": self.p_bt.get().strip() or "1",
            "dry": self.p_dry.get(),
        }

        async def coro():
            client = await self._ensure_client()
            kwargs = dict(
                target=opts["channel"],
                download_dir=self.settings.download_dir,
                limit=int(opts["limit"]) if opts["limit"] else None,
                since=parse_day(opts["since"] or None),
                until=parse_day(opts["until"] or None, end_of_day=True),
                keep_previews=not opts["no_previews"],
                download_direct=not opts["catalog_only"],
                download_torrents=not opts["catalog_only"] and not opts["no_bt"],
                dry_run=opts["dry"],
            )
            # concurrency knobs exist only on newer parse_channel; pass if supported.
            import inspect

            if "http_concurrency" in inspect.signature(parse_channel).parameters:
                kwargs["http_concurrency"] = int(opts["http"])
                kwargs["bt_concurrency"] = int(opts["bt"])
            await parse_channel(client, **kwargs)
            print("Parse task finished.\n")

        self._run_task(coro(), self.parse_btn)

    # ---------- lifecycle ----------
    def _on_close(self) -> None:
        sys.stdout, sys.stderr = self._stdout, self._stderr
        try:
            if self.client is not None:
                self.loop.submit(self.client.disconnect())
        except Exception:
            pass
        self.loop.stop()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


if __name__ == "__main__":
    run_gui()
