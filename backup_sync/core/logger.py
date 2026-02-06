#!/usr/bin/env python3
"""
Logging configuration for Backup Sync addon.
Provides consistent logging to both stdout (for HA UI) and file.
"""

import logging
import sys
from pathlib import Path
from typing import Optional

# Mapping from string levels to logging constants
LOG_LEVELS = {
    "OFF": logging.CRITICAL + 10,    # Higher than CRITICAL = disable all
    "DEBUG": logging.DEBUG,          # 10
    "INFO": logging.INFO,            # 20  
    "WARNING": logging.WARNING,      # 30
    "WARN": logging.WARNING,         # 30 (alias)
    "ERROR": logging.ERROR,          # 40
    "CRITICAL": logging.CRITICAL,    # 50
    "FATAL": logging.CRITICAL,       # 50 (alias)
}

def setup_logging(
    log_level: str = "INFO",
    log_file: Optional[str] = "/config/backup_sync.log"
) -> logging.Logger:
    """
    Setup logging configuration.
    
    Args:
        log_level: Logging level as string (OFF, DEBUG, INFO, WARNING, ERROR)
        log_file: Path to log file, or None for stdout only
    
    Returns:
        Configured logger instance
    
    Raises:
        ValueError: If log_level is invalid
    """
    # Convert string level to logging constant
    level_str_upper = log_level.upper()
    if level_str_upper not in LOG_LEVELS:
        valid_levels = ", ".join(sorted(LOG_LEVELS.keys()))
        raise ValueError(
            f"Invalid log level: '{log_level}'. Must be one of: {valid_levels}"
        )
    
    numeric_level = LOG_LEVELS[level_str_upper]
    
    # Create logger
    logger = logging.getLogger("backup_sync")
    logger.setLevel(numeric_level)
    
    # For OFF level, we can return early with just the logger
    # No handlers needed since nothing will be logged anyway
    if level_str_upper == "OFF":
        logger.propagate = True
        return logger
    
    # Clear any existing handlers (except for OFF level)
    logger.handlers.clear()
    
    # Create formatter
    # '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # 1. Console handler (for HA Supervisor UI)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # 2. File handler (for persistent logs)
    if log_file:
        try:
            # Ensure log directory exists
            log_path = Path(log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setLevel(numeric_level)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
            
            logger.debug(f"File logging enabled: {log_file}")
        except Exception as e:
            # Use basic logger since file logging failed
            logger.warning(f"Could not setup file logging: {e}")
    
    # Prevent propagation to root logger
    logger.propagate = False
    
    return logger

def get_logger(name: str = "backup_sync") -> logging.Logger:
    """
    Get a logger instance with the given name.
    
    Args:
        name: Logger name (usually module name)
    
    Returns:
        Logger instance
    """
    return logging.getLogger(name)

# Example usage in other modules:
# from core.logger import get_logger
# logger = get_logger(__name__)
# logger.info("Module started")