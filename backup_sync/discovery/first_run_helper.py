#!/usr/bin/env python3
"""
First run helper for Backup Sync addon.
Provides assistance when addon starts without configured USB device.
"""

import logging
from typing import List, Optional
from pathlib import Path

from discovery.disk_scanner import DiskScanner, DiskInfo

logger = logging.getLogger(__name__)


class FirstRunHelper:
    """Helper for first-time setup and disk discovery"""

    def __init__(self, notifier: Optional[NotifySender] = None):
        self.disk_scanner = DiskScanner()
        self.notifier = notifier

    def discover_and_log_disks(self) -> List[DiskInfo]:
        logger.info("=" * 60)
        logger.info("FIRST RUN DETECTED: No USB device configured")
        logger.info("=" * 60)

        usb_disks = self.disk_scanner.scan_usb_disks()

        if not usb_disks:
            self._handle_no_disks_found()
            return []

        self._log_discovered_disks(usb_disks)
        self._log_configuration_instructions(usb_disks)

        return usb_disks

    def suggest_best_disk(self, disks: List[DiskInfo]) -> Optional[str]:
        if not disks:
            return None

        partitions = [d for d in disks if d.is_partition]
        disks_to_consider = partitions or disks

        disks_with_fs = [d for d in disks_to_consider if d.filesystem]
        disks_to_consider = disks_with_fs or disks_to_consider

        ext4_disks = [d for d in disks_to_consider if d.filesystem == "ext4"]
        disks_to_consider = ext4_disks or disks_to_consider

        largest_disk = max(disks_to_consider, key=lambda d: d.size_gb)
        return largest_disk.name

    def _handle_no_disks_found(self):
        logger.error("No USB disks found!")
        logger.info("Please connect a USB drive and restart the addon.")

    def _log_discovered_disks(self, disks: List[DiskInfo]):
        logger.info(f"Found {len(disks)} USB device(s):")

        for i, disk in enumerate(disks, 1):
            size = f"{disk.size_gb:.1f} GB" if disk.size_gb >= 1 else f"{disk.size_gb * 1024:.0f} MB"
            fs = disk.filesystem or "Unknown"
            mount = disk.mountpoint or "Not mounted"

            logger.info(f"{i}. {disk.name}")
            logger.info(f"   Path: {disk.device_path}")
            logger.info(f"   Size: {size}")
            logger.info(f"   Filesystem: {fs}")
            logger.info(f"   Status: {mount}")

            if disk.is_partition:
                logger.info(f"   Partition of: {disk.parent_disk}")

    def _log_configuration_instructions(self, disks: List[DiskInfo]):
        logger.info("=" * 60)
        logger.info("CONFIGURATION INSTRUCTIONS")
        logger.info("=" * 60)

        if disks:
            logger.info(f"Suggested device: {self.suggest_best_disk(disks)}")

    def validate_device_choice(self, device_name: str) -> bool:
        if not device_name:
            logger.error("No device name provided")
            return False

        device_path = Path(f"/dev/{device_name}")
        if not device_path.exists():
            logger.error(f"Device {device_path} does not exist")
            return False

        disk_info = self.disk_scanner.get_disk_by_name(device_name)
        if not disk_info or not disk_info.is_usb:
            logger.error(f"Device {device_name} is not a valid USB device")
            return False

        logger.info(f"Device validation passed: {device_name}")
        return True
