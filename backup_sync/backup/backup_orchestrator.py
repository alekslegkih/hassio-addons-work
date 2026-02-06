#!/usr/bin/env python3
"""
Main backup orchestrator.
Coordinates monitoring, copying, and cleanup of backups.
"""

import time
import threading
import logging
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, List, Callable
from datetime import datetime

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from config.loader import Config
from notification.notify_sender import NotifySender  # Обновлённый импорт
from backup.backup_processor import BackupProcessor
from backup.backup_watcher import BackupWatcher
from backup.cleanup_manager import CleanupManager

logger = logging.getLogger(__name__)

@dataclass
class OrchestratorStatus:
    """Status information about the orchestrator"""
    is_running: bool
    is_monitoring: bool
    start_time: datetime
    backups_processed: int
    backups_failed: int
    last_backup_time: Optional[datetime]
    source_dir: Path
    dest_dir: Path

class BackupOrchestrator:
    """
    Main orchestrator that coordinates all backup operations.
    Manages monitoring, processing, and cleanup.
    """
    
    def __init__(
        self,
        config: Config,
        notifier: NotifySender,  # Обновлённый тип
        source_dir: Path,
        dest_dir: Path
    ):
        """
        Initialize the orchestrator.
        
        Args:
            config: Addon configuration
            notifier: Notification client
            source_dir: Source directory (/backup)
            dest_dir: Destination directory (/media/backups)
        """
        self.config = config
        self.notifier = notifier
        self.source_dir = source_dir
        self.dest_dir = dest_dir
        
        # Initialize components
        self.backup_processor = BackupProcessor(config, notifier, source_dir, dest_dir)
        self.cleanup_manager = CleanupManager(config.max_copies, dest_dir)
        
        # Monitoring
        self.watcher = BackupWatcher(self.backup_processor)
        self.observer = Observer()
        
        # State
        self.is_running = False
        self.is_monitoring = False
        self.start_time = datetime.now()
        self.backups_processed = 0
        self.backups_failed = 0
        self.last_backup_time = None
        
        # Thread safety
        self.lock = threading.Lock()
        
        logger.info("Backup orchestrator initialized")
        logger.info(f"Source: {source_dir}")
        logger.info(f"Destination: {dest_dir}")
        logger.info(f"Max copies: {config.max_copies}")
    
    def start_monitoring(self) -> None:
        """
        Start monitoring for new backups.
        This method blocks until monitoring is stopped.
        """
        if self.is_monitoring:
            logger.warning("Monitoring already running")
            return
        
        logger.info("Starting backup monitoring...")
        
        try:
            # Schedule watcher
            self.observer.schedule(
                self.watcher,
                str(self.source_dir),
                recursive=False
            )
            
            # Start observer
            self.observer.start()
            self.is_monitoring = True
            self.is_running = True
            
            logger.info(f"Monitoring started on {self.source_dir}")
            
            # Send startup notification
            self.notifier.send_info(  # Обновлённый метод
                "Backup Sync Monitoring Started",
                f"Watching {self.source_dir} for new backups.\n"
                f"Destination: {self.dest_dir}\n"
                f"Max backups to keep: {self.config.max_copies}"
            )
            
            # Keep the main thread alive
            while self.is_running:
                time.sleep(1)
                
        except KeyboardInterrupt:
            logger.info("Monitoring interrupted by user")
        except Exception as e:
            logger.error(f"Monitoring error: {e}", exc_info=True)
            self.notifier.send_error(  # Обновлённый метод
                "Monitoring Error",
                f"Backup monitoring failed: {e}"
            )
        finally:
            self.stop_monitoring()
    
    def stop_monitoring(self) -> None:
        """Stop monitoring for new backups"""
        if not self.is_monitoring:
            return
        
        logger.info("Stopping backup monitoring...")
        
        try:
            self.is_running = False
            self.is_monitoring = False
            
            # Stop observer
            if self.observer:
                self.observer.stop()
                self.observer.join(timeout=5)
            
            logger.info("Backup monitoring stopped")
            
            # Send stop notification
            self.notifier.send_info(  # Обновлённый метод
                "Backup Sync Stopped",
                "Backup monitoring has been stopped."
            )
            
        except Exception as e:
            logger.error(f"Error stopping monitoring: {e}")
    
    def sync_existing_backups(self) -> List[str]:
        """
        Synchronize existing backups from source to destination.
        
        Returns:
            List of successfully synced backup filenames
        """
        logger.info("Starting sync of existing backups...")
        
        synced_backups = []
        
        try:
            # Get all .tar files in source directory
            source_backups = list(self.source_dir.glob("*.tar"))
            
            if not source_backups:
                logger.info("No existing backups found to sync")
                return []
            
            logger.info(f"Found {len(source_backups)} existing backup(s)")
            
            # Process each backup
            for backup_file in source_backups:
                try:
                    # Check if already exists in destination
                    dest_file = self.dest_dir / backup_file.name
                    if dest_file.exists():
                        logger.info(f"Backup already exists: {backup_file.name}")
                        continue
                    
                    # Process the backup
                    logger.info(f"Syncing: {backup_file.name}")
                    result = self.backup_processor.process_backup(backup_file)
                    
                    with self.lock:
                        if result.success:
                            self.backups_processed += 1
                            self.last_backup_time = datetime.now()
                            synced_backups.append(backup_file.name)
                            logger.info(f"Successfully synced: {backup_file.name}")
                        else:
                            self.backups_failed += 1
                            logger.error(f"Failed to sync: {backup_file.name}")
                    
                except Exception as e:
                    logger.error(f"Error syncing {backup_file.name}: {e}")
                    with self.lock:
                        self.backups_failed += 1
            
            # Perform cleanup after syncing
            if synced_backups:
                self.cleanup_manager.cleanup_old_backups()
            
            # Send summary notification
            if synced_backups:
                self.notifier.send_info(  # Обновлённый метод
                    "Existing Backups Synced",
                    f"Successfully synced {len(synced_backups)} backup(s):\n"
                    f"{', '.join(synced_backups[:5])}"
                    f"{'...' if len(synced_backups) > 5 else ''}"
                )
            
            logger.info(f"Sync completed: {len(synced_backups)} backup(s) synced")
            return synced_backups
            
        except Exception as e:
            logger.error(f"Error during sync of existing backups: {e}")
            self.notifier.send_error(  # Обновлённый метод
                "Sync Failed",
                f"Failed to sync existing backups: {e}"
            )
            return []
    
    def process_single_backup(self, backup_path: Path) -> bool:
        """
        Process a single backup file.
        
        Args:
            backup_path: Path to backup file
            
        Returns:
            True if processing was successful
        """
        try:
            logger.info(f"Processing backup: {backup_path.name}")
            
            result = self.backup_processor.process_backup(backup_path)
            
            with self.lock:
                if result.success:
                    self.backups_processed += 1
                    self.last_backup_time = datetime.now()
                    
                    # Perform cleanup
                    self.cleanup_manager.cleanup_old_backups()
                    
                    logger.info(f"Successfully processed: {backup_path.name}")
                    return True
                else:
                    self.backups_failed += 1
                    logger.error(f"Failed to process: {backup_path.name}")
                    return False
                    
        except Exception as e:
            logger.error(f"Error processing {backup_path.name}: {e}")
            with self.lock:
                self.backups_failed += 1
            return False
    
    def get_status(self) -> OrchestratorStatus:
        """Get current status of the orchestrator"""
        return OrchestratorStatus(
            is_running=self.is_running,
            is_monitoring=self.is_monitoring,
            start_time=self.start_time,
            backups_processed=self.backups_processed,
            backups_failed=self.backups_failed,
            last_backup_time=self.last_backup_time,
            source_dir=self.source_dir,
            dest_dir=self.dest_dir
        )
    
    def get_destination_info(self) -> dict:
        """Get information about destination directory"""
        try:
            # Get list of backups in destination
            backup_files = list(self.dest_dir.glob("*.tar"))
            backup_files.sort(key=lambda x: x.stat().st_mtime)
            
            # Calculate total size
            total_size = sum(f.stat().st_size for f in backup_files)
            total_size_gb = total_size / (1024**3)
            
            # Get oldest and newest
            oldest = backup_files[0].name if backup_files else None
            newest = backup_files[-1].name if backup_files else None
            
            return {
                "backup_count": len(backup_files),
                "total_size_gb": round(total_size_gb, 2),
                "oldest_backup": oldest,
                "newest_backup": newest,
                "files": [f.name for f in backup_files[-10:]]  # Last 10 backups
            }
            
        except Exception as e:
            logger.error(f"Error getting destination info: {e}")
            return {
                "backup_count": 0,
                "total_size_gb": 0,
                "oldest_backup": None,
                "newest_backup": None,
                "files": []
            }
    
    def force_cleanup(self) -> List[str]:
        """
        Force cleanup of old backups regardless of limit.
        
        Returns:
            List of deleted backup filenames
        """
        logger.info("Forcing cleanup of old backups...")
        
        try:
            deleted = self.cleanup_manager.cleanup_old_backups(force=True)
            
            if deleted:
                logger.info(f"Cleaned up {len(deleted)} backup(s)")
                self.notifier.send_info(  # Обновлённый метод
                    "Backup Cleanup",
                    f"Cleaned up {len(deleted)} old backup(s)"
                )
            else:
                logger.info("No backups needed cleanup")
            
            return deleted
            
        except Exception as e:
            logger.error(f"Error during forced cleanup: {e}")
            self.notifier.send_error(  # Обновлённый метод
                "Cleanup Failed",
                f"Failed to clean up old backups: {e}"
            )
            return []
    
    def validate_destination(self) -> bool:
        """
        Validate destination directory.
        
        Returns:
            True if destination is valid
        """
        try:
            # Check if directory exists and is writable
            if not self.dest_dir.exists():
                logger.error(f"Destination directory does not exist: {self.dest_dir}")
                return False
            
            if not self.dest_dir.is_dir():
                logger.error(f"Destination is not a directory: {self.dest_dir}")
                return False
            
            # Test write permission
            test_file = self.dest_dir / ".write_test"
            try:
                test_file.touch()
                test_file.unlink()
            except Exception as e:
                logger.error(f"Cannot write to destination: {e}")
                return False
            
            logger.info(f"Destination validated: {self.dest_dir}")
            return True
            
        except Exception as e:
            logger.error(f"Error validating destination: {e}")
            return False
    
    def register_callback(self, event_type: str, callback: Callable) -> None:
        """
        Register a callback for backup events.
        
        Args:
            event_type: Event type ('backup_started', 'backup_completed', 'backup_failed')
            callback: Callback function
        """
        self.watcher.register_callback(event_type, callback)
    
    def get_performance_stats(self) -> dict:
        """Get performance statistics"""
        uptime = datetime.now() - self.start_time
        uptime_hours = uptime.total_seconds() / 3600
        
        if uptime_hours > 0 and self.backups_processed > 0:
            backups_per_hour = self.backups_processed / uptime_hours
        else:
            backups_per_hour = 0
        
        success_rate = 0
        if self.backups_processed + self.backups_failed > 0:
            success_rate = (self.backups_processed / 
                          (self.backups_processed + self.backups_failed)) * 100
        
        return {
            "uptime_hours": round(uptime_hours, 2),
            "backups_processed": self.backups_processed,
            "backups_failed": self.backups_failed,
            "success_rate_percent": round(success_rate, 1),
            "backups_per_hour": round(backups_per_hour, 2),
            "last_backup": self.last_backup_time.isoformat() if self.last_backup_time else None
        }