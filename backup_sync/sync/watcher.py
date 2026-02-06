#!/usr/bin/env python3

import time
import sys
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

BACKUP_DIR = Path("/backup")
QUEUE_FILE = Path("/tmp/backup_sync.queue")
WAIT_TIME = 300  # фиксировано


def emit(event: str):
    print(event, flush=True)


class BackupHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
            return

        path = Path(event.src_path)

        # интересуют только tar-архивы
        if not path.name.endswith(".tar") and not path.name.endswith(".tar.gz"):
            return

        emit(f"EVENT:NEW_BACKUP:{path}")

        # ждём, пока HA закончит запись
        time.sleep(WAIT_TIME)

        if not path.exists():
            emit(f"EVENT:BACKUP_GONE:{path}")
            return

        try:
            with QUEUE_FILE.open("a") as f:
                f.write(str(path) + "\n")
            emit(f"EVENT:ENQUEUED:{path}")
        except Exception as e:
            emit(f"EVENT:FATAL:QUEUE_WRITE_FAILED:{e}")


def main():
    if not BACKUP_DIR.exists():
        emit("EVENT:FATAL:BACKUP_DIR_NOT_FOUND")
        sys.exit(1)

    emit("EVENT:WATCHER_STARTED")

    event_handler = BackupHandler()
    observer = Observer()
    observer.schedule(event_handler, str(BACKUP_DIR), recursive=False)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        observer.stop()
        observer.join()


if __name__ == "__main__":
    main()
