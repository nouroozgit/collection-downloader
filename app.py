"""Collection Downloader — دانلود همه‌ی پست‌های بورد پینترست / کالکشن اینستاگرام.

یک رابط وب محلی (فقط روی همین کامپیوتر) که gallery-dl را اجرا می‌کند.
اجرا:  python app.py   →  http://127.0.0.1:8765
"""
import hashlib
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

FROZEN = bool(getattr(sys, "frozen", False))                       # running as the PyInstaller exe
HERE = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parent   # user data lives here
RES = Path(getattr(sys, "_MEIPASS", HERE))                          # bundled read-only files (index.html)
SETTINGS_FILE = HERE / "settings.json"
SOURCES_FILE = HERE / "sources.json"
COOKIES_FILE = HERE / "cookies.txt"
CONFIG_FILE = HERE / "gallery-dl.conf.json"
THUMB_DIR = HERE / ".thumbs"
PORT = int(os.environ.get("CD_PORT", "8765"))

DEFAULT_SETTINGS = {
    "out_dir": str(Path.home() / "Downloads" / "Collections"),
    "browser": "",              # "", firefox, chrome, edge, ...
    "cookies_file": "",         # path to cookies.txt (Netscape format)
    "proxy": "",                # e.g. http://127.0.0.1:10809
    "videos": True,
    "save_captions": True,      # write <file>.txt next to every file (caption + link)
    "collection_folders": True, # Instagram collections → instagram/collections/<name>/
    "profile_all": False,       # Instagram profile → posts + reels + stories + highlights
    "yt_quality": "1080",       # best | 1080 | 720 | 480 | audio (mp3)
    "yt_playlist": False,       # a video link that belongs to a playlist → download the whole playlist
}
YT_QUALITIES = {"best", "1080", "720", "480", "audio"}
YT_COOKIES_FILE = HERE / "cookies-youtube.txt"

IMG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
VID_EXT = {".mp4", ".webm", ".mov", ".m4v", ".mkv"}
AUD_EXT = {".mp3", ".m4a", ".opus", ".ogg", ".wav", ".flac"}

JOBS = {}
STATE_LOCK = threading.Lock()   # guards settings/sources files and the scan cache
SCAN_CACHE = {"root": None, "time": 0.0, "files": []}
SERVER = None


# ───────────────────────── settings & sources ─────────────────────────

def load_settings():
    s = dict(DEFAULT_SETTINGS)
    try:
        s.update(json.loads(SETTINGS_FILE.read_text(encoding="utf-8")))
    except Exception:
        pass
    return s


def save_settings(s):
    SETTINGS_FILE.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")


def out_root(s=None):
    return Path((s or load_settings())["out_dir"]).expanduser()


def load_sources():
    try:
        data = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_sources(items):
    SOURCES_FILE.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def norm_url(u):
    return u.strip().rstrip("/").lower()


def guess_name(url):
    """A readable default name for a saved source."""
    try:
        p = urlparse(url)
        parts = [unquote(x) for x in p.path.split("/") if x]
        host = p.netloc.lower()
        if "youtube" in host or "youtu.be" in host:
            if parts and parts[0] == "playlist":
                return "یوتیوب · پلی‌لیست " + (parse_qs(p.query).get("list", [""])[0][-8:])
            return "یوتیوب · " + (parts[0] if parts else host)
        if "instagram" in host:
            if "saved" in parts:
                i = parts.index("saved")
                tail = parts[i + 1:]
                return "اینستاگرام ذخیره‌شده‌ها" + (f" · {tail[0]}" if tail and tail[0] != "all-posts" else "")
            return "اینستاگرام · " + (parts[0] if parts else host)
        if "pin.it" in host:
            return "پین " + (parts[0] if parts else "")
        return "پینترست · " + " / ".join(parts[:2]) if parts else host
    except Exception:
        return url[:40]


# ───────────────────────── cookies (Instagram login) ─────────────────────────

def yt_cookies_status():
    if not YT_COOKIES_FILE.exists():
        return {"exists": False}
    try:
        found = parse_cookies(YT_COOKIES_FILE.read_text(encoding="utf-8", errors="replace"),
                              ("youtube.com", "google.com"))
    except Exception:
        return {"exists": True, "logged_in": False}
    exp = max([found.get(n, 0) for n in ("__Secure-3PSID", "SID", "LOGIN_INFO") if n in found] or [0])
    logged = any(n in found for n in ("SID", "__Secure-3PSID", "LOGIN_INFO"))
    return {"exists": True, "logged_in": logged, "expires": exp, "expired": bool(exp) and exp < time.time()}


def parse_cookies(text, domains=("instagram.com",)):
    """Return {name: expiry} for cookies of the given domains in a Netscape cookies.txt. Never returns values."""
    found = {}
    for line in text.splitlines():
        if line.startswith("#HttpOnly_"):
            line = line[len("#HttpOnly_"):]
        elif line.startswith("#") or not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) >= 7 and any(d in parts[0] for d in domains):
            try:
                found[parts[5]] = int(float(parts[4]))
            except ValueError:
                found[parts[5]] = 0
    return found


def cookies_status():
    if not COOKIES_FILE.exists():
        return {"exists": False}
    try:
        found = parse_cookies(COOKIES_FILE.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return {"exists": True, "logged_in": False}
    exp = found.get("sessionid")
    return {"exists": True, "logged_in": exp is not None,
            "expires": exp or 0,                      # 0 → session cookie
            "expired": bool(exp) and exp < time.time()}


# ───────────────────────── gallery-dl command ─────────────────────────

def python_exe():
    exe = Path(sys.executable)
    if exe.name.lower() == "pythonw.exe":
        cand = exe.with_name("python.exe")
        if cand.exists():
            return str(cand)
    return str(exe)


def tool_cmd(module):
    """Command prefix that runs gallery_dl / yt_dlp: `python -m X`, or the exe itself in --tool mode when frozen."""
    if FROZEN:
        return [sys.executable, "--tool", module]
    return [python_exe(), "-m", module]


def run_tool_and_exit(module, args):
    """Entry point of `app.exe --tool gallery_dl|yt_dlp ...` (the frozen exe has no separate python)."""
    for stream in ("stdout", "stderr"):                 # a windowed exe may start without usable std streams
        if getattr(sys, stream) is None:
            try:
                setattr(sys, stream, open(1 if stream == "stdout" else 2, "w", encoding="utf-8", closefd=False))
            except OSError:
                setattr(sys, stream, open(os.devnull, "w"))
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if module == "gallery_dl":
        import gallery_dl
        sys.argv = ["gallery-dl"] + args
        gallery_dl.main()
    else:
        import yt_dlp
        yt_dlp.main(args)
    sys.exit(0)


def find_ffmpeg():
    """ffmpeg is needed to merge YouTube video+audio. PATH may be stale in apps started from the desktop."""
    bundled = HERE / "tools" / "ffmpeg.exe"
    if bundled.exists():
        return str(bundled)
    found = shutil.which("ffmpeg")
    if found:
        return found
    base = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
    for hit in base.glob("Gyan.FFmpeg*/**/bin/ffmpeg.exe"):
        return str(hit)
    return None


def find_node():
    """yt-dlp needs a JavaScript runtime to solve YouTube's challenges (Node works; Deno is its default)."""
    bundled = HERE / "tools" / "node.exe"
    if bundled.exists():
        return str(bundled)
    if shutil.which("deno"):
        return None                     # yt-dlp's default
    found = shutil.which("node")
    if found:
        return found
    for cand in (r"C:\Program Files\nodejs\node.exe", r"C:\Program Files (x86)\nodejs\node.exe"):
        if os.path.exists(cand):
            return cand
    return None


def is_youtube(url):
    u = url.lower()
    return bool(re.search(r"https?://([a-z0-9-]+\.)?(youtube\.com|youtu\.be|youtube-nocookie\.com)/", u))


def detect_site(url):
    u = url.lower()
    if is_youtube(u):
        return "youtube"
    if "pinterest." in u or "pin.it/" in u:
        return "pinterest"
    if "instagram.com" in u:
        return "instagram"
    return "other"


def build_config(s):
    """gallery-dl config: caption sidecar files, collection folders, profile contents."""
    cfg = {"extractor": {"instagram": {}, "pinterest": {}}}
    ig, pin = cfg["extractor"]["instagram"], cfg["extractor"]["pinterest"]
    if s.get("save_captions", True):
        ig["postprocessors"] = [{
            "name": "metadata", "event": "file", "mode": "custom", "extension": "txt",
            "format": "@{username}\n\n{description|''}\n\n{post_url|''}"}]
        pin["postprocessors"] = [{
            "name": "metadata", "event": "file", "mode": "custom", "extension": "txt",
            "format": "{description|title|grid_title|''}\n\n{link|''}\nhttps://www.pinterest.com/pin/{id}/"}]
    if s.get("collection_folders", True):
        ig["collection"] = {"directory": ["{category}", "collections", "{collection_name}"]}
    if s.get("profile_all"):
        ig["include"] = "posts,reels,stories,highlights"
    return cfg


def build_yt_command(url, s):
    """yt-dlp command: single video, playlist or channel; files go to youtube/<playlist or channel>/."""
    out = out_root(s)
    q = s.get("yt_quality") if s.get("yt_quality") in YT_QUALITIES else "1080"
    ffmpeg = find_ffmpeg()
    cmd = tool_cmd("yt_dlp") + ["--no-quiet", "--newline", "--no-colors",
           "--print", "before_dl:▶ %(title)s", "--print", "after_move:filepath",
           "--windows-filenames", "--ignore-errors",
           "--sleep-interval", "1", "--max-sleep-interval", "4",
           # separate archives so the same video can be saved once as video and once as mp3
           "--download-archive", str(out / (".yt-archive-audio.txt" if q == "audio" else ".yt-archive.txt"))]
    node = find_node()
    if node:
        cmd += ["--js-runtimes", f"node:{node}"]
    if ffmpeg:
        cmd += ["--ffmpeg-location", ffmpeg]
    if q == "audio":
        cmd += ["-f", "ba/b"]
        if ffmpeg:
            cmd += ["-x", "--audio-format", "mp3", "--audio-quality", "0"]
    else:
        cap = "" if q == "best" else f"[height<={q}]"
        # h264 + AAC among equal resolutions: plays everywhere and edits well
        cmd += ["-S", "res,vcodec:h264,acodec:m4a"]
        cmd += ["-f", f"bv*{cap}+ba/b{cap}" if ffmpeg else f"b{cap}/b"]
        if ffmpeg:
            cmd += ["--merge-output-format", "mp4"]
    if s.get("save_captions", True):
        cmd += ["--write-description"]
    if "list=" in url and "/playlist" not in url.lower() and not s.get("yt_playlist"):
        cmd += ["--no-playlist"]
    if YT_COOKIES_FILE.exists():
        cmd += ["--cookies", str(YT_COOKIES_FILE)]
    if s.get("proxy"):
        cmd += ["--proxy", s["proxy"]]
    template = str(out / "youtube").replace("%", "%%") + \
        "/%(playlist_title,uploader).80B/%(playlist_index&{} - |)s%(title).150B [%(id)s].%(ext)s"
    cmd += ["-o", template, url]
    return cmd


def build_command(url, s):
    site = detect_site(url)
    out = out_root(s)
    if site == "youtube":
        return build_yt_command(url, s), site
    CONFIG_FILE.write_text(json.dumps(build_config(s), ensure_ascii=False, indent=2), encoding="utf-8")
    cmd = tool_cmd("gallery_dl") + ["-c", str(CONFIG_FILE), "--destination", str(out),
           "--download-archive", str(out / ".archive.sqlite3"),
           "-o", "output.progress=false"]
    if s.get("proxy"):
        cmd += ["--proxy", s["proxy"]]
    if s.get("cookies_file"):
        cmd += ["--cookies", s["cookies_file"]]
    elif COOKIES_FILE.exists():
        cmd += ["--cookies", str(COOKIES_FILE)]
    elif s.get("browser"):
        cmd += ["--cookies-from-browser", s["browser"]]
    if not s.get("videos", True):
        cmd += ["-o", "videos=false"]
    if site == "instagram":
        # چند ثانیه مکث بین درخواست‌ها تا اینستاگرام حساب را محدود نکند
        cmd += ["--sleep-request", "2-5"]
    elif site == "pinterest":
        cmd += ["--sleep-request", "0.5-1.5"]
    cmd.append(url)
    return cmd, site


# ───────────────────────── download jobs ─────────────────────────

def run_job(job_id, urls, s):
    """Download each link in turn; one bad link doesn't stop the rest."""
    job = JOBS[job_id]
    failed = 0
    for i, url in enumerate(urls, 1):
        if job["state"] == "cancelled":
            return
        job["current"] = i
        if len(urls) > 1:
            job["log"].append(f"── لینک {i} از {len(urls)}: {url}")
        before = job["count"]
        rc = run_one(job, url, s)
        if rc != 0:
            failed += 1
        mark_source_run(url, job["count"] - before, rc == 0 and job["state"] != "cancelled")
    SCAN_CACHE["time"] = 0.0            # gallery should see the new files
    if job["state"] == "cancelled":
        return
    job["failed"] = failed
    job["state"] = "done" if failed == 0 else "error"


def mark_source_run(url, new_files, ok):
    with STATE_LOCK:
        items = load_sources()
        key = norm_url(url)
        changed = False
        for it in items:
            if norm_url(it["url"]) == key:
                it.update(last_run=int(time.time()), last_new=new_files, last_ok=bool(ok))
                changed = True
        if changed:
            save_sources(items)


def run_one(job, url, s):
    cmd, site = build_command(url, s)
    job["site"] = site
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", errors="replace", env=env,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception as e:  # noqa: BLE001
        job["log"].append(f"[خطا] {e}")
        return 1
    job["proc"] = proc
    for line in proc.stdout:
        line = line.rstrip()
        if not line:
            continue
        is_file = False
        if site == "youtube":
            m = re.match(r"^\[download\]\s+([\d.]+)%(?:\s+of\s+~?\s*(\S+))?(?:\s+at\s+(\S+))?(?:\s+ETA\s+(\S+))?", line)
            if m:                               # live progress → progress bar, not log spam
                job["progress"] = {"pct": float(m.group(1)), "size": m.group(2) or "",
                                   "speed": m.group(3) or "", "eta": m.group(4) or ""}
                continue
            if "has already been recorded in the archive" in line:
                job["skipped"] += 1
                line = "تکراری (قبلاً دانلود شده): " + line.split("]", 1)[-1].strip()
            elif re.match(r"^(\[youtube[^\]]*\]|\[info\]|\[jsc|\[Merger\]|\[ExtractAudio\]|\[FixupM4a\]|"
                          r"\[download\] (Sleeping|Destination)|Deleting original file)", line):
                continue                        # internal steps: keep the log readable
        if line.startswith("# "):           # already in archive → skipped
            job["skipped"] += 1
            line = "تکراری (قبلاً دانلود شده): " + line[2:]
        elif re.match(r"^[A-Za-z]:\\|^/", line):  # a saved file path
            job["count"] += 1
            job["last_file"] = line
            is_file = True
        job["log"].append(line)
        low = line.lower()
        hint = None
        if is_file or line.startswith("تکراری"):
            pass  # never treat a saved path / skipped file as an error message
        elif "failed to decrypt" in low or "'nonetype' object has no attribute 'decode'" in low:
            hint = ("[راهنما] کروم/اج جدید کوکی‌ها را قفل می‌کنند و برنامه نمی‌تواند ورود شما را بخواند. "
                    "با افزونه‌ی «Get cookies.txt LOCALLY» از صفحه‌ی instagram.com خروجی بگیرید و "
                    "در بخش «ورود اینستاگرام» همین صفحه آپلود کنید.")
        elif "login required" in low or "redirect to login" in low or "/accounts/login" in low:
            hint = "[راهنما] اینستاگرام ورود به حساب می‌خواهد — فایل cookies.txt را در بخش «ورود اینستاگرام» آپلود کنید (شاید منقضی شده)."
        elif "requested pin could not be found" in low and "/pin/e1_" in url.lower():
            hint = ("[راهنما] این لینک پین شناسه‌ی جدید e1_ دارد که بدون ورود قابل دانلود نیست. "
                    "لینک را در حالتی که وارد پینترست شده‌اید کپی کنید (یا از دکمه‌ی Share لینک pin.it بگیرید).")
        elif re.search(r"\b429\b|too many requests|please wait a few minutes", low):
            hint = ("[راهنما] یوتیوب موقتاً محدود کرده؛ کمی بعد دوباره امتحان کنید." if site == "youtube"
                    else "[راهنما] اینستاگرام موقتاً محدود کرده؛ چند ساعت بعد دوباره امتحان کنید.")
        elif site == "youtube" and re.search(r"not a bot|sign in to confirm|confirm you.re not", low):
            hint = ("[راهنما] یوتیوب ورود به حساب می‌خواهد. در تنظیمات بخش «ورود یوتیوب» فایل cookies.txt "
                    "یوتیوب را آپلود کنید (روش مثل اینستاگرام است، ولی وقتی در youtube.com وارد هستید).")
        elif site == "youtube" and re.search(r"video unavailable|this video is unavailable|private video|not available in your country|blocked it", low):
            hint = "[راهنما] این ویدیو در دسترس نیست (خصوصی، حذف‌شده یا محدود به کشور/سن). اگر محدودیت سنی است، ورود یوتیوب لازم است."
        elif site == "youtube" and "unable to download" in low and ("timed out" in low or "getaddrinfo" in low or "connection" in low):
            hint = "[راهنما] اتصال به یوتیوب برقرار نشد. VPN را بررسی کنید یا در تنظیمات پیشرفته پروکسی بدهید."
        elif site == "youtube" and "ffmpeg" in low and ("not found" in low or "not installed" in low):
            hint = "[راهنما] ffmpeg پیدا نشد؛ برای کیفیت‌های بالا و mp3 لازم است."
        if hint and hint not in job["log"]:
            job["log"].append(hint)
        if len(job["log"]) > 2000:
            job["log"] = job["log"][-1500:]
    proc.wait()
    job["progress"] = None
    return proc.returncode


# ───────────────────────── gallery ─────────────────────────

def scan_files(root):
    """All media files under root, newest first. Cached for a few seconds."""
    now = time.time()
    with STATE_LOCK:
        if SCAN_CACHE["root"] == str(root) and now - SCAN_CACHE["time"] < 8:
            return SCAN_CACHE["files"]
    files = []
    if root.exists():
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for fn in filenames:
                ext = os.path.splitext(fn)[1].lower()
                if ext in IMG_EXT or ext in VID_EXT or ext in AUD_EXT:
                    full = os.path.join(dirpath, fn)
                    try:
                        st = os.stat(full)
                    except OSError:
                        continue
                    files.append((full, st.st_mtime, st.st_size))
    files.sort(key=lambda x: x[1], reverse=True)
    with STATE_LOCK:
        SCAN_CACHE.update(root=str(root), time=now, files=files)
    return files


def read_caption(full, limit=2000):
    # Instagram/Pinterest: <file>.mp4.txt   ·   YouTube: <file>.description
    for side in (full + ".txt", os.path.splitext(full)[0] + ".description"):
        try:
            with open(side, encoding="utf-8", errors="replace") as f:
                return f.read(limit).strip()
        except OSError:
            continue
    return ""


def gallery_page(offset, limit, q):
    root = out_root()
    files = scan_files(root)
    q = (q or "").strip().lower()
    if q:
        files = [f for f in files if q in f[0].lower() or q in read_caption(f[0]).lower()]
    page = []
    for full, mtime, size in files[offset:offset + limit]:
        rel = os.path.relpath(full, root).replace("\\", "/")
        ext = os.path.splitext(full)[1].lower()
        page.append({"p": rel, "kind": "video" if ext in VID_EXT else "audio" if ext in AUD_EXT else "image",
                     "mtime": int(mtime), "size": size,
                     "folder": os.path.dirname(rel), "caption": read_caption(full)})
    return {"total": len(files), "items": page}


def safe_path(rel):
    """Resolve a relative path from the browser; must stay inside the output folder."""
    root = out_root().resolve()
    p = (root / rel).resolve()
    try:
        p.relative_to(root)
    except ValueError:
        return None
    return p if p.is_file() else None


def make_thumb(p):
    try:
        from PIL import Image
    except ImportError:
        return None
    key = hashlib.sha1(f"{p}|{p.stat().st_mtime_ns}".encode("utf-8", "replace")).hexdigest()
    dest = THUMB_DIR / f"{key}.jpg"
    if dest.exists():
        return dest
    try:
        THUMB_DIR.mkdir(exist_ok=True)
        with Image.open(p) as im:
            im.seek(0)
            im = im.convert("RGB")
            im.thumbnail((480, 480))
            im.save(dest, "JPEG", quality=80)
        return dest
    except Exception:
        return None


# ───────────────────────── HTTP handler ─────────────────────────

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False))

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def _local_only(self):
        host = (self.headers.get("Host") or "").split(":")[0]
        return host in ("127.0.0.1", "localhost")

    def _serve_file(self, p, ctype=None):
        ctype = ctype or mimetypes.guess_type(str(p))[0] or "application/octet-stream"
        size = p.stat().st_size
        start, end, code = 0, size - 1, 200
        rng = re.match(r"bytes=(\d*)-(\d*)", self.headers.get("Range") or "")
        if rng and (rng.group(1) or rng.group(2)):
            if rng.group(1):
                start = int(rng.group(1))
                end = int(rng.group(2)) if rng.group(2) else size - 1
            else:                                   # suffix range: last N bytes
                start = max(0, size - int(rng.group(2)))
            end = min(end, size - 1)
            if start > end:
                return self._send(416, "", "text/plain", {"Content-Range": f"bytes */{size}"})
            code = 206
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Cache-Control", "private, max-age=3600")
        if code == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        try:
            with open(p, "rb") as f:
                f.seek(start)
                left = end - start + 1
                while left > 0:
                    chunk = f.read(min(1 << 20, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def do_GET(self):
        if not self._local_only():
            return self._send(403, "forbidden", "text/plain")
        u = urlparse(self.path)
        qs = parse_qs(u.query)
        if u.path in ("/", "/index.html"):
            return self._send(200, (RES / "index.html").read_bytes(), "text/html; charset=utf-8")
        if u.path == "/api/settings":
            return self._json(load_settings())
        if u.path == "/api/sources":
            return self._json(load_sources())
        if u.path == "/api/cookies":
            return self._json(cookies_status())
        if u.path == "/api/cookies-yt":
            return self._json(yt_cookies_status())
        if u.path == "/api/gallery":
            def num(k, d):
                try:
                    return max(0, int(qs.get(k, [d])[0]))
                except ValueError:
                    return d
            return self._json(gallery_page(num("offset", 0), min(num("limit", 60) or 60, 200),
                                           qs.get("q", [""])[0]))
        if u.path in ("/api/file", "/api/thumb"):
            p = safe_path(qs.get("p", [""])[0])
            if not p:
                return self._send(404, "not found", "text/plain")
            if u.path == "/api/thumb" and p.suffix.lower() in IMG_EXT:
                t = make_thumb(p)
                if t:
                    return self._serve_file(t, "image/jpeg")
            return self._serve_file(p)
        m = re.match(r"^/api/job/([0-9a-f]+)$", u.path)
        if m:
            job = JOBS.get(m.group(1))
            if not job:
                return self._json({"error": "not found"}, 404)
            start = int(qs.get("from", ["0"])[0] or 0)
            return self._json({k: v for k, v in job.items() if k != "proc"} | {
                "log": job["log"][start:], "log_len": len(job["log"])})
        self._send(404, "not found", "text/plain")

    def do_POST(self):
        if not self._local_only() or self.headers.get("X-App") != "cd":
            return self._send(403, "forbidden", "text/plain")
        path = urlparse(self.path).path
        if path == "/api/settings":
            s = load_settings()
            s.update({k: v for k, v in self._body().items() if k in DEFAULT_SETTINGS})
            save_settings(s)
            return self._json(s)
        if path == "/api/start":
            b = self._body()
            # one or many links, separated by new lines / spaces; duplicates dropped
            urls = list(dict.fromkeys(re.findall(r"https?://\S+", b.get("url") or "")))
            if not urls:
                return self._json({"error": "لینک معتبر نیست"}, 400)
            s = load_settings()
            out_root(s).mkdir(parents=True, exist_ok=True)
            job_id = uuid.uuid4().hex[:12]
            JOBS[job_id] = {"id": job_id, "urls": urls, "total": len(urls), "current": 0,
                            "failed": 0, "state": "running", "log": [],
                            "count": 0, "skipped": 0, "last_file": "", "site": "", "progress": None}
            threading.Thread(target=run_job, args=(job_id, urls, s), daemon=True).start()
            return self._json({"id": job_id})
        m = re.match(r"^/api/job/([0-9a-f]+)/cancel$", path)
        if m and m.group(1) in JOBS:
            job = JOBS[m.group(1)]
            job["state"] = "cancelled"
            if job.get("proc"):
                job["proc"].terminate()
            return self._json({"ok": True})
        if path == "/api/open-folder":
            root = out_root()
            root.mkdir(parents=True, exist_ok=True)
            os.startfile(str(root))
            return self._json({"ok": True})
        if path == "/api/reveal":
            p = safe_path(self._body().get("p", ""))
            if not p:
                return self._json({"error": "not found"}, 404)
            subprocess.Popen(["explorer", "/select,", str(p)])
            return self._json({"ok": True})
        if path == "/api/sources":
            b = self._body()
            added = 0
            with STATE_LOCK:
                items = load_sources()
                known = {norm_url(x["url"]) for x in items}
                for url in dict.fromkeys(re.findall(r"https?://\S+", b.get("url") or "")):
                    if norm_url(url) in known:
                        continue
                    items.append({"id": uuid.uuid4().hex[:8], "url": url,
                                  "name": (b.get("name") or "").strip() or guess_name(url),
                                  "added": int(time.time()), "last_run": 0, "last_new": 0, "last_ok": True})
                    known.add(norm_url(url))
                    added += 1
                save_sources(items)
            return self._json({"added": added, "sources": load_sources()})
        if path == "/api/sources/delete":
            sid = self._body().get("id")
            with STATE_LOCK:
                save_sources([x for x in load_sources() if x["id"] != sid])
            return self._json(load_sources())
        if path == "/api/sources/rename":
            b = self._body()
            with STATE_LOCK:
                items = load_sources()
                for x in items:
                    if x["id"] == b.get("id") and (b.get("name") or "").strip():
                        x["name"] = b["name"].strip()
                save_sources(items)
            return self._json(items)
        if path == "/api/cookies":
            text = (self._body().get("text") or "")
            found = parse_cookies(text)
            if "sessionid" not in found:
                return self._json({"error": "در این فایل ورود اینستاگرام (sessionid) پیدا نشد. "
                                            "مطمئن شوید در حالی که وارد instagram.com بودید خروجی گرفته‌اید."}, 400)
            COOKIES_FILE.write_text(text, encoding="utf-8")
            return self._json(cookies_status())
        if path == "/api/cookies-yt":
            text = (self._body().get("text") or "")
            names = parse_cookies(text, ("youtube.com", "google.com"))
            if not names:
                return self._json({"error": "در این فایل کوکی‌های یوتیوب پیدا نشد. وقتی در youtube.com وارد بودید خروجی بگیرید."}, 400)
            YT_COOKIES_FILE.write_text(text, encoding="utf-8")
            return self._json(yt_cookies_status())
        if path == "/api/cookies-yt/delete":
            if YT_COOKIES_FILE.exists():
                YT_COOKIES_FILE.unlink()
            return self._json(yt_cookies_status())
        if path == "/api/cookies/delete":
            if COOKIES_FILE.exists():
                COOKIES_FILE.unlink()
            return self._json(cookies_status())
        if path == "/api/quit":
            self._json({"ok": True})
            threading.Thread(target=lambda: (time.sleep(0.3), SERVER.shutdown()), daemon=True).start()
            return
        self._send(404, "not found", "text/plain")


class Server(ThreadingHTTPServer):
    # On Windows SO_REUSEADDR lets a second copy bind a port that is already in use,
    # which would make two servers share one port. Turn it off so the second launch fails fast.
    allow_reuse_address = False
    daemon_threads = True


def say(msg):
    if sys.stdout:                       # pythonw has no console
        try:
            print(msg)
        except Exception:
            pass


def main():
    global SERVER
    if len(sys.argv) > 2 and sys.argv[1] == "--tool" and sys.argv[2] in ("gallery_dl", "yt_dlp"):
        run_tool_and_exit(sys.argv[2], sys.argv[3:])      # child process of the frozen exe
    url =f"http://127.0.0.1:{PORT}"
    try:
        SERVER = Server(("127.0.0.1", PORT), Handler)
    except OSError:                      # already running → just open it
        say(f"برنامه از قبل روی {url} اجرا است؛ صفحه باز می‌شود.")
        if "--no-browser" not in sys.argv:
            webbrowser.open(url)
        return
    say(f"Collection Downloader روی {url} اجرا شد — برای بستن Ctrl+C")
    if "--no-browser" not in sys.argv:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        SERVER.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
