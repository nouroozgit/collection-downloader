@echo off
rem Builds dist\CollectionDownloader\CollectionDownloader.exe (needs: pip install pyinstaller)
chcp 65001 >nul
cd /d "%~dp0"
python -m pip install -U pyinstaller gallery-dl "yt-dlp[default]" pillow || exit /b 1
python -m PyInstaller --noconfirm --clean --noconsole --name CollectionDownloader --icon icon.ico ^
  --add-data "index.html;." --collect-all yt_dlp --collect-all gallery_dl --collect-all yt_dlp_ejs ^
  --hidden-import PIL app.py || exit /b 1

rem portable ffmpeg + node (needed for YouTube): copied from this PC if found
if not exist "dist\CollectionDownloader\tools" mkdir "dist\CollectionDownloader\tools"
for /f "delims=" %%F in ('where ffmpeg 2^>nul') do if not exist "dist\CollectionDownloader\tools\ffmpeg.exe" copy "%%F" "dist\CollectionDownloader\tools\ffmpeg.exe" >nul
for /f "delims=" %%F in ('where node 2^>nul') do if not exist "dist\CollectionDownloader\tools\node.exe" copy "%%F" "dist\CollectionDownloader\tools\node.exe" >nul
echo.
echo Done: dist\CollectionDownloader\CollectionDownloader.exe
