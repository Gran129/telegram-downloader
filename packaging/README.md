# 打包与发布 (Windows)

本目录用于把 `tgdl` 打包成带图形界面的 Windows 安装包
`TelegramDownloader-Setup-<版本>.exe`。

> 重要：PyInstaller **不能跨平台编译**。Windows 的 `.exe` 必须在 **Windows** 上构建
> （本地 Windows 机器或 GitHub Actions 的 `windows-latest`）。Linux/macOS 上构建不出可在
> Windows 运行的程序。

## 方式一：GitHub Actions 自动发布到 Releases（推荐）

工作流 `.github/workflows/release.yml` 会在推送 `v*` 标签时，在 Windows runner 上：
PyInstaller 打包 → NSIS 生成安装包 → 上传到 GitHub Release。

```bash
# 合并本 PR 到 main 后：
git tag v1.3.4
git push origin v1.3.4
```

几分钟后到仓库 **Releases** 页面即可下载 `TelegramDownloader-Setup-1.3.4.exe`。
（也可在 Actions 里手动触发 `workflow_dispatch`，产物在该次运行的 Artifacts 中。）

### 让发布版内置 api_id/api_hash(终端用户免填,可选)

在仓库 `Settings → Secrets and variables → Actions` 添加两个 secret:
`TGDL_DEFAULT_API_ID`、`TGDL_DEFAULT_API_HASH`(用你自己在 my.telegram.org 申请的)。
CI 会在打包前生成 `tgdl/_defaults.py`(不入库)把凭据内置进 exe;这样发布出来的程序
终端用户只需登录手机号,连 api_id/api_hash 都不用填。不设置这两个 secret 也能用,
只是用户首次要自己填一次。

## 方式二：在自己的 Windows 上本地构建

需要已安装 Python 3.10+ 和 [NSIS](https://nsis.sourceforge.io/Download)。
在仓库根目录运行：

```bat
packaging\build_windows.cmd 1.3.4
```

产物 `TelegramDownloader-Setup-1.3.4.exe` 会生成在仓库根目录。

## 手动分步（等价）

```bat
pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm packaging\tgdl.spec
makensis /DVERSION=1.3.4 packaging\installer.nsi
```

- `tgdl.spec`：PyInstaller 配置，产出 `dist\TelegramDownloader\TelegramDownloader.exe`（onedir，无控制台窗口，内嵌图标 + `version_info.txt` 版本信息）。
- `installer.nsi`：NSIS 脚本，把上面的目录装进 `Program Files`，创建开始菜单 / 桌面快捷方式和卸载程序。
- 同时会打一个 **便携版** `TelegramDownloader-<版本>-portable-win64.zip`（解压即用，浏览器一般不拦 zip）。

## 减少杀毒误报

未签名的 PyInstaller exe 常被杀软/浏览器误报。本项目已做的缓解：onedir（非 onefile）、关闭 UPX、内嵌 `version_info.txt`（公司/产品/版本元数据）。想彻底消除需**代码签名**（付费 OV/EV 证书，需你自备）。发新版时记得同步更新 `version_info.txt` 里的版本号。

## 不想装，直接从源码跑 GUI

双击仓库根目录的 `start-gui.cmd`（首次会自动建 venv、装依赖、复制 `.env`），
或命令行 `python -m tgdl gui`。
