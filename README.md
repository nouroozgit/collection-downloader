# Collection Downloader

**English** · [فارسی](#فارسی)

A local web app (Persian UI) that bulk-downloads **Pinterest** boards and pins, **Instagram** saved collections, posts and reels, and **YouTube** videos and playlists. It runs only on your own computer and wraps [gallery-dl](https://github.com/mikf/gallery-dl) and [yt-dlp](https://github.com/yt-dlp/yt-dlp).

## Features

- Paste one link or many (one per line): a whole board / collection / playlist, or a single post, reel, pin or video
- **My sources** list: save boards, collections and playlists, then "Update all" fetches only what is new
- Re-runs skip files you already have (download archive)
- Captions and the original post link saved next to every file, and searchable
- **Gallery** tab with thumbnails, a video/audio player and "show in folder"
- YouTube: quality choice (best / 1080 / 720 / 480) or audio only (mp3), progress bar
- Instagram collections go into their own folders; optional full-profile mode (posts, reels, stories, highlights)
- Stop button, and clear Persian hints when something fails (login expired, rate limit, unavailable video)

## Requirements

- Windows, Python 3.10+
- `pip install gallery-dl "yt-dlp[default]" pillow`
- For YouTube: [Node.js](https://nodejs.org) and [ffmpeg](https://ffmpeg.org) on the PATH (the exe build bundles both)

## Run

```
python app.py
```

It opens http://127.0.0.1:8765. You can also double-click `Start.bat` (shows a console) or `Start-Hidden.vbs` (no window). If the app is already running, launching it again just opens the page. Use **Settings → Quit** to stop it.

## Instagram login

Instagram shows almost nothing without a login. Export `cookies.txt` while logged in to instagram.com (for example with the *Get cookies.txt LOCALLY* browser extension) and upload it in **Settings → Instagram login**. Recent Chrome and Edge encrypt their cookies, so reading them straight from the browser usually fails; the exported file is the reliable way. A YouTube login is optional and works the same way.

> `cookies.txt` is as sensitive as your password. It is listed in `.gitignore` and must never be committed or shared.

## Build the Windows exe

```
build_exe.bat
```

Produces `dist\CollectionDownloader\CollectionDownloader.exe` (PyInstaller). Keep the `_internal` and `tools` folders next to it.

## Notes

- Only download content you have the right to save, and respect the terms of each site.
- Instagram may temporarily rate-limit your account on very large collections; the app pauses between requests to reduce this.
- Pinterest links that start with `/pin/e1_` cannot be fetched without a login; use the `pin.it` share link instead.

## License

Released under the [MIT License](LICENSE). The bundled third-party tools keep their own licenses (see the release notes).

---

<div dir="rtl" id="فارسی">

# دانلود کالکشن

[English](#collection-downloader) · **فارسی**

یک برنامه‌ی وب محلی با رابط فارسی برای دانلود گروهی بورد و پین‌های **پینترست**، کالکشن‌های ذخیره‌شده، پست‌ها و ریل‌های **اینستاگرام** و ویدیو و پلی‌لیست‌های **یوتیوب**. فقط روی کامپیوتر خودتان اجرا می‌شود و از [gallery-dl](https://github.com/mikf/gallery-dl) و [yt-dlp](https://github.com/yt-dlp/yt-dlp) استفاده می‌کند.

## امکانات

- یک لینک یا چند لینک (هر کدام در یک خط): کل بورد / کالکشن / پلی‌لیست، یا یک پست، ریل، پین و ویدیوی تکی
- فهرست **منبع‌های من**: بورد، کالکشن و پلی‌لیست را ذخیره کنید؛ «به‌روزرسانی همه» فقط موارد جدید را می‌گیرد
- فایل‌هایی که قبلاً دانلود شده‌اند دوباره دانلود نمی‌شوند
- کپشن و لینک اصلی پست کنار هر فایل ذخیره می‌شود و قابل جستجوست
- تب **گالری** با پیش‌نمایش، پخش ویدیو و صدا و «نمایش در پوشه»
- یوتیوب: انتخاب کیفیت (بهترین / ۱۰۸۰ / ۷۲۰ / ۴۸۰) یا فقط صدا (mp3) و نوار پیشرفت
- کالکشن‌های اینستاگرام در پوشه‌ی جدا ذخیره می‌شوند؛ حالت اختیاری پروفایل کامل (پست، ریل، استوری، هایلایت)
- دکمه‌ی توقف و پیام‌های راهنمای فارسی هنگام خطا (منقضی‌شدن ورود، محدودیت درخواست، ویدیوی در دسترس نبودن)

## پیش‌نیازها

- ویندوز و پایتون ۳٫۱۰ به بالا
- `pip install gallery-dl "yt-dlp[default]" pillow`
- برای یوتیوب: [Node.js](https://nodejs.org) و [ffmpeg](https://ffmpeg.org) (در نسخه‌ی exe هر دو همراه برنامه هستند)

## اجرا

```
python app.py
```

صفحه‌ی http://127.0.0.1:8765 باز می‌شود. می‌توانید `Start.bat` (با پنجره‌ی کنسول) یا `Start-Hidden.vbs` (بدون پنجره) را هم دوبار کلیک کنید. اگر برنامه از قبل باز باشد، اجرای دوباره فقط صفحه را باز می‌کند. برای بستن: **تنظیمات ← بستن برنامه**.

## ورود اینستاگرام

اینستاگرام بدون ورود به حساب تقریباً چیزی نشان نمی‌دهد. وقتی در instagram.com وارد هستید، فایل `cookies.txt` را خروجی بگیرید (مثلاً با افزونه‌ی *Get cookies.txt LOCALLY*) و در **تنظیمات ← ورود اینستاگرام** آپلود کنید. کروم و اج جدید کوکی‌هایشان را رمز می‌کنند و خواندن مستقیم از مرورگر معمولاً جواب نمی‌دهد؛ فایل خروجی راه مطمئن است. ورود یوتیوب اختیاری است و به همین شکل انجام می‌شود.

> فایل `cookies.txt` به اندازه‌ی رمز حساب شما حساس است. در `.gitignore` قرار دارد و هرگز نباید در گیت قرار بگیرد یا با کسی به اشتراک گذاشته شود.

## ساخت exe ویندوز

```
build_exe.bat
```

خروجی: `dist\CollectionDownloader\CollectionDownloader.exe` (با PyInstaller). پوشه‌های `_internal` و `tools` باید کنار آن بمانند.

## نکات

- فقط محتوایی را دانلود کنید که حق ذخیره‌ی آن را دارید و به شرایط استفاده‌ی هر سایت پایبند باشید.
- در کالکشن‌های خیلی بزرگ ممکن است اینستاگرام موقتاً حساب را محدود کند؛ برنامه بین درخواست‌ها مکث می‌کند تا این احتمال کم شود.
- لینک‌های پینترست که با `/pin/e1_` شروع می‌شوند بدون ورود قابل دانلود نیستند؛ از لینک اشتراک‌گذاری `pin.it` استفاده کنید.

## مجوز

تحت [مجوز MIT](LICENSE) منتشر شده است. ابزارهای همراه شخص ثالث مجوز خودشان را دارند (جزئیات در یادداشت‌های ریلیز).

</div>
