"""YouTube / URL audio playback via mpv (+ yt-dlp) with IPC pause/resume/seek."""

from __future__ import annotations

import json
import os
import re
import signal
import socket
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

_lock = threading.RLock()
_proc: subprocess.Popen[str] | None = None
_state: dict[str, Any] = {
    "playing": False,
    "paused": False,
    "url": None,
    "title": None,
    "started_at": None,
    "error": None,
    "sink": None,
}

_RUNTIME = Path(os.environ.get("XDG_RUNTIME_DIR", f"/tmp/user-{os.getuid()}"))
IPC_PATH = _RUNTIME / "bt-speaker-remote-mpv.sock"


def _run(args: list[str], timeout: float = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)


def _list_bt_sink() -> str | None:
    result = _run(["pactl", "list", "short", "sinks"], timeout=5)
    for line in (result.stdout or "").splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1].startswith("bluez_output."):
            return parts[1]
    return None


def _default_sink_name() -> str | None:
    r = _run(["pactl", "get-default-sink"], timeout=5)
    name = (r.stdout or "").strip()
    return name or None


def ensure_bt_sink_default() -> str | None:
    """Prefer a connected bluez sink as default output."""
    bt_sink = _list_bt_sink()
    if bt_sink:
        _run(["pactl", "set-default-sink", bt_sink], timeout=5)
        _run(["pactl", "set-sink-mute", bt_sink, "0"], timeout=5)
    return bt_sink


def has_bt_audio() -> bool:
    """True when PulseAudio/PipeWire has a bluez output sink."""
    return _list_bt_sink() is not None


def resolve_title(url: str) -> str | None:
    """Resolve a display title. Playlist-aware (no --no-playlist)."""
    try:
        r = _run(
            [
                "yt-dlp",
                "--flat-playlist",
                "--playlist-end",
                "1",
                "--print",
                "%(playlist_title)s|||%(playlist_count)s|||%(title)s",
                url,
            ],
            timeout=45,
        )
        lines = [ln.strip() for ln in (r.stdout or "").splitlines() if ln.strip()]
        if not lines:
            return None
        parts = lines[0].split("|||")
        pl_title = (parts[0] if parts else "").strip()
        pl_count_raw = (parts[1] if len(parts) > 1 else "").strip()
        first_title = (parts[2] if len(parts) > 2 else "").strip()

        def _na(s: str) -> bool:
            return not s or s.upper() == "NA"

        pl_count = 0
        try:
            if not _na(pl_count_raw):
                pl_count = int(float(pl_count_raw))
        except ValueError:
            pl_count = 0

        looks_like_playlist = pl_count > 1 or (
            "list=" in url.lower() and not _na(pl_title)
        )
        if looks_like_playlist:
            if not _na(pl_title):
                return pl_title
            if not _na(first_title):
                return f"Playlist · {first_title}"
            return "Playlist"
        if not _na(first_title):
            return first_title
        return None
    except Exception:
        return None


def search_youtube(query: str, limit: int = 10) -> dict[str, Any]:
    """Search YouTube via yt-dlp ytsearchN:query. Returns list of {id,title,url,duration?}."""
    query = (query or "").strip()
    if not query:
        return {"ok": False, "error": "Missing query", "results": []}
    try:
        limit_i = max(1, min(25, int(limit)))
    except (TypeError, ValueError):
        limit_i = 10
    try:
        r = _run(
            [
                "yt-dlp",
                "--flat-playlist",
                "--print",
                "%(id)s|||%(title)s|||%(webpage_url)s|||%(duration)s",
                f"ytsearch{limit_i}:{query}",
            ],
            timeout=60,
        )
        if r.returncode != 0 and not (r.stdout or "").strip():
            err = (r.stderr or "").strip()[-400:] or f"yt-dlp exited {r.returncode}"
            return {"ok": False, "error": err, "results": [], "query": query}

        results: list[dict[str, Any]] = []
        for line in (r.stdout or "").splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split("|||")
            if len(parts) < 2:
                continue
            vid_id = parts[0].strip()
            title = parts[1].strip()
            url = parts[2].strip() if len(parts) > 2 else ""
            duration: float | None = None
            if len(parts) > 3:
                raw_dur = parts[3].strip()
                if raw_dur and raw_dur.upper() not in ("NA", "NONE", "NULL"):
                    try:
                        duration = float(raw_dur)
                    except ValueError:
                        duration = None
            if not url or url.upper() == "NA":
                if vid_id and vid_id.upper() != "NA":
                    url = f"https://www.youtube.com/watch?v={vid_id}"
                else:
                    continue
            results.append(
                {
                    "id": vid_id if vid_id.upper() != "NA" else None,
                    "title": title if title.upper() != "NA" else url,
                    "url": url,
                    "duration": duration,
                }
            )
        return {
            "ok": True,
            "query": query,
            "results": results,
            "count": len(results),
        }
    except Exception as e:
        return {"ok": False, "error": str(e), "results": [], "query": query}


def _cleanup_ipc() -> None:
    try:
        if IPC_PATH.exists():
            IPC_PATH.unlink()
    except OSError:
        pass


def _mpv_ipc(command: list[Any], timeout: float = 2.0) -> dict[str, Any] | None:
    """Send a JSON IPC command to the running mpv. Returns parsed response or None."""
    if not IPC_PATH.exists():
        return None
    payload = json.dumps({"command": command}).encode("utf-8") + b"\n"
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            sock.connect(str(IPC_PATH))
            sock.sendall(payload)
            data = b""
            while b"\n" not in data:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                data += chunk
        line = data.split(b"\n", 1)[0].decode("utf-8", errors="replace")
        return json.loads(line) if line else None
    except (OSError, json.JSONDecodeError, TimeoutError):
        return None


def _mpv_get(prop: str) -> Any:
    resp = _mpv_ipc(["get_property", prop])
    if resp and resp.get("error") == "success":
        return resp.get("data")
    return None


def _mpv_ok(resp: dict[str, Any] | None) -> bool:
    return bool(resp and resp.get("error") == "success")


def _with_status(ok: bool, error: str | None = None, **extra: Any) -> dict[str, Any]:
    """Merge status; put error after get_status so it is not overwritten."""
    out = {"ok": ok, **get_status(), **extra}
    if error is not None:
        out["error"] = error
    return out


def _watch_proc(proc: subprocess.Popen[str], url: str) -> None:
    global _proc
    proc.wait()
    with _lock:
        if _proc is proc:
            _state["playing"] = False
            _state["paused"] = False
            if proc.returncode not in (0, -signal.SIGTERM, -15, -signal.SIGINT, -2):
                err = ""
                try:
                    if proc.stderr:
                        err = proc.stderr.read()[-500:]
                except Exception:
                    pass
                if err:
                    _state["error"] = err
            _proc = None
            _cleanup_ipc()


def stop() -> dict[str, Any]:
    global _proc
    with _lock:
        proc = _proc
        _proc = None
        _state["playing"] = False
        _state["paused"] = False
    if proc and proc.poll() is None:
        # Prefer graceful quit via IPC
        _mpv_ipc(["quit"])
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            try:
                proc.send_signal(signal.SIGINT)
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
    _cleanup_ipc()
    return _with_status(True)


def play(url: str) -> dict[str, Any]:
    url = (url or "").strip()
    if not url:
        return {"ok": False, "error": "Missing URL"}

    sink = ensure_bt_sink_default()

    title = resolve_title(url) or url
    stop()
    _cleanup_ipc()

    # Ensure runtime dir exists for the IPC socket
    try:
        IPC_PATH.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass

    env = os.environ.copy()
    # Do NOT pass --no-playlist — allow YouTube playlists/mixes
    cmd = [
        "mpv",
        "--no-video",
        "--really-quiet",
        "--no-terminal",
        "--force-window=no",
        f"--input-ipc-server={IPC_PATH}",
        f"--title=bt-speaker-remote:{title[:80]}",
        "--ytdl-format=bestaudio/best",
        url,
    ]
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
    except FileNotFoundError:
        return {"ok": False, "error": "mpv is not installed"}

    with _lock:
        global _proc
        _proc = proc
        _state.update(
            {
                "playing": True,
                "paused": False,
                "url": url,
                "title": title,
                "started_at": time.time(),
                "error": None,
                "sink": sink,
            }
        )

    threading.Thread(target=_watch_proc, args=(proc, url), daemon=True).start()

    # Brief check — if mpv dies immediately, surface error
    time.sleep(1.2)
    if proc.poll() is not None:
        err = ""
        try:
            if proc.stderr:
                err = (proc.stderr.read() or "")[-800:]
        except Exception:
            pass
        with _lock:
            _state["playing"] = False
            _state["error"] = err or f"mpv exited with code {proc.returncode}"
        _cleanup_ipc()
        return {"ok": False, "error": _state["error"], "title": title, "sink": sink}

    return {"ok": True, "title": title, "url": url, "sink": sink, **get_status()}


def pause() -> dict[str, Any]:
    with _lock:
        proc = _proc
        if not proc or proc.poll() is not None:
            return _with_status(False, "Nothing playing")
    resp = _mpv_ipc(["set_property", "pause", True])
    # mpv JSON IPC sets "error": "success" on OK
    if not _mpv_ok(resp):
        return _with_status(False, "mpv IPC pause failed — is playback running?")
    with _lock:
        _state["paused"] = True
        _state["playing"] = False
    return _with_status(True)


def resume() -> dict[str, Any]:
    with _lock:
        proc = _proc
        if not proc or proc.poll() is not None:
            return _with_status(False, "Nothing to resume")
    resp = _mpv_ipc(["set_property", "pause", False])
    if not _mpv_ok(resp):
        return _with_status(False, "mpv IPC resume failed")
    with _lock:
        _state["paused"] = False
        _state["playing"] = True
    return _with_status(True)


def seek(
    seconds: float | None = None,
    percent: float | None = None,
) -> dict[str, Any]:
    """Seek absolute seconds and/or percent. Prefer seconds if both given."""
    with _lock:
        proc = _proc
        if not proc or proc.poll() is not None:
            return _with_status(False, "Nothing playing")

    if seconds is not None:
        try:
            sec = float(seconds)
        except (TypeError, ValueError):
            return _with_status(False, "Invalid seconds")
        resp = _mpv_ipc(["seek", sec, "absolute"])
        if not _mpv_ok(resp):
            return _with_status(False, "mpv seek (seconds) failed")
        return _with_status(True)

    if percent is not None:
        try:
            pct = float(percent)
        except (TypeError, ValueError):
            return _with_status(False, "Invalid percent")
        pct = max(0.0, min(100.0, pct))
        resp = _mpv_ipc(["seek", pct, "absolute-percent"])
        if not _mpv_ok(resp):
            return _with_status(False, "mpv seek (percent) failed")
        return _with_status(True)

    return _with_status(False, "Provide seconds or percent")


def next_track() -> dict[str, Any]:
    with _lock:
        proc = _proc
        if not proc or proc.poll() is not None:
            return _with_status(False, "Nothing playing")
    resp = _mpv_ipc(["playlist-next", "weak"])
    if not _mpv_ok(resp):
        return _with_status(False, "playlist-next failed (end of playlist?)")
    time.sleep(0.15)
    media = _mpv_get("media-title")
    if isinstance(media, str) and media.strip():
        with _lock:
            _state["title"] = media.strip()
    return _with_status(True)


def previous_track() -> dict[str, Any]:
    with _lock:
        proc = _proc
        if not proc or proc.poll() is not None:
            return _with_status(False, "Nothing playing")
    resp = _mpv_ipc(["playlist-prev", "weak"])
    if not _mpv_ok(resp):
        return _with_status(False, "playlist-prev failed (start of playlist?)")
    time.sleep(0.15)
    media = _mpv_get("media-title")
    if isinstance(media, str) and media.strip():
        with _lock:
            _state["title"] = media.strip()
    return _with_status(True)


def get_status() -> dict[str, Any]:
    with _lock:
        alive = bool(_proc and _proc.poll() is None)
        paused = bool(alive and _state.get("paused"))
        playing = bool(alive and not _state.get("paused"))
        base = {
            "playing": playing,
            "paused": paused,
            "url": _state.get("url"),
            "title": _state.get("title"),
            "started_at": _state.get("started_at"),
            "error": _state.get("error"),
            "sink": _state.get("sink"),
            "time_pos": None,
            "duration": None,
            "percent": None,
            "playlist_pos": None,
            "playlist_count": None,
        }

    if not alive:
        return base

    # Live pause bit from mpv (keeps status accurate if IPC used elsewhere)
    pause_prop = _mpv_get("pause")
    if isinstance(pause_prop, bool):
        with _lock:
            _state["paused"] = pause_prop
            _state["playing"] = not pause_prop
        base["paused"] = pause_prop
        base["playing"] = not pause_prop

    time_pos = _mpv_get("time-pos")
    duration = _mpv_get("duration")
    percent = _mpv_get("percent-pos")
    playlist_pos = _mpv_get("playlist-pos")
    playlist_count = _mpv_get("playlist-count")

    def _num(v: Any) -> float | None:
        if v is None:
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    base["time_pos"] = _num(time_pos)
    base["duration"] = _num(duration)
    base["percent"] = _num(percent)
    try:
        base["playlist_pos"] = int(playlist_pos) if playlist_pos is not None else None
    except (TypeError, ValueError):
        base["playlist_pos"] = None
    try:
        base["playlist_count"] = int(playlist_count) if playlist_count is not None else None
    except (TypeError, ValueError):
        base["playlist_count"] = None

    media = _mpv_get("media-title")
    if isinstance(media, str) and media.strip():
        # Prefer live track title when playlist advances
        pl_count = base.get("playlist_count") or 0
        if pl_count > 1:
            base["title"] = media.strip()
            with _lock:
                _state["title"] = media.strip()

    return base


def set_volume(percent: int) -> dict[str, Any]:
    percent = max(0, min(150, int(percent)))
    sink = ensure_bt_sink_default()
    target = sink or "@DEFAULT_SINK@"
    r = _run(["pactl", "set-sink-volume", target, f"{percent}%"], timeout=5)
    return {"ok": r.returncode == 0, "volume": percent, "sink": sink}


def get_volume() -> dict[str, Any]:
    """Read volume without changing the default sink."""
    sink = _list_bt_sink() or _default_sink_name() or "@DEFAULT_SINK@"
    r = _run(["pactl", "get-sink-volume", sink], timeout=5)
    text = r.stdout or ""
    m = re.search(r"/\s*(\d+)%", text)
    vol = int(m.group(1)) if m else None
    return {
        "ok": True,
        "volume": vol,
        "raw": text.strip(),
        "sink": sink if sink != "@DEFAULT_SINK@" else None,
    }
