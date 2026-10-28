"""Shared request validation — no Flask / Bluetooth / yt-dlp imports."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

ERR_MISSING_URL = "חסר קישור"
ERR_MISSING_URL_OR_FILE = "חסר קישור או קובץ"
ERR_BAD_URL = "קישור לא תקין. הדבק קישור יוטיוב מלא"
ERR_BAD_YOUTUBE = "קישור יוטיוב חסר מזהה סרטון או פלייליסט"
ERR_MISSING_ADDRESS = "חסר כתובת בלוטות׳"
ERR_BAD_ADDRESS = "כתובת בלוטות׳ לא תקינה"
ERR_NO_SPEAKER = "אין רמקול בלוטות׳ מחובר"
ERR_BAD_VOLUME = "עוצמת שמע לא תקינה"
ERR_MISSING_SEARCH = "חסרות מילות חיפוש"
ERR_BAD_SCAN = "משך סריקה לא תקין"
ERR_BAD_SKIP = "מספר דילוג לא תקין"
ERR_BAD_SEEK = "ערך דילוג לא תקין"

_BT_ADDR = re.compile(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")
_YT_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_YT_PATH_ID = re.compile(r"^/(?:shorts|embed|live)/([A-Za-z0-9_-]{11})")
_YT_BE_ID = re.compile(r"^/([A-Za-z0-9_-]{11})")

_PLAYER_ERR = {
    "Missing sources": ERR_BAD_URL,
    "Missing URL": ERR_MISSING_URL,
    "Missing url": ERR_MISSING_URL,
    "Missing url or file_id": ERR_MISSING_URL_OR_FILE,
    "No Bluetooth speaker connected": ERR_NO_SPEAKER,
    "Nothing playing": "כלום לא מתנגן",
    "Nothing to resume": "אין מה להמשיך",
    "playlist-next failed (end of playlist?)": "זה השיר האחרון בתור",
    "playlist-prev failed (start of playlist?)": "זה השיר הראשון בתור",
    "Invalid delta": ERR_BAD_SKIP,
    "Invalid index": "מיקום בתור לא תקין",
    "Invalid seconds/percent": ERR_BAD_SEEK,
    "Invalid seconds": ERR_BAD_SEEK,
    "Invalid percent": ERR_BAD_SEEK,
    "File not found": "הקובץ לא נמצא",
    "Playlist is empty": "הפלייליסט ריק",
    "Playlist not found": "הפלייליסט לא נמצא",
    "Missing playlist_id": "חסר מזהה פלייליסט",
    "Provide percent": "חסר אחוז עוצמה",
    "Missing q": ERR_MISSING_SEARCH,
    "Missing query": ERR_MISSING_SEARCH,
    "Missing address": ERR_MISSING_ADDRESS,
}


def friendly(msg: str | None) -> str:
    if not msg:
        return "הפעולה נכשלה"
    return _PLAYER_ERR.get(msg, msg)


def is_bt_address(value: str) -> bool:
    return bool(_BT_ADDR.match((value or "").strip()))


def _host(raw: str) -> str:
    host = (raw or "").split("/")[0].split("?")[0].split(":")[0].strip().lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def is_youtube_host(host: str) -> bool:
    h = (host or "").lower()
    if h.startswith("www."):
        h = h[4:]
    return h in {
        "youtube.com",
        "youtu.be",
        "music.youtube.com",
        "m.youtube.com",
        "youtube-nocookie.com",
    } or h.endswith(".youtube.com") or h.endswith(".youtube-nocookie.com")


def coerce_play_url(raw: str) -> str | None:
    """Return an http(s)/ytdl URL, adding https:// for bare YouTube hosts."""
    s = (raw or "").strip()
    if not s:
        return None
    low = s.lower()
    if low.startswith(("http://", "https://", "ytdl://")):
        return s
    if low.startswith("//") and is_youtube_host(_host(s[2:])):
        return "https:" + s
    if is_youtube_host(_host(s)):
        return "https://" + s.lstrip("/")
    return None


def youtube_has_target(url: str) -> bool:
    try:
        u = urlparse(url)
    except ValueError:
        return False
    qs = parse_qs(u.query, keep_blank_values=False)
    vid = (qs.get("v") or [""])[0]
    if vid and _YT_ID.match(vid):
        return True
    plist = (qs.get("list") or [""])[0].strip()
    if plist:
        return True
    path = u.path or ""
    if _YT_PATH_ID.match(path):
        return True
    host = (u.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if host == "youtu.be" and _YT_BE_ID.match(path):
        return True
    return False


def play_url_error(raw: str) -> str | None:
    """None if the URL may be sent to the player."""
    s = (raw or "").strip()
    if not s:
        return ERR_MISSING_URL
    coerced = coerce_play_url(s)
    if not coerced:
        return ERR_BAD_URL
    try:
        host = (urlparse(coerced).hostname or "")
    except ValueError:
        return ERR_BAD_URL
    if is_youtube_host(host) and not youtube_has_target(coerced):
        return ERR_BAD_YOUTUBE
    return None
