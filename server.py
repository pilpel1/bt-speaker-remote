#!/usr/bin/env python3
"""BT Speaker Remote — local Bluetooth and YouTube audio control panel."""

from __future__ import annotations

import os
import socket
from functools import wraps
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

import auth_store
import bluetooth_ctl as bt
import library
import media_store
import player

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"

app = Flask(__name__, static_folder=str(STATIC), static_url_path="/static")
app.config["MAX_CONTENT_LENGTH"] = library.MAX_UPLOAD_BYTES


def _extract_token() -> str:
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    header = request.headers.get("X-Api-Token", "").strip()
    if header:
        return header
    return (request.args.get("token") or "").strip()


def _request_authorized() -> bool:
    token = _extract_token()
    if not token:
        return False
    if auth_store.master_token_ok(token):
        return True
    return auth_store.find_valid_device_token(token) is not None


def require_token(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not _request_authorized():
            return jsonify({"ok": False, "error": "Unauthorized", "auth_required": True}), 401
        return fn(*args, **kwargs)

    return wrapper


def require_admin(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        token = _extract_token()
        if not token or not auth_store.is_admin_token(token):
            return jsonify({"ok": False, "error": "Admin only", "auth_required": True}), 403
        return fn(*args, **kwargs)

    return wrapper


def _public_base_url() -> str:
    """Best-effort base URL for invite links shown in the admin UI."""
    forced = os.environ.get("BT_SPEAKER_PUBLIC_URL", "").strip().rstrip("/")
    if forced:
        return forced
    # Prefer Tailscale IP so copied links work from phones
    try:
        import subprocess

        ts = subprocess.check_output(
            ["tailscale", "ip", "-4"], text=True, timeout=2
        ).strip()
        if ts:
            port = os.environ.get("BT_SPEAKER_PORT", "8765")
            return f"http://{ts}:{port}"
    except Exception:
        pass
    return request.host_url.rstrip("/")


@app.after_request
def _no_cache_api(resp):
    if request.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


@app.errorhandler(413)
def _too_large(_e):
    return jsonify({"ok": False, "error": "File too large (max 80MB)"}), 413


@app.get("/")
def index():
    return send_from_directory(STATIC, "index.html")


@app.get("/manifest.webmanifest")
def manifest():
    resp = send_from_directory(STATIC, "manifest.webmanifest")
    resp.headers["Content-Type"] = "application/manifest+json"
    return resp


@app.get("/sw.js")
def service_worker():
    resp = send_from_directory(STATIC, "sw.js")
    resp.headers["Content-Type"] = "application/javascript; charset=utf-8"
    resp.headers["Service-Worker-Allowed"] = "/"
    resp.headers["Cache-Control"] = "no-cache"
    return resp


@app.get("/api/health")
def health():
    return jsonify(
        {
            "ok": True,
            "service": "bt-speaker-remote",
            "auth_required": True,
            "invite_hours": auth_store.INVITE_TTL_HOURS,
        }
    )


@app.post("/api/auth/redeem")
def auth_redeem():
    """Public: exchange 24h invite → long-lived device token (or validate existing)."""
    data = request.get_json(silent=True) or {}
    token = (data.get("token") or request.args.get("token") or "").strip()
    result = auth_store.redeem_invite(token)
    code = 200 if result.get("ok") else 401
    return jsonify(result), code


@app.get("/api/auth/me")
@require_token
def auth_me():
    info = auth_store.session_info(_extract_token())
    return jsonify({"ok": True, "auth": info})


@app.get("/api/auth/admin/registry")
@require_token
@require_admin
def auth_admin_registry():
    reg = auth_store.admin_registry()
    base = _public_base_url()
    for inv in reg["invites"]:
        if inv.get("open") and inv.get("token"):
            inv["invite_url"] = f"{base}/?token={inv['token']}"
    return jsonify(reg)


@app.post("/api/auth/admin/invite")
@require_token
@require_admin
def auth_admin_invite():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"ok": False, "error": "Provide a device name"}), 400
    hours = data.get("hours")
    try:
        hours_i = int(hours) if hours is not None else auth_store.INVITE_TTL_HOURS
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "Invalid hours"}), 400
    inv = auth_store.create_invite(name, hours=hours_i)
    base = _public_base_url()
    return jsonify(
        {
            "ok": True,
            "invite": {
                **{k: v for k, v in inv.items()},
                "invite_url": f"{base}/?token={inv['token']}",
                "open": True,
            },
        }
    )


@app.post("/api/auth/admin/revoke")
@require_token
@require_admin
def auth_admin_revoke():
    data = request.get_json(silent=True) or {}
    device_id = (data.get("device_id") or data.get("id") or "").strip()
    if not device_id:
        return jsonify({"ok": False, "error": "Missing device_id"}), 400
    result = auth_store.revoke_device(device_id)
    code = 200 if result.get("ok") else 400
    return jsonify(result), code


@app.post("/api/auth/admin/delete")
@require_token
@require_admin
def auth_admin_delete():
    data = request.get_json(silent=True) or {}
    device_id = (data.get("device_id") or data.get("id") or "").strip()
    if not device_id:
        return jsonify({"ok": False, "error": "Missing device_id"}), 400
    result = auth_store.delete_device(device_id)
    code = 200 if result.get("ok") else 400
    return jsonify(result), code


@app.post("/api/auth/admin/delete-invite")
@require_token
@require_admin
def auth_admin_delete_invite():
    data = request.get_json(silent=True) or {}
    invite_id = (data.get("invite_id") or data.get("id") or "").strip()
    if not invite_id:
        return jsonify({"ok": False, "error": "Missing invite_id"}), 400
    ok = auth_store.delete_invite(invite_id)
    if not ok:
        return jsonify({"ok": False, "error": "Invite not found"}), 404
    return jsonify({"ok": True, "id": invite_id})


@app.get("/api/status")
@require_token
def status():
    light = str(request.args.get("light") or "").lower() in ("1", "true", "yes")
    try:
        if light:
            b = bt.get_status_cached(force=False, fetch=False)
            if not b:
                b = {"powered": True, "connected": [], "devices": []}
            # pactl only — bluetoothctl on page refresh can drop A2DP (BCM43142).
            if player.has_bt_audio() and not (b.get("connected") or []):
                b = {
                    **b,
                    "powered": True,
                    "connected": [{"name": "רמקול", "connected": True, "is_audio": True}],
                }
        else:
            b = bt.get_status_cached(force=True, fetch=True)
    except Exception as e:
        b = {"error": str(e), "powered": False, "connected": [], "devices": []}
    try:
        p = player.get_status()
        v = player.get_volume()
    except Exception as e:
        p = {"error": str(e)}
        v = {}
    host = socket.gethostname()
    auth = auth_store.session_info(_extract_token())
    return jsonify(
        {
            "ok": True,
            "host": host,
            "bluetooth": b,
            "player": p,
            "volume": v.get("volume"),
            "auth": auth,
            "light": light,
        }
    )


@app.post("/api/bluetooth/power")
@require_token
def bluetooth_power():
    data = request.get_json(silent=True) or {}
    on = data.get("on")
    if on is None:
        return jsonify({"ok": False, "error": 'Provide {"on": true|false}'}), 400
    try:
        result = bt.power_on() if on else bt.power_off()
        return jsonify(result)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.post("/api/bluetooth/scan")
@require_token
def bluetooth_scan():
    data = request.get_json(silent=True) or {}
    seconds = float(data.get("seconds", 18))
    seconds = max(5, min(30, seconds))
    wait = bool(data.get("wait", True))
    try:
        if wait:
            return jsonify(bt.scan_and_wait(seconds))
        return jsonify(bt.start_scan(seconds))
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.get("/api/bluetooth/devices")
@require_token
def bluetooth_devices():
    try:
        devices = bt.list_devices()
        return jsonify({"ok": True, "devices": devices, "count": len(devices)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.post("/api/bluetooth/connect")
@require_token
def bluetooth_connect():
    data = request.get_json(silent=True) or {}
    address = (data.get("address") or "").strip()
    if not address:
        return jsonify({"ok": False, "error": "Missing address"}), 400
    try:
        result = bt.connect(address)
        player.ensure_bt_sink_default()
        return jsonify(result)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.post("/api/bluetooth/disconnect")
@require_token
def bluetooth_disconnect():
    data = request.get_json(silent=True) or {}
    address = data.get("address") or None
    try:
        player.stop()
        return jsonify(bt.disconnect(address))
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.post("/api/bluetooth/remove")
@require_token
def bluetooth_remove():
    data = request.get_json(silent=True) or {}
    address = (data.get("address") or "").strip()
    if not address:
        return jsonify({"ok": False, "error": "Missing address"}), 400
    try:
        player.stop()
        return jsonify(bt.remove_device(address))
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


def _bt_speaker_connected() -> bool:
    """Soft check: Pulse bluez sink OR a connected BlueZ audio device."""
    if player.has_bt_audio():
        return True
    try:
        st = bt.get_status()
        connected = st.get("connected") or []
        return any(d.get("is_audio") for d in connected)
    except Exception:
        return False


def _ensure_speaker_ready():
    """Return (error_response, status_code) or (None, None) if ready."""
    if not _bt_speaker_connected():
        return jsonify({"ok": False, "error": "No Bluetooth speaker connected"}), 400
    try:
        st = bt.get_status()
        if not st.get("powered"):
            bt.power_on()
    except Exception:
        pass
    return None, None


def _record_play_history(
    result: dict,
    *,
    source: str,
    url: str | None = None,
    file_id: str | None = None,
    playlist_id: str | None = None,
    title: str | None = None,
) -> None:
    if not result.get("ok"):
        return
    media_store.add_history(
        title=title or result.get("title"),
        source=source,
        url=url or result.get("url"),
        file_id=file_id,
        playlist_id=playlist_id,
    )


@app.post("/api/play")
@require_token
def play():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or data.get("link") or "").strip()
    file_id = (data.get("file_id") or "").strip()
    if not url and not file_id:
        return jsonify({"ok": False, "error": "Missing url or file_id"}), 400
    try:
        err, code = _ensure_speaker_ready()
        if err is not None:
            return err, code
        title = (data.get("title") or "").strip() or None
        if file_id:
            item = library.resolve(file_id)
            if not item:
                return jsonify({"ok": False, "error": "File not found"}), 404
            result = player.play(str(item["path"]), title=item.get("title") or title)
            _record_play_history(
                result,
                source="file",
                file_id=file_id,
                title=item.get("title"),
            )
        else:
            result = player.play(url, title=title)
            _record_play_history(result, source="url", url=url, title=title)
        code = 200 if result.get("ok") else 500
        return jsonify(result), code
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.post("/api/play/playlist")
@require_token
def play_playlist():
    data = request.get_json(silent=True) or {}
    playlist_id = (data.get("playlist_id") or data.get("id") or "").strip()
    if not playlist_id:
        return jsonify({"ok": False, "error": "Missing playlist_id"}), 400
    pl = media_store.get_playlist(playlist_id)
    if not pl:
        return jsonify({"ok": False, "error": "Playlist not found"}), 404
    sources: list[str] = []
    for it in pl.get("items") or []:
        if it.get("kind") == "file" and it.get("file_id"):
            item = library.resolve(it["file_id"])
            if item:
                sources.append(str(item["path"]))
        elif it.get("kind") == "url" and it.get("url"):
            sources.append(it["url"])
    if not sources:
        return jsonify({"ok": False, "error": "Playlist is empty"}), 400
    try:
        err, code = _ensure_speaker_ready()
        if err is not None:
            return err, code
        result = player.play_list(
            sources,
            title=pl.get("name"),
            start_index=int(data.get("start_index") or data.get("index") or 0),
        )
        _record_play_history(
            result,
            source="playlist",
            playlist_id=playlist_id,
            title=pl.get("name"),
        )
        code = 200 if result.get("ok") else 500
        return jsonify(result), code
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.get("/api/library")
@require_token
def library_list():
    try:
        return jsonify(library.list_files())
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "files": []}), 500


@app.post("/api/library")
@require_token
def library_upload():
    f = request.files.get("file") or request.files.get("audio")
    if not f or not f.filename:
        return jsonify({"ok": False, "error": "Missing file"}), 400
    kind = (request.form.get("kind") or request.args.get("kind") or "uploads").strip()
    try:
        data = f.read()
        result = library.save_bytes(f.filename, data, kind=kind)
        code = 200 if result.get("ok") else 400
        return jsonify(result), code
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.delete("/api/library/<file_id>")
@require_token
def library_delete(file_id: str):
    try:
        result = library.delete_file(file_id)
        code = 200 if result.get("ok") else 404
        return jsonify(result), code
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.post("/api/library/delete")
@require_token
def library_delete_post():
    data = request.get_json(silent=True) or {}
    file_id = (data.get("file_id") or data.get("id") or "").strip()
    if not file_id:
        return jsonify({"ok": False, "error": "Missing file_id"}), 400
    try:
        result = library.delete_file(file_id)
        code = 200 if result.get("ok") else 404
        return jsonify(result), code
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.post("/api/library/save-url")
@require_token
def library_save_url():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or data.get("link") or "").strip()
    if not url:
        return jsonify({"ok": False, "error": "Missing url"}), 400
    try:
        result = library.save_url_async(url)
        code = 200 if result.get("ok") else 400
        return jsonify(result), code
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.post("/api/record")
@require_token
def record_upload():
    f = request.files.get("file") or request.files.get("audio")
    if not f:
        return jsonify({"ok": False, "error": "Missing file"}), 400
    play_now = str(request.form.get("play") or request.args.get("play") or "").lower() in (
        "1",
        "true",
        "yes",
    )
    filename = f.filename or "recording.webm"
    if not Path(filename).suffix:
        filename = filename + ".webm"
    try:
        data = f.read()
        result = library.save_bytes(filename, data, kind="recordings")
        if not result.get("ok"):
            return jsonify(result), 400
        file_info = result.get("file") or {}
        if play_now:
            err, code = _ensure_speaker_ready()
            if err is not None:
                return jsonify({**result, "played": False, "play_error": "No Bluetooth speaker connected"}), 200
            item = library.resolve(file_info.get("id") or "")
            if item:
                played = player.play(str(item["path"]), title=item.get("title") or "הקלטה")
                _record_play_history(
                    played,
                    source="file",
                    file_id=file_info.get("id"),
                    title=item.get("title") or "הקלטה",
                )
                result["played"] = bool(played.get("ok"))
                result["player"] = played
                if not played.get("ok"):
                    result["play_error"] = played.get("error")
            else:
                result["played"] = False
        return jsonify(result)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.get("/api/playlists")
@require_token
def playlists_list():
    try:
        pls = media_store.list_playlists()
        return jsonify({"ok": True, "playlists": pls, "count": len(pls)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "playlists": []}), 500


@app.post("/api/playlists")
@require_token
def playlists_create():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"ok": False, "error": "Provide a playlist name"}), 400
    try:
        pl = media_store.create_playlist(name)
        return jsonify({"ok": True, "playlist": pl})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.patch("/api/playlists/<playlist_id>")
@require_token
def playlists_rename(playlist_id: str):
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    try:
        result = media_store.rename_playlist(playlist_id, name)
        code = 200 if result.get("ok") else 400
        return jsonify(result), code
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.delete("/api/playlists/<playlist_id>")
@require_token
def playlists_delete(playlist_id: str):
    try:
        result = media_store.delete_playlist(playlist_id)
        code = 200 if result.get("ok") else 404
        return jsonify(result), code
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.post("/api/playlists/<playlist_id>/items")
@require_token
def playlists_add_item(playlist_id: str):
    data = request.get_json(silent=True) or {}
    kind = (data.get("kind") or "").strip()
    try:
        result = media_store.add_item(
            playlist_id,
            kind=kind,
            title=data.get("title"),
            file_id=data.get("file_id"),
            url=data.get("url") or data.get("link"),
        )
        code = 200 if result.get("ok") else 400
        return jsonify(result), code
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.delete("/api/playlists/<playlist_id>/items/<item_id>")
@require_token
def playlists_remove_item(playlist_id: str, item_id: str):
    try:
        result = media_store.remove_item(playlist_id, item_id)
        code = 200 if result.get("ok") else 404
        return jsonify(result), code
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.post("/api/playlists/<playlist_id>/items/reorder")
@require_token
def playlists_reorder(playlist_id: str):
    data = request.get_json(silent=True) or {}
    item_ids = data.get("item_ids") or data.get("ids") or []
    if not isinstance(item_ids, list):
        return jsonify({"ok": False, "error": "item_ids must be a list"}), 400
    try:
        result = media_store.reorder_items(playlist_id, item_ids)
        code = 200 if result.get("ok") else 400
        return jsonify(result), code
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.get("/api/history")
@require_token
def history_list():
    try:
        items = media_store.list_history()
        return jsonify({"ok": True, "items": items, "count": len(items)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "items": []}), 500


@app.post("/api/stop")
@require_token
def stop():
    try:
        return jsonify(player.stop())
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.post("/api/pause")
@require_token
def pause():
    try:
        return jsonify(player.pause())
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.post("/api/resume")
@require_token
def resume():
    try:
        return jsonify(player.resume())
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.post("/api/seek")
@require_token
def seek():
    data = request.get_json(silent=True) or {}
    seconds = data.get("seconds")
    percent = data.get("percent")
    if seconds is None and percent is None:
        return jsonify({"ok": False, "error": 'Provide {"seconds": N} or {"percent": N}'}), 400
    try:
        result = player.seek(
            seconds=float(seconds) if seconds is not None else None,
            percent=float(percent) if percent is not None else None,
        )
        code = 200 if result.get("ok") else 400
        return jsonify(result), code
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "Invalid seconds/percent"}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.post("/api/skip")
@require_token
def skip_tracks():
    data = request.get_json(silent=True) or {}
    try:
        if data.get("index") is not None:
            result = player.skip_tracks(index=int(data.get("index")))
        else:
            result = player.skip_tracks(delta=int(data.get("delta", data.get("n", 1))))
        if result.get("superseded"):
            return jsonify({**player.get_status(), "ok": True, "superseded": True})
        code = 200 if result.get("ok") else 400
        return jsonify(result), code
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "Invalid delta"}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.post("/api/next")
@require_token
def next_track():
    try:
        result = player.skip_tracks(1)
        if result.get("superseded"):
            return jsonify({**player.get_status(), "ok": True, "superseded": True})
        code = 200 if result.get("ok") else 400
        return jsonify(result), code
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.post("/api/previous")
@require_token
def previous_track():
    try:
        result = player.skip_tracks(-1)
        if result.get("superseded"):
            return jsonify({**player.get_status(), "ok": True, "superseded": True})
        code = 200 if result.get("ok") else 400
        return jsonify(result), code
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/search", methods=["GET", "POST"])
@require_token
def search():
    data = request.get_json(silent=True) or {}
    q = (data.get("q") or data.get("query") or request.args.get("q") or request.args.get("query") or "").strip()
    limit = data.get("limit", request.args.get("limit", 10))
    if not q:
        return jsonify({"ok": False, "error": "Missing q", "results": []}), 400
    try:
        result = player.search_youtube(q, limit=limit)
        code = 200 if result.get("ok") else 500
        return jsonify(result), code
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "results": []}), 500


@app.post("/api/volume")
@require_token
def volume():
    data = request.get_json(silent=True) or {}
    if "percent" not in data and "volume" not in data:
        return jsonify({"ok": False, "error": "Provide percent"}), 400
    percent = data.get("percent", data.get("volume"))
    try:
        return jsonify(player.set_volume(int(percent)))
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


def main() -> None:
    auth_store.ensure_store()
    media_store.ensure_store()
    library.ensure_dirs()
    host = os.environ.get("BT_SPEAKER_HOST", "0.0.0.0")
    port = int(os.environ.get("BT_SPEAKER_PORT", "8765"))
    print(f"BT Speaker Remote → http://{host}:{port}")
    print("On Tailscale, open: http://<this-machine-tailscale-ip>:8765")
    print(f"Auth: device invites ({auth_store.INVITE_TTL_HOURS}h) → long-lived device tokens")
    print(f"Store: {auth_store.STORE_PATH}")
    try:
        from waitress import serve

        serve(app, host=host, port=port, threads=8)
    except ImportError:
        app.run(host=host, port=port, threaded=True, debug=False)


if __name__ == "__main__":
    main()
