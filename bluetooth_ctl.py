"""Bluetooth helpers via bluetoothctl / BlueZ."""

from __future__ import annotations

import re
import subprocess
import threading
import time
from typing import Any

ADAPTER_TIMEOUT = 8
STALE_MSG = (
    "הרמקול תקוע על חיבור מת. לחץ INPUT (צא מבלוטות׳ וחזור) "
    "או כבה/הדלק את הרמקול, ואז התחבר שוב."
)

_connect_lock = threading.Lock()
_status_cache_lock = threading.Lock()
_status_cache: dict[str, Any] | None = None
_status_cache_at: float = 0.0
_STATUS_CACHE_TTL = 8.0

# Music only. Hands-Free/HSP on this speaker crashes bluetoothd (double free).
_A2DP_UUIDS = (
    "0000110b-0000-1000-8000-00805f9b34fb",  # Audio Sink
    "0000110d-0000-1000-8000-00805f9b34fb",  # A2DP
)
_HFP_UUIDS = (
    "0000111e-0000-1000-8000-00805f9b34fb",
    "00001108-0000-1000-8000-00805f9b34fb",
)


def _bluez_path(address: str) -> str:
    return "/org/bluez/hci0/dev_" + address.upper().replace(":", "_")


def _busctl(*args: str, timeout: float = 20) -> str:
    result = _run(["busctl", *args], timeout=timeout)
    return ((result.stdout or "") + (result.stderr or "")).strip()


def _drop_hfp(address: str) -> None:
    path = _bluez_path(address)
    for uuid in _HFP_UUIDS:
        _busctl(
            "call",
            "org.bluez",
            path,
            "org.bluez.Device1",
            "DisconnectProfile",
            "s",
            uuid,
            timeout=8,
        )


def _connect_a2dp(address: str) -> str:
    path = _bluez_path(address)
    logs: list[str] = []
    for uuid in _A2DP_UUIDS:
        out = _busctl(
            "--timeout=25",
            "call",
            "org.bluez",
            path,
            "org.bluez.Device1",
            "ConnectProfile",
            "s",
            uuid,
            timeout=30,
        )
        logs.append(out)
        time.sleep(1.2)
        info = _bt("info", address, timeout=6)
        if re.search(r"Connected:\s*yes", info, re.I):
            break
    _drop_hfp(address)
    return "\n".join(logs)


def _run(args: list[str], timeout: float = 15) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _bt(*cmd: str, timeout: float = 15) -> str:
    result = _run(["bluetoothctl", *cmd], timeout=timeout)
    out = (result.stdout or "") + (result.stderr or "")
    return out.strip()


def _rfkill_unblock_bluetooth() -> None:
    """BCM43142 often ends soft-blocked; unblock before power on."""
    try:
        _run(["rfkill", "unblock", "bluetooth"], timeout=5)
    except Exception:
        pass


def power_on() -> dict[str, Any]:
    invalidate_status_cache()
    _rfkill_unblock_bluetooth()
    # Retry — BlueZ can return Busy right after unblock/reset
    last = ""
    for _ in range(4):
        last = _bt("power", "on")
        status = get_status()
        if status.get("powered"):
            _bt("pairable", "on")
            return {"ok": True, **status}
        time.sleep(0.6)
    status = get_status()
    return {
        "ok": status.get("powered", False),
        **status,
        "error": None if status.get("powered") else (last or "Failed to power on Bluetooth"),
    }


def power_off() -> dict[str, Any]:
    invalidate_status_cache()
    # Disconnect first so audio cleans up
    try:
        for dev in list_devices():
            if dev.get("connected"):
                _bt("disconnect", dev["address"], timeout=10)
    except Exception:
        pass
    _bt("power", "off")
    status = get_status()
    return {"ok": not status.get("powered", True), **status}


def invalidate_status_cache() -> None:
    global _status_cache, _status_cache_at
    with _status_cache_lock:
        _status_cache = None
        _status_cache_at = 0.0


def _put_status_cache(data: dict[str, Any]) -> None:
    global _status_cache, _status_cache_at
    with _status_cache_lock:
        _status_cache = data
        _status_cache_at = time.time()


def get_status_cached(*, force: bool = False, fetch: bool = True) -> dict[str, Any]:
    """Reuse a recent bluetoothctl dump so polling doesn't poke BlueZ every 1.5s."""
    now = time.time()
    with _status_cache_lock:
        cached = _status_cache
        age = now - _status_cache_at
    if cached is not None and not force:
        if not fetch or age < _STATUS_CACHE_TTL:
            return cached
    if not fetch:
        return cached or {}
    data = get_status()
    _put_status_cache(data)
    return data


def _busctl_prop(path: str, iface: str, name: str, timeout: float = 3) -> str:
    return _busctl(
        "get-property",
        "org.bluez",
        path,
        iface,
        name,
        timeout=timeout,
    )


def _parse_busctl_bool(raw: str) -> bool:
    return bool(re.search(r"\btrue\b", raw, re.I))


def _parse_busctl_str(raw: str) -> str:
    m = re.search(r'"((?:\\.|[^"\\])*)"', raw)
    if not m:
        return ""
    return m.group(1).replace(r"\"", '"')


def peek_status() -> dict[str, Any]:
    """Read-only BlueZ via busctl. Avoids bluetoothctl (BCM43142 can drop A2DP)."""
    powered = False
    adapter = "/org/bluez/hci0"
    tree = _busctl("tree", "org.bluez", timeout=4)
    adapters = re.findall(r"/org/bluez/hci\d+(?=/|$)", tree)
    if adapters:
        adapter = adapters[0]
    raw_powered = _busctl_prop(adapter, "org.bluez.Adapter1", "Powered")
    if raw_powered:
        powered = _parse_busctl_bool(raw_powered)
    paths = sorted(set(re.findall(r"/org/bluez/hci\d+/dev_[0-9A-Fa-f_]+", tree)))
    devices: list[dict[str, Any]] = []
    for path in paths:
        connected = _parse_busctl_bool(_busctl_prop(path, "org.bluez.Device1", "Connected"))
        name = _parse_busctl_str(_busctl_prop(path, "org.bluez.Device1", "Name"))
        alias = _parse_busctl_str(_busctl_prop(path, "org.bluez.Device1", "Alias"))
        address = _parse_busctl_str(_busctl_prop(path, "org.bluez.Device1", "Address"))
        icon = _parse_busctl_str(_busctl_prop(path, "org.bluez.Device1", "Icon"))
        paired = _parse_busctl_bool(_busctl_prop(path, "org.bluez.Device1", "Paired"))
        uuids_raw = _busctl_prop(path, "org.bluez.Device1", "UUIDs")
        if not address:
            m = re.search(r"dev_([0-9A-Fa-f_]+)$", path)
            if m:
                address = m.group(1).replace("_", ":").upper()
        is_audio = (
            "audio" in icon.lower()
            or "headset" in icon.lower()
            or "0000110b" in uuids_raw.lower()
            or "0000110d" in uuids_raw.lower()
            or "0000110a" in uuids_raw.lower()
            or "audio" in uuids_raw.lower()
            or "a2dp" in uuids_raw.lower()
        )
        devices.append(
            {
                "address": address.upper() if address else "",
                "name": name or alias or address or path.rsplit("/", 1)[-1],
                "icon": icon,
                "class": "",
                "rssi": None,
                "paired": paired,
                "trusted": False,
                "connected": connected,
                "is_audio": is_audio,
            }
        )
    devices.sort(key=lambda d: (not d["is_audio"], not d["connected"], d["name"].lower()))
    connected = [d for d in devices if d.get("connected")]
    return {
        "powered": powered,
        "discovering": False,
        "adapter_name": "Bluetooth host",
        "connected": connected,
        "devices": devices,
        "device_count": len(devices),
    }


def get_status_light() -> dict[str, Any]:
    """Fresh-enough status for polling. Never calls bluetoothctl."""
    with _status_cache_lock:
        cached = _status_cache
        age = time.time() - _status_cache_at
    if cached is not None and age < _STATUS_CACHE_TTL:
        return cached
    try:
        data = peek_status()
    except Exception:
        return cached or {"powered": False, "connected": [], "devices": []}
    _put_status_cache(data)
    return data


def get_status() -> dict[str, Any]:
    show = _bt("show", timeout=ADAPTER_TIMEOUT)
    powered = bool(re.search(r"Powered:\s*yes", show, re.I))
    discovering = bool(re.search(r"Discovering:\s*yes", show, re.I))
    name_m = re.search(r"Name:\s*(.+)", show)
    alias_m = re.search(r"Alias:\s*(.+)", show)
    devices = list_devices()
    connected = [d for d in devices if d.get("connected")]
    return {
        "powered": powered,
        "discovering": discovering,
        "adapter_name": (
            (alias_m or name_m).group(1).strip()
            if (alias_m or name_m)
            else "Bluetooth host"
        ),
        "connected": connected,
        "devices": devices,
        "device_count": len(devices),
    }


def _parse_devices_lines(text: str) -> list[dict[str, str]]:
    devices: list[dict[str, str]] = []
    for line in text.splitlines():
        line = line.strip()
        m = re.match(r"Device\s+([0-9A-Fa-f:]{17})\s+(.*)$", line)
        if m:
            devices.append({"address": m.group(1).upper(), "name": m.group(2).strip() or m.group(1)})
    return devices


def list_devices() -> list[dict[str, Any]]:
    raw = _bt("devices", timeout=ADAPTER_TIMEOUT)
    base = _parse_devices_lines(raw)
    enriched: list[dict[str, Any]] = []
    for dev in base:
        info = _bt("info", dev["address"], timeout=6)
        if "not available" in info.lower():
            continue
        name_m = re.search(r"^\s*Name:\s*(.+)$", info, re.M)
        alias_m = re.search(r"^\s*Alias:\s*(.+)$", info, re.M)
        icon_m = re.search(r"^\s*Icon:\s*(.+)$", info, re.M)
        class_m = re.search(r"^\s*Class:\s*(.+)$", info, re.M)
        rssi_m = re.search(r"^\s*RSSI:\s*(.+)$", info, re.M)
        uuids = re.findall(r"UUID:\s*(.+?)\s+\(([0-9a-fA-F-]+)\)", info)
        name = (name_m.group(1).strip() if name_m else None) or (
            alias_m.group(1).strip() if alias_m else None
        ) or dev["name"]
        icon = icon_m.group(1).strip() if icon_m else ""
        is_audio = (
            "audio" in icon.lower()
            or any("audio" in u[0].lower() or "a2dp" in u[0].lower() or "headset" in u[0].lower() for u in uuids)
            or "0000110b" in info.lower()  # Audio Sink
            or "0000110a" in info.lower()  # Audio Source
        )
        enriched.append(
            {
                "address": dev["address"],
                "name": name,
                "icon": icon,
                "class": class_m.group(1).strip() if class_m else "",
                "rssi": rssi_m.group(1).strip() if rssi_m else None,
                "paired": bool(re.search(r"Paired:\s*yes", info, re.I)),
                "trusted": bool(re.search(r"Trusted:\s*yes", info, re.I)),
                "connected": bool(re.search(r"Connected:\s*yes", info, re.I)),
                "is_audio": is_audio,
            }
        )
    # Audio devices first, then name
    enriched.sort(key=lambda d: (not d["is_audio"], not d["connected"], d["name"].lower()))
    return enriched


_scan_lock = threading.Lock()
_scan_thread: threading.Thread | None = None
_scan_until = 0.0


def _scan_worker(seconds: float) -> None:
    global _scan_until
    proc = subprocess.Popen(
        ["bluetoothctl"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    assert proc.stdin is not None
    try:
        # BCM43142 dual-mode scan starves classic inquiry; speakers are BR/EDR.
        proc.stdin.write("power on\nagent NoInputNoOutput\ndefault-agent\npairable on\nscan bredr\n")
        proc.stdin.flush()
        end = time.time() + seconds
        _scan_until = end
        while time.time() < end:
            time.sleep(0.4)
        proc.stdin.write("scan off\nquit\n")
        proc.stdin.flush()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    finally:
        _scan_until = 0.0
        if proc.poll() is None:
            proc.kill()


def start_scan(seconds: float = 18) -> dict[str, Any]:
    global _scan_thread
    with _scan_lock:
        if _scan_thread and _scan_thread.is_alive():
            remaining = max(0, int(_scan_until - time.time()))
            return {"ok": True, "scanning": True, "seconds_remaining": remaining, "message": "Scan already running"}
        power_on()
        _scan_thread = threading.Thread(target=_scan_worker, args=(seconds,), daemon=True)
        _scan_thread.start()
    return {"ok": True, "scanning": True, "seconds": seconds}


def scan_and_wait(seconds: float = 18) -> dict[str, Any]:
    start_scan(seconds)
    # Wait for worker
    t = _scan_thread
    if t:
        t.join(timeout=seconds + 5)
    devices = list_devices()
    invalidate_status_cache()
    return {"ok": True, "devices": devices, "count": len(devices)}


def _force_a2dp_profile(address: str) -> str | None:
    """Lock the card on A2DP. HFP/HSP on S-233 crashed bluetoothd (AT+NREC=0)."""
    card = f"bluez_card.{address.upper().replace(':', '_')}"
    preferred = ("a2dp-sink-sbc_xq", "a2dp-sink")
    chosen = None
    for _ in range(12):
        result = _run(["pactl", "list", "cards"], timeout=6)
        text = result.stdout or ""
        if card not in text:
            time.sleep(0.4)
            continue
        for profile in preferred:
            if profile in text:
                chosen = profile
                break
        if chosen:
            break
        time.sleep(0.4)
    if chosen:
        _run(["pactl", "set-card-profile", card, chosen], timeout=6)
    return chosen


def _set_bt_default_sink(address: str) -> str | None:
    """Point PipeWire/Pulse default sink at this Bluetooth device if present."""
    mac_us = address.upper().replace(":", "_")
    result = _run(["pactl", "list", "short", "sinks"], timeout=5)
    sink = None
    for line in (result.stdout or "").splitlines():
        parts = line.split()
        if len(parts) >= 2 and mac_us in parts[1]:
            sink = parts[1]
            break
    if not sink:
        # Wait a moment for bluez sink to appear
        for _ in range(10):
            time.sleep(0.5)
            result = _run(["pactl", "list", "short", "sinks"], timeout=5)
            for line in (result.stdout or "").splitlines():
                parts = line.split()
                if len(parts) >= 2 and mac_us in parts[1]:
                    sink = parts[1]
                    break
            if sink:
                break
    if sink:
        _run(["pactl", "set-default-sink", sink], timeout=5)
        _run(["pactl", "set-sink-mute", sink, "0"], timeout=5)
        # Move existing streams if any
        inputs = _run(["pactl", "list", "short", "sink-inputs"], timeout=5)
        for line in (inputs.stdout or "").splitlines():
            idx = line.split()[0] if line.split() else None
            if idx and idx.isdigit():
                _run(["pactl", "move-sink-input", idx, sink], timeout=5)
    return sink


def _stale_link_error(log: str) -> bool:
    return bool(
        re.search(
            r"page-timeout|host is down|br-connection-page-timeout",
            log,
            re.I,
        )
    )


def connect(address: str) -> dict[str, Any]:
    with _connect_lock:
        result = _connect_locked(address)
        invalidate_status_cache()
        return result


def _connect_locked(address: str) -> dict[str, Any]:
    address = address.upper().strip()
    power_on()
    info = _bt("info", address, timeout=6)
    known = "not available" not in info.lower()
    already_paired = bool(re.search(r"Paired:\s*yes", info, re.I)) if known else False

    # Unpaired leftover / unknown device: classic inquiry, then Pair (not Connect on dead keys).
    if not already_paired:
        start_scan(18)
        time.sleep(18)
        info = _bt("info", address, timeout=6)
        if "not available" in info.lower():
            return {
                "ok": False,
                "error": f"Device {address} not found. Scan again with speaker in pairing mode.",
            }

    if already_paired:
        script = f"""power on
agent NoInputNoOutput
default-agent
pairable on
trust {address}
quit
"""
    else:
        script = f"""power on
agent NoInputNoOutput
default-agent
pairable on
pair {address}
trust {address}
quit
"""
    proc = subprocess.run(
        ["bluetoothctl"],
        input=script,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    out = out + "\n" + _connect_a2dp(address)
    time.sleep(1.5)
    info = _bt("info", address, timeout=6)
    connected = bool(re.search(r"Connected:\s*yes", info, re.I))
    paired = bool(re.search(r"Paired:\s*yes", info, re.I))
    sink = None
    profile = None
    if connected:
        profile = _force_a2dp_profile(address)
        sink = _set_bt_default_sink(address)
    name_m = re.search(r"^\s*Name:\s*(.+)$", info, re.M)
    if connected:
        error = None
    else:
        extra = out
        if not _stale_link_error(extra):
            journal = _run(
                ["journalctl", "-u", "bluetooth", "--since", "45 sec ago", "--no-pager"],
                timeout=4,
            )
            extra = extra + "\n" + (journal.stdout or "")
        error = STALE_MSG if _stale_link_error(extra) else (
            "Connection failed. Put speaker in pairing mode and try again."
        )
    return {
        "ok": connected,
        "address": address,
        "name": name_m.group(1).strip() if name_m else address,
        "paired": paired,
        "connected": connected,
        "audio_sink": sink,
        "profile": profile,
        "log": out[-1500:],
        "error": error,
    }


def disconnect(address: str | None = None) -> dict[str, Any]:
    if not address:
        connected = [d for d in list_devices() if d.get("connected")]
        if not connected:
            return {"ok": True, "message": "Nothing connected"}
        address = connected[0]["address"]
    address = address.upper().strip()
    _bt("disconnect", address, timeout=12)
    time.sleep(0.5)
    info = _bt("info", address, timeout=6)
    still = bool(re.search(r"Connected:\s*yes", info, re.I))
    invalidate_status_cache()
    return {"ok": not still, "address": address, "connected": still}


def remove_device(address: str) -> dict[str, Any]:
    address = address.upper().strip()
    _bt("disconnect", address, timeout=8)
    out = _bt("remove", address, timeout=8)
    invalidate_status_cache()
    return {"ok": "been removed" in out.lower() or "not available" in out.lower(), "log": out}
