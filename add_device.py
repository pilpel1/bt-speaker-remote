#!/usr/bin/env python3
"""CLI: create 24h invite links / list / revoke authorized browsers."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

import auth_store

ROOT = Path(__file__).resolve().parent


def _base_url() -> str:
    port = os.environ.get("BT_SPEAKER_PORT", "8765")
    try:
        ts = subprocess.check_output(["tailscale", "ip", "-4"], text=True, timeout=3).strip()
        if ts:
            return f"http://{ts}:{port}"
    except Exception:
        pass
    return f"http://127.0.0.1:{port}"


def cmd_add(name: str, hours: int) -> int:
    auth_store.ensure_store()
    inv = auth_store.create_invite(name, hours=hours)
    base = _base_url()
    link = f"{base}/?token={inv['token']}"
    print()
    print(f"Device name : {inv['name']}")
    print(f"Invite id   : {inv['id']}")
    print(f"Expires     : {inv['expires_at']}  ({hours}h, one-time)")
    print()
    print("One-time invite link (send only to that person/device):")
    print(link)
    print()
    print("After they open it once, the invite is spent.")
    print("Their browser keeps a long-lived token until you revoke the device.")
    print(f"Bookmark (no token): {base}/")
    print()
    print(f"Registry file: {auth_store.STORE_PATH}")
    return 0


def cmd_list() -> int:
    auth_store.ensure_store()
    devices = auth_store.list_devices()
    invites = auth_store.list_invites(include_used=True)
    print(f"\n== Registered devices ({len(devices)}) ==")
    if not devices:
        print("(none)")
    for d in devices:
        flag = "REVOKED" if d["revoked"] else "OK"
        admin = " admin" if d.get("admin") else ""
        print(
            f"  [{flag}]{admin} {d['id']}  {d['name']}"
            f"  created={d['created_at']}  last_seen={d['last_seen'] or '-'}"
            f"  token={d['token_prefix']}"
        )
    print(f"\n== Invites ({len(invites)}) ==")
    if not invites:
        print("(none)")
    for inv in invites:
        if inv["used"]:
            state = "USED"
        elif inv["expired"]:
            state = "EXPIRED"
        else:
            state = "OPEN"
        print(
            f"  [{state}] {inv['id']}  {inv['name']}"
            f"  expires={inv['expires_at']}  device={inv['device_id'] or '-'}"
        )
    print(f"\nFile: {auth_store.STORE_PATH}\n")
    return 0


def cmd_revoke(device_id: str) -> int:
    result = auth_store.revoke_device(device_id)
    if result.get("ok"):
        print(f"Revoked {device_id}. That browser will get 401 until you create a new invite.")
        return 0
    print(result.get("error") or f"No device with id {device_id}", file=sys.stderr)
    return 1


def cmd_delete(device_id: str) -> int:
    result = auth_store.delete_device(device_id)
    if result.get("ok"):
        print(f"Deleted {device_id} from registry.")
        return 0
    print(result.get("error") or f"No device with id {device_id}", file=sys.stderr)
    return 1


def main() -> int:
    # Load .env if present (for port / master token display only)
    env_path = ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip()
            if "#" in v:
                v = v.split("#", 1)[0].strip()
            os.environ.setdefault(k, v)

    p = argparse.ArgumentParser(
        description="Manage BT Speaker Remote authorized devices (named invites)."
    )
    p.add_argument(
        "name",
        nargs="?",
        help='Friendly name, e.g. "My phone" (creates a 24h invite)',
    )
    p.add_argument("--list", "-l", action="store_true", help="List devices + invites")
    p.add_argument("--revoke", metavar="DEVICE_ID", help="Revoke a registered device")
    p.add_argument("--delete", metavar="DEVICE_ID", help="Delete device row from JSON")
    p.add_argument(
        "--hours",
        type=int,
        default=auth_store.INVITE_TTL_HOURS,
        help=f"Invite lifetime in hours (default {auth_store.INVITE_TTL_HOURS})",
    )
    args = p.parse_args()

    if args.list:
        return cmd_list()
    if args.revoke:
        return cmd_revoke(args.revoke)
    if args.delete:
        return cmd_delete(args.delete)
    if args.name:
        return cmd_add(args.name, args.hours)

    p.print_help()
    print()
    print('Example:  ./add_device.sh "My phone"')
    print("          ./add_device.sh --list")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
