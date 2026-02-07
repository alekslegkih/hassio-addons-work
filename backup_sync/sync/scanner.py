#!/usr/bin/env python3

import sys
from pathlib import Path

BACKUP_DIR = Path("/backup")
QUEUE_FILE = Path("/tmp/backup_sync.queue")

# Получаем mount_point из аргументов
if len(sys.argv) > 1:
    TARGET_DIR = Path(f"/media/{sys.argv[1]}")
else:
    # fallback значение
    TARGET_DIR = Path("/media/baskups")

def emit(event: str):
    print(event, flush=True)

def main():
    if not BACKUP_DIR.exists():
        emit("EVENT:FATAL:BACKUP_DIR_NOT_FOUND")
        sys.exit(1)
    
    if not TARGET_DIR.exists():
        emit(f"EVENT:FATAL:TARGET_DIR_NOT_FOUND:{TARGET_DIR}")
        sys.exit(1)

    emit("EVENT:SCANNER_STARTED")
    
    # Получаем список уже скопированных файлов
    existing_files = set()
    for ext in ('*.tar', '*.tar.gz'):
        for f in TARGET_DIR.glob(ext):
            existing_files.add(f.name)
    
    # Поиск бэкапов
    backups = []
    for ext in ('*.tar', '*.tar.gz'):
        backups.extend(BACKUP_DIR.glob(ext))
    
    # Сортируем по времени создания (старые первыми)
    backups.sort(key=lambda p: p.stat().st_mtime)
    
    if not backups:
        emit("EVENT:SCANNER_EMPTY")
        return
    
    new_backups = 0
    skipped_backups = 0
    
    for backup in backups:
        if backup.name in existing_files:
            emit(f"EVENT:SCANNER_SKIPPED:{backup.name}")
            skipped_backups += 1
            continue
            
        try:
            with QUEUE_FILE.open("a") as f:
                f.write(str(backup) + "\n")
            emit(f"EVENT:SCANNER_ENQUEUED:{backup}")
            new_backups += 1
        except Exception as e:
            emit(f"EVENT:FATAL:QUEUE_WRITE_FAILED:{e}")
            sys.exit(1)
    
    emit(f"EVENT:SCANNER_DONE:{new_backups}")
    if skipped_backups > 0:
        emit(f"EVENT:SCANNER_SKIPPED_COUNT:{skipped_backups}")

if __name__ == "__main__":
    main()