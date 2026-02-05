#!/usr/bin/env python3
"""
Disk scanner for detecting USB disks and partitions.
Uses system commands (lsblk, blkid) to identify available storage devices.
"""

import logging
import re
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from core.shell_executor import run_command

logger = logging.getLogger(__name__)

@dataclass
class DiskInfo:
    """Information about a disk or partition"""
    name: str              # e.g., "sda1", "sdb"
    device_path: Path      # e.g., "/dev/sda1"
    size_gb: float         # Size in gigabytes
    filesystem: str        # e.g., "ext4", "vfat", "ntfs"
    label: str             # Disk label (if available)
    uuid: str              # Disk UUID (if available)
    mountpoint: str        # Current mount point (if mounted)
    is_usb: bool           # True if device is USB
    is_partition: bool     # True if this is a partition (e.g., sda1)
    parent_disk: str       # Parent disk name (e.g., "sda" for "sda1")

class DiskScanner:
    """Scanner for USB disks and partitions"""
    
    def __init__(self):
        self._available_commands = self._check_available_commands()
    
    def scan_usb_disks(self) -> List[DiskInfo]:
        """
        Scan system for all available USB disks and partitions.
        
        Returns:
            List of DiskInfo objects for USB devices
        """
        logger.info("Scanning for USB disks...")
        
        # Get all block devices
        all_disks = self._get_all_block_devices()
        
        # Filter USB devices
        usb_disks = self._filter_usb_devices(all_disks)
        
        # Get detailed info for each USB device
        detailed_disks = []
        for disk in usb_disks:
            detailed_info = self._get_detailed_disk_info(disk)
            if detailed_info:
                detailed_disks.append(detailed_info)
        
        logger.info(f"Found {len(detailed_disks)} USB disk(s)/partition(s)")
        return detailed_disks
    
    def get_disk_by_name(self, device_name: str) -> Optional[DiskInfo]:
        """
        Get detailed information for a specific disk/partition.
        
        Args:
            device_name: Device name (e.g., "sda1")
            
        Returns:
            DiskInfo object or None if not found
        """
        # Get all block devices
        all_disks = self._get_all_block_devices()
        
        # Find the specific device
        for disk in all_disks:
            if disk.get("name") == device_name:
                detailed_info = self._get_detailed_disk_info(disk)
                if detailed_info and detailed_info.is_usb:
                    return detailed_info
        
        return None
    
    def _get_all_block_devices(self) -> List[Dict[str, Any]]:
        """Get list of all block devices using lsblk"""
        devices = []
        
        # Try JSON output first (more reliable)
        success, stdout, stderr = run_command([
            "lsblk", "-J", "-o", 
            "NAME,SIZE,TYPE,MOUNTPOINT,LABEL,UUID,FSTYPE"
        ])
        
        if success and stdout:
            return self._parse_lsblk_json(stdout)
        
        # Fallback to text parsing
        success, stdout, stderr = run_command([
            "lsblk", "-o", 
            "NAME,SIZE,TYPE,MOUNTPOINT,LABEL,UUID,FSTYPE"
        ])
        
        if success and stdout:
            return self._parse_lsblk_text(stdout)
        
        logger.error("Failed to get block device list")
        return []
    
    def _parse_lsblk_json(self, json_output: str) -> List[Dict[str, Any]]:
        """Parse lsblk JSON output"""
        import json
        try:
            data = json.loads(json_output)
            return self._extract_devices_from_tree(data.get("blockdevices", []))
        except Exception as e:
            logger.error(f"Failed to parse lsblk JSON: {e}")
            return []
    
    def _extract_devices_from_tree(self, devices: List[Dict], parent: str = "") -> List[Dict]:
        """Recursively extract devices from lsblk tree structure"""
        result = []
        
        for device in devices:
            # Add current device
            device_info = {
                "name": device.get("name", ""),
                "size": device.get("size", ""),
                "type": device.get("type", ""),
                "mountpoint": device.get("mountpoint", ""),
                "label": device.get("label", ""),
                "uuid": device.get("uuid", ""),
                "fstype": device.get("fstype", ""),
                "parent": parent
            }
            result.append(device_info)
            
            # Recursively process children
            if "children" in device and device["children"]:
                result.extend(self._extract_devices_from_tree(
                    device["children"], 
                    device.get("name", "")
                ))
        
        return result
    
    def _parse_lsblk_text(self, text_output: str) -> List[Dict[str, Any]]:
        """Parse lsblk text output (fallback)"""
        devices = []
        lines = text_output.strip().split('\n')
        
        # Skip header
        for line in lines[1:]:
            parts = line.split()
            if len(parts) >= 7:
                devices.append({
                    "name": parts[0],
                    "size": parts[1],
                    "type": parts[2],
                    "mountpoint": parts[3] if parts[3] != "" else "",
                    "label": parts[4] if parts[4] != "" else "",
                    "uuid": parts[5] if parts[5] != "" else "",
                    "fstype": parts[6] if parts[6] != "" else "",
                    "parent": ""
                })
        
        return devices
    
    def _filter_usb_devices(self, all_devices: List[Dict]) -> List[Dict]:
        """Filter USB devices from all block devices"""
        usb_devices = []
        
        for device in all_devices:
            device_name = device.get("name", "")
            
            # Skip loop devices and RAM disks
            if device_name.startswith(("loop", "ram", "zram")):
                continue
            
            # Check if device is USB
            is_usb = self._is_usb_device(device_name)
            
            if is_usb:
                usb_devices.append(device)
                logger.debug(f"Found USB device: {device_name}")
        
        return usb_devices
    
    def _is_usb_device(self, device_name: str) -> bool:
        """
        Check if device is connected via USB.
        
        Args:
            device_name: Device name (e.g., "sda", "sdb1")
            
        Returns:
            True if device is USB
        """
        # Get base device name (without partition number)
        base_device = re.sub(r'\d+$', '', device_name)
        
        # Check sysfs for USB connection
        sysfs_path = Path(f"/sys/block/{base_device}/device")
        
        if not sysfs_path.exists():
            # For NVMe devices
            sysfs_path = Path(f"/sys/block/{device_name}/device")
        
        if sysfs_path.exists():
            # Check if it's a symlink to USB bus
            try:
                real_path = sysfs_path.resolve()
                return "usb" in str(real_path).lower()
            except Exception:
                pass
        
        # Alternative: check removable attribute
        removable_path = Path(f"/sys/block/{base_device}/removable")
        if removable_path.exists():
            try:
                with open(removable_path, 'r') as f:
                    return f.read().strip() == "1"
            except Exception:
                pass
        
        # Default: assume non-USB for system disks
        # System disks are usually sda, mmcblk0 (eMMC), nvme0n1
        system_disks = {"sda", "mmcblk0", "nvme0n1", "vda"}
        return base_device not in system_disks
    
    def _get_detailed_disk_info(self, device: Dict) -> Optional[DiskInfo]:
        """Get detailed information for a single device"""
        try:
            name = device.get("name", "")
            size_str = device.get("size", "0")
            
            # Parse size (e.g., "10G", "500M", "1T")
            size_gb = self._parse_size_to_gb(size_str)
            
            # Determine if it's a partition
            is_partition = bool(re.search(r'\d+$', name))
            parent_disk = re.sub(r'\d+$', '', name) if is_partition else name
            
            return DiskInfo(
                name=name,
                device_path=Path(f"/dev/{name}"),
                size_gb=size_gb,
                filesystem=device.get("fstype", ""),
                label=device.get("label", ""),
                uuid=device.get("uuid", ""),
                mountpoint=device.get("mountpoint", ""),
                is_usb=self._is_usb_device(name),
                is_partition=is_partition,
                parent_disk=parent_disk
            )
        except Exception as e:
            logger.error(f"Failed to get disk info for {device}: {e}")
            return None
    
    def _parse_size_to_gb(self, size_str: str) -> float:
        """Convert size string (e.g., '10G', '500M') to gigabytes"""
        if not size_str:
            return 0.0
        
        # Remove spaces and convert to uppercase
        size_str = size_str.strip().upper()
        
        # Extract number and unit
        match = re.match(r'^(\d+\.?\d*)([KMGTP]?)B?$', size_str)
        if not match:
            return 0.0
        
        number = float(match.group(1))
        unit = match.group(2)
        
        # Convert to GB
        multipliers = {"K": 1/1024/1024, "M": 1/1024, "G": 1, "T": 1024, "P": 1024*1024}
        multiplier = multipliers.get(unit, 1)  # Default to GB if no unit
        
        return number * multiplier
    
    def _check_available_commands(self) -> Dict[str, bool]:
        """Check which system commands are available"""
        commands = ["lsblk", "blkid", "mount", "umount"]
        available = {}
        
        for cmd in commands:
            success, _, _ = run_command(["which", cmd], check=False)
            available[cmd] = success
        
        return available