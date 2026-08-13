"""Playlists and recent-play history — JSON files, atomic writes."""

from __future__ import annotations

import json
import os
import secrets
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
PLAYLISTS_PATH = ROOT / "playlists.json"
HISTORY_PATH = ROOT / "history.json"
HISTORY_LIMIT = 50

_lock = threading.RLock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load(path: Path, empty: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return dict(empty)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(empty)
    if not isinstance(data, dict):
        return dict(empty)
    return data


def _save(path: Path, data: dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def ensure_store() -> None:
    with _lock:
        if not PLAYLISTS_PATH.exists():
            _save(PLAYLISTS_PATH, {"playlists": []})
        if not HISTORY_PATH.exists():
            _save(HISTORY_PATH, {"items": []})


def list_playlists() -> list[dict[str, Any]]:
    with _lock:
        data = _load(PLAYLISTS_PATH, {"playlists": []})
        pls = data.get("playlists") or []
        return [p for p in pls if isinstance(p, dict)]


def get_playlist(playlist_id: str) -> dict[str, Any] | None:
    playlist_id = (playlist_id or "").strip()
    for p in list_playlists():
        if p.get("id") == playlist_id:
            return p
    return None


def create_playlist(name: str) -> dict[str, Any]:
    name = (name or "").strip() or "פלייליסט"
    pl = {
        "id": f"pl_{secrets.token_hex(6)}",
        "name": name,
        "created_at": _now_iso(),
        "items": [],
    }
    with _lock:
        data = _load(PLAYLISTS_PATH, {"playlists": []})
        data.setdefault("playlists", [])
        data["playlists"].append(pl)
        _save(PLAYLISTS_PATH, data)
    return pl


def rename_playlist(playlist_id: str, name: str) -> dict[str, Any]:
    name = (name or "").strip()
    if not name:
        return {"ok": False, "error": "Missing name"}
    with _lock:
        data = _load(PLAYLISTS_PATH, {"playlists": []})
        found = None
        for p in data.get("playlists") or []:
            if p.get("id") == playlist_id:
                p["name"] = name
                found = p
                break
        if not found:
            return {"ok": False, "error": "Playlist not found"}
        _save(PLAYLISTS_PATH, data)
        return {"ok": True, "playlist": found}


def delete_playlist(playlist_id: str) -> dict[str, Any]:
    with _lock:
        data = _load(PLAYLISTS_PATH, {"playlists": []})
        before = data.get("playlists") or []
        after = [p for p in before if p.get("id") != playlist_id]
        if len(after) == len(before):
            return {"ok": False, "error": "Playlist not found"}
        data["playlists"] = after
        _save(PLAYLISTS_PATH, data)
        return {"ok": True, "id": playlist_id}


def add_item(
    playlist_id: str,
    *,
    kind: str,
    title: str | None = None,
    file_id: str | None = None,
    url: str | None = None,
) -> dict[str, Any]:
    kind = (kind or "").strip()
    if kind not in ("file", "url"):
        return {"ok": False, "error": "kind must be file or url"}
    item: dict[str, Any] = {
        "id": f"it_{secrets.token_hex(6)}",
        "kind": kind,
        "title": (title or "").strip() or None,
    }
    if kind == "file":
        fid = (file_id or "").strip()
        if not fid:
            return {"ok": False, "error": "Missing file_id"}
        item["file_id"] = fid
        item["url"] = None
    else:
        u = (url or "").strip()
        if not u:
            return {"ok": False, "error": "Missing url"}
        item["url"] = u
        item["file_id"] = None
        if not item["title"]:
            item["title"] = u
    with _lock:
        data = _load(PLAYLISTS_PATH, {"playlists": []})
        found = None
        for p in data.get("playlists") or []:
            if p.get("id") == playlist_id:
                p.setdefault("items", []).append(item)
                found = p
                break
        if not found:
            return {"ok": False, "error": "Playlist not found"}
        _save(PLAYLISTS_PATH, data)
        return {"ok": True, "item": item, "playlist": found}


def remove_item(playlist_id: str, item_id: str) -> dict[str, Any]:
    with _lock:
        data = _load(PLAYLISTS_PATH, {"playlists": []})
        found = None
        for p in data.get("playlists") or []:
            if p.get("id") == playlist_id:
                items = p.get("items") or []
                after = [it for it in items if it.get("id") != item_id]
                if len(after) == len(items):
                    return {"ok": False, "error": "Item not found"}
                p["items"] = after
                found = p
                break
        if not found:
            return {"ok": False, "error": "Playlist not found"}
        _save(PLAYLISTS_PATH, data)
        return {"ok": True, "playlist": found}


def reorder_items(playlist_id: str, item_ids: list[str]) -> dict[str, Any]:
    ids = [str(x).strip() for x in (item_ids or []) if str(x).strip()]
    with _lock:
        data = _load(PLAYLISTS_PATH, {"playlists": []})
        found = None
        for p in data.get("playlists") or []:
            if p.get("id") == playlist_id:
                found = p
                break
        if not found:
            return {"ok": False, "error": "Playlist not found"}
        by_id = {it.get("id"): it for it in (found.get("items") or [])}
        ordered = [by_id[i] for i in ids if i in by_id]
        leftover = [it for it in (found.get("items") or []) if it.get("id") not in set(ids)]
        found["items"] = ordered + leftover
        _save(PLAYLISTS_PATH, data)
        return {"ok": True, "playlist": found}


def add_history(
    *,
    title: str | None,
    source: str,
    url: str | None = None,
    file_id: str | None = None,
    playlist_id: str | None = None,
) -> None:
    entry = {
        "title": (title or "").strip() or "Untitled",
        "source": source,
        "url": url,
        "file_id": file_id,
        "playlist_id": playlist_id,
        "played_at": _now_iso(),
    }
    with _lock:
        data = _load(HISTORY_PATH, {"items": []})
        items = [x for x in (data.get("items") or []) if isinstance(x, dict)]
        # Dedupe consecutive identical plays
        if items:
            last = items[0]
            if (
                last.get("source") == entry["source"]
                and last.get("url") == entry["url"]
                and last.get("file_id") == entry["file_id"]
                and last.get("playlist_id") == entry["playlist_id"]
            ):
                last["played_at"] = entry["played_at"]
                last["title"] = entry["title"]
                data["items"] = items[:HISTORY_LIMIT]
                _save(HISTORY_PATH, data)
                return
        items.insert(0, entry)
        data["items"] = items[:HISTORY_LIMIT]
        _save(HISTORY_PATH, data)


def list_history() -> list[dict[str, Any]]:
    with _lock:
        data = _load(HISTORY_PATH, {"items": []})
        items = [x for x in (data.get("items") or []) if isinstance(x, dict)]
        return items[:HISTORY_LIMIT]
