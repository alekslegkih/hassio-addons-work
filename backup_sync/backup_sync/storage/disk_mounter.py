#!/usr/bin/env python3
"""
Disk mounter for USB drives.
Handles mounting, unmounting, and mount point management.
"""

import logging
import time
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, List

from utils.shell_executor import run_command

logger = logging.getLogger(__name__)

@dataclass
class MountResult:
    """Result of mount operation"""
    success: bool
    device: str                    # e.g., "sdb1"
    mount_point: Path              # e.g., "/media/backups"
    filesystem: str                # e.g., "ext4"
    error: Optional[str] = None    # Error message if failed
    was_already_mounted: bool = False  # True if device was already mounted

class DiskMounter:
    """Handles mounting of USB drives to specified mount points"""
    
    DEFAULT_MOUNT_POINT = Path("/media/backups")
    DEFAULT_MOUNT_OPTIONS = "defaults,nofail"
    
    def __init__(self, mount_point: Optional[Path] = None):
        self.mount_point = mount_point or self.DEFAULT_MOUNT_POINT
    
    def mount_usb_device(self, device: str, filesystem: Optional[str] = None) -> MountResult:
        """
        Mount USB device to mount point.
        
        Args:
            device: Device name (e.g., "sdb1")
            filesystem: Filesystem type (auto-detected if None)
            
        Returns:
            MountResult with operation status
        """
        device_path = Path(f"/dev/{device}")
        
        # Validate device exists
        if not device_path.exists():
            return MountResult(
                success=False,
                device=device,
                mount_point=self.mount_point,
                filesystem="",
                error=f"Device {device_path} does not exist"
            )
        
        # Check if already mounted
        current_mount = self._get_device_mount_point(device)
        if current_mount:
            logger.warning(f"Device {device} already mounted at {current_mount}")
            
            # If mounted elsewhere, try to unmount first
            if str(current_mount) != str(self.mount_point):
                logger.info(f"Remounting {device} from {current_mount} to {self.mount_point}")
                unmount_success = self.unmount_device(device)
                if not unmount_success:
                    return MountResult(
                        success=False,
                        device=device,
                        mount_point=self.mount_point,
                        filesystem="",
                        error=f"Failed to unmount from {current_mount}"
                    )
            else:
                # Already mounted at correct location
                fs_type = self._detect_filesystem(device) or "unknown"
                return MountResult(
                    success=True,
                    device=device,
                    mount_point=self.mount_point,
                    filesystem=fs_type,
                    was_already_mounted=True
                )
        
        # Detect filesystem if not provided
        if not filesystem:
            filesystem = self._detect_filesystem(device) or "auto"
        
        # Prepare mount point
        mount_prepared = self._prepare_mount_point()
        if not mount_prepared:
            return MountResult(
                success=False,
                device=device,
                mount_point=self.mount_point,
                filesystem=filesystem,
                error=f"Failed to prepare mount point {self.mount_point}"
            )
        
        # Mount the device
        logger.info(f"Mounting {device} ({filesystem}) to {self.mount_point}")
        mount_success = self._perform_mount(device_path, filesystem)
        
        if mount_success:
            # Verify mount succeeded
            if self._is_mounted_correctly(device):
                logger.info(f"Successfully mounted {device} to {self.mount_point}")
                return MountResult(
                    success=True,
                    device=device,
                    mount_point=self.mount_point,
                    filesystem=filesystem
                )
            else:
                return MountResult(
                    success=False,
                    device=device,
                    mount_point=self.mount_point,
                    filesystem=filesystem,
                    error="Mount appeared successful but device not found at mount point"
                )
        else:
            return MountResult(
                success=False,
                device=device,
                mount_point=self.mount_point,
                filesystem=filesystem,
                error=f"Mount command failed for {device}"
            )
    
    def unmount_device(self, device: str) -> bool:
        """
        Unmount a device.
        
        Args:
            device: Device name (e.g., "sdb1")
            
        Returns:
            True if successfully unmounted
        """
        logger.info(f"Unmounting {device}")
        
        # Try unmount with retries
        for attempt in range(3):
            success, stdout, stderr = run_command([
                "umount", f"/dev/{device}"
            ], check=False)
            
            if success:
                logger.info(f"Successfully unmounted {device}")
                return True
            elif "not mounted" in stderr.lower():
                logger.info(f"Device {device} was not mounted")
                return True
            
            logger.warning(f"Unmount attempt {attempt + 1} failed: {stderr}")
            time.sleep(1)
        
        logger.error(f"Failed to unmount {device} after 3 attempts")
        return False
    
    def unmount_mount_point(self, mount_point: Path) -> bool:
        """
        Unmount whatever is mounted at a mount point.
        
        Args:
            mount_point: Path to unmount
            
        Returns:
            True if successfully unmounted
        """
        if not self._is_mount_point(mount_point):
            logger.info(f"{mount_point} is not a mount point")
            return True
        
        logger.info(f"Unmounting {mount_point}")
        
        for attempt in range(3):
            success, stdout, stderr = run_command([
                "umount", str(mount_point)
            ], check=False)
            
            if success:
                logger.info(f"Successfully unmounted {mount_point}")
                return True
            
            logger.warning(f"Unmount attempt {attempt + 1} failed: {stderr}")
            time.sleep(1)
        
        logger.error(f"Failed to unmount {mount_point} after 3 attempts")
        return False
    
    def _prepare_mount_point(self) -> bool:
        """Prepare mount point directory"""
        try:
            # Create directory if it doesn't exist
            self.mount_point.mkdir(parents=True, exist_ok=True)
            
            # Check if directory is empty (except for maybe .DS_Store or thumbs.db)
            items = list(self.mount_point.iterdir())
            if items:
                # Check if it's just system files
                system_files = {'.DS_Store', 'thumbs.db', '.Trash', '.fseventsd'}
                real_items = [item for item in items if item.name not in system_files]
                
                if real_items:
                    logger.warning(f"Mount point {self.mount_point} contains files: {real_items}")
                    # We'll mount anyway - might be a re-mount
            return True
            
        except Exception as e:
            logger.error(f"Failed to prepare mount point {self.mount_point}: {e}")
            return False
    
    def _perform_mount(self, device_path: Path, filesystem: str) -> bool:
        """Execute mount command"""
        mount_cmd = [
            "mount",
            "-t", filesystem,
            "-o", self.DEFAULT_MOUNT_OPTIONS,
            str(device_path),
            str(self.mount_point)
        ]
        
        success, stdout, stderr = run_command(mount_cmd, check=False)
        
        if not success:
            logger.error(f"Mount command failed: {stderr}")
            
            # Try with different options for certain filesystems
            if "wrong fs type" in stderr.lower() or "unknown filesystem" in stderr.lower():
                logger.info(f"Trying with auto filesystem detection")
                mount_cmd = [
                    "mount",
                    "-o", self.DEFAULT_MOUNT_OPTIONS,
                    str(device_path),
                    str(self.mount_point)
                ]
                success, stdout, stderr = run_command(mount_cmd, check=False)
        
        return success
    
    def _detect_filesystem(self, device: str) -> Optional[str]:
        """Detect filesystem of a device"""
        success, stdout, stderr = run_command([
            "blkid", "-s", "TYPE", "-o", "value", f"/dev/{device}"
        ], check=False)
        
        if success and stdout:
            return stdout.strip()
        
        # Try with lsblk
        success, stdout, stderr = run_command([
            "lsblk", "-o", "FSTYPE", "-n", f"/dev/{device}"
        ], check=False)
        
        if success and stdout:
            return stdout.strip()
        
        return None
    
    def _get_device_mount_point(self, device: str) -> Optional[Path]:
        """Get current mount point of a device"""
        success, stdout, stderr = run_command([
            "findmnt", "-n", "-o", "TARGET", f"/dev/{device}"
        ], check=False)
        
        if success and stdout:
            mount_point = stdout.strip()
            if mount_point:
                return Path(mount_point)
        
        # Alternative method
        success, stdout, stderr = run_command([
            "mount"
        ], check=False)
        
        if success and stdout:
            for line in stdout.split('\n'):
                if f"/dev/{device}" in line:
                    parts = line.split()
                    if len(parts) >= 3:
                        return Path(parts[2])
        
        return None
    
    def _is_mounted_correctly(self, device: str) -> bool:
        """Check if device is correctly mounted to our mount point"""
        current_mount = self._get_device_mount_point(device)
        if not current_mount:
            return False
        
        return current_mount.resolve() == self.mount_point.resolve()
    
    def _is_mount_point(self, path: Path) -> bool:
        """Check if path is a mount point"""
        try:
            # Check if path is a mount point by comparing device IDs
            path_stat = path.stat()
            parent_stat = path.parent.stat()
            
            # Different device IDs means it's a mount point
            return path_stat.st_dev != parent_stat.st_dev
        except Exception:
            return False
    
    def cleanup_mount_point(self) -> bool:
        """
        Clean up mount point directory if empty.
        
        Returns:
            True if cleaned up or already empty
        """
        try:
            if not self.mount_point.exists():
                return True
            
            # Check if it's a mount point
            if self._is_mount_point(self.mount_point):
                logger.warning(f"Cannot cleanup {self.mount_point} - it's a mount point")
                return False
            
            # Check if directory is empty
            items = list(self.mount_point.iterdir())
            system_files = {'.DS_Store', 'thumbs.db', '.Trash', '.fseventsd'}
            real_items = [item for item in items if item.name not in system_files]
            
            if not real_items:
                # Remove system files
                for item in items:
                    if item.name in system_files:
                        try:
                            item.unlink()
                        except:
                            pass
                
                # Try to remove directory
                try:
                    self.mount_point.rmdir()
                    logger.info(f"Cleaned up mount point {self.mount_point}")
                    return True
                except Exception as e:
                    logger.warning(f"Could not remove mount point directory: {e}")
                    return False
            else:
                logger.warning(f"Cannot cleanup {self.mount_point} - contains files: {real_items}")
                return False
                
        except Exception as e:
            logger.error(f"Error cleaning up mount point: {e}")
            return False
    
    def list_mounted_devices(self) -> List[dict]:
        """List all currently mounted devices"""
        devices = []
        
        success, stdout, stderr = run_command(["mount"], check=False)
        if not success:
            return devices
        
        for line in stdout.split('\n'):
            if '/dev/' in line:
                parts = line.split()
                if len(parts) >= 3:
                    device = parts[0]
                    mount_point = parts[2]
                    
                    # Extract device name from path
                    if device.startswith('/dev/'):
                        device_name = device[5:]  # Remove '/dev/'
                        devices.append({
                            'device': device_name,
                            'mount_point': mount_point,
                            'filesystem': parts[4] if len(parts) > 4 else 'unknown'
                        })
        
        return devices