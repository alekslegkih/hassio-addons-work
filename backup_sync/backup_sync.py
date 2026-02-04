#!/usr/bin/env python3
"""
Скрипт для автоматической синхронизации бэкапов с системного диска на RAID массив
Использует watchdog для отслеживания изменений файловой системы
"""

import os
import sys
import time
import shutil
import logging
import threading
from datetime import datetime
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import argparse

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('/config/backup_sync.log')
    ]
)
logger = logging.getLogger(__name__)

class BackupSyncHandler(FileSystemEventHandler):
    """Обработчик событий файловой системы для синхронизации бэкапов"""
    
    def __init__(self, source_dir, dest_dir, max_copies, wait_time):
        self.source_dir = Path(source_dir)
        self.dest_dir = Path(dest_dir)
        self.max_copies = max_copies
        self.wait_time = wait_time
        self.processing_files = set()
        self.lock = threading.Lock()
        
        # Создаем целевую директорию если не существует
        self.dest_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Инициализация монитора бэкапов")
        logger.info(f"Источник: {self.source_dir}")
        logger.info(f"Назначение: {self.dest_dir}")
        logger.info(f"Максимум копий: {self.max_copies}")
        logger.info(f"Ожидание перед копированием: {self.wait_time} секунд")
    
    def on_created(self, event):
        """Обработка создания нового файла"""
        if not event.is_directory:
            file_path = Path(event.src_path)
            if file_path.suffix == '.tar':
                self.process_backup(file_path)
    
    def process_backup(self, file_path):
        """Обработка нового бэкап-файла"""
        # Проверяем, не обрабатывается ли уже этот файл
        with self.lock:
            if file_path in self.processing_files:
                return
            self.processing_files.add(file_path)
        
        try:
            logger.info(f"Обнаружен новый бэкап: {file_path.name}")
            
            # Ждем указанное время перед копированием
            logger.info(f"Ожидание {self.wait_time} секунд перед копированием...")
            time.sleep(self.wait_time)
            
            # Проверяем, существует ли файл (на случай если он был удален за время ожидания)
            if not file_path.exists():
                logger.warning(f"Файл {file_path.name} больше не существует, пропускаем")
                return
            
            # Проверяем размер файла (должен быть больше 0)
            file_size = file_path.stat().st_size
            if file_size == 0:
                logger.error(f"Файл {file_path.name} пустой, пропускаем")
                return
            
            logger.info(f"Размер файла: {file_size / (1024*1024):.2f} MB")
            
            # Копируем файл
            dest_file = self.dest_dir / file_path.name
            logger.info(f"Копирование в {dest_file}")
            
            shutil.copy2(file_path, dest_file)
            
            # Проверяем успешность копирования
            if dest_file.exists() and dest_file.stat().st_size == file_size:
                logger.info(f"Файл успешно скопирован")
                # Удаляем старые копии
                self.cleanup_old_backups()
            else:
                logger.error(f"Ошибка при копировании: размеры не совпадают")
                
        except Exception as e:
            logger.error(f"Ошибка при обработке файла {file_path.name}: {e}")
        finally:
            with self.lock:
                self.processing_files.discard(file_path)
    
    def cleanup_old_backups(self):
        """Удаление старых бэкапов при превышении лимита"""
        try:
            # Получаем все файлы .tar в целевой директории
            backup_files = list(self.dest_dir.glob("*.tar"))
            
            if len(backup_files) <= self.max_copies:
                logger.info(f"Количество бэкапов в пределах лимита: {len(backup_files)}")
                return
            
            # Сортируем файлы по времени изменения (старые первыми)
            backup_files.sort(key=lambda x: x.stat().st_mtime)
            
            # Определяем сколько файлов нужно удалить
            to_delete = len(backup_files) - self.max_copies
            logger.info(f"Удаление {to_delete} старых бэкапов")
            
            # Удаляем самые старые файлы
            for i in range(to_delete):
                old_file = backup_files[i]
                logger.info(f"Удаление: {old_file.name}")
                old_file.unlink()
                
        except Exception as e:
            logger.error(f"Ошибка при удалении старых бэкапов: {e}")
    
    def sync_existing_backups(self):
        """Синхронизация уже существующих бэкапов при старте"""
        logger.info("Проверка существующих бэкапов...")
        source_backups = list(self.source_dir.glob("*.tar"))
        
        for backup in source_backups:
            dest_backup = self.dest_dir / backup.name
            if not dest_backup.exists():
                logger.info(f"Обнаружен несинхронизированный бэкап: {backup.name}")
                self.process_backup(backup)

def parse_arguments():
    """Парсинг аргументов командной строки"""
    parser = argparse.ArgumentParser(description='Синхронизация бэкапов на RAID массив')
    parser.add_argument('--source-dir', default='/backup', 
                       help='Исходная директория с бэкапами')
    parser.add_argument('--dest-dir', default='/media/Backup',
                       help='Целевая директория на RAID')
    parser.add_argument('--max-copies', type=int, default=5,
                       help='Максимальное количество копий на RAID')
    parser.add_argument('--wait-time', type=int, default=300,
                       help='Время ожидания перед копированием (секунды)')
    parser.add_argument('--check-existing', action='store_true',
                       help='Проверить и синхронизировать существующие бэкапы при старте')
    
    return parser.parse_args()

def main():
    """Основная функция"""
    args = parse_arguments()
    
    # Проверяем существование исходной директории
    source_path = Path(args.source_dir)
    if not source_path.exists():
        logger.error(f"Исходная директория не существует: {source_path}")
        sys.exit(1)
    
    # Создаем обработчик и наблюдатель
    event_handler = BackupSyncHandler(
        source_dir=args.source_dir,
        dest_dir=args.dest_dir,
        max_copies=args.max_copies,
        wait_time=args.wait_time
    )
    
    # Синхронизируем существующие бэкапы если нужно
    if args.check_existing:
        event_handler.sync_existing_backups()
    
    # Создаем и запускаем наблюдатель
    observer = Observer()
    observer.schedule(event_handler, args.source_dir, recursive=False)
    
    try:
        logger.info("Запуск мониторинга директории...")
        observer.start()
        
        # Бесконечный цикл
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Остановка мониторинга...")
        observer.stop()
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        observer.stop()
        sys.exit(1)
    finally:
        observer.join()

if __name__ == "__main__":
    main()