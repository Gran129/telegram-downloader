@echo off
REM Build the Windows GUI exe (PyInstaller) and NSIS installer.
REM Run from the repository root on Windows:  packaging\build_windows.cmd [version]
setlocal
cd /d "%~dp0.."

set "VERSION=%~1"
if "%VERSION%"=="" set "VERSION=1.3.1"

echo === Installing build dependencies ===
python -m pip install --upgrade pip || goto :err
python -m pip install -r requirements.txt pyinstaller || goto :err

echo === Building exe with PyInstaller ===
pyinstaller --noconfirm packaging\tgdl.spec || goto :err

echo === Building installer with NSIS ===
set "MAKENSIS=makensis"
where makensis >nul 2>nul || set "MAKENSIS=%PROGRAMFILES(x86)%\NSIS\makensis.exe"
"%MAKENSIS%" /DVERSION=%VERSION% packaging\installer.nsi || goto :err

echo.
echo Done. Installer: TelegramDownloader-Setup-%VERSION%.exe
goto :eof

:err
echo Build failed.
exit /b 1
