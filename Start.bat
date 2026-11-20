@echo off
chcp 65001 >nul
cd /d "%~dp0"
python -m gallery_dl --version >nul 2>&1 || python -m pip install --upgrade gallery-dl yt-dlp pillow
python -c "import PIL" >nul 2>&1 || python -m pip install pillow
python -c "import yt_dlp_ejs" >nul 2>&1 || python -m pip install -U "yt-dlp[default]"
python app.py
pause

