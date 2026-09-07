"""YouTube / URL audio playback via mpv (+ yt-dlp) with IPC pause/resume/seek."""

from __future__ import annotations

import hashlib
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
# Bumped on every play/skip/stop. Stale download threads must not start mpv.
_play_gen: int = 0
# url -> {stem, proc, path, complete, error, at}
_jobs: dict[str, dict[str, Any]] = {}
KEEP_SEC = 20 * 60
START_BYTES = 384 * 1024
PREFETCH_AHEAD = 2
MAX_PARALLEL_DL = 3
_STREAM_EXT = {".webm", ".ogg", ".opus", ".mp3", ".mkv", ".ts", ".mpeg", ".flac"}
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
# Prefer webm/opus so we can start mpv before the file is complete (m4a often
# has the moov atom at the end → unplayable until the download finishes).
YTDLP_FORMAT = (
    "bestaudio[ext=webm]/bestaudio[acodec=opus]/"
    "best[protocol=m3u8_native][height<=480]/bestaudio/best/18"
)


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


def _expand_yt_playlist(url: str, limit: int = 80) -> tuple[list[tuple[str, str]], str]:
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
    _sweep_jobs(drop_all=True)


def _kill_proc(proc: subprocess.Popen[Any] | None) -> None:
    if proc and proc.poll() is None:
        try:
            proc.kill()
        except Exception:
            pass
        try:
            proc.wait(timeout=1)
        except Exception:
            pass


def _kill_all_jobs() -> None:
    global _ytdl_proc, _prefetch_proc
    with _lock:
        procs = [j.get("proc") for j in _jobs.values() if j.get("proc")]
        for job in _jobs.values():
            job["proc"] = None
        _ytdl_proc = None
        _prefetch_proc = None
    for proc in procs:
        _kill_proc(proc)


def _kill_ytdl() -> None:
    _kill_all_jobs()


def _kill_prefetch() -> None:
    _kill_all_jobs()


def _gen_ok(gen: int | None, *, locked: bool = False) -> bool:
    if gen is None:
        return True
    if locked:
        return gen == _play_gen
    with _lock:
        return gen == _play_gen


def _bump_gen() -> int:
    global _play_gen
    with _lock:
        _play_gen += 1
        return _play_gen


def _superseded(extra: dict[str, Any] | None = None) -> dict[str, Any]:
    out = {"ok": False, "superseded": True, "error": "superseded"}
    if extra:
        out.update(extra)
    return out


def _kill_orphaned_mpv(keep: subprocess.Popen[Any] | None = None) -> None:
    """Kill leftover mpv processes from overlapping skip/play requests."""
    keep_pid = keep.pid if keep is not None else None
    try:
        r = _run(["pgrep", "-f", "bt-speaker-remote-mpv.sock"], timeout=3)
    except Exception:
        return
    for line in (r.stdout or "").splitlines():
        line = line.strip()
        if not line.isdigit():
            continue
        pid = int(line)
        if keep_pid is not None and pid == keep_pid:
            continue
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    time.sleep(0.05)
    try:
        r = _run(["pgrep", "-f", "bt-speaker-remote-mpv.sock"], timeout=3)
    except Exception:
        return
    for line in (r.stdout or "").splitlines():
        line = line.strip()
        if not line.isdigit():
            continue
        pid = int(line)
        if keep_pid is not None and pid == keep_pid:
            continue
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
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
                "%(id)s|||%(title)s|||%(webpage_url)s|||%(duration)s|||%(channel)s|||%(uploader)s|||%(thumbnail)s",
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
            channel = ""
            if len(parts) > 4:
                channel = parts[4].strip()
            if (not channel or channel.upper() == "NA") and len(parts) > 5:
                channel = parts[5].strip()
            if channel.upper() == "NA":
                channel = ""
            thumb = ""
            if len(parts) > 6:
                thumb = parts[6].strip()
                if thumb.upper() in ("NA", "NONE", "NULL"):
                    thumb = ""
            if not url or url.upper() == "NA":
                if vid_id and vid_id.upper() != "NA":
                    url = f"https://www.youtube.com/watch?v={vid_id}"
                else:
                    continue
            if not thumb and vid_id and vid_id.upper() != "NA":
                thumb = f"https://i.ytimg.com/vi/{vid_id}/mqdefault.jpg"
            results.append(
                {
                    "id": vid_id if vid_id.upper() != "NA" else None,
                    "title": title if title.upper() != "NA" else url,
                    "url": url,
                    "duration": duration,
                    "channel": channel or None,
                    "uploader": channel or None,
                    "thumbnail": thumb or None,
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
    global _proc, _play_gen
    proc.wait()
    next_index: int | None = None
    next_gen: int | None = None
    resume_at = 0.0
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
        still_dl = _job_still_downloading(url)
        # Advance only on clean EOF. Do NOT treat leftover yt-dlp stderr
        # (403 retries that later succeeded) as a failure — that was stopping mixes.
        if rc == 0 and still_dl:
            # Growing-file EOF: replay same track from last position.
            next_index = qidx
            resume_at = float(_state.get("time_pos") or 0)
            _play_gen += 1
            next_gen = _play_gen
            _state["loading"] = True
            _state["playing"] = True
        elif rc == 0 and qlen > 1 and qidx + 1 < qlen:
            next_index = qidx + 1
            _play_gen += 1
            next_gen = _play_gen
            _state["loading"] = True
            _state["playing"] = True
        elif rc not in (0, None, -signal.SIGTERM, -15, -signal.SIGINT, -2):
            err = _err_text()
            _state["error"] = _friendly_error(err) or f"mpv exited {rc}"
    _cleanup_ipc()
    if next_index is not None:
        try:
            _play_from_index(
                next_index, wait_for_mpv=False, gen=next_gen, resume_at=resume_at
            )
        except Exception as e:
            with _lock:
                _state["playing"] = False
                _state["loading"] = False
                _state["error"] = str(e)[:300]


def stop() -> dict[str, Any]:
    global _proc, _queue, _queue_titles, _queue_index, _queue_title, _current_file, _play_gen
    with _lock:
        _play_gen += 1
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
    _kill_all_jobs()
    _cleanup_ipc()
    _kill_orphaned_mpv()
    _sweep_jobs(drop_all=False)
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


def _url_stem(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8", errors="replace")).hexdigest()[:16]


def _job_file(stem: str) -> Path | None:
    if not stem or not PLAY_DIR.is_dir():
        return None
    files = [
        p
        for p in PLAY_DIR.glob(f"{stem}.*")
        if p.is_file() and not p.name.endswith(".part")
    ]
    if not files:
        return None
    files.sort(key=lambda p: p.stat().st_size, reverse=True)
    return files[0]


def _path_size(path: Path | None) -> int:
    if not path:
        return 0
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _ext_streamable(path: Path | None) -> bool:
    return bool(path and path.suffix.lower() in _STREAM_EXT)


def _job_still_downloading(url: str) -> bool:
    with _lock:
        job = _jobs.get(url) or {}
        if job.get("complete"):
            return False
        proc = job.get("proc")
        return bool(proc and proc.poll() is None)


def _keep_urls() -> set[str]:
    keep: set[str] = set()
    qidx = _queue_index
    for i, u in enumerate(_queue):
        if abs(i - qidx) <= PREFETCH_AHEAD + 1:
            keep.add(u)
    playing = _state.get("url")
    if playing:
        keep.add(str(playing))
    return keep


def _running_dl_count() -> int:
    n = 0
    for job in _jobs.values():
        proc = job.get("proc")
        if proc is not None and proc.poll() is None:
            n += 1
    return n


def _sweep_jobs(*, drop_all: bool = False) -> None:
    now = time.time()
    with _lock:
        keep = set() if drop_all else _keep_urls()
        items = list(_jobs.items())
    for url, job in items:
        stem = str(job.get("stem") or "")
        path = job.get("path") if isinstance(job.get("path"), Path) else _job_file(stem)
        at = float(job.get("at") or 0)
        proc = job.get("proc")
        live = bool(proc and proc.poll() is None)
        stale = drop_all or (url not in keep and now - at > KEEP_SEC)
        if stale and live:
            _kill_proc(proc)
            live = False
        if stale and not live:
            _unlink_quiet(path if isinstance(path, Path) else None)
            with _lock:
                _jobs.pop(url, None)
    if not PLAY_DIR.is_dir():
        return
    keep_stems = set()
    with _lock:
        keep_stems = {str(j.get("stem") or "") for j in _jobs.values()}
        if not drop_all:
            for u in _keep_urls():
                keep_stems.add(_url_stem(u))
    for p in list(PLAY_DIR.iterdir()):
        try:
            if p.stem in keep_stems and not drop_all:
                continue
            if drop_all or now - p.stat().st_mtime > KEEP_SEC:
                p.unlink()
        except OSError:
            pass


def _mark_job_done(url: str, ytdl: subprocess.Popen[Any], rc: int | None, err: str) -> None:
    stem = _url_stem(url)
    path = _job_file(stem)
    with _lock:
        job = _jobs.get(url)
        if not job:
            return
        if job.get("proc") is ytdl:
            job["proc"] = None
        job["path"] = path
        job["at"] = time.time()
        if rc == 0 and path:
            job["complete"] = True
            job["error"] = None
        elif not job.get("complete"):
            job["error"] = err or "הורדה מיוטיוב נכשלה"


def _start_job(url: str) -> dict[str, Any]:
    """Start or reuse a yt-dlp job for this URL. Never kills a useful cache file."""
    try:
        PLAY_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return {"error": f"Cannot create play dir: {e}"}
    stem = _url_stem(url)
    with _lock:
        job = _jobs.get(url)
        if job:
            proc = job.get("proc")
            path = job.get("path") if isinstance(job.get("path"), Path) else _job_file(stem)
            if path:
                job["path"] = path
            if job.get("complete") and path and _path_size(path) > 0:
                return job
            if proc is not None and proc.poll() is None:
                return job
            if path and _path_size(path) > 0 and job.get("complete"):
                return job
        if _running_dl_count() >= MAX_PARALLEL_DL and not (job and job.get("proc")):
            return job or {"stem": stem, "waiting": True}
        job = {
            "stem": stem,
            "proc": None,
            "path": _job_file(stem),
            "complete": False,
            "error": None,
            "at": time.time(),
        }
        _jobs[url] = job

    existing = _job_file(stem)
    if existing and _path_size(existing) > 0:
        with _lock:
            job["path"] = existing
            job["at"] = time.time()
            _jobs[url] = job

    cmd = [
        *YTDLP_PREFIX,
        "--no-playlist",
        "--no-progress",
        "--no-part",
        "--continue",
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
    local_err: list[str] = []

    def _drain_ytdl() -> None:
        try:
            while True:
                chunk = ytdl.stderr.read(4096) if ytdl.stderr else b""
                if not chunk:
                    break
                text = chunk.decode("utf-8", errors="replace") if isinstance(chunk, bytes) else chunk
                local_err.append(text)
                _err_add(text)
        except Exception:
            pass

    if ytdl.stderr:
        threading.Thread(target=_drain_ytdl, daemon=True).start()

    with _lock:
        job = _jobs.get(url) or job
        job["proc"] = ytdl
        job["at"] = time.time()
        _jobs[url] = job

    def _reap() -> None:
        try:
            rc = ytdl.wait(timeout=180)
        except subprocess.TimeoutExpired:
            _kill_proc(ytdl)
            rc = ytdl.poll()
        _mark_job_done(url, ytdl, rc, "".join(local_err))
        _prefetch_around()

    threading.Thread(target=_reap, daemon=True).start()
    return job


def _file_playable(path: Path | None, complete: bool) -> bool:
    if not path or _path_size(path) <= 0:
        return False
    if complete:
        return True
    if _ext_streamable(path) and _path_size(path) >= START_BYTES:
        return True
    return False


def _ensure_youtube(url: str, gen: int | None = None) -> tuple[Path | None, str | None]:
    """Return a path as soon as mpv can start (partial webm, or full m4a)."""
    job = _start_job(url)
    if job.get("error") and not job.get("path"):
        return None, str(job.get("error"))
    deadline = time.time() + 120
    while time.time() < deadline:
        if gen is not None and not _gen_ok(gen):
            return None, "superseded"
        with _lock:
            job = _jobs.get(url) or {}
            proc = job.get("proc")
            complete = bool(job.get("complete"))
            err = job.get("error")
            stem = str(job.get("stem") or _url_stem(url))
        path = job.get("path") if isinstance(job.get("path"), Path) else _job_file(stem)
        if path:
            with _lock:
                if url in _jobs:
                    _jobs[url]["path"] = path
                    _jobs[url]["at"] = time.time()
        if _file_playable(path, complete):
            return path, None
        live = bool(proc and proc.poll() is None)
        if not live and not complete:
            if _file_playable(path, True) or _file_playable(path, False):
                return path, None
            if err:
                return None, str(err)
            # Slot was full — retry start.
            _start_job(url)
        time.sleep(0.2)
    path = _job_file(_url_stem(url))
    if _file_playable(path, True) or _file_playable(path, False):
        return path, None
    return None, "הורדת יוטיוב לקחה יותר מדי זמן"


def _prefetch_around(index: int | None = None) -> None:
    with _lock:
        qidx = _queue_index if index is None else index
        urls: list[str] = []
        for i in range(qidx + 1, min(len(_queue), qidx + 1 + PREFETCH_AHEAD)):
            urls.append(_queue[i])
        # Keep previous track warm for skip-back.
        if qidx > 0:
            urls.append(_queue[qidx - 1])
    for u in urls:
        if not _is_youtube(u):
            continue
        with _lock:
            job = _jobs.get(u) or {}
            proc = job.get("proc")
            if job.get("complete") or (proc is not None and proc.poll() is None):
                continue
            if _running_dl_count() >= MAX_PARALLEL_DL:
                break
        _start_job(u)
    _sweep_jobs(drop_all=False)


def _take_prefetched(index: int, url: str, gen: int | None = None) -> tuple[Path | None, str | None]:
    if _is_youtube(url):
        return _ensure_youtube(url, gen=gen)
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


def _play_from_index(
    index: int, *, wait_for_mpv: bool, gen: int | None = None, resume_at: float = 0.0
) -> dict[str, Any]:
    """Play queue[index], skipping tracks that fail before mpv starts."""
    last: dict[str, Any] = {"ok": False, "error": "End of playlist"}
    i = index
    while True:
        if gen is not None and not _gen_ok(gen):
            return _superseded()
        with _lock:
            qlen = len(_queue)
        if i < 0 or i >= qlen:
            with _lock:
                if gen is not None and not _gen_ok(gen, locked=True):
                    return _superseded()
                _state["loading"] = False
                if not _state.get("error"):
                    _state["error"] = last.get("error") or "נגמר התור"
            return last
        last = _play_queue_index(
            i, wait_for_mpv=wait_for_mpv, gen=gen, resume_at=resume_at if i == index else 0.0
        )
        if last.get("superseded"):
            return last
        if last.get("ok") or last.get("started"):
            return last
        with _lock:
            if not _queue:
                return last
        i += 1


def _play_queue_index(
    index: int, *, wait_for_mpv: bool = True, gen: int | None = None, resume_at: float = 0.0
) -> dict[str, Any]:
    global _proc, _queue_index, _current_file
    with _lock:
        if gen is None:
            gen = _play_gen
        elif gen != _play_gen:
            return _superseded()
        if index < 0 or index >= len(_queue):
            return {"ok": False, "error": "End of playlist"}
        url = _queue[index]
        display = _track_display(index, url)
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
    _kill_orphaned_mpv()
    _err_clear()
    if not _gen_ok(gen):
        return _superseded()
    sink = ensure_bt_sink_default()
    if not _gen_ok(gen):
        return _superseded()

    path: Path | None = None
    mpv_src: str
    if _is_youtube(url):
        path, dl_err = _take_prefetched(index, url, gen=gen)
        if not _gen_ok(gen) or dl_err == "superseded":
            return _superseded()
        if dl_err or path is None:
            with _lock:
                if not _gen_ok(gen, locked=True):
                    return _superseded()
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
        if not _gen_ok(gen, locked=True):
            return _superseded()
        if index >= len(_queue) or _queue[index] != url:
            _state["loading"] = False
            _state["playing"] = False
            return {"ok": False, "error": "Queue changed"}

    _stop_mpv_only()
    _kill_orphaned_mpv()
    if not _gen_ok(gen):
        return _superseded()

    try:
        IPC_PATH.parent.mkdir(parents=True, exist_ok=True)
        proc = _start_mpv_sources([mpv_src], display)
    except FileNotFoundError:
        with _lock:
            if _gen_ok(gen, locked=True):
                _state["loading"] = False
                _state["playing"] = False
        return {"ok": False, "error": "mpv is not installed"}

    claimed = False
    with _lock:
        if _gen_ok(gen, locked=True):
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
            claimed = True

    if not claimed:
        if proc.poll() is None:
            try:
                proc.kill()
            except Exception:
                pass
            try:
                proc.wait(timeout=1)
            except Exception:
                pass
        _cleanup_ipc()
        return _superseded()

    _kill_orphaned_mpv(keep=proc)

    threading.Thread(target=_watch_proc, args=(proc, url), daemon=True).start()
    if _gen_ok(gen):
        _prefetch_around(index)

    if wait_for_mpv:
        err = _wait_until_playing(proc, timeout=12.0)
        if not _gen_ok(gen):
            return _superseded()
        if err:
            with _lock:
                if not _gen_ok(gen, locked=True):
                    return _superseded()
                _state["playing"] = False
                _state["loading"] = False
                _state["error"] = err
            return {"ok": False, "error": err, "title": display, "sink": sink, "started": True}
        if resume_at and resume_at > 1.0:
            _mpv_ipc(["seek", float(resume_at), "absolute"])
    elif resume_at and resume_at > 1.0:
        _wait_until_playing(proc, timeout=8.0)
        _mpv_ipc(["seek", float(resume_at), "absolute"])

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
        "--cache=yes",
        "--demuxer-readahead-secs=8",
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


def play_list(
    items: list[str], title: str | None = None, start_index: int = 0
) -> dict[str, Any]:
    global _proc, _queue, _queue_titles, _queue_index, _queue_title
    raw = _normalize_sources(items)
    sources, source_titles, pl_title = _expand_sources(raw)
    if not sources:
        return {"ok": False, "error": "Missing sources"}

    titles = list(source_titles)
    while len(titles) < len(sources):
        titles.append("")
    for i, src in enumerate(sources):
        if not titles[i]:
            titles[i] = _local_title(src) if not _is_http_url(src) else ""

    sink = ensure_bt_sink_default()
    first = sources[0]
    display = (title or "").strip() or pl_title
    if not display:
        if len(sources) > 1:
            display = titles[0] or f"מיקס · {len(sources)} רצועות"
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

    try:
        start_i = int(start_index)
    except (TypeError, ValueError):
        start_i = 0
    start_i = max(0, min(start_i, len(sources) - 1))

    with _lock:
        _queue = sources
        _queue_titles = titles
        _queue_index = start_i
        _queue_title = display
        gen = _play_gen
    _prefetch_around(start_i)
    return _play_from_index(start_i, wait_for_mpv=True, gen=gen)


def enqueue(
    items: list[str], title: str | None = None, *, expand: bool = True
) -> dict[str, Any]:
    """Append to the playing queue without stopping the current track."""
    global _queue, _queue_titles, _queue_title, _queue_index
    raw = _normalize_sources(items)
    if not raw:
        return {"ok": False, "error": "Missing sources"}
    if expand:
        sources, source_titles, _pl = _expand_sources(raw)
    else:
        sources, source_titles = raw, [""] * len(raw)
    if not sources:
        return {"ok": False, "error": "Missing sources"}
    titles = list(source_titles)
    while len(titles) < len(sources):
        titles.append("")
    for i, src in enumerate(sources):
        if not titles[i]:
            if title and i == 0:
                titles[i] = title[:200]
            elif not _is_http_url(src):
                titles[i] = _local_title(src)
    if len(sources) == 1 and title:
        titles[0] = title[:200]

    start_now = False
    with _lock:
        alive = bool(_proc and _proc.poll() is None) or bool(_state.get("loading"))
        if not _queue:
            cur = (_state.get("url") or "").strip()
            if alive and cur:
                _queue = [cur]
                _queue_titles = [str(_state.get("title") or "")[:200]]
                _queue_index = 0
                if not _queue_title:
                    _queue_title = _state.get("title")
            else:
                start_now = True
        if not start_now:
            # skip exact duplicate of the last queued url
            for src, ttl in zip(sources, titles):
                if _queue and _queue[-1] == src:
                    continue
                _queue.append(src)
                _queue_titles.append(ttl)
            if _queue_title and "רצועות" not in str(_queue_title) and len(_queue) > 1:
                _queue_title = f"{_queue_title} · {len(_queue)} רצועות"
            added_at = len(_queue) - 1

    if start_now:
        return play_list(sources, title=title)

    _prefetch_around()
    out = get_status()
    out["ok"] = True
    out["added"] = len(sources)
    out["queue_index_added"] = added_at
    return out


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


def skip_tracks(delta: int | None = None, index: int | None = None) -> dict[str, Any]:
    """Jump by delta, or to an absolute index. Does not kill cached downloads."""
    global _play_gen, _queue_index
    with _lock:
        qlen = len(_queue)
        qidx = _queue_index
        proc = _proc
    if index is not None:
        try:
            target = int(index)
        except (TypeError, ValueError):
            return _with_status(False, "Invalid index")
        delta_i = target - qidx
    else:
        try:
            delta_i = int(delta if delta is not None else 1)
        except (TypeError, ValueError):
            return _with_status(False, "Invalid delta")
    if delta_i == 0:
        return _with_status(True)

    if qlen > 1:
        target = qidx + delta_i
        if target < 0:
            return _with_status(False, "playlist-prev failed (start of playlist?)")
        if target >= qlen:
            return _with_status(False, "playlist-next failed (end of playlist?)")
        with _lock:
            _play_gen += 1
            gen = _play_gen
            _queue_index = target
            url = _queue[target]
            display = _track_display(target, url)
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
        _prefetch_around(target)
        return _play_from_index(target, wait_for_mpv=True, gen=gen)

    if not proc or proc.poll() is not None:
        return _with_status(False, "Nothing playing")
    steps = abs(delta_i)
    cmd = "playlist-next" if delta_i > 0 else "playlist-prev"
    last_ok = False
    for _ in range(steps):
        resp = _mpv_ipc([cmd, "weak"])
        last_ok = _mpv_ok(resp)
        if not last_ok:
            break
    if not last_ok:
        err = (
            "playlist-next failed (end of playlist?)"
            if delta_i > 0
            else "playlist-prev failed (start of playlist?)"
        )
        return _with_status(False, err)
    time.sleep(0.15)
    media = _mpv_get("media-title")
    if isinstance(media, str) and media.strip():
        with _lock:
            _state["title"] = media.strip()
    return _with_status(True)


def next_track() -> dict[str, Any]:
    return skip_tracks(1)


def previous_track() -> dict[str, Any]:
    return skip_tracks(-1)


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
            base["queue_title"] = _queue_title
            qitems: list[dict[str, Any]] = []
            for i, u in enumerate(_queue):
                t = ""
                if i < len(_queue_titles) and _queue_titles[i]:
                    t = _queue_titles[i]
                elif not _is_http_url(u):
                    t = _local_title(u)
                else:
                    t = f"רצועה {i + 1}"
                job = _jobs.get(u) or {}
                path = job.get("path") if isinstance(job.get("path"), Path) else None
                qitems.append(
                    {
                        "index": i,
                        "title": t[:200],
                        "current": i == qidx,
                        "ready": bool(
                            job.get("complete")
                            or _file_playable(path, False)
                            or (not _is_youtube(u) and Path(u).is_file())
                        ),
                    }
                )
            base["queue"] = qitems

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
    if base["time_pos"] is not None:
        with _lock:
            _state["time_pos"] = base["time_pos"]
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
