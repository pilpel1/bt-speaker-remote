"""Local audio library: scan, upload, delete, save YouTube URLs via yt-dlp."""

from __future__ import annotations

import hashlib
import os
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
MEDIA_ROOT = ROOT / "media"
SUBDIRS = ("uploads", "recordings", "saved")

AUDIO_EXTS = {
    ".mp3",
    ".m4a",
    ".aac",
    ".ogg",
    ".oga",
    ".opus",
    ".wav",
    ".flac",
    ".webm",
    ".mp4",
    ".wma",
    ".m4b",
}
MAX_UPLOAD_BYTES = 80 * 1024 * 1024
MAX_FILES = 500
MAX_SCAN_DEPTH = 4

_lock = threading.RLock()
_save_job: dict[str, Any] = {
    "status": "idle",
    "url": None,
    "error": None,
    "title": None,
}


def ensure_dirs() -> None:
    MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
    for name in SUBDIRS:
        (MEDIA_ROOT / name).mkdir(parents=True, exist_ok=True)


def extra_media_dir() -> Path | None:
    raw = os.environ.get("BT_SPEAKER_MEDIA_DIR", "").strip()
    if not raw:
        return None
    p = Path(raw).expanduser()
    try:
        p = p.resolve()
    except OSError:
        return None
    if p.is_dir():
        return p
    return None


def _file_id(path: Path) -> str:
    return hashlib.sha256(str(path).encode("utf-8", errors="replace")).hexdigest()[:20]


def _safe_stem(name: str) -> str:
    name = Path(name).name
    name = re.sub(r"[^\w.\- \u0590-\u05FF]+", "_", name, flags=re.UNICODE)
    name = name.strip(" ._")
    return name or "audio"


def _title_of(path: Path) -> str:
    return path.stem.replace("_", " ").strip() or path.name


def _kind_for(path: Path) -> str:
    try:
        rel = path.relative_to(MEDIA_ROOT)
        top = rel.parts[0] if rel.parts else ""
        if top in SUBDIRS:
            return top
    except ValueError:
        pass
    return "extra"


def _is_audio(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in AUDIO_EXTS and not path.name.startswith(".")


def _scan_dir(root: Path, *, depth: int = 0) -> list[Path]:
    out: list[Path] = []
    if depth > MAX_SCAN_DEPTH or not root.is_dir():
        return out
    try:
        entries = sorted(root.iterdir(), key=lambda p: p.name.lower())
    except OSError:
        return out
    for entry in entries:
        if len(out) >= MAX_FILES:
            break
        if entry.name.startswith("."):
            continue
        if entry.is_dir():
            out.extend(_scan_dir(entry, depth=depth + 1))
        elif _is_audio(entry):
            out.append(entry)
    return out[:MAX_FILES]


def _stat_item(path: Path) -> dict[str, Any] | None:
    try:
        resolved = path.resolve()
        st = resolved.stat()
    except OSError:
        return None
    return {
        "id": _file_id(resolved),
        "name": resolved.name,
        "title": _title_of(resolved),
        "kind": _kind_for(resolved),
        "size": int(st.st_size),
        "mtime": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc)
        .replace(microsecond=0)
        .isoformat(),
        "ext": resolved.suffix.lower(),
        "path": resolved,
    }


def _scan_all() -> list[dict[str, Any]]:
    ensure_dirs()
    paths: list[Path] = []
    for name in SUBDIRS:
        paths.extend(_scan_dir(MEDIA_ROOT / name))
    extra = extra_media_dir()
    if extra:
        try:
            extra_res = extra.resolve()
            media_res = MEDIA_ROOT.resolve()
            if extra_res != media_res and media_res not in extra_res.parents:
                paths.extend(_scan_dir(extra_res))
        except OSError:
            pass
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for p in paths:
        item = _stat_item(p)
        if not item or item["id"] in seen:
            continue
        seen.add(item["id"])
        items.append(item)
        if len(items) >= MAX_FILES:
            break
    items.sort(key=lambda x: x.get("mtime") or "", reverse=True)
    return items


def list_files() -> dict[str, Any]:
    items = _scan_all()
    public = [{k: v for k, v in it.items() if k != "path"} for it in items]
    with _lock:
        job = dict(_save_job)
    return {
        "ok": True,
        "files": public,
        "count": len(public),
        "save_job": {
            "status": job.get("status") or "idle",
            "url": job.get("url"),
            "error": job.get("error"),
            "title": job.get("title"),
        },
    }


def resolve(file_id: str) -> dict[str, Any] | None:
    file_id = (file_id or "").strip()
    if not file_id:
        return None
    for item in _scan_all():
        if item["id"] == file_id:
            return item
    return None


def _unique_path(directory: Path, filename: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    safe = _safe_stem(filename)
    ext = Path(safe).suffix.lower()
    if ext not in AUDIO_EXTS:
        ext = ".webm"
        stem = safe
    else:
        stem = Path(safe).stem
    candidate = directory / f"{stem}{ext}"
    n = 2
    while candidate.exists():
        candidate = directory / f"{stem}_{n}{ext}"
        n += 1
        if n > 200:
            candidate = directory / f"{stem}_{int(time.time())}{ext}"
            break
    return candidate


def save_bytes(filename: str, data: bytes, kind: str = "uploads") -> dict[str, Any]:
    if kind not in SUBDIRS:
        kind = "uploads"
    if not data:
        return {"ok": False, "error": "Empty file"}
    if len(data) > MAX_UPLOAD_BYTES:
        return {"ok": False, "error": f"File too large (max {MAX_UPLOAD_BYTES // (1024 * 1024)}MB)"}
    ext = Path(filename or "").suffix.lower()
    if ext and ext not in AUDIO_EXTS:
        return {"ok": False, "error": f"Unsupported audio type: {ext}"}
    ensure_dirs()
    dest = _unique_path(MEDIA_ROOT / kind, filename or f"audio{ext or '.webm'}")
    dest.write_bytes(data)
    item = _stat_item(dest)
    if not item:
        return {"ok": False, "error": "Saved but could not read file"}
    public = {k: v for k, v in item.items() if k != "path"}
    return {"ok": True, "file": public}


def delete_file(file_id: str) -> dict[str, Any]:
    item = resolve(file_id)
    if not item:
        return {"ok": False, "error": "File not found"}
    path: Path = item["path"]
    try:
        path.relative_to(MEDIA_ROOT.resolve())
    except ValueError:
        return {"ok": False, "error": "Cannot delete files outside the media folder"}
    try:
        path.unlink()
    except OSError as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "id": file_id}


def save_job_status() -> dict[str, Any]:
    with _lock:
        return dict(_save_job)


def save_url_async(url: str) -> dict[str, Any]:
    url = (url or "").strip()
    if not url:
        return {"ok": False, "error": "Missing url"}
    with _lock:
        if _save_job.get("status") == "running":
            return {"ok": False, "error": "Save already in progress"}
        _save_job.update(
            {"status": "running", "url": url, "error": None, "title": None}
        )
    threading.Thread(target=_save_url_worker, args=(url,), daemon=True).start()
    return {"ok": True, "started": True, "status": "running"}


def _save_url_worker(url: str) -> None:
    import subprocess

    ensure_dirs()
    dest_dir = MEDIA_ROOT / "saved"
    dest_dir.mkdir(parents=True, exist_ok=True)
    out_tmpl = str(dest_dir / "%(title)s [%(id)s].%(ext)s")
    from player import YTDLP_PREFIX

    cmd = [
        *YTDLP_PREFIX,
        "-f",
        "bestaudio/best",
        "--no-playlist",
        "--no-overwrites",
        "-o",
        out_tmpl,
        url,
    ]
    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        err = (r.stderr or "").strip()[-400:]
        if r.returncode != 0:
            with _lock:
                _save_job.update(
                    {
                        "status": "error",
                        "error": err or f"yt-dlp exited {r.returncode}",
                    }
                )
            return
        title = None
        # Best-effort: newest file in saved/
        newest = None
        newest_mtime = 0.0
        for p in dest_dir.iterdir():
            if not _is_audio(p):
                continue
            try:
                mt = p.stat().st_mtime
            except OSError:
                continue
            if mt > newest_mtime:
                newest_mtime = mt
                newest = p
        if newest:
            title = _title_of(newest)
        with _lock:
            _save_job.update({"status": "ok", "error": None, "title": title})
    except subprocess.TimeoutExpired:
        with _lock:
            _save_job.update({"status": "error", "error": "Download timed out"})
    except FileNotFoundError:
        with _lock:
            _save_job.update({"status": "error", "error": "yt-dlp is not installed"})
    except Exception as e:
        with _lock:
            _save_job.update({"status": "error", "error": str(e)})
