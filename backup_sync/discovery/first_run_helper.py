#!/usr/bin/env python3
"""
First run helper for Backup Sync addon.
Provides assistance when addon starts without configured USB device.
"""

import logging
import sys
from typing import List, Optional
from pathlib import Path

from discovery.disk_scanner import DiskScanner, DiskInfo

from core.logger import get_logger
logger = get_logger()


class FirstRunHelper:
    """Helper for first-time setup and disk discovery"""
    
    def __init__(self):
        self.disk_scanner = DiskScanner()

    def discover_and_log_disks(self) -> List[DiskInfo]:
        """
        Discover USB disks and log information for user.
        
        Returns:
            List of discovered USB disks/partitions
        """
        logger.info("=" * 60)
        logger.info("FIRST RUN DETECTED: No USB device configured")
        logger.info("=" * 60)
        
        # Scan for USB disks
        usb_disks = self.disk_scanner.scan_usb_disks()
        
        if not usb_disks:
            self._handle_no_disks_found()
            return []
        
        # Log discovered disks
        self._log_discovered_disks(usb_disks)
        
        # Log instructions
        self._log_configuration_instructions(usb_disks)
        
        return usb_disks
    
    def suggest_best_disk(self, disks: List[DiskInfo]) -> Optional[str]:
        """
        Suggest the best disk for backups based on heuristics.
        
        Args:
            disks: List of discovered USB disks
            
        Returns:
            Suggested device name (e.g., "sdb1") or None
        """
        if not disks:
            return None
        
        # Prefer partitions over whole disks
        partitions = [d for d in disks if d.is_partition]
        if partitions:
            disks_to_consider = partitions
        else:
            disks_to_consider = disks
        
        # Prefer disks with filesystem
        disks_with_fs = [d for d in disks_to_consider if d.filesystem]
        if disks_with_fs:
            disks_to_consider = disks_with_fs
        
        # Prefer ext4 filesystem
        ext4_disks = [d for d in disks_to_consider if d.filesystem == "ext4"]
        if ext4_disks:
            disks_to_consider = ext4_disks
        
        # Choose the largest disk
        if disks_to_consider:
            largest_disk = max(disks_to_consider, key=lambda d: d.size_gb)
            return largest_disk.name
        
        return disks[0].name if disks else None
    
    def _handle_no_disks_found(self):
        """Handle case when no USB disks are found"""
        logger.error("No USB disks found!")
        logger.info("Please connect a USB drive and restart the addon.")
        logger.info("")
        logger.info("Supported drives:")
        logger.info("  - USB flash drives")
        logger.info("  - USB external hard drives")
        logger.info("  - SD cards (via USB adapter)")
        logger.info("")
        logger.info("Note: The drive should be formatted with a supported")
        logger.info("      filesystem (ext4, NTFS, FAT32, exFAT).")
    
    def _log_discovered_disks(self, disks: List[DiskInfo]):
        """Log information about discovered disks"""
        logger.info(f"Found {len(disks)} USB device(s):")
        logger.info("")
        
        for i, disk in enumerate(disks, 1):
            # Format size
            if disk.size_gb >= 1:
                size_str = f"{disk.size_gb:.1f} GB"
            else:
                size_mb = disk.size_gb * 1024
                size_str = f"{size_mb:.0f} MB"
            
            # Format filesystem info
            fs_info = disk.filesystem if disk.filesystem else "Unknown/Unformatted"
            
            # Format mount status
            if disk.mountpoint:
                mount_status = f"Mounted at {disk.mountpoint}"
            else:
                mount_status = "Not mounted"
            
            # Format label/UUID
            identifier = ""
            if disk.label:
                identifier = f"Label: {disk.label}"
            elif disk.uuid:
                identifier = f"UUID: {disk.uuid[:8]}..."
            else:
                identifier = "No label/UUID"
            
            # Log disk info
            logger.info(f"{i}. Device: {disk.name}")
            logger.info(f"   Path: {disk.device_path}")
            logger.info(f"   Size: {size_str}")
            logger.info(f"   Filesystem: {fs_info}")
            logger.info(f"   Status: {mount_status}")
            logger.info(f"   {identifier}")
            
            # Additional info for partitions
            if disk.is_partition:
                logger.info(f"   Partition of: {disk.parent_disk}")
            
            logger.info("")
               
        try:
            # Create message with disk list
            disk_list = []
            for disk in disks[:5]:  # Show max 5 disks
                size_gb = f"{disk.size_gb:.0f}" if disk.size_gb >= 1 else "<1"
                fs = disk.filesystem or "Unknown"
                disk_list.append(f"- {disk.name}: {size_gb}GB, {fs}")
            
            if len(disks) > 5:
                disk_list.append(f"... and {len(disks) - 5} more")
            
            disk_list_str = "\n".join(disk_list)
            
            logger.info("Notification sent via notify service")
            
        except Exception as e:
            logger.warning(f"Could not send discovery notification: {e}")
    
    def _log_configuration_instructions(self, disks: List[DiskInfo]):
        """Log step-by-step instructions for user"""
        logger.info("=" * 60)
        logger.info("CONFIGURATION INSTRUCTIONS:")
        logger.info("=" * 60)
        logger.info("")
        logger.info("To configure Backup Sync:")
        logger.info("")
        logger.info("1. Open the Backup Sync addon in Home Assistant")
        logger.info("2. Click on 'Configuration' tab")
        logger.info("3. Look for 'USB Disk Partition' field")
        logger.info("4. Enter one of the device names from above")
        logger.info("")
        
        # Show example based on available disks
        if disks:
            example_disk = disks[0].name
            logger.info(f"   Example: Enter '{example_disk}'")
            logger.info("")
        
        logger.info("5. Click 'SAVE' at the bottom")
        logger.info("6. Restart the addon")
        logger.info("")
        logger.info("The addon will now exit. Please configure it and restart.")
        logger.info("=" * 60)
        
        # Suggest a disk if possible
        suggested = self.suggest_best_disk(disks)
        if suggested:
            logger.info(f"")
            logger.info(f"SUGGESTION: Use '{suggested}' for best results")
            logger.info(f"")
    
    def validate_device_choice(self, device_name: str) -> bool:
        """
        Validate user's device choice.
        
        Args:
            device_name: Device name entered by user
            
        Returns:
            True if device exists and is USB
        """
        if not device_name:
            logger.error("No device name provided")
            return False
        
        # Check if device exists
        device_path = Path(f"/dev/{device_name}")
        if not device_path.exists():
            logger.error(f"Device {device_path} does not exist")
            return False
        
        # Get disk info
        disk_info = self.disk_scanner.get_disk_by_name(device_name)
        if not disk_info:
            logger.error(f"Could not get info for device {device_name}")
            return False
        
        # Check if it's USB
        if not disk_info.is_usb:
            logger.error(f"Device {device_name} is not a USB device")
            logger.info(f"This appears to be a system disk. Please use a USB drive.")
            return False
        
        # Check if mounted (warn if mounted elsewhere)
        if disk_info.mountpoint and disk_info.mountpoint != "/media/backups":
            logger.warning(f"Device {device_name} is already mounted at {disk_info.mountpoint}")
            logger.warning("It will be remounted to /media/backups")
        
        logger.info(f"Device validation passed: {device_name}")
        logger.info(f"  Size: {disk_info.size_gb:.1f} GB")
        logger.info(f"  Filesystem: {disk_info.filesystem}")
        logger.info(f"  Label: {disk_info.label or 'None'}")
        
        return True