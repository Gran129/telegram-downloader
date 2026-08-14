# Telegram 私密频道图片 / 视频下载器

用 Telegram **官方 MTProto API**（Telethon）登录你自己的账号，下载**你已经加入**的频道或群里的图片和视频。

它不能破解没权限的频道，也不能绕过 Telegram 的成员限制。

## 能做什么

- 登录账号（手机号 + 验证码，如有二次验证会再要密码）
- 列出账号里的频道 / 超级群 / 群，并标出是否私密
- 按频道 ID、`@用户名`、`t.me` 链接或私密邀请链接下载
- 只下图片、只下视频，或两种都下
- 按日期范围、数量上限过滤
- 已下载过的文件自动跳过（可断点续下）
- 进度条显示每个文件

## 环境

- Windows 10/11
- Python 3.10 或更高（[python.org](https://www.python.org/downloads/) ，安装时勾选 Add Python to PATH）

## 第一次使用

### 1. 申请 API（只需一次）

1. 打开 [https://my.telegram.org](https://my.telegram.org)
2. 用你的 Telegram 账号登录
3. 进入 **API development tools**
4. 创建一个应用，记下 `api_id` 和 `api_hash`

这两项是 Telegram 发给**你的账号**的开发凭证，不要发给别人。

### 2. 填写配置

双击 `run.cmd`。第一次会复制 `.env.example` 为 `.env` 并打开记事本。填：

```
TELEGRAM_API_ID=12345678
TELEGRAM_API_HASH=你的hash
TELEGRAM_PHONE=+8613800138000
DOWNLOAD_DIR=./downloads
```

手机号建议带国际区号。`TELEGRAM_PHONE` 也可以留空，运行时再输入。

### 3. 登录

```text
run.cmd login
```

Telegram 会把验证码发到 App。输入后会在本目录生成 `tgdl_session.session`。这个文件 = 登录态，**不要上传、不要发给任何人**。

### 4. 列出频道

```text
run.cmd list
```

私密频道没有 `@username`，请复制左侧数字 ID，例如 `-1001234567890`。

### 5. 下载

```text
run.cmd download --channel -1001234567890
run.cmd download --channel @somechannel --type photo
run.cmd download --channel "https://t.me/+xxxxxxxx" --type video --limit 50
run.cmd download --channel -1001234567890 --since 2026-01-01 --until 2026-08-01
```

不带参数双击 `run.cmd` 会进入菜单。

文件保存在：

```text
downloads/频道名/photos/
downloads/频道名/videos/
```

文件名：`日期_消息ID.扩展名`

## 命令一览

| 命令 | 作用 |
|------|------|
| `python -m tgdl` | 交互菜单 |
| `python -m tgdl login` | 登录 |
| `python -m tgdl list` | 列出频道 |
| `python -m tgdl download -c ID` | 下载 Telegram 里的图/视频 |
| `python -m tgdl parse -c ID` | 链接解析机器人：保留链接、预览，并尝试直链下载 |

`download` 常用参数：

- `-c / --channel` 频道 ID、用户名或链接
- `-t / --type` `photo`、`video`、`animation`、`all`（默认 `photo,video`）
- `-n / --limit` 最多保存多少个文件
- `--since` / `--until` 日期 `YYYY-MM-DD`
- `--no-skip` 即使已存在也重新下载
- `--dry-run` 只列出匹配的图片/视频，不下载

## 内置链接解析机器人（parse）

资源群里常见「文字 + 链接 + Telegram 预览图」。`parse` 会：

1. **保留所有链接**（写入 `parsed/links.jsonl` 和 `parsed/links.md`）
2. **保存 Telegram 链接预览**
3. **HTTP 直链**图片/视频 → `parsed/direct/`
4. **磁力链接 / `.torrent` 文件** → `parsed/torrents/`（需 aria2 或 libtorrent）
5. **`t.me` 帖子**：账号能打开则收下媒体
6. **网盘链接**：只写入清单（百度/夸克/阿里云盘等走官方客户端）

BT 引擎优先用本机 `aria2c`，没有则尝试 `pip install libtorrent`。

Windows 安装 aria2：从 https://github.com/aria2/aria2/releases 下载，把 `aria2c.exe` 放到 PATH，或放到 `C:\aria2\aria2c.exe`。

```text
run.cmd parse --channel -1001234567890
run.cmd parse --channel -1001234567890 --dry-run --limit 80
run.cmd parse --channel -1001234567890 --catalog-only
run.cmd parse --channel -1001234567890 --no-bt
```

`--catalog-only`：只存清单，不下直链/BT。  
`--no-bt`：解析磁力/种子但不启动下载。  
`--no-previews`：不保存 Telegram 预览图。

输出目录：

```text
downloads/频道名/photos/
downloads/频道名/videos/
downloads/频道名/parsed/direct/
downloads/频道名/parsed/torrents/
downloads/频道名/parsed/links.md
```

资源群 / 链接预览也会扫到：

- 机器人发出的照片、视频、相册：**会下载**
- 机器人把视频/图片当文件发出（`.mp4` / `.jpg` 等）：**会下载**
- 消息里的链接预览大图 / 预览视频：**会下载**
- 磁力 / `.torrent`：安装 aria2 后 **会下载**
- 网盘分享页：只保存链接

只看会下哪些、先不下：

```text
run.cmd download --channel -1001234567890 --dry-run --limit 30
```

手动安装：

```text
py -3 -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env
.venv\Scripts\python -m tgdl list
```

## 使用限制（请务必遵守）

- 只能下载**当前登录账号已经加入**的对话。
- 请尊重版权和频道规定，下载内容仅供个人备份。
- 不要把 `.env`、`*.session` 提交到 Git 或发给别人。
- 下载太快可能触发 Telegram 限流（Flood wait）。脚本会提示需要等待的秒数，稍后再跑即可；已下过的文件会跳过。
- 这不是破解工具。打不开的私密频道，说明你的账号没有权限。

## 项目结构

```text
telegram-media-downloader/
  run.cmd              Windows 启动
  requirements.txt
  .env.example
  tgdl/
    cli.py             命令行
    client.py          登录
    channels.py        列出对话
    downloader.py      Telegram 媒体
    parser.py          链接解析机器人
    links.py           URL 分类
    http_fetch.py      直链下载
    config.py          读取 .env
```

## 常见问题

**提示 Missing TELEGRAM_API_ID**  
还没填 `.env`，或文件不在项目根目录。

**Cannot access / ChannelPrivateError**  
账号还没加入该频道。先在 Telegram 里加入，再 `list` 复制 ID。

**一直要验证码**  
删掉目录里的 `tgdl_session.session` 后重新 `login`。不要多开好几个脚本同时登录。

**只下到一部分就停了**  
遇到限流。看终端里的秒数，等结束再执行同一条命令（会跳过已有文件）。
