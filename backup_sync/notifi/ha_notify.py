#!/usr/bin/env python3

import sys
import json
import subprocess
from pathlib import Path

OPTIONS_FILE = Path("/data/options.json")


def load_notify_service():
    if not OPTIONS_FILE.exists():
        return ""

    try:
        with OPTIONS_FILE.open() as f:
            options = json.load(f)
        return options.get("notify_service", "") or ""
    except Exception:
        return ""


def send_notification(service, title, message):
    payload = {
        "title": title,
        "message": message,
    }

    cmd = [
        "curl",
        "-s",
        "-X", "POST",
        "-H", "Content-Type: application/json",
        "-d", json.dumps(payload),
        f"http://supervisor/core/api/services/{service.replace('.', '/')}",
    ]

    try:
        subprocess.run(cmd, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def main():
    if len(sys.argv) < 4:
        sys.exit(0)

    level = sys.argv[1]
    title = sys.argv[2]
    message = sys.argv[3]

    if level not in ("success", "error", "fatal"):
        sys.exit(0)

    notify_service = load_notify_service()
    if not notify_service:
        sys.exit(0)

    send_notification(notify_service, title, message)


if __name__ == "__main__":
    main()
