"""Tkinter GUI for tgdl — a login-first, Telegram-client-like front end.

Flow mirrors the official client: log in with your phone (code / 2FA in a
dialog), then your groups/channels are listed automatically; pick one and
download. api_id/api_hash are only needed once (or baked into the build), and
the download folder defaults automatically, so there is nothing else to fill.

The asyncio event loop runs in a background thread; the UI submits coroutines
to it and receives log output through a thread-safe queue.
"""

from __future__ import annotations

import asyncio
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path

from tgdl.channels import list_media_dialogs
from tgdl.client import build_client
from tgdl.config import (
    Settings,
    credentials_available,
    default_download_dir,
    load_settings,
    read_env_values,
    update_env,
)
from tgdl.downloader import download_channel

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


def _icon_path() -> Path | None:
    candidates = []
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", ""))
        candidates.append(base / "tgdl" / "assets" / "app.png")
    candidates.append(Path(__file__).resolve().parent / "assets" / "app.png")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


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
        import tkinter as tk  # noqa: F401
        from tkinter import ttk  # noqa: F401
    except Exception as exc:  # pragma: no cover - platform dependent
        print(
            "Tkinter is not available. On Debian/Ubuntu install it with:\n"
            "  sudo apt-get install -y python3-tk\n"
            f"({exc})"
        )
        raise SystemExit(1)

    _silence_progress_bars()
    _App().run()


class _App:
    def __init__(self) -> None:
        import tkinter as tk
        from tkinter import messagebox, scrolledtext, simpledialog, ttk

        self.tk = tk
        self.ttk = ttk
        self.messagebox = messagebox
        self.simpledialog = simpledialog
        self.scrolledtext = scrolledtext

        self.loop = AsyncLoop()
        self.client = None
        self.settings: Settings | None = None
        self.log_queue: "queue.Queue[str]" = queue.Queue()

        self.root = tk.Tk()
        self.root.title("Telegram 下载器")
        self.root.geometry("820x680")
        self.root.minsize(720, 560)
        self._app_icon = None
        try:
            icon = _icon_path()
            if icon is not None:
                self._app_icon = tk.PhotoImage(file=str(icon))
                self.root.iconphoto(True, self._app_icon)
        except Exception:
            pass

        env = read_env_values()
        self.creds_available = credentials_available()
        self.api_id_var = tk.StringVar(value=env["api_id"])
        self.api_hash_var = tk.StringVar(value=env["api_hash"])
        self.phone_var = tk.StringVar(value=env["phone"])
        self.download_dir_var = tk.StringVar(value=env["download_dir"] or str(default_download_dir()))
        self.status_var = tk.StringVar(value="未登录")
        self.manual_var = tk.StringVar()

        self.type_photo = tk.BooleanVar(value=True)
        self.type_video = tk.BooleanVar(value=True)
        self.type_anim = tk.BooleanVar(value=False)
        self.dl_limit = tk.StringVar()

        self.p_no_previews = tk.BooleanVar(value=False)
        self.p_catalog_only = tk.BooleanVar(value=False)
        self.p_no_bt = tk.BooleanVar(value=False)
        self.p_dry = tk.BooleanVar(value=False)
        self.p_limit = tk.StringVar()

        self._build_ui()

        self._stdout, self._stderr = sys.stdout, sys.stderr
        writer = _QueueWriter(self.log_queue)
        sys.stdout = writer
        sys.stderr = writer

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(100, self._drain_log)

    # ---------- UI ----------
    def _build_ui(self) -> None:
        tk, ttk = self.tk, self.ttk
        pad = {"padx": 6, "pady": 4}

        # First-run credentials (only when the app has none yet).
        if not self.creds_available:
            setup = ttk.LabelFrame(self.root, text="首次设置(仅一次):Telegram API")
            setup.pack(fill="x", **pad)
            msg = (
                "打开 https://my.telegram.org → API development tools,创建应用,"
                "把 api_id 和 api_hash 填到这里(只需一次,之后会记住)。"
            )
            ttk.Label(setup, text=msg, wraplength=760, foreground="#555").grid(
                row=0, column=0, columnspan=4, sticky="w", **pad
            )
            ttk.Label(setup, text="api_id").grid(row=1, column=0, sticky="w", **pad)
            ttk.Entry(setup, textvariable=self.api_id_var, width=18).grid(row=1, column=1, sticky="w", **pad)
            ttk.Label(setup, text="api_hash").grid(row=1, column=2, sticky="w", **pad)
            ttk.Entry(setup, textvariable=self.api_hash_var, width=40).grid(row=1, column=3, sticky="w", **pad)
            ttk.Button(setup, text="保存", command=self.on_save_creds).grid(row=1, column=4, **pad)
            self._setup_frame = setup

        # Login row (phone → code, like the official client).
        login = ttk.LabelFrame(self.root, text="登录")
        login.pack(fill="x", **pad)
        ttk.Label(login, text="手机号(带国际区号,可留空登录时再输)").grid(
            row=0, column=0, sticky="w", **pad
        )
        ttk.Entry(login, textvariable=self.phone_var, width=22).grid(row=0, column=1, sticky="w", **pad)
        self.login_btn = ttk.Button(login, text="登录 Telegram", command=self.on_login)
        self.login_btn.grid(row=0, column=2, **pad)
        ttk.Button(login, text="设置", command=self._open_settings).grid(row=0, column=3, **pad)
        ttk.Label(login, text="状态:").grid(row=0, column=4, sticky="e", **pad)
        ttk.Label(login, textvariable=self.status_var, foreground="#0a6").grid(row=0, column=5, sticky="w", **pad)

        # Your chats.
        chats = ttk.LabelFrame(self.root, text="我的群组 / 频道(登录后自动加载)")
        chats.pack(fill="both", expand=True, **pad)
        cols = ("id", "kind", "name")
        self.tree = ttk.Treeview(chats, columns=cols, show="headings", height=9, selectmode="browse")
        self.tree.heading("id", text="ID")
        self.tree.heading("kind", text="类型")
        self.tree.heading("name", text="名称")
        self.tree.column("id", width=140, anchor="w")
        self.tree.column("kind", width=100, anchor="w")
        self.tree.column("name", width=460, anchor="w")
        self.tree.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=6)
        sb = ttk.Scrollbar(chats, orient="vertical", command=self.tree.yview)
        sb.pack(side="left", fill="y", pady=6)
        self.tree.configure(yscrollcommand=sb.set)

        side = ttk.Frame(chats)
        side.pack(side="left", fill="y", padx=6, pady=6)
        self.refresh_btn = ttk.Button(side, text="刷新列表", command=self.on_list)
        self.refresh_btn.pack(fill="x", pady=2)
        ttk.Label(side, text="或手动输入\nID/@用户名/邀请链接", foreground="#555").pack(anchor="w", pady=(8, 0))
        ttk.Entry(side, textvariable=self.manual_var, width=22).pack(fill="x", pady=2)

        # Download / advanced tabs.
        nb = ttk.Notebook(self.root)
        nb.pack(fill="x", **pad)
        nb.add(self._build_download_tab(), text="下载")
        nb.add(self._build_parse_tab(), text="解析链接(高级)")

        # Download folder row.
        folder = ttk.Frame(self.root)
        folder.pack(fill="x", **pad)
        ttk.Label(folder, text="下载到:").pack(side="left")
        ttk.Label(folder, textvariable=self.download_dir_var, foreground="#333").pack(side="left", padx=6)
        ttk.Button(folder, text="更改", command=self._change_dir).pack(side="left")
        ttk.Button(folder, text="打开下载文件夹", command=self._open_folder).pack(side="left", padx=6)

        logframe = ttk.LabelFrame(self.root, text="日志")
        logframe.pack(fill="both", expand=True, **pad)
        self.log = self.scrolledtext.ScrolledText(logframe, height=8, wrap="word", state="disabled")
        self.log.pack(fill="both", expand=True, padx=4, pady=4)

    def _build_download_tab(self):
        ttk = self.ttk
        pad = {"padx": 6, "pady": 4}
        frame = ttk.Frame(self.root)
        types = ttk.Frame(frame)
        types.grid(row=0, column=0, columnspan=4, sticky="w", **pad)
        ttk.Label(types, text="下载类型:").pack(side="left")
        ttk.Checkbutton(types, text="图片", variable=self.type_photo).pack(side="left")
        ttk.Checkbutton(types, text="视频", variable=self.type_video).pack(side="left")
        ttk.Checkbutton(types, text="GIF", variable=self.type_anim).pack(side="left")
        ttk.Label(frame, text="数量上限(可空)").grid(row=1, column=0, sticky="w", **pad)
        ttk.Entry(frame, textvariable=self.dl_limit, width=10).grid(row=1, column=1, sticky="w", **pad)
        self.download_btn = ttk.Button(frame, text="下载所选", command=self.on_download)
        self.download_btn.grid(row=1, column=3, sticky="e", **pad)
        frame.columnconfigure(2, weight=1)
        return frame

    def _build_parse_tab(self):
        ttk = self.ttk
        pad = {"padx": 6, "pady": 4}
        frame = ttk.Frame(self.root)
        ttk.Label(frame, text="扫描消息里的链接:保留链接、下预览、直链、磁力/种子", foreground="#555").grid(
            row=0, column=0, columnspan=4, sticky="w", **pad
        )
        ttk.Label(frame, text="数量上限(可空)").grid(row=1, column=0, sticky="w", **pad)
        ttk.Entry(frame, textvariable=self.p_limit, width=10).grid(row=1, column=1, sticky="w", **pad)
        ttk.Checkbutton(frame, text="不下预览", variable=self.p_no_previews).grid(row=2, column=0, sticky="w", **pad)
        ttk.Checkbutton(frame, text="只存清单", variable=self.p_catalog_only).grid(row=2, column=1, sticky="w", **pad)
        ttk.Checkbutton(frame, text="不下磁力/种子", variable=self.p_no_bt).grid(row=2, column=2, sticky="w", **pad)
        ttk.Checkbutton(frame, text="试运行", variable=self.p_dry).grid(row=2, column=3, sticky="w", **pad)
        self.parse_btn = ttk.Button(frame, text="解析所选", command=self.on_parse)
        self.parse_btn.grid(row=3, column=3, sticky="e", **pad)
        frame.columnconfigure(2, weight=1)
        return frame

    # ---------- helpers ----------
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

    def _current_download_dir(self) -> Path:
        raw = self.download_dir_var.get().strip()
        return Path(raw).expanduser() if raw else default_download_dir()

    def _selected_target(self) -> str | None:
        sel = self.tree.selection()
        if sel:
            values = self.tree.item(sel[0], "values")
            if values:
                return str(values[0])
        manual = self.manual_var.get().strip()
        return manual or None

    def _ask(self, prompt: str, secret: bool = False) -> str:
        answer: dict[str, str | None] = {}
        done = threading.Event()

        def ask_on_ui() -> None:
            show = "*" if secret else ""
            answer["value"] = self.simpledialog.askstring("Telegram", prompt, show=show, parent=self.root)
            done.set()

        self.root.after(0, ask_on_ui)
        done.wait()
        value = answer.get("value")
        if value is None:
            raise RuntimeError("已取消")
        return value.strip()

    def _run_task(self, coro, button) -> None:
        if button is not None:
            button.config(state="disabled")
        future = self.loop.submit(coro)

        def finished(fut) -> None:
            try:
                fut.result()
            except Exception as exc:  # noqa: BLE001
                self._log(f"\n[错误] {exc}\n")
            finally:
                if button is not None:
                    self.root.after(0, lambda: button.config(state="normal"))

        future.add_done_callback(finished)

    def _save_dir_only(self) -> None:
        values = read_env_values()
        values["download_dir"] = self.download_dir_var.get().strip() or str(default_download_dir())
        update_env(values)

    # ---------- client ----------
    async def _ensure_client(self):
        if self.client is not None:
            return self.client
        settings = load_settings()
        self.settings = settings
        await self.client_start(settings)
        me = await self.client.get_me()
        if me is None:
            raise RuntimeError("登录失败")
        name = " ".join(p for p in (me.first_name, me.last_name) if p)
        handle = f"@{me.username}" if me.username else ""
        print(f"已登录:{name} {handle} (id={me.id})".strip())
        self._set_status(f"已登录:{name} {handle}".strip())
        return self.client

    async def client_start(self, settings) -> None:
        self.client = build_client(settings)
        await self.client.start(
            phone=lambda: settings.phone or self._ask("手机号(带国际区号,如 +8613800138000):"),
            code_callback=lambda: self._ask("Telegram 发来的验证码:"),
            password=lambda: self._ask("两步验证密码:", secret=True),
        )

    # ---------- handlers ----------
    def on_save_creds(self) -> None:
        if not self.api_id_var.get().strip() or not self.api_hash_var.get().strip():
            self.messagebox.showwarning("缺少信息", "请先填写 api_id 和 api_hash。")
            return
        update_env(
            {
                "api_id": self.api_id_var.get().strip(),
                "api_hash": self.api_hash_var.get().strip(),
                "phone": self.phone_var.get().strip(),
                "download_dir": self.download_dir_var.get().strip() or str(default_download_dir()),
            }
        )
        self.creds_available = True
        if getattr(self, "_setup_frame", None) is not None:
            self._setup_frame.destroy()
            self._setup_frame = None
        self._log("已保存凭据。现在点『登录 Telegram』。\n")

    def on_login(self) -> None:
        if not credentials_available() and not (
            self.api_id_var.get().strip() and self.api_hash_var.get().strip()
        ):
            self.messagebox.showwarning("缺少信息", "请先在『首次设置』里填写 api_id / api_hash 并保存。")
            return
        # persist phone/dir so they are remembered
        update_env(
            {
                "api_id": self.api_id_var.get().strip(),
                "api_hash": self.api_hash_var.get().strip(),
                "phone": self.phone_var.get().strip(),
                "download_dir": self.download_dir_var.get().strip() or str(default_download_dir()),
            }
        )
        self._log("正在登录…(首次会向你的 Telegram 发送验证码)\n")

        async def coro():
            await self._ensure_client()
            await self._load_dialogs()

        self._run_task(coro(), self.login_btn)

    def on_list(self) -> None:
        async def coro():
            await self._ensure_client()
            await self._load_dialogs()

        self._run_task(coro(), self.refresh_btn)

    async def _load_dialogs(self) -> None:
        items = await list_media_dialogs(self.client)
        rows = [(str(it.entity_id), it.kind, it.title) for it in items]

        def apply():
            self.tree.delete(*self.tree.get_children())
            for row in rows:
                self.tree.insert("", "end", values=row)

        self.root.after(0, apply)
        print(f"已加载 {len(rows)} 个群组/频道。点选一个,然后『下载所选』。")

    def _types_string(self) -> str:
        return ",".join(
            name
            for name, var in (
                ("photo", self.type_photo),
                ("video", self.type_video),
                ("animation", self.type_anim),
            )
            if var.get()
        )

    def on_download(self) -> None:
        target = self._selected_target()
        if not target:
            self.messagebox.showwarning("未选择", "请先在列表里选一个群组/频道,或手动输入。")
            return
        types_raw = self._types_string()
        if not types_raw:
            self.messagebox.showwarning("未选择", "至少选择一种下载类型。")
            return
        limit = self.dl_limit.get().strip()

        async def coro():
            await self._ensure_client()
            await download_channel(
                self.client,
                target=target,
                download_dir=self.settings.download_dir,
                types=parse_types(types_raw),
                limit=int(limit) if limit else None,
                since=None,
                until=None,
                skip_existing=True,
                dry_run=False,
            )
            print("下载完成。点『打开下载文件夹』查看。\n")

        self._run_task(coro(), self.download_btn)

    def on_parse(self) -> None:
        target = self._selected_target()
        if not target:
            self.messagebox.showwarning("未选择", "请先在列表里选一个群组/频道,或手动输入。")
            return
        limit = self.p_limit.get().strip()
        opts = {
            "no_previews": self.p_no_previews.get(),
            "catalog_only": self.p_catalog_only.get(),
            "no_bt": self.p_no_bt.get(),
            "dry": self.p_dry.get(),
        }

        async def coro():
            await self._ensure_client()
            kwargs = dict(
                target=target,
                download_dir=self.settings.download_dir,
                limit=int(limit) if limit else None,
                since=None,
                until=None,
                keep_previews=not opts["no_previews"],
                download_direct=not opts["catalog_only"],
                download_torrents=not opts["catalog_only"] and not opts["no_bt"],
                dry_run=opts["dry"],
            )
            await parse_channel(self.client, **kwargs)
            print("解析完成。\n")

        self._run_task(coro(), self.parse_btn)

    def _change_dir(self) -> None:
        from tkinter import filedialog

        chosen = filedialog.askdirectory()
        if chosen:
            self.download_dir_var.set(chosen)
            self._save_dir_only()
            if self.settings is not None:
                self.settings = Settings(
                    api_id=self.settings.api_id,
                    api_hash=self.settings.api_hash,
                    phone=self.settings.phone,
                    download_dir=Path(chosen),
                )

    def _open_folder(self) -> None:
        folder = self._current_download_dir()
        folder.mkdir(parents=True, exist_ok=True)
        try:
            if sys.platform.startswith("win"):
                os.startfile(str(folder))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except Exception as exc:  # noqa: BLE001
            self._log(f"[错误] 打不开文件夹:{exc}\n")

    def _open_settings(self) -> None:
        tk, ttk = self.tk, self.ttk
        win = tk.Toplevel(self.root)
        win.title("设置")
        win.transient(self.root)
        pad = {"padx": 8, "pady": 6}
        ttk.Label(win, text="api_id").grid(row=0, column=0, sticky="w", **pad)
        ttk.Entry(win, textvariable=self.api_id_var, width=20).grid(row=0, column=1, **pad)
        ttk.Label(win, text="api_hash").grid(row=1, column=0, sticky="w", **pad)
        ttk.Entry(win, textvariable=self.api_hash_var, width=42).grid(row=1, column=1, **pad)
        ttk.Label(win, text="下载目录").grid(row=2, column=0, sticky="w", **pad)
        ttk.Entry(win, textvariable=self.download_dir_var, width=42).grid(row=2, column=1, **pad)

        def save_and_close():
            self.on_save_creds()
            win.destroy()

        ttk.Button(win, text="保存", command=save_and_close).grid(row=3, column=1, sticky="e", **pad)

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
