"""Per-device auth: 24h invite links → long-lived device tokens until revoked."""

from __future__ import annotations

import json
import os
import secrets
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
STORE_PATH = ROOT / "authorized_devices.json"
_lock = threading.RLock()

INVITE_TTL_HOURS = int(os.environ.get("BT_SPEAKER_INVITE_HOURS", "24"))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _empty() -> dict[str, Any]:
    return {"devices": [], "invites": []}


def _load() -> dict[str, Any]:
    if not STORE_PATH.exists():
        return _empty()
    try:
        data = json.loads(STORE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty()
    if not isinstance(data, dict):
        return _empty()
    data.setdefault("devices", [])
    data.setdefault("invites", [])
    return data


def _save(data: dict[str, Any]) -> None:
    tmp = STORE_PATH.with_suffix(".json.tmp")
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(STORE_PATH)
    try:
        os.chmod(STORE_PATH, 0o600)
    except OSError:
        pass


def ensure_store() -> None:
    with _lock:
        if not STORE_PATH.exists():
            _save(_empty())


def _has_admin(data: dict[str, Any]) -> bool:
    return any(d.get("admin") and not d.get("revoked") for d in data["devices"])


def create_invite(name: str, hours: int | None = None) -> dict[str, Any]:
    name = (name or "").strip() or "Unnamed device"
    ttl = hours if hours is not None else INVITE_TTL_HOURS
    ttl = max(1, min(168, int(ttl)))
    now = _now()
    invite = {
        "id": f"inv_{secrets.token_hex(6)}",
        "name": name,
        "token": secrets.token_urlsafe(32),
        "created_at": _iso(now),
        "expires_at": _iso(now + timedelta(hours=ttl)),
        "used": False,
        "used_at": None,
        "device_id": None,
    }
    with _lock:
        data = _load()
        data["invites"].append(invite)
        _save(data)
    return dict(invite)


def list_devices(*, include_admin_flag: bool = True) -> list[dict[str, Any]]:
    with _lock:
        data = _load()
        out = []
        for d in data["devices"]:
            row = {
                "id": d["id"],
                "name": d["name"],
                "created_at": d.get("created_at"),
                "last_seen": d.get("last_seen"),
                "revoked": bool(d.get("revoked")),
                "token_prefix": (d.get("token") or "")[:8] + "…",
            }
            if include_admin_flag:
                row["admin"] = bool(d.get("admin"))
            out.append(row)
        return out


def list_invites(*, include_used: bool = True, include_secrets: bool = False) -> list[dict[str, Any]]:
    with _lock:
        data = _load()
        now = _now()
        out = []
        for inv in data["invites"]:
            expired = _parse_iso(inv["expires_at"]) < now
            if not include_used and (inv.get("used") or expired):
                continue
            row = {
                "id": inv["id"],
                "name": inv["name"],
                "created_at": inv.get("created_at"),
                "expires_at": inv.get("expires_at"),
                "used": bool(inv.get("used")),
                "expired": expired,
                "device_id": inv.get("device_id"),
                "open": (not inv.get("used") and not expired and bool(inv.get("token"))),
            }
            if include_secrets and row["open"]:
                row["token"] = inv["token"]
            else:
                prefix = inv.get("token") or ""
                row["token_prefix"] = (prefix[:8] + "…") if prefix else ""
            out.append(row)
        return out


def delete_invite(invite_id: str) -> bool:
    with _lock:
        data = _load()
        before = len(data["invites"])
        data["invites"] = [i for i in data["invites"] if i["id"] != invite_id]
        if len(data["invites"]) == before:
            return False
        _save(data)
        return True


def revoke_device(device_id: str) -> dict[str, Any]:
    with _lock:
        data = _load()
        target = None
        for d in data["devices"]:
            if d["id"] == device_id:
                target = d
                break
        if not target:
            return {"ok": False, "error": "Device not found"}
        if target.get("admin") and not target.get("revoked"):
            admins = [d for d in data["devices"] if d.get("admin") and not d.get("revoked")]
            if len(admins) <= 1:
                return {"ok": False, "error": "Cannot revoke the last admin"}
        target["revoked"] = True
        _save(data)
        return {"ok": True, "id": device_id}


def delete_device(device_id: str) -> dict[str, Any]:
    with _lock:
        data = _load()
        target = next((d for d in data["devices"] if d["id"] == device_id), None)
        if not target:
            return {"ok": False, "error": "Device not found"}
        if target.get("admin") and not target.get("revoked"):
            admins = [d for d in data["devices"] if d.get("admin") and not d.get("revoked")]
            if len(admins) <= 1:
                return {"ok": False, "error": "Cannot delete the last admin"}
        data["devices"] = [d for d in data["devices"] if d["id"] != device_id]
        _save(data)
        return {"ok": True, "id": device_id}


def set_admin(device_id: str, admin: bool = True) -> dict[str, Any]:
    with _lock:
        data = _load()
        target = next((d for d in data["devices"] if d["id"] == device_id), None)
        if not target:
            return {"ok": False, "error": "Device not found"}
        if not admin and target.get("admin"):
            admins = [d for d in data["devices"] if d.get("admin") and not d.get("revoked")]
            if len(admins) <= 1:
                return {"ok": False, "error": "Cannot remove the last admin"}
        target["admin"] = bool(admin)
        _save(data)
        return {"ok": True, "id": device_id, "admin": bool(admin)}


def _token_matches(a: str, b: str) -> bool:
    if not a or not b or len(a) != len(b):
        return False
    return secrets.compare_digest(a, b)


def find_valid_device_token(token: str) -> dict[str, Any] | None:
    token = (token or "").strip()
    if not token:
        return None
    with _lock:
        data = _load()
        for d in data["devices"]:
            if d.get("revoked"):
                continue
            if _token_matches(token, d.get("token") or ""):
                now = _now()
                prev = d.get("last_seen")
                should_touch = True
                if prev:
                    try:
                        should_touch = (now - _parse_iso(prev)).total_seconds() > 60
                    except ValueError:
                        should_touch = True
                if should_touch:
                    d["last_seen"] = _iso(now)
                    _save(data)
                return d
    return None


def session_info(token: str) -> dict[str, Any] | None:
    """Return public session fields for a device token, or master."""
    if master_token_ok(token):
        return {
            "device_id": None,
            "device_name": "Master token",
            "admin": True,
            "master": True,
        }
    d = find_valid_device_token(token)
    if not d:
        return None
    return {
        "device_id": d["id"],
        "device_name": d["name"],
        "admin": bool(d.get("admin")),
        "master": False,
    }


def is_admin_token(token: str) -> bool:
    info = session_info(token)
    return bool(info and info.get("admin"))


def redeem_invite(invite_token: str) -> dict[str, Any]:
    """Exchange a one-time invite for a long-lived device token."""
    invite_token = (invite_token or "").strip()
    if not invite_token:
        return {"ok": False, "error": "Missing token"}

    existing = find_valid_device_token(invite_token)
    if existing:
        return {
            "ok": True,
            "kind": "device",
            "device_id": existing["id"],
            "device_name": existing["name"],
            "device_token": existing["token"],
            "admin": bool(existing.get("admin")),
        }

    with _lock:
        data = _load()
        now = _now()
        inv = None
        for candidate in data["invites"]:
            if candidate.get("used"):
                continue
            if _parse_iso(candidate["expires_at"]) < now:
                continue
            if _token_matches(invite_token, candidate.get("token") or ""):
                inv = candidate
                break
        if not inv:
            return {
                "ok": False,
                "error": "Invite invalid, used, or expired",
            }

        # First registered device becomes admin (so UI management always has an owner)
        make_admin = not _has_admin(data)
        device = {
            "id": f"dev_{secrets.token_hex(6)}",
            "name": inv["name"],
            "token": secrets.token_urlsafe(32),
            "created_at": _iso(now),
            "last_seen": _iso(now),
            "revoked": False,
            "admin": make_admin,
            "from_invite_id": inv["id"],
        }
        inv["used"] = True
        inv["used_at"] = _iso(now)
        inv["device_id"] = device["id"]
        inv["token"] = ""
        data["devices"].append(device)
        cutoff = now - timedelta(days=7)
        data["invites"] = [
            i
            for i in data["invites"]
            if not (
                i.get("used")
                and i.get("used_at")
                and _parse_iso(i["used_at"]) < cutoff
            )
        ]
        _save(data)

    return {
        "ok": True,
        "kind": "invite",
        "device_id": device["id"],
        "device_name": device["name"],
        "device_token": device["token"],
        "admin": make_admin,
        "message": f'Registered as "{device["name"]}". Invite link is now spent.',
    }


def master_token_ok(token: str) -> bool:
    master = os.environ.get("BT_SPEAKER_TOKEN", "").strip()
    if not master or not token or len(master) != len(token):
        return False
    return secrets.compare_digest(master, token)


def admin_registry() -> dict[str, Any]:
    return {
        "ok": True,
        "devices": list_devices(),
        "invites": list_invites(include_used=True, include_secrets=True),
        "invite_hours_default": INVITE_TTL_HOURS,
    }
