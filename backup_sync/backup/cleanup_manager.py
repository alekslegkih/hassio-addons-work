#!/usr/bin/env python3
"""
Cleanup manager for old backups.
Keeps only the specified number of most recent backups.
"""

import logging
import time
from pathlib import Path
from typing import List, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class CleanupResult:
    """Result of cleanup operation"""
    success: bool
    backups_deleted: List[str]
    backups_kept: List[str]
    total_freed_bytes: int
    error: Optional[str] = None

class CleanupManager:
    """
    Manages cleanup of old backup files to maintain the configured limit.
    """
    
    def __init__(self, max_backups: int, backup_dir: Path):
        """
        Initialize cleanup manager.
        
        Args:
            max_backups: Maximum number of backups to keep
            backup_dir: Directory containing backup files
        """
        self.max_backups = max_backups
        self.backup_dir = backup_dir
        
        # Ensure directory exists
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Cleanup manager initialized: keep {max_backups} backups in {backup_dir}")
    
    def cleanup_old_backups(self, force: bool = False) -> List[str]:
        """
        Clean up old backups, keeping only the most recent ones.
        
        Args:
            force: If True, cleanup even if under limit
            
        Returns:
            List of deleted backup filenames
        """
        try:
            # Get all backup files
            backup_files = self._get_backup_files()
            
            if not backup_files:
                logger.debug("No backup files found to clean up")
                return []
            
            # Check if cleanup is needed
            if not force and len(backup_files) <= self.max_backups:
                logger.debug(f"No cleanup needed: {len(backup_files)} <= {self.max_backups}")
                return []
            
            # Sort by modification time (oldest first)
            backup_files.sort(key=lambda x: x[1])
            
            # Calculate how many to delete
            to_delete_count = len(backup_files) - self.max_backups
            if to_delete_count <= 0 and not force:
                return []
            
            # Get files to delete (oldest ones)
            files_to_delete = backup_files[:to_delete_count]
            
            # Delete the files
            deleted_files = []
            total_freed = 0
            
            for file_path, mtime, size in files_to_delete:
                try:
                    # Delete the file
                    file_path.unlink()
                    deleted_files.append(file_path.name)
                    total_freed += size
                    
                    logger.info(f"Deleted old backup: {file_path.name} "
                              f"({self._format_size(size)}, {self._format_time(mtime)})")
                    
                except Exception as e:
                    logger.error(f"Failed to delete {file_path.name}: {e}")
            
            # Log summary
            if deleted_files:
                kept_count = len(backup_files) - len(deleted_files)
                logger.info(
                    f"Cleanup completed:\n"
                    f"  Deleted: {len(deleted_files)} backup(s)\n"
                    f"  Kept: {kept_count} backup(s)\n"
                    f"  Freed: {self._format_size(total_freed)}"
                )
            
            return deleted_files
            
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
            return []
    
    def get_backup_stats(self) -> dict:
        """
        Get statistics about backup files.
        
        Returns:
            Dictionary with backup statistics
        """
        try:
            backup_files = self._get_backup_files()
            
            if not backup_files:
                return {
                    "count": 0,
                    "total_size_bytes": 0,
                    "total_size_formatted": "0 B",
                    "oldest": None,
                    "newest": None,
                    "files": []
                }
            
            # Sort by modification time
            backup_files.sort(key=lambda x: x[1])
            
            # Calculate totals
            total_size = sum(size for _, _, size in backup_files)
            
            # Get oldest and newest
            oldest_file = backup_files[0][0] if backup_files else None
            newest_file = backup_files[-1][0] if backup_files else None
            
            # Get file list with details
            file_details = []
            for file_path, mtime, size in backup_files:
                file_details.append({
                    "name": file_path.name,
                    "size_bytes": size,
                    "size_formatted": self._format_size(size),
                    "modified": datetime.fromtimestamp(mtime).isoformat(),
                    "modified_relative": self._format_time(mtime)
                })
            
            return {
                "count": len(backup_files),
                "total_size_bytes": total_size,
                "total_size_formatted": self._format_size(total_size),
                "oldest": oldest_file.name if oldest_file else None,
                "newest": newest_file.name if newest_file else None,
                "files": file_details
            }
            
        except Exception as e:
            logger.error(f"Error getting backup stats: {e}")
            return {
                "count": 0,
                "total_size_bytes": 0,
                "total_size_formatted": "0 B",
                "oldest": None,
                "newest": None,
                "files": []
            }
    
    def find_oldest_backup(self) -> Optional[Tuple[Path, float, int]]:
        """
        Find the oldest backup file.
        
        Returns:
            Tuple of (file_path, modification_time, size) or None
        """
        backup_files = self._get_backup_files()
        
        if not backup_files:
            return None
        
        # Sort by modification time (oldest first)
        backup_files.sort(key=lambda x: x[1])
        
        return backup_files[0]
    
    def find_largest_backup(self) -> Optional[Tuple[Path, float, int]]:
        """
        Find the largest backup file by size.
        
        Returns:
            Tuple of (file_path, modification_time, size) or None
        """
        backup_files = self._get_backup_files()
        
        if not backup_files:
            return None
        
        # Sort by size (largest first)
        backup_files.sort(key=lambda x: x[2], reverse=True)
        
        return backup_files[0]
    
    def delete_specific_backup(self, backup_name: str) -> bool:
        """
        Delete a specific backup file by name.
        
        Args:
            backup_name: Name of backup file to delete
            
        Returns:
            True if deleted successfully
        """
        file_path = self.backup_dir / backup_name
        
        if not file_path.exists():
            logger.warning(f"Backup file not found: {backup_name}")
            return False
        
        try:
            size = file_path.stat().st_size
            file_path.unlink()
            logger.info(f"Deleted backup: {backup_name} ({self._format_size(size)})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete {backup_name}: {e}")
            return False
    
    def verify_backup_integrity(self, check_hashes: bool = False) -> dict:
        """
        Verify integrity of backup files.
        
        Args:
            check_hashes: If True, calculate and verify file hashes
            
        Returns:
            Dictionary with verification results
        """
        backup_files = self._get_backup_files()
        
        if not backup_files:
            return {"total": 0, "valid": 0, "invalid": 0, "details": []}
        
        results = {
            "total": len(backup_files),
            "valid": 0,
            "invalid": 0,
            "details": []
        }
        
        for file_path, mtime, size in backup_files:
            file_info = {
                "name": file_path.name,
                "size_bytes": size,
                "exists": True,
                "readable": False,
                "hash": None,
                "error": None
            }
            
            try:
                # Check if file is readable
                with open(file_path, 'rb') as f:
                    # Try to read first and last bytes
                    f.read(1)
                    f.seek(-1, 2)  # Go to last byte
                    f.read(1)
                
                file_info["readable"] = True
                
                # Calculate hash if requested
                if check_hashes:
                    file_info["hash"] = self._calculate_file_hash(file_path)
                
                results["valid"] += 1
                file_info["status"] = "valid"
                
            except Exception as e:
                results["invalid"] += 1
                file_info["status"] = "invalid"
                file_info["error"] = str(e)
            
            results["details"].append(file_info)
        
        logger.info(f"Integrity check: {results['valid']} valid, {results['invalid']} invalid")
        return results
    
    def _get_backup_files(self) -> List[Tuple[Path, float, int]]:
        """
        Get all backup files with their modification times and sizes.
        
        Returns:
            List of tuples (file_path, modification_time, size)
        """
        backup_files = []
        
        try:
            for file_path in self.backup_dir.glob("*.tar"):
                try:
                    stat = file_path.stat()
                    backup_files.append((
                        file_path,
                        stat.st_mtime,
                        stat.st_size
                    ))
                except Exception as e:
                    logger.warning(f"Could not stat {file_path}: {e}")
            
            # Also check for .tar.gz files if they exist
            for file_path in self.backup_dir.glob("*.tar.gz"):
                try:
                    stat = file_path.stat()
                    backup_files.append((
                        file_path,
                        stat.st_mtime,
                        stat.st_size
                    ))
                except Exception as e:
                    logger.warning(f"Could not stat {file_path}: {e}")
        
        except Exception as e:
            logger.error(f"Error scanning backup directory: {e}")
        
        return backup_files
    
    def _calculate_file_hash(self, file_path: Path, algorithm: str = "md5") -> str:
        """
        Calculate file hash for integrity checking.
        
        Args:
            file_path: Path to file
            algorithm: Hash algorithm to use
            
        Returns:
            Hex digest of file hash
        """
        import hashlib
        
        hash_func = hashlib.new(algorithm)
        
        with open(file_path, 'rb') as f:
            # Read in chunks for large files
            for chunk in iter(lambda: f.read(8192), b''):
                hash_func.update(chunk)
        
        return hash_func.hexdigest()
    
    def _format_size(self, size_bytes: int) -> str:
        """Format file size in human-readable format"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} PB"
    
    def _format_time(self, timestamp: float) -> str:
        """Format timestamp as relative time"""
        from datetime import datetime, timedelta
        
        file_time = datetime.fromtimestamp(timestamp)
        now = datetime.now()
        time_diff = now - file_time
        
        if time_diff < timedelta(minutes=1):
            return "just now"
        elif time_diff < timedelta(hours=1):
            minutes = int(time_diff.total_seconds() / 60)
            return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
        elif time_diff < timedelta(days=1):
            hours = int(time_diff.total_seconds() / 3600)
            return f"{hours} hour{'s' if hours != 1 else ''} ago"
        elif time_diff < timedelta(days=30):
            days = int(time_diff.days)
            return f"{days} day{'s' if days != 1 else ''} ago"
        else:
            months = int(time_diff.days / 30)
            return f"{months} month{'s' if months != 1 else ''} ago"
    
    def get_storage_usage(self) -> dict:
        """
        Get storage usage information.
        
        Returns:
            Dictionary with storage usage details
        """
        import shutil
        
        try:
            # Get disk usage for the backup directory
            usage = shutil.disk_usage(self.backup_dir)
            
            # Get backup files stats
            stats = self.get_backup_stats()
            
            return {
                "total_bytes": usage.total,
                "used_bytes": usage.used,
                "free_bytes": usage.free,
                "total_formatted": self._format_size(usage.total),
                "used_formatted": self._format_size(usage.used),
                "free_formatted": self._format_size(usage.free),
                "free_percent": (usage.free / usage.total) * 100 if usage.total > 0 else 0,
                "backup_files": stats
            }
            
        except Exception as e:
            logger.error(f"Error getting storage usage: {e}")
            return {
                "total_bytes": 0,
                "used_bytes": 0,
                "free_bytes": 0,
                "total_formatted": "0 B",
                "used_formatted": "0 B",
                "free_formatted": "0 B",
                "free_percent": 0,
                "backup_files": {"count": 0, "total_size_bytes": 0}
            }
    
    def needs_cleanup(self) -> bool:
        """
        Check if cleanup is needed.
        
        Returns:
            True if number of backups exceeds the limit
        """
        backup_files = self._get_backup_files()
        return len(backup_files) > self.max_backups
    
    def get_cleanup_plan(self) -> dict:
        """
        Get a plan for what would be deleted in next cleanup.
        
        Returns:
            Dictionary with cleanup plan
        """
        backup_files = self._get_backup_files()
        
        if not backup_files:
            return {
                "needed": False,
                "current_count": 0,
                "max_allowed": self.max_backups,
                "to_delete": [],
                "to_keep": [],
                "freed_space": 0
            }
        
        # Sort by modification time (oldest first)
        backup_files.sort(key=lambda x: x[1])
        
        current_count = len(backup_files)
        needs_cleanup = current_count > self.max_backups
        
        plan = {
            "needed": needs_cleanup,
            "current_count": current_count,
            "max_allowed": self.max_backups,
            "to_delete": [],
            "to_keep": [],
            "freed_space": 0
        }
        
        if needs_cleanup:
            # Calculate how many to delete
            to_delete_count = current_count - self.max_backups
            files_to_delete = backup_files[:to_delete_count]
            files_to_keep = backup_files[to_delete_count:]
            
            # Add to delete list
            for file_path, mtime, size in files_to_delete:
                plan["to_delete"].append({
                    "name": file_path.name,
                    "size": size,
                    "size_formatted": self._format_size(size),
                    "modified": datetime.fromtimestamp(mtime).isoformat(),
                    "modified_relative": self._format_time(mtime)
                })
                plan["freed_space"] += size
            
            # Add to keep list
            for file_path, mtime, size in files_to_keep:
                plan["to_keep"].append({
                    "name": file_path.name,
                    "size": size,
                    "size_formatted": self._format_size(size),
                    "modified": datetime.fromtimestamp(mtime).isoformat(),
                    "modified_relative": self._format_time(mtime)
                })
        else:
            # All files would be kept
            for file_path, mtime, size in backup_files:
                plan["to_keep"].append({
                    "name": file_path.name,
                    "size": size,
                    "size_formatted": self._format_size(size),
                    "modified": datetime.fromtimestamp(mtime).isoformat(),
                    "modified_relative": self._format_time(mtime)
                })
        
        plan["freed_space_formatted"] = self._format_size(plan["freed_space"])
        
        return plan