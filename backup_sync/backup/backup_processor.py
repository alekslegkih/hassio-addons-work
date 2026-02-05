#!/usr/bin/env python3
"""
Backup processor for individual backup files.
Handles waiting, copying, verification, and retry logic.
"""

import time
import shutil
import hashlib
import logging
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Tuple, Callable
from datetime import datetime

from config.loader import Config
from notification.ha_notifier import HANotifier

logger = logging.getLogger(__name__)

@dataclass
class BackupResult:
    """Result of backup processing"""
    success: bool
    source_path: Path
    destination_path: Path
    source_size: int
    destination_size: int
    error: Optional[str] = None
    attempts: int = 1
    duration: float = 0.0  # seconds
    checksum_match: bool = False

class BackupProcessor:
    """
    Processes individual backup files with retry logic and verification.
    """
    
    def __init__(
        self,
        config: Config,
        notifier: HANotifier,
        source_dir: Path,
        dest_dir: Path
    ):
        """
        Initialize backup processor.
        
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
        
        # Ensure destination exists
        self.dest_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Backup processor initialized: {source_dir} -> {dest_dir}")
    
    def process_backup(self, backup_path: Path) -> BackupResult:
        """
        Process a single backup file.
        
        Args:
            backup_path: Path to backup file
            
        Returns:
            BackupResult with processing status
        """
        backup_name = backup_path.name
        logger.info(f"Processing backup: {backup_name}")
        
        # Send start notification
        self._notify_backup_started(backup_name)
        
        # Validate source file
        validation_result = self._validate_source_file(backup_path)
        if not validation_result[0]:
            return BackupResult(
                success=False,
                source_path=backup_path,
                destination_path=self.dest_dir / backup_name,
                source_size=0,
                destination_size=0,
                error=f"Source validation failed: {validation_result[1]}"
            )
        
        # Wait before copying (allow backup to complete)
        if self.config.wait_time > 0:
            logger.info(f"Waiting {self.config.wait_time} seconds before copying...")
            time.sleep(self.config.wait_time)
            
            # Re-validate after waiting
            validation_result = self._validate_source_file(backup_path)
            if not validation_result[0]:
                return BackupResult(
                    success=False,
                    source_path=backup_path,
                    destination_path=self.dest_dir / backup_name,
                    source_size=0,
                    destination_size=0,
                    error=f"Source changed during wait: {validation_result[1]}"
                )
        
        # Calculate source checksum (optional, for verification)
        source_checksum = None
        if self._should_calculate_checksum(backup_path):
            logger.info("Calculating source checksum...")
            source_checksum = self._calculate_checksum(backup_path)
        
        # Copy with retry logic
        start_time = time.time()
        copy_result = self._copy_with_retry(
            source=backup_path,
            destination=self.dest_dir / backup_name,
            source_checksum=source_checksum
        )
        duration = time.time() - start_time
        
        # Prepare result
        result = BackupResult(
            success=copy_result[0],
            source_path=backup_path,
            destination_path=self.dest_dir / backup_name,
            source_size=backup_path.stat().st_size,
            destination_size=(self.dest_dir / backup_name).stat().st_size if copy_result[0] else 0,
            error=copy_result[1],
            attempts=copy_result[2],
            duration=duration,
            checksum_match=copy_result[3] if len(copy_result) > 3 else False
        )
        
        # Handle result
        if result.success:
            self._handle_success(result)
        else:
            self._handle_failure(result)
        
        return result
    
    def _validate_source_file(self, backup_path: Path) -> Tuple[bool, str]:
        """
        Validate source backup file.
        
        Returns:
            (is_valid, error_message)
        """
        try:
            # Check if file exists
            if not backup_path.exists():
                return False, "File does not exist"
            
            # Check if it's a file
            if not backup_path.is_file():
                return False, "Not a regular file"
            
            # Check file size
            file_size = backup_path.stat().st_size
            if file_size == 0:
                return False, "File is empty"
            
            # Check if it's a .tar file
            if backup_path.suffix != '.tar':
                return False, f"Not a .tar file: {backup_path.suffix}"
            
            # Check if file is still being written (optional)
            # This is a simple check - if size changes between two reads
            size1 = backup_path.stat().st_size
            time.sleep(0.1)
            size2 = backup_path.stat().st_size
            
            if size1 != size2:
                return False, "File is still being written"
            
            return True, "Valid"
            
        except Exception as e:
            return False, f"Validation error: {e}"
    
    def _should_calculate_checksum(self, file_path: Path) -> bool:
        """
        Determine if we should calculate checksum for a file.
        Large files may skip checksum for performance.
        """
        file_size = file_path.stat().st_size
        # Calculate checksum for files up to 10GB
        return file_size < 10 * 1024**3  # 10 GB
    
    def _calculate_checksum(self, file_path: Path, algorithm: str = "md5") -> str:
        """
        Calculate file checksum.
        
        Args:
            file_path: Path to file
            algorithm: Hash algorithm (md5, sha1, sha256)
            
        Returns:
            Hex digest of file checksum
        """
        hash_func = hashlib.new(algorithm)
        
        with open(file_path, 'rb') as f:
            # Read in chunks to handle large files
            for chunk in iter(lambda: f.read(8192), b''):
                hash_func.update(chunk)
        
        return hash_func.hexdigest()
    
    def _copy_with_retry(
        self,
        source: Path,
        destination: Path,
        source_checksum: Optional[str] = None
    ) -> Tuple[bool, Optional[str], int, bool]:
        """
        Copy file with retry logic and verification.
        
        Returns:
            (success, error_message, attempts_made, checksum_match)
        """
        last_error = None
        checksum_match = False
        
        for attempt in range(1, self.config.max_retries + 1):
            logger.info(f"Copy attempt {attempt}/{self.config.max_retries}")
            
            try:
                # Remove destination if it exists from previous attempt
                if destination.exists():
                    destination.unlink()
                
                # Copy file
                shutil.copy2(source, destination)
                
                # Verify copy
                verification_result = self._verify_copy(source, destination, source_checksum)
                
                if verification_result[0]:
                    checksum_match = verification_result[2] if len(verification_result) > 2 else False
                    logger.info(f"Copy successful (attempt {attempt})")
                    return True, None, attempt, checksum_match
                else:
                    last_error = verification_result[1]
                    logger.warning(f"Copy verification failed (attempt {attempt}): {last_error}")
            
            except Exception as e:
                last_error = str(e)
                logger.error(f"Copy error (attempt {attempt}): {e}")
            
            # Wait before retry (except on last attempt)
            if attempt < self.config.max_retries:
                wait_time = self.config.retry_delay * attempt  # Exponential backoff
                logger.info(f"Waiting {wait_time}s before retry...")
                time.sleep(wait_time)
        
        # All attempts failed
        error_msg = f"Failed after {self.config.max_retries} attempts"
        if last_error:
            error_msg += f": {last_error}"
        
        return False, error_msg, self.config.max_retries, False
    
    def _verify_copy(
        self,
        source: Path,
        destination: Path,
        source_checksum: Optional[str] = None
    ) -> Tuple[bool, Optional[str], bool]:
        """
        Verify that copy was successful.
        
        Returns:
            (is_valid, error_message, checksum_match)
        """
        try:
            # Check if destination exists
            if not destination.exists():
                return False, "Destination file not created", False
            
            # Compare file sizes
            source_size = source.stat().st_size
            dest_size = destination.stat().st_size
            
            if source_size != dest_size:
                return False, f"Size mismatch: source={source_size}, dest={dest_size}", False
            
            # Compare checksums if available
            if source_checksum:
                logger.info("Verifying checksum...")
                dest_checksum = self._calculate_checksum(destination)
                
                if source_checksum != dest_checksum:
                    return False, f"Checksum mismatch: {source_checksum[:8]} != {dest_checksum[:8]}", False
                
                logger.info("Checksum verification passed")
                return True, None, True
            
            # If no checksum, just check size and existence
            return True, None, False
            
        except Exception as e:
            return False, f"Verification error: {e}", False
    
    def _notify_backup_started(self, backup_name: str) -> None:
        """Send notification about backup start"""
        try:
            self.notifier.send_info_notification(
                "Backup Copy Started",
                f"Starting to copy backup: {backup_name}"
            )
        except Exception as e:
            logger.warning(f"Could not send start notification: {e}")
    
    def _handle_success(self, result: BackupResult) -> None:
        """Handle successful backup processing"""
        # Calculate speed
        speed_mbps = 0
        if result.duration > 0:
            speed_mbps = (result.source_size / result.duration) / (1024**2)
        
        logger.info(
            f"Backup processed successfully: {result.source_path.name}\n"
            f"  Size: {result.source_size / (1024**2):.1f} MB\n"
            f"  Duration: {result.duration:.1f}s\n"
            f"  Speed: {speed_mbps:.1f} MB/s\n"
            f"  Attempts: {result.attempts}"
        )
        
        # Send success notification
        try:
            self.notifier.send_info_notification(
                "Backup Copied Successfully",
                f"Backup copied: {result.source_path.name}\n"
                f"Size: {result.source_size / (1024**2):.1f} MB\n"
                f"Time: {result.duration:.1f}s"
            )
        except Exception as e:
            logger.warning(f"Could not send success notification: {e}")
    
    def _handle_failure(self, result: BackupResult) -> None:
        """Handle failed backup processing"""
        logger.error(
            f"Backup processing failed: {result.source_path.name}\n"
            f"  Error: {result.error}\n"
            f"  Attempts: {result.attempts}"
        )
        
        # Send error notification
        try:
            self.notifier.send_error_notification(
                "Backup Copy Failed",
                f"Failed to copy backup: {result.source_path.name}\n"
                f"Error: {result.error}\n"
                f"Attempts: {result.attempts}"
            )
        except Exception as e:
            logger.warning(f"Could not send error notification: {e}")
    
    def get_backup_size(self, backup_path: Path) -> str:
        """Get human-readable backup size"""
        size_bytes = backup_path.stat().st_size
        
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        
        return f"{size_bytes:.1f} PB"