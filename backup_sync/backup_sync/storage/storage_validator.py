#!/usr/bin/env python3
"""
Storage validator for backup destination.
Checks availability, free space, and write permissions.
"""

import os
import logging
import shutil
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class StorageInfo:
    """Storage information and statistics"""
    path: Path
    total_gb: float           # Total space in GB
    used_gb: float           # Used space in GB
    free_gb: float           # Free space in GB
    free_percent: float      # Free space as percentage
    is_mount_point: bool     # True if path is a mount point
    is_writable: bool        # True if writable
    filesystem: Optional[str] = None  # Filesystem type if available

class StorageValidator:
    """Validates storage location for backups"""
    
    # Minimum free space required (in GB)
    MIN_FREE_SPACE_GB = 1.0
    
    def __init__(self, min_free_space_gb: float = MIN_FREE_SPACE_GB):
        self.min_free_space_gb = min_free_space_gb
    
    def is_storage_available(self, path: Path) -> bool:
        """
        Check if storage location is available for backups.
        
        Args:
            path: Path to check
            
        Returns:
            True if storage is suitable for backups
        """
        checks = [
            self._check_path_exists,
            self._check_is_directory,
            self._check_is_mount_point,
            self._check_writable,
            self._check_free_space,
        ]
        
        for check_func in checks:
            result, message = check_func(path)
            if not result:
                logger.error(f"Storage validation failed: {message}")
                return False
        
        logger.info(f"Storage validation passed for {path}")
        return True
    
    def get_storage_info(self, path: Path) -> StorageInfo:
        """
        Get detailed storage information.
        
        Args:
            path: Path to analyze
            
        Returns:
            StorageInfo object with all statistics
        """
        try:
            # Get disk usage statistics
            stat = shutil.disk_usage(path)
            
            total_gb = stat.total / (1024**3)
            used_gb = (stat.total - stat.free) / (1024**3)
            free_gb = stat.free / (1024**3)
            free_percent = (stat.free / stat.total) * 100 if stat.total > 0 else 0
            
            # Check if it's a mount point
            is_mount_point = self._is_mount_point(path)
            
            # Check writable
            is_writable = self._test_write_access(path)
            
            # Try to detect filesystem
            filesystem = self._detect_filesystem(path) if is_mount_point else None
            
            return StorageInfo(
                path=path,
                total_gb=total_gb,
                used_gb=used_gb,
                free_gb=free_gb,
                free_percent=free_percent,
                is_mount_point=is_mount_point,
                is_writable=is_writable,
                filesystem=filesystem
            )
            
        except Exception as e:
            logger.error(f"Failed to get storage info for {path}: {e}")
            # Return minimal info
            return StorageInfo(
                path=path,
                total_gb=0,
                used_gb=0,
                free_gb=0,
                free_percent=0,
                is_mount_point=False,
                is_writable=False
            )
    
    def estimate_backup_capacity(self, storage_info: StorageInfo, avg_backup_size_gb: float = 0.5) -> int:
        """
        Estimate how many backups can fit in available space.
        
        Args:
            storage_info: StorageInfo object
            avg_backup_size_gb: Average backup size in GB
            
        Returns:
            Estimated number of backups that can fit
        """
        if avg_backup_size_gb <= 0:
            return 0
        
        return int(storage_info.free_gb // avg_backup_size_gb)
    
    def check_backup_fits(self, storage_info: StorageInfo, backup_size_bytes: int) -> bool:
        """
        Check if a backup of given size will fit in available space.
        
        Args:
            storage_info: StorageInfo object
            backup_size_bytes: Size of backup in bytes
            
        Returns:
            True if backup will fit
        """
        backup_size_gb = backup_size_bytes / (1024**3)
        return storage_info.free_gb >= backup_size_gb + self.min_free_space_gb
    
    def _check_path_exists(self, path: Path) -> tuple[bool, str]:
        """Check if path exists"""
        if not path.exists():
            return False, f"Path does not exist: {path}"
        return True, "Path exists"
    
    def _check_is_directory(self, path: Path) -> tuple[bool, str]:
        """Check if path is a directory"""
        if not path.is_dir():
            return False, f"Path is not a directory: {path}"
        return True, "Is a directory"
    
    def _check_is_mount_point(self, path: Path) -> tuple[bool, str]:
        """Check if path is a mount point (recommended for backups)"""
        if not self._is_mount_point(path):
            logger.warning(f"Path {path} is not a mount point. This may be unsafe for backups.")
            # Don't fail, just warn - could be a subdirectory of a mount point
        return True, "Mount point check passed"
    
    def _check_writable(self, path: Path) -> tuple[bool, str]:
        """Check if path is writable"""
        if not self._test_write_access(path):
            return False, f"Path is not writable: {path}"
        return True, "Is writable"
    
    def _check_free_space(self, path: Path) -> tuple[bool, str]:
        """Check if there's enough free space"""
        try:
            stat = shutil.disk_usage(path)
            free_gb = stat.free / (1024**3)
            
            if free_gb < self.min_free_space_gb:
                return False, f"Insufficient free space: {free_gb:.1f}GB < {self.min_free_space_gb}GB"
            
            # Log space info
            total_gb = stat.total / (1024**3)
            free_percent = (stat.free / stat.total) * 100 if stat.total > 0 else 0
            
            logger.info(f"Storage space: {free_gb:.1f}GB free of {total_gb:.1f}GB ({free_percent:.1f}%)")
            
            if free_percent < 10:
                logger.warning(f"Low free space: only {free_percent:.1f}% free")
            
            return True, f"Free space OK: {free_gb:.1f}GB"
            
        except Exception as e:
            return False, f"Could not check free space: {e}"
    
    def _is_mount_point(self, path: Path) -> bool:
        """Check if path is a mount point"""
        try:
            # Compare device IDs of path and its parent
            path_stat = path.stat()
            parent_stat = path.parent.stat()
            
            # Different device IDs = mount point
            return path_stat.st_dev != parent_stat.st_dev
        except Exception:
            return False
    
    def _test_write_access(self, path: Path) -> bool:
        """Test if directory is writable by trying to create a test file"""
        test_file = path / ".write_test"
        
        try:
            # Try to create and delete a test file
            test_file.touch()
            test_file.unlink()
            return True
        except Exception as e:
            logger.debug(f"Write test failed for {path}: {e}")
            return False
        finally:
            # Cleanup just in case
            if test_file.exists():
                try:
                    test_file.unlink()
                except:
                    pass
    
    def _detect_filesystem(self, path: Path) -> Optional[str]:
        """Try to detect filesystem type of mount point"""
        try:
            import subprocess
            
            # Use findmnt command
            result = subprocess.run(
                ["findmnt", "-n", "-o", "FSTYPE", str(path)],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
                
        except Exception as e:
            logger.debug(f"Could not detect filesystem for {path}: {e}")
        
        return None
    
    def validate_for_backups(self, path: Path, expected_backup_size_gb: float = 1.0) -> tuple[bool, list[str]]:
        """
        Comprehensive validation for backup storage.
        
        Args:
            path: Path to validate
            expected_backup_size_gb: Expected size of backups in GB
            
        Returns:
            Tuple of (is_valid, list_of_warnings)
        """
        warnings = []
        
        # Basic availability check
        if not self.is_storage_available(path):
            return False, ["Storage not available"]
        
        # Get detailed info
        info = self.get_storage_info(path)
        
        # Check if it's a mount point (warning if not)
        if not info.is_mount_point:
            warnings.append(f"Path {path} is not a mount point. Using a subdirectory may be unsafe.")
        
        # Check free space for expected backup size
        if not self.check_backup_fits(info, int(expected_backup_size_gb * 1024**3)):
            warnings.append(f"Expected backup size ({expected_backup_size_gb}GB) may not fit with current free space ({info.free_gb:.1f}GB)")
        
        # Check filesystem type (warning for certain filesystems)
        if info.filesystem:
            problematic_fs = {"vfat", "fat32", "fat16", "exfat", "ntfs"}
            if info.filesystem.lower() in problematic_fs:
                warnings.append(f"Filesystem {info.filesystem} may have limitations (file size, permissions, performance). Consider using ext4.")
        
        # Estimate capacity
        capacity = self.estimate_backup_capacity(info, expected_backup_size_gb)
        logger.info(f"Estimated backup capacity: {capacity} backups of {expected_backup_size_gb}GB each")
        
        if capacity < 3:
            warnings.append(f"Low storage capacity: only {capacity} backups of {expected_backup_size_gb}GB each will fit")
        
        return len(warnings) == 0, warnings