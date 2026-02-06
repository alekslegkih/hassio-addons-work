#!/usr/bin/env python3

import sys
from pathlib import Path

BACKUP_DIR = Path("/backup")
QUEUE_FILE = Path("/tmp/backup_sync.queue")


def emit(event: str):
    print(event, flush=True)


def main():
    if not BACKUP_DIR.exists():
        emit("EVENT:FATAL:BACKUP_DIR_NOT_FOUND")
        sys.exit(1)

    emit("EVENT:SCANNER_STARTED")

    backups = sorted(
        BACKUP_DIR.glob("*.tar"),
        key=lambda p: p.stat().st_mtime
    )
    backups += sorted(
        BACKUP_DIR.glob("*.tar.gz"),
        key=lambda p: p.stat().st_mtime
    )

    if not backups:
        emit("EVENT:SCANNER_EMPTY")
        return

    for backup in backups:
        try:
            with QUEUE_FILE.open("a") as f:
                f.write(str(backup) + "\n")
            emit(f"EVENT:SCANNER_ENQUEUED:{backup}")
        except Exception as e:
            emit(f"EVENT:FATAL:QUEUE_WRITE_FAILED:{e}")
            sys.exit(1)

    emit(f"EVENT:SCANNER_DONE:{len(backups)}")


if __name__ == "__main__":
    main()
