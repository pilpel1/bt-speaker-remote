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
_proc: subprocess.Popen[Any] | None = None
_ytdl_proc: subprocess.Popen[Any] | None = None
_prefetch_proc: subprocess.Popen[Any] | None = None
_queue: list[str] = []
_queue_titles: list[str] = []
_queue_index: int = 0
_queue_title: str | None = None
_current_file: Path | None = None
_prefetch: dict[str, Any] = {
    "gen": 0,
    "status": "idle",
    "index": None,
    "url": None,
    "path": None,
    "error": None,
}
_err_lock = threading.Lock()
_err_buf: list[str] = []
_state: dict[str, Any] = {
    "playing": False,
    "paused": False,
    "url": None,
    "title": None,
    "started_at": None,
    "error": None,
    "sink": None,
    "loading": False,
}

_RUNTIME = Path(os.environ.get("XDG_RUNTIME_DIR", f"/tmp/user-{os.getuid()}"))
IPC_PATH = _RUNTIME / "bt-speaker-remote-mpv.sock"
PLAY_DIR = _RUNTIME / "bt-speaker-play"
_NODE = "/usr/bin/node" if os.path.isfile("/usr/bin/node") else "node"

# YouTube 2026: mpv's ytdl_hook gets HTTP 403. yt-dlp itself can download
# if it has a JS runtime + the `web` player client (android_vr URLs 403).
YTDLP_PREFIX = [
    "yt-dlp",
    "--js-runtimes",
    f"node:{_NODE}" if _NODE.startswith("/") else "node",
    "--extractor-args",
    "youtube:player_client=web_safari,web,mweb,tv",
    "--throttled-rate",
    "50K",
    "--retries",
    "8",
]
YTDLP_FORMAT = "best[protocol=m3u8_native][height<=480]/bestaudio/best/18"


def _run(args: list[str], timeout: float = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)


def _child_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PATH"] = "/usr/local/bin:/usr/bin:" + env.get("PATH", "")
    # PipeWire restores Movie/video streams at ~12–50%. Tag as music.
    env["PULSE_PROP_media.role"] = "music"
    env["PULSE_PROP_application.name"] = "bt-speaker-remote"
    env["PULSE_PROP_media.icon_name"] = "audio-headphones"
    return env


def _is_youtube(url: str) -> bool:
    s = (url or "").lower()
    return any(
        host in s
        for host in (
            "youtube.com",
            "youtu.be",
            "music.youtube.com",
            "youtube-nocookie.com",
        )
    )


def _looks_like_yt_playlist(url: str) -> bool:
    u = (url or "").lower()
    return _is_youtube(url) and (
        "list=" in u or "/playlist" in u or "start_radio=1" in u or "radio=1" in u
    )


def _yt_watch_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def _expand_yt_playlist(url: str, limit: int = 40) -> tuple[list[tuple[str, str]], str]:
    """Return ([(watch_url, title), ...], playlist_title)."""
    try:
        r = _run(
            [
                *YTDLP_PREFIX,
                "--yes-playlist",
                "--flat-playlist",
                "--playlist-end",
                str(limit),
                "--print",
                "%(playlist_title)s|||%(id)s|||%(webpage_url)s|||%(title)s",
                url,
            ],
            timeout=60,
        )
    except Exception:
        return ([(url, "")], "")
    entries: list[tuple[str, str]] = []
    pl_title = ""
    for line in (r.stdout or "").splitlines():
        parts = [p.strip() for p in line.split("|||")]
        while len(parts) < 4:
            parts.append("")
        raw_pl, vid, web, title = parts[0], parts[1], parts[2], parts[3]
        if raw_pl and raw_pl.upper() != "NA" and not pl_title:
            pl_title = raw_pl
        href = ""
        if web.startswith("http://") or web.startswith("https://"):
            href = web
        elif vid and vid.upper() != "NA":
            href = _yt_watch_url(vid)
        if not href:
            continue
        nice = "" if not title or title.upper() == "NA" else title
        if entries and entries[-1][0] == href:
            continue
        entries.append((href, nice))
    return (entries or [(url, "")], pl_title)


def _expand_sources(sources: list[str]) -> tuple[list[str], list[str], str]:
    urls: list[str] = []
    titles: list[str] = []
    pl_title = ""
    for src in sources:
        if _looks_like_yt_playlist(src):
            entries, name = _expand_yt_playlist(src)
            if name and not pl_title:
                pl_title = name
            for href, title in entries:
                if urls and urls[-1] == href:
                    continue
                urls.append(href)
                titles.append(title)
        else:
            urls.append(src)
            titles.append("")
    return urls, titles, pl_title


def _err_clear() -> None:
    with _err_lock:
        _err_buf.clear()


def _err_add(text: str) -> None:
    if not text:
        return
    with _err_lock:
        _err_buf.append(text)
        joined = "".join(_err_buf)
        if len(joined) > 8000:
            _err_buf[:] = [joined[-4000:]]


def _err_text() -> str:
    with _err_lock:
        return "".join(_err_buf).strip()


def _drain_bytes(pipe: Any) -> None:
    try:
        while True:
            chunk = pipe.read(4096)
            if not chunk:
                break
            if isinstance(chunk, bytes):
                _err_add(chunk.decode("utf-8", errors="replace"))
            else:
                _err_add(chunk)
    except Exception:
        pass


def _drain_text(pipe: Any) -> None:
    try:
        for line in pipe:
            _err_add(line)
    except Exception:
        pass


def _looks_like_fail(err: str) -> bool:
    s = err.lower()
    return any(
        tok in s
        for tok in (
            "403",
            "forbidden",
            "error",
            "failed to open",
            "no video or audio",
            "sign in",
        )
    )


def _friendly_error(raw: str) -> str:
    s = (raw or "").lower()
    if "403" in s or "forbidden" in s:
        return "יוטיוב חסם את הסטרים (403). צריך JS runtime + player_client=web."
    if "no supported javascript runtime" in s:
        return "חסר JS runtime ל-yt-dlp (node/deno)."
    if "requested format is not available" in s or "only images are available" in s:
        return "יוטיוב לא נתן פורמט אודיו לסרטון הזה."
    if "no video or audio" in s or "failed to open" in s:
        return "ההשמעה נכשלה בטעינת הסטרים מיוטיוב."
    tail = (raw or "").strip().splitlines()
    msg = tail[-1] if tail else "Playback failed"
    return msg[-300:]


def _cleanup_play_files() -> None:
    try:
        if PLAY_DIR.is_dir():
            for p in PLAY_DIR.iterdir():
                try:
                    p.unlink()
                except OSError:
                    pass
    except OSError:
        pass


def _kill_ytdl() -> None:
    global _ytdl_proc
    proc = _ytdl_proc
    _ytdl_proc = None
    if proc and proc.poll() is None:
        try:
            proc.kill()
        except Exception:
            pass
        try:
            proc.wait(timeout=1)
        except Exception:
            pass


def _kill_prefetch() -> None:
    global _prefetch_proc
    with _lock:
        _prefetch["gen"] = int(_prefetch.get("gen") or 0) + 1
        _prefetch.update(
            status="idle", index=None, url=None, path=None, error=None
        )
    proc = _prefetch_proc
    _prefetch_proc = None
    if proc and proc.poll() is None:
        try:
            proc.kill()
        except Exception:
            pass
        try:
            proc.wait(timeout=1)
        except Exception:
            pass


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


def _default_source_name() -> str | None:
    r = _run(["pactl", "get-default-source"], timeout=5)
    name = (r.stdout or "").strip()
    return name or None


def _bt_card_name() -> str | None:
    r = _run(["pactl", "list", "cards", "short"], timeout=5)
    for line in (r.stdout or "").splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1].startswith("bluez_card."):
            return parts[1]
    return None


def _card_active_profile(card: str) -> str:
    r = _run(["pactl", "list", "cards"], timeout=8)
    in_card = False
    for line in (r.stdout or "").splitlines():
        s = line.strip()
        if s.startswith("Name:"):
            in_card = s.split(":", 1)[1].strip() == card
        elif in_card and s.startswith("Active Profile:"):
            return s.split(":", 1)[1].strip()
    return ""


def _card_has_profile(card: str, profile: str) -> bool:
    r = _run(["pactl", "list", "cards"], timeout=8)
    in_card = False
    in_profiles = False
    for line in (r.stdout or "").splitlines():
        s = line.strip()
        if s.startswith("Name:"):
            in_card = s.split(":", 1)[1].strip() == card
            in_profiles = False
        elif in_card and s.startswith("Profiles:"):
            in_profiles = True
        elif in_card and s.startswith("Active Profile:"):
            return False
        elif in_card and in_profiles and s.startswith(profile + ":"):
            return True
    return False


def _prefer_internal_mic() -> None:
    """HFP steals the speaker into 8kHz mono. Don't use BT as default source."""
    src = _default_source_name()
    if not src or not src.startswith("bluez_input."):
        return
    r = _run(["pactl", "list", "short", "sources"], timeout=5)
    analog = None
    for line in (r.stdout or "").splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1].startswith("alsa_input.") and ".monitor" not in parts[1]:
            analog = parts[1]
            break
    if analog:
        _run(["pactl", "set-default-source", analog], timeout=5)


def _switch_to_a2dp(card: str) -> bool:
    """Headset/HFP is 8kHz mono. A2DP is stereo music."""
    active = _card_active_profile(card)
    if active.startswith("a2dp-sink"):
        return True
    _prefer_internal_mic()
    candidates = []
    for p in ("a2dp-sink-sbc_xq", "a2dp-sink", "a2dp-sink-aac", "a2dp-sink-aptx"):
        if _card_has_profile(card, p):
            candidates.append(p)
    if not candidates:
        candidates = ["a2dp-sink-sbc_xq", "a2dp-sink"]
    for p in candidates:
        r = _run(["pactl", "set-card-profile", card, p], timeout=8)
        if r.returncode == 0:
            time.sleep(0.5)
            if _list_bt_sink():
                return True
    return _card_active_profile(card).startswith("a2dp-sink")


def _move_inputs_to_sink(sink: str) -> None:
    inputs = _run(["pactl", "list", "short", "sink-inputs"], timeout=5)
    for line in (inputs.stdout or "").splitlines():
        idx = line.split()[0] if line.split() else None
        if idx and idx.isdigit():
            _run(["pactl", "move-sink-input", idx, sink], timeout=5)


def ensure_bt_sink_default() -> str | None:
    """Prefer A2DP (music) bluez sink as default output. Avoid HFP 8kHz."""
    card = _bt_card_name()
    if card:
        _switch_to_a2dp(card)
    bt_sink = _list_bt_sink()
    if bt_sink:
        _run(["pactl", "set-default-sink", bt_sink], timeout=5)
        _run(["pactl", "set-sink-mute", bt_sink, "0"], timeout=5)
        _move_inputs_to_sink(bt_sink)
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


def _watch_proc(proc: subprocess.Popen[Any], url: str) -> None:
    global _proc
    proc.wait()
    next_index: int | None = None
    with _lock:
        if _proc is not proc:
            return
        _proc = None
        _state["playing"] = False
        _state["paused"] = False
        _state["loading"] = False
        qlen = len(_queue)
        qidx = _queue_index
        rc = proc.returncode
        # Advance only on clean EOF. Do NOT treat leftover yt-dlp stderr
        # (403 retries that later succeeded) as a failure — that was stopping mixes.
        if rc == 0 and qlen > 1 and qidx + 1 < qlen:
            next_index = qidx + 1
            _state["loading"] = True
            _state["playing"] = True
        elif rc not in (0, None, -signal.SIGTERM, -15, -signal.SIGINT, -2):
            err = _err_text()
            _state["error"] = _friendly_error(err) or f"mpv exited {rc}"
    _cleanup_ipc()
    if next_index is not None:
        try:
            _play_from_index(next_index, wait_for_mpv=False)
        except Exception as e:
            with _lock:
                _state["playing"] = False
                _state["loading"] = False
                _state["error"] = str(e)[:300]


def stop() -> dict[str, Any]:
    global _proc, _queue, _queue_titles, _queue_index, _queue_title, _current_file
    with _lock:
        proc = _proc
        _proc = None
        _queue = []
        _queue_titles = []
        _queue_index = 0
        _queue_title = None
        _state["playing"] = False
        _state["paused"] = False
        _state["loading"] = False
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
    _kill_prefetch()
    _kill_ytdl()
    _cleanup_ipc()
    _cleanup_play_files()
    _current_file = None
    return _with_status(True)


def _is_http_url(src: str) -> bool:
    s = (src or "").strip().lower()
    return s.startswith("http://") or s.startswith("https://") or s.startswith("ytdl://")


def _local_title(path: str) -> str:
    return Path(path).stem.replace("_", " ").strip() or Path(path).name


def _normalize_sources(items: list[str]) -> list[str]:
    out: list[str] = []
    for raw in items:
        src = (raw or "").strip()
        if not src:
            continue
        if _is_http_url(src):
            out.append(src)
            continue
        p = Path(src).expanduser()
        if p.is_file():
            out.append(str(p.resolve()))
    return out


def play(url: str, title: str | None = None) -> dict[str, Any]:
    url = (url or "").strip()
    if not url:
        return {"ok": False, "error": "Missing URL"}
    return play_list([url], title=title)


def _wait_until_playing(proc: subprocess.Popen[Any], timeout: float = 35.0) -> str | None:
    """Block until mpv has a time-pos, or return an error string."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            err = _err_text()
            return _friendly_error(err) or f"mpv exited with code {proc.returncode}"
        pos = _mpv_get("time-pos")
        if pos is not None:
            try:
                float(pos)
                return None
            except (TypeError, ValueError):
                pass
        time.sleep(0.25)
    err = _err_text()
    return _friendly_error(err) or "Timeout waiting for playback to start"


def _unlink_quiet(path: Path | None) -> None:
    if not path:
        return
    try:
        if path.is_file() and path.parent == PLAY_DIR:
            path.unlink()
    except OSError:
        pass


def _download_youtube_to(
    url: str, stem: str, *, prefetch: bool = False
) -> tuple[Path | None, str | None]:
    """Download with yt-dlp to PLAY_DIR/stem.ext. Does not wipe other queue files."""
    global _ytdl_proc, _prefetch_proc
    try:
        PLAY_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return None, f"Cannot create play dir: {e}"
    for old in PLAY_DIR.glob(f"{stem}.*"):
        _unlink_quiet(old)
    cmd = [
        *YTDLP_PREFIX,
        "--no-playlist",
        "--no-progress",
        "-f",
        YTDLP_FORMAT,
        "-o",
        str(PLAY_DIR / f"{stem}.%(ext)s"),
        url,
    ]
    ytdl = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        env=_child_env(),
    )
    if prefetch:
        _prefetch_proc = ytdl
    else:
        _ytdl_proc = ytdl
    local_err: list[str] = []

    def _drain_ytdl() -> None:
        try:
            while True:
                chunk = ytdl.stderr.read(4096) if ytdl.stderr else b""
                if not chunk:
                    break
                text = chunk.decode("utf-8", errors="replace") if isinstance(chunk, bytes) else chunk
                local_err.append(text)
                if not prefetch:
                    _err_add(text)
        except Exception:
            pass

    if ytdl.stderr:
        threading.Thread(target=_drain_ytdl, daemon=True).start()
    try:
        rc = ytdl.wait(timeout=120)
    except subprocess.TimeoutExpired:
        if prefetch:
            _kill_prefetch()
        else:
            _kill_ytdl()
        return None, "הורדת יוטיוב לקחה יותר מדי זמן"
    finally:
        if prefetch:
            if _prefetch_proc is ytdl:
                _prefetch_proc = None
        elif _ytdl_proc is ytdl:
            _ytdl_proc = None

    files = [
        p
        for p in PLAY_DIR.glob(f"{stem}.*")
        if p.is_file() and not p.name.endswith(".part")
    ]
    if rc != 0 or not files:
        return None, _friendly_error("".join(local_err) or _err_text()) or "הורדה מיוטיוב נכשלה"
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0], None


def _prefetch_worker(index: int, url: str, gen: int) -> None:
    path, err = _download_youtube_to(url, f"n{index}", prefetch=True)
    with _lock:
        if gen != _prefetch.get("gen"):
            _unlink_quiet(path)
            return
        if path:
            _prefetch.update(status="ready", path=path, error=None, index=index, url=url)
        else:
            _prefetch.update(status="error", path=None, error=err, index=index, url=url)


def _start_prefetch(index: int) -> None:
    with _lock:
        if index < 0 or index >= len(_queue):
            return
        url = _queue[index]
        if _prefetch.get("status") in ("ready", "running") and _prefetch.get("index") == index:
            return
        _prefetch["gen"] = int(_prefetch.get("gen") or 0) + 1
        gen = _prefetch["gen"]
        _prefetch.update(status="running", index=index, url=url, path=None, error=None)
    old = _prefetch_proc
    # drop previous prefetch download so it doesn't fight the new one
    if old and old.poll() is None:
        try:
            old.kill()
        except Exception:
            pass
    if _is_youtube(url):
        threading.Thread(
            target=_prefetch_worker, args=(index, url, gen), daemon=True
        ).start()
        return
    p = Path(url)
    with _lock:
        if gen != _prefetch.get("gen"):
            return
        _prefetch.update(
            status="ready" if p.is_file() else "idle",
            path=p if p.is_file() else None,
            index=index,
            url=url,
            error=None,
        )


def _take_prefetched(index: int, url: str) -> tuple[Path | None, str | None]:
    deadline = time.time() + 120
    while time.time() < deadline:
        with _lock:
            st = {
                "status": _prefetch.get("status"),
                "index": _prefetch.get("index"),
                "url": _prefetch.get("url"),
                "path": _prefetch.get("path"),
                "error": _prefetch.get("error"),
            }
        if st["index"] != index or st["url"] != url:
            break
        if st["status"] == "ready" and st["path"]:
            with _lock:
                _prefetch.update(status="idle", path=None)
            return Path(st["path"]), None
        if st["status"] == "error":
            return None, st["error"] or "הורדה מיוטיוב נכשלה"
        if st["status"] != "running":
            break
        time.sleep(0.2)
    if _is_youtube(url):
        return _download_youtube_to(url, f"c{index}", prefetch=False)
    p = Path(url)
    if p.is_file():
        return p, None
    return None, None


def _stop_mpv_only() -> None:
    """Quit current mpv without clearing the queue or prefetch."""
    global _proc
    with _lock:
        proc = _proc
        _proc = None
    if proc and proc.poll() is None:
        _mpv_ipc(["quit"])
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
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


def _track_display(index: int, url: str) -> str:
    if 0 <= index < len(_queue_titles) and _queue_titles[index]:
        return _queue_titles[index][:200]
    return (_queue_title or _state.get("title") or url)[:200]


def _play_from_index(index: int, *, wait_for_mpv: bool) -> dict[str, Any]:
    """Play queue[index], skipping tracks that fail before mpv starts."""
    last: dict[str, Any] = {"ok": False, "error": "End of playlist"}
    i = index
    while True:
        with _lock:
            qlen = len(_queue)
        if i < 0 or i >= qlen:
            with _lock:
                _state["loading"] = False
                if not _state.get("error"):
                    _state["error"] = last.get("error") or "נגמר התור"
            return last
        last = _play_queue_index(i, wait_for_mpv=wait_for_mpv)
        if last.get("ok") or last.get("started"):
            return last
        with _lock:
            if not _queue:
                return last
        i += 1


def _play_queue_index(index: int, *, wait_for_mpv: bool = True) -> dict[str, Any]:
    global _proc, _queue_index, _current_file
    with _lock:
        if index < 0 or index >= len(_queue):
            return {"ok": False, "error": "End of playlist"}
        url = _queue[index]
        display = _track_display(index, url)
        old_file = _current_file
        _state.update(
            {
                "loading": True,
                "playing": True,
                "paused": False,
                "url": url,
                "title": display,
                "error": None,
            }
        )

    _stop_mpv_only()
    _err_clear()
    sink = ensure_bt_sink_default()

    path: Path | None = None
    mpv_src: str
    if _is_youtube(url):
        path, dl_err = _take_prefetched(index, url)
        if dl_err or path is None:
            with _lock:
                _state["loading"] = False
                _state["playing"] = False
                _state["error"] = dl_err or "הורדה מיוטיוב נכשלה"
            return {
                "ok": False,
                "error": dl_err or "הורדה מיוטיוב נכשלה",
                "title": display,
                "sink": sink,
            }
        mpv_src = str(path)
    elif Path(url).is_file():
        path = Path(url)
        mpv_src = str(path)
    else:
        mpv_src = url

    with _lock:
        if index >= len(_queue) or _queue[index] != url:
            _state["loading"] = False
            _state["playing"] = False
            return {"ok": False, "error": "Queue changed"}

    try:
        IPC_PATH.parent.mkdir(parents=True, exist_ok=True)
        proc = _start_mpv_sources([mpv_src], display)
    except FileNotFoundError:
        with _lock:
            _state["loading"] = False
            _state["playing"] = False
        return {"ok": False, "error": "mpv is not installed"}

    with _lock:
        _proc = proc
        _queue_index = index
        _current_file = path
        _state.update(
            {
                "playing": True,
                "paused": False,
                "loading": False,
                "url": url,
                "title": display,
                "started_at": time.time(),
                "error": None,
                "sink": sink,
            }
        )

    if old_file and old_file != path:
        _unlink_quiet(old_file)

    threading.Thread(target=_watch_proc, args=(proc, url), daemon=True).start()
    _start_prefetch(index + 1)

    if wait_for_mpv:
        err = _wait_until_playing(proc, timeout=12.0)
        if err:
            with _lock:
                _state["playing"] = False
                _state["loading"] = False
                _state["error"] = err
            return {"ok": False, "error": err, "title": display, "sink": sink, "started": True}

    return {"ok": True, "title": display, "url": url, "sink": sink, "started": True, **get_status()}


def _start_mpv_sources(sources: list[str], display: str) -> subprocess.Popen[Any]:
    env = _child_env()
    cmd = [
        "mpv",
        "--no-video",
        "--really-quiet",
        "--no-terminal",
        "--force-window=no",
        "--audio-channels=stereo",
        f"--input-ipc-server={IPC_PATH}",
        f"--title=bt-speaker-remote:{display[:80]}",
        f"--force-media-title={display[:80].replace(chr(10), ' ')}",
        "--ytdl-format=bestaudio/best",
        *sources,
    ]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        env=env,
    )
    if proc.stderr:
        threading.Thread(target=_drain_bytes, args=(proc.stderr,), daemon=True).start()
    return proc


def play_list(items: list[str], title: str | None = None) -> dict[str, Any]:
    global _proc, _queue, _queue_titles, _queue_index, _queue_title
    raw = _normalize_sources(items)
    sources, source_titles, pl_title = _expand_sources(raw)
    if not sources:
        return {"ok": False, "error": "Missing sources"}

    sink = ensure_bt_sink_default()
    first = sources[0]
    display = (title or "").strip() or pl_title
    if not display:
        if len(sources) > 1:
            display = source_titles[0] or f"מיקס · {len(sources)} רצועות"
        elif _is_http_url(first):
            display = resolve_title(first) or first
        else:
            display = _local_title(first)
        if len(sources) > 1 and not _is_http_url(first):
            display = f"{display} · {len(sources)} רצועות"
    if len(sources) > 1 and "רצועות" not in display:
        display = f"{display} · {len(sources)} רצועות"

    print(f"[bt-speaker] queue {len(sources)} track(s)", flush=True)

    stop()
    _cleanup_ipc()
    _err_clear()

    try:
        IPC_PATH.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass

    all_local = all(not _is_http_url(s) for s in sources)
    if all_local:
        try:
            proc = _start_mpv_sources(sources, display)
        except FileNotFoundError:
            return {"ok": False, "error": "mpv is not installed"}
        with _lock:
            _proc = proc
            _queue = []
            _queue_titles = []
            _queue_index = 0
            _queue_title = None
            _state.update(
                {
                    "playing": True,
                    "paused": False,
                    "loading": False,
                    "url": first,
                    "title": display,
                    "started_at": time.time(),
                    "error": None,
                    "sink": sink,
                }
            )
        threading.Thread(target=_watch_proc, args=(proc, first), daemon=True).start()
        err = _wait_until_playing(proc, timeout=12.0)
        if err:
            with _lock:
                _state["playing"] = False
                _state["error"] = err
            return {"ok": False, "error": err, "title": display, "sink": sink}
        return {"ok": True, "title": display, "url": first, "sink": sink, **get_status()}

    with _lock:
        _queue = sources
        _queue_titles = source_titles
        _queue_index = 0
        _queue_title = display
    return _play_from_index(0, wait_for_mpv=True)


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
        qlen = len(_queue)
        qidx = _queue_index
        proc = _proc
    if qlen > 1:
        if qidx + 1 >= qlen:
            return _with_status(False, "playlist-next failed (end of playlist?)")
        return _play_from_index(qidx + 1, wait_for_mpv=True)
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
        qlen = len(_queue)
        qidx = _queue_index
        proc = _proc
    if qlen > 1:
        if qidx <= 0:
            return _with_status(False, "playlist-prev failed (start of playlist?)")
        return _play_queue_index(qidx - 1, wait_for_mpv=True)
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
        loading = bool(_state.get("loading"))
        paused = bool(alive and _state.get("paused"))
        playing = bool((alive or loading) and not paused)
        title = _state.get("title")
        qlen = len(_queue)
        qidx = _queue_index
        our_queue = qlen > 1
        if our_queue and 0 <= qidx < len(_queue_titles) and _queue_titles[qidx]:
            title = _queue_titles[qidx]
        base = {
            "playing": playing,
            "paused": paused,
            "loading": loading,
            "url": _state.get("url"),
            "title": title,
            "started_at": _state.get("started_at"),
            "error": _state.get("error"),
            "sink": _state.get("sink"),
            "time_pos": None,
            "duration": None,
            "percent": None,
            "playlist_pos": None,
            "playlist_count": None,
        }
        if our_queue:
            base["playlist_pos"] = qidx
            base["playlist_count"] = qlen

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
    if not our_queue:
        try:
            base["playlist_pos"] = int(playlist_pos) if playlist_pos is not None else None
        except (TypeError, ValueError):
            base["playlist_pos"] = None
        try:
            base["playlist_count"] = int(playlist_count) if playlist_count is not None else None
        except (TypeError, ValueError):
            base["playlist_count"] = None

    if not our_queue:
        media = _mpv_get("media-title")
        if isinstance(media, str) and media.strip():
            pl_count = base.get("playlist_count") or 0
            if pl_count > 1:
                base["title"] = media.strip()
                with _lock:
                    _state["title"] = media.strip()

    return base


def _mpv_sink_input_ids() -> list[str]:
    r = _run(["pactl", "list", "sink-inputs"], timeout=8)
    ids: list[str] = []
    current: str | None = None
    is_ours = False
    for line in (r.stdout or "").splitlines():
        if line.startswith("Sink Input #"):
            if current and is_ours:
                ids.append(current)
            current = line.split("#", 1)[1].strip()
            is_ours = False
            continue
        if current is None:
            continue
        low = line.lower()
        if "application.name" in low and "mpv" in low:
            is_ours = True
        if "application.name" in low and "bt-speaker-remote" in low:
            is_ours = True
        if "node.name" in low and '"mpv"' in low:
            is_ours = True
    if current and is_ours:
        ids.append(current)
    return ids


def set_volume(percent: int) -> dict[str, Any]:
    percent = max(0, min(150, int(percent)))
    sink = ensure_bt_sink_default()
    target = sink or "@DEFAULT_SINK@"
    r = _run(["pactl", "set-sink-volume", target, f"{percent}%"], timeout=5)
    # Don't stack: keep mpv/stream at 100%, user control is the sink.
    _mpv_ipc(["set_property", "volume", 100])
    for idx in _mpv_sink_input_ids():
        _run(["pactl", "set-sink-input-volume", idx, "100%"], timeout=5)
    actual = get_volume()
    return {
        "ok": r.returncode == 0,
        "volume": actual.get("volume") if actual.get("volume") is not None else percent,
        "sink": sink,
    }


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
