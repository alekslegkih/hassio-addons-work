"""
Discovery module for detecting and analyzing USB disks.
"""

from .disk_scanner import DiskScanner, DiskInfo
from .first_run_helper import FirstRunHelper

__all__ = ["DiskScanner", "DiskInfo", "FirstRunHelper"]