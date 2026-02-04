#!/usr/bin/env python3
"""
Backup synchronization script for Home Assistant OS
Syncs backups from system drive to external RAID array using watchdog
"""

import os
import sys
import time
import shutil
import logging
import threading
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import argparse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('/config/backup_sync.log')
    ]
)
logger = logging.getLogger(__name__)

# Fixed source directory (always /backup in HAOS addons)
SOURCE_DIR = Path("/backup")

class BackupSyncHandler(FileSystemEventHandler):
    """File system event handler for backup synchronization"""
    
    def __init__(self, dest_dir, max_copies, wait_time):
        self.dest_dir = Path(dest_dir)
        self.max_copies = max_copies
        self.wait_time = wait_time
        self.processing_files = set()
        self.lock = threading.Lock()
        
        # Create destination directory if it doesn't exist
        self.dest_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info("Initializing backup monitor")
        logger.info(f"Source (fixed): {SOURCE_DIR}")
        logger.info(f"Destination: {self.dest_dir}")
        logger.info(f"Max copies to keep: {self.max_copies}")
        logger.info(f"Wait before copying: {self.wait_time} seconds")
        
        # Validate source directory
        if not SOURCE_DIR.exists():
            logger.error(f"Source directory does not exist: {SOURCE_DIR}")
            logger.error("This should never happen in HAOS. Check addon configuration.")
            sys.exit(1)
    
    def on_created(self, event):
        """Handle new file creation events"""
        if not event.is_directory:
            file_path = Path(event.src_path)
            if file_path.suffix == '.tar':
                self.process_backup(file_path)
    
    def process_backup(self, file_path):
        """Process a new backup file"""
        # Check if file is already being processed
        with self.lock:
            if file_path in self.processing_files:
                return
            self.processing_files.add(file_path)
        
        try:
            logger.info(f"New backup detected: {file_path.name}")
            
            # Wait specified time before copying
            logger.info(f"Waiting {self.wait_time} seconds before copying...")
            time.sleep(self.wait_time)
            
            # Check if file still exists (might have been deleted during wait)
            if not file_path.exists():
                logger.warning(f"File {file_path.name} no longer exists, skipping")
                return
            
            # Check file size (should be > 0)
            file_size = file_path.stat().st_size
            if file_size == 0:
                logger.error(f"File {file_path.name} is empty, skipping")
                return
            
            logger.info(f"File size: {file_size / (1024*1024):.2f} MB")
            
            # Copy file
            dest_file = self.dest_dir / file_path.name
            logger.info(f"Copying to {dest_file}")
            
            shutil.copy2(file_path, dest_file)
            
            # Verify copy was successful
            if dest_file.exists() and dest_file.stat().st_size == file_size:
                logger.info(f"File successfully copied")
                # Clean up old backups
                self.cleanup_old_backups()
            else:
                logger.error(f"Copy error: file sizes don't match")
                
        except Exception as e:
            logger.error(f"Error processing file {file_path.name}: {e}")
        finally:
            with self.lock:
                self.processing_files.discard(file_path)
    
    def cleanup_old_backups(self):
        """Remove old backups when exceeding limit"""
        try:
            # Get all .tar files in destination directory
            backup_files = list(self.dest_dir.glob("*.tar"))
            
            if len(backup_files) <= self.max_copies:
                logger.info(f"Backup count within limit: {len(backup_files)}")
                return
            
            # Sort files by modification time (oldest first)
            backup_files.sort(key=lambda x: x.stat().st_mtime)
            
            # Calculate how many files to delete
            to_delete = len(backup_files) - self.max_copies
            logger.info(f"Deleting {to_delete} oldest backups")
            
            # Delete the oldest files
            for i in range(to_delete):
                old_file = backup_files[i]
                logger.info(f"Deleting: {old_file.name}")
                old_file.unlink()
                
        except Exception as e:
            logger.error(f"Error cleaning up old backups: {e}")
    
    def sync_existing_backups(self):
        """Sync existing backups on startup"""
        logger.info("Checking for existing backups...")
        source_backups = list(SOURCE_DIR.glob("*.tar"))
        
        for backup in source_backups:
            dest_backup = self.dest_dir / backup.name
            if not dest_backup.exists():
                logger.info(f"Found unsynced backup: {backup.name}")
                self.process_backup(backup)

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Synchronize backups to RAID array')
    parser.add_argument('--dest-dir', default='/media/Backup',
                       help='Destination directory on RAID')
    parser.add_argument('--max-copies', type=int, default=5,
                       help='Maximum number of copies to keep on RAID')
    parser.add_argument('--wait-time', type=int, default=300,
                       help='Wait time before copying (seconds)')
    parser.add_argument('--sync-existing-on-start', action='store_true',
                       help='Check and sync existing backups on startup')
    
    return parser.parse_args()

def main():
    """Main function"""
    args = parse_arguments()
    
    # Create handler and observer
    event_handler = BackupSyncHandler(
        dest_dir=args.dest_dir,
        max_copies=args.max_copies,
        wait_time=args.wait_time
    )
    
    # Sync existing backups if requested
    if args.sync_existing_on_start:
        event_handler.sync_existing_backups()
    
    # Create and start observer
    observer = Observer()
    observer.schedule(event_handler, str(SOURCE_DIR), recursive=False)
    
    try:
        logger.info("Starting directory monitoring...")
        observer.start()
        
        # Keep running
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Stopping monitor...")
        observer.stop()
    except Exception as e:
        logger.error(f"Critical error: {e}")
        observer.stop()
        sys.exit(1)
    finally:
        observer.join()

if __name__ == "__main__":
    main()