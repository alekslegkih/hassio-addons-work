#!/usr/bin/env python3
"""
File system watcher for detecting new backup files.
Uses watchdog to monitor the backup directory for new .tar files.
"""

import threading
import logging
import time
from pathlib import Path
from typing import Optional, Dict, Callable, List
from datetime import datetime

from watchdog.events import FileSystemEventHandler

logger = logging.getLogger(__name__)

class BackupWatcher(FileSystemEventHandler):
    """
    Watches for new backup files and triggers processing.
    Handles file system events from watchdog.
    """
    
    def __init__(self, backup_processor):
        """
        Initialize the backup watcher.
        
        Args:
            backup_processor: Instance of BackupProcessor to handle new backups
        """
        super().__init__()
        self.backup_processor = backup_processor
        
        # State tracking
        self.recently_processed: Dict[str, datetime] = {}
        self.processing_lock = threading.Lock()
        self.callbacks: Dict[str, List[Callable]] = {
            'backup_detected': [],
            'backup_processing_started': [],
            'backup_processing_completed': [],
            'backup_processing_failed': []
        }
        
        # Configuration
        self.debounce_seconds = 2  # Ignore duplicate events within this time
        self.max_recent_size = 100  # Max size of recent files cache
        
        logger.info("Backup watcher initialized")
    
    def on_created(self, event):
        """
        Handle file creation events.
        
        Args:
            event: Watchdog filesystem event
        """
        # Ignore directories
        if event.is_directory:
            return
        
        file_path = Path(event.src_path)
        
        # Only process .tar files
        if file_path.suffix != '.tar':
            logger.debug(f"Ignoring non-tar file: {file_path.name}")
            return
        
        # Check if this is a duplicate event (debouncing)
        if self._is_duplicate_event(file_path):
            logger.debug(f"Ignoring duplicate event for: {file_path.name}")
            return
        
        # Record this event
        self._record_event(file_path)
        
        # Process the backup
        self._process_backup_file(file_path)
    
    def on_moved(self, event):
        """
        Handle file move/rename events.
        Some backup systems might create temp files then rename them.
        
        Args:
            event: Watchdog filesystem event
        """
        # Only process if destination is a .tar file
        dest_path = Path(event.dest_path)
        if dest_path.suffix != '.tar':
            return
        
        logger.info(f"Backup file moved/renamed: {dest_path.name}")
        
        # Check if this is a duplicate event
        if self._is_duplicate_event(dest_path):
            logger.debug(f"Ignoring duplicate move event for: {dest_path.name}")
            return
        
        # Record this event
        self._record_event(dest_path)
        
        # Process the backup
        self._process_backup_file(dest_path)
    
    def _process_backup_file(self, file_path: Path):
        """
        Process a detected backup file.
        
        Args:
            file_path: Path to the backup file
        """
        backup_name = file_path.name
        
        # Validate file exists and is accessible
        if not self._validate_file(file_path):
            logger.error(f"Cannot process backup, file invalid: {backup_name}")
            self._trigger_callbacks('backup_processing_failed', {
                'backup_name': backup_name,
                'error': 'File validation failed',
                'file_path': str(file_path)
            })
            return
        
        logger.info(f"New backup detected: {backup_name}")
        
        # Trigger backup detected callbacks
        self._trigger_callbacks('backup_detected', {
            'backup_name': backup_name,
            'file_path': str(file_path),
            'file_size': file_path.stat().st_size,
            'detection_time': datetime.now()
        })
        
        # Start processing in a separate thread to avoid blocking watchdog
        thread = threading.Thread(
            target=self._process_in_thread,
            args=(file_path,),
            name=f"BackupProcessor-{backup_name}"
        )
        thread.daemon = True
        thread.start()
    
    def _process_in_thread(self, file_path: Path):
        """
        Process backup file in a separate thread.
        
        Args:
            file_path: Path to the backup file
        """
        backup_name = file_path.name
        
        try:
            # Trigger processing started callbacks
            self._trigger_callbacks('backup_processing_started', {
                'backup_name': backup_name,
                'file_path': str(file_path),
                'start_time': datetime.now()
            })
            
            # Process the backup
            result = self.backup_processor.process_backup(file_path)
            
            # Trigger appropriate callback based on result
            if result.success:
                self._trigger_callbacks('backup_processing_completed', {
                    'backup_name': backup_name,
                    'file_path': str(file_path),
                    'result': result,
                    'completion_time': datetime.now()
                })
            else:
                self._trigger_callbacks('backup_processing_failed', {
                    'backup_name': backup_name,
                    'file_path': str(file_path),
                    'result': result,
                    'error': result.error,
                    'completion_time': datetime.now()
                })
            
        except Exception as e:
            logger.error(f"Error processing backup {backup_name} in thread: {e}")
            self._trigger_callbacks('backup_processing_failed', {
                'backup_name': backup_name,
                'file_path': str(file_path),
                'error': str(e),
                'completion_time': datetime.now()
            })
    
    def _validate_file(self, file_path: Path) -> bool:
        """
        Validate that a file can be processed.
        
        Args:
            file_path: Path to validate
            
        Returns:
            True if file is valid for processing
        """
        try:
            # Check file exists
            if not file_path.exists():
                logger.warning(f"File no longer exists: {file_path}")
                return False
            
            # Check it's a file (not directory)
            if not file_path.is_file():
                logger.warning(f"Not a regular file: {file_path}")
                return False
            
            # Check file size
            file_size = file_path.stat().st_size
            if file_size == 0:
                logger.warning(f"File is empty: {file_path}")
                return False
            
            # Check if file is accessible
            with open(file_path, 'rb') as test_file:
                test_file.read(1)  # Try to read one byte
            
            return True
            
        except Exception as e:
            logger.error(f"File validation failed for {file_path}: {e}")
            return False
    
    def _is_duplicate_event(self, file_path: Path) -> bool:
        """
        Check if this is a duplicate event for the same file.
        Implements debouncing to avoid multiple triggers.
        
        Args:
            file_path: Path to check
            
        Returns:
            True if this is likely a duplicate event
        """
        with self.processing_lock:
            file_name = file_path.name
            
            if file_name in self.recently_processed:
                last_time = self.recently_processed[file_name]
                time_diff = (datetime.now() - last_time).total_seconds()
                
                if time_diff < self.debounce_seconds:
                    return True
            
            return False
    
    def _record_event(self, file_path: Path):
        """
        Record that an event occurred for a file.
        
        Args:
            file_path: Path to record
        """
        with self.processing_lock:
            file_name = file_path.name
            self.recently_processed[file_name] = datetime.now()
            
            # Clean up old entries if cache gets too large
            if len(self.recently_processed) > self.max_recent_size:
                self._cleanup_recent_cache()
    
    def _cleanup_recent_cache(self):
        """Clean up old entries from the recent files cache"""
        cutoff_time = datetime.now().timestamp() - 3600  # 1 hour ago
        
        to_remove = []
        for file_name, timestamp in self.recently_processed.items():
            if timestamp.timestamp() < cutoff_time:
                to_remove.append(file_name)
        
        for file_name in to_remove:
            del self.recently_processed[file_name]
        
        if to_remove:
            logger.debug(f"Cleaned up {len(to_remove)} old entries from recent cache")
    
    def register_callback(self, event_type: str, callback: Callable):
        """
        Register a callback for backup events.
        
        Args:
            event_type: Type of event to listen for
                      ('backup_detected', 'backup_processing_started', 
                       'backup_processing_completed', 'backup_processing_failed')
            callback: Function to call when event occurs
                     Receives a dict with event data
        """
        if event_type not in self.callbacks:
            logger.error(f"Unknown event type: {event_type}")
            return
        
        self.callbacks[event_type].append(callback)
        logger.debug(f"Registered callback for event type: {event_type}")
    
    def unregister_callback(self, event_type: str, callback: Callable):
        """
        Unregister a callback.
        
        Args:
            event_type: Event type
            callback: Callback to remove
        """
        if event_type in self.callbacks and callback in self.callbacks[event_type]:
            self.callbacks[event_type].remove(callback)
            logger.debug(f"Unregistered callback for event type: {event_type}")
    
    def _trigger_callbacks(self, event_type: str, event_data: dict):
        """
        Trigger all callbacks for an event type.
        
        Args:
            event_type: Type of event
            event_data: Data to pass to callbacks
        """
        if event_type not in self.callbacks:
            return
        
        for callback in self.callbacks[event_type]:
            try:
                callback(event_data)
            except Exception as e:
                logger.error(f"Error in callback for {event_type}: {e}")
    
    def get_recent_files(self) -> Dict[str, datetime]:
        """
        Get recently processed files.
        
        Returns:
            Dictionary of filename -> last processed time
        """
        with self.processing_lock:
            return self.recently_processed.copy()
    
    def clear_recent_cache(self):
        """Clear the recent files cache"""
        with self.processing_lock:
            self.recently_processed.clear()
            logger.info("Recent files cache cleared")
    
    def wait_for_file_stable(self, file_path: Path, check_interval: float = 1.0, 
                           max_checks: int = 10) -> bool:
        """
        Wait for a file to become stable (stop changing size).
        Useful for ensuring backup is complete.
        
        Args:
            file_path: Path to file
            check_interval: Seconds between checks
            max_checks: Maximum number of checks
            
        Returns:
            True if file stabilized, False if timed out
        """
        logger.info(f"Waiting for {file_path.name} to stabilize...")
        
        last_size = -1
        stable_checks = 0
        required_stable_checks = 2  # Need 2 consecutive same-size readings
        
        for check in range(max_checks):
            try:
                current_size = file_path.stat().st_size
                
                if current_size == last_size:
                    stable_checks += 1
                    logger.debug(f"File size stable for {stable_checks} checks: {current_size} bytes")
                else:
                    stable_checks = 0
                    logger.debug(f"File size changed: {last_size} -> {current_size} bytes")
                
                last_size = current_size
                
                # Check if file has been stable long enough
                if stable_checks >= required_stable_checks:
                    logger.info(f"File stabilized after {check + 1} checks")
                    return True
                
                # Wait before next check
                time.sleep(check_interval)
                
            except Exception as e:
                logger.warning(f"Error checking file size: {e}")
                time.sleep(check_interval)
        
        logger.warning(f"File did not stabilize after {max_checks} checks")
        return False