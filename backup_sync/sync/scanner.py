#!/usr/bin/env python3

import sys
import os
from pathlib import Path

BACKUP_DIR = Path("/backup")
QUEUE_FILE = Path("/tmp/backup_sync.queue")

def emit(event: str):
    """Вывод события в stdout"""
    print(event, flush=True)

def check_target_dir(target_dir: Path) -> bool:
    """Проверяет, что целевая директория доступна"""
    if not target_dir.exists():
        emit(f"EVENT:FATAL:TARGET_DIR_NOT_EXISTS:{target_dir}")
        return False
    
    if not target_dir.is_dir():
        emit(f"EVENT:FATAL:TARGET_NOT_DIR:{target_dir}")
        return False
    
    # Проверяем возможность записи (опционально)
    try:
        test_file = target_dir / ".write_test"
        test_file.touch()
        test_file.unlink()
    except Exception as e:
        emit(f"EVENT:FATAL:TARGET_NOT_WRITABLE:{e}")
        return False
    
    return True

def get_existing_backups(target_dir: Path) -> set:
    """Возвращает set с именами уже существующих бэкапов"""
    existing_files = set()
    for ext in ('*.tar', '*.tar.gz'):
        for f in target_dir.glob(ext):
            existing_files.add(f.name)
    return existing_files

def main():
    # Получаем mount_point из аргументов
    if len(sys.argv) > 1:
        mount_point = sys.argv[1]
        TARGET_DIR = Path(f"/media/{mount_point}")
    else:
        # Fallback: пытаемся получить из переменной окружения
        mount_point = os.getenv('MOUNT_POINT', 'baskups')
        TARGET_DIR = Path(f"/media/{mount_point}")
    
    # Проверяем исходную директорию
    if not BACKUP_DIR.exists():
        emit("EVENT:FATAL:BACKUP_DIR_NOT_FOUND")
        sys.exit(1)
    
    if not BACKUP_DIR.is_dir():
        emit("EVENT:FATAL:BACKUP_NOT_DIR")
        sys.exit(1)
    
    # Проверяем целевую директорию
    if not check_target_dir(TARGET_DIR):
        sys.exit(1)
    
    emit("EVENT:SCANNER_STARTED")
    emit(f"EVENT:SCANNER_TARGET:{TARGET_DIR}")
    
    # Получаем список уже скопированных файлов
    existing_files = get_existing_backups(TARGET_DIR)
    if existing_files:
        emit(f"EVENT:SCANNER_EXISTING:{len(existing_files)}")
    
    # Поиск бэкапов
    backups = []
    for ext in ('*.tar', '*.tar.gz'):
        backups.extend(BACKUP_DIR.glob(ext))
    
    # Сортируем по времени создания (старые первыми)
    backups.sort(key=lambda p: p.stat().st_mtime)
    
    if not backups:
        emit("EVENT:SCANNER_EMPTY")
        return
    
    emit(f"EVENT:SCANNER_FOUND:{len(backups)}")
    
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
    
    if new_backups == 0 and skipped_backups > 0:
        emit("EVENT:SCANNER_ALL_EXIST")

if __name__ == "__main__":
    main()