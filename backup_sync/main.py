#!/usr/bin/env python3
"""
Main orchestrator for Backup Sync addon.
Coordinates all components: disk discovery, mounting, monitoring, and backup processing.
"""

import sys
import logging
import time
from pathlib import Path

# Import our modules
from config.loader import ConfigLoader
from discovery.disk_scanner import DiskScanner
from discovery.first_run_helper import FirstRunHelper
from storage.disk_mounter import DiskMounter
from storage.storage_validator import StorageValidator
from backup.backup_orchestrator import BackupOrchestrator
from notification.ha_notifier import HANotifier
from utils.logger import setup_logging

def main():
    """Main entry point for the Backup Sync addon"""
    
    # 1. Setup logging
    logger = setup_logging()
    logger.info("=" * 60)
    logger.info("Starting Backup Sync addon")
    logger.info("=" * 60)
    
    try:
        # 2. Load configuration
        logger.info("Loading configuration...")
        config = ConfigLoader.load()
        logger.info(f"USB device configured: {config.usb_device or 'Not set (first run)'}")
        logger.info(f"Max copies to keep: {config.max_copies}")
        logger.info(f"Wait time: {config.wait_time}s")
        
        # 3. First run check - if no USB device configured
        if not config.usb_device:
            logger.info("First run detected - no USB device configured")
            helper = FirstRunHelper()
            available_disks = helper.discover_and_log_disks()
            
            if not available_disks:
                logger.error("No USB disks found. Please connect a USB drive.")
                sys.exit(1)
                
            # Will exit here, waiting for user to configure the addon
            sys.exit(0)
        
        # 4. Initialize HA notifier (for error notifications)
        notifier = HANotifier()
        
        # 5. Mount USB device
        logger.info(f"Mounting USB device: {config.usb_device}")
        mounter = DiskMounter()
        mount_result = mounter.mount_usb_device(
            device=config.usb_device,
            mount_point="/media/backups"
        )
        
        if not mount_result.success:
            error_msg = f"Failed to mount {config.usb_device}: {mount_result.error}"
            logger.error(error_msg)
            notifier.send_error_notification("Mount failed", error_msg)
            sys.exit(1)
        
        logger.info(f"Successfully mounted {config.usb_device} to /media/backups")
        
        # 6. Validate storage
        logger.info("Validating storage...")
        validator = StorageValidator()
        storage_path = Path("/media/backups")
        
        if not validator.is_storage_available(storage_path):
            error_msg = "Storage validation failed"
            logger.error(error_msg)
            notifier.send_error_notification("Storage error", error_msg)
            sys.exit(1)
        
        # Get storage info
        storage_info = validator.get_storage_info(storage_path)
        logger.info(f"Storage free space: {storage_info.free_gb:.1f} GB")
        logger.info(f"Storage total space: {storage_info.total_gb:.1f} GB")
        
        # 7. Initialize backup orchestrator
        logger.info("Initializing backup orchestrator...")
        orchestrator = BackupOrchestrator(
            config=config,
            notifier=notifier,
            source_dir=Path("/backup"),
            dest_dir=storage_path
        )
        
        # 8. Sync existing backups if configured
        if config.sync_existing_on_start:
            logger.info("Syncing existing backups...")
            sync_results = orchestrator.sync_existing_backups()
            logger.info(f"Synced {len([r for r in sync_results if r.success])} existing backups")
        
        # 9. Start monitoring for new backups
        logger.info("Starting backup monitor...")
        logger.info(f"Monitoring source: /backup")
        logger.info(f"Destination: /media/backups")
        logger.info(f"Max copies to keep: {config.max_copies}")
        logger.info("=" * 60)
        logger.info("Backup Sync is now running and monitoring for new backups")
        logger.info("=" * 60)
        
        # Send startup notification
        notifier.send_info_notification(
            "Backup Sync Started",
            f"Monitoring /backup for new backups. Destination: /media/backups"
        )
        
        # 10. Start the orchestrator (this will run forever)
        orchestrator.start_monitoring()
        
        # If we get here, monitoring was stopped
        logger.info("Backup monitoring stopped")
        
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    except Exception as e:
        logger.error(f"Unexpected error in main: {e}", exc_info=True)
        # Try to send error notification
        try:
            notifier.send_error_notification("Fatal error", str(e))
        except:
            pass
        sys.exit(1)
    finally:
        logger.info("Backup Sync addon stopped")

if __name__ == "__main__":
    main()