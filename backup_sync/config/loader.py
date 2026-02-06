#!/usr/bin/env python3
"""
Configuration loader for Backup Sync addon.
Loads settings from /data/options.json and provides defaults.
"""

import json
import logging
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Any

# Import our modules
from core.logger import setup_logging

@dataclass
class Config:
    """Main configuration for Backup Sync addon"""
    usb_device: str                    # e.g., "sda1", "sdb1"
    max_copies: int                   # Maximum number of backups to keep
    wait_time: int                    # Seconds to wait before copying
    sync_existing_on_start: bool      # Sync existing backups on startup
    max_retries: int                  # Maximum retry attempts
    retry_delay: int                  # Delay between retries (seconds)
    log_level: str                    # Logging level: DEBUG, INFO, WARNING, ERROR
    notify_service: str               # Notification service channel

class ConfigLoader:
    """Loads and validates configuration from options.json"""
    
    DEFAULT_CONFIG = {
        "usb_device": "",
        "max_copies": 5,
        "wait_time": 300,
        "sync_existing_on_start": True,
        "max_retries": 3,
        "retry_delay": 30,
        "log_level": "INFO",
        "notify_service": "notification_channel"
    }
    
    @staticmethod
    def load(config_path: str = "/data/options.json") -> Config:
        """
        Load configuration from HAOS options.json
        
        Args:
            config_path: Path to options.json file
            
        Returns:
            Config object with all settings
            
        Raises:
            FileNotFoundError: If config file doesn't exist
            json.JSONDecodeError: If config file is invalid JSON
        """
        config_file = Path(config_path)
        
        if not config_file.exists():
            print(f"[WARNING]Config file not found at {config_path}, using defaults")
            user_config = {}
        else:
            try:
                with open(config_file, 'r') as f:
                    user_config = json.load(f)
                print(f"[INFO]Loaded config from {config_path}")
            except json.JSONDecodeError as e:
                print(f"[ERROR] Invalid JSON in config file: {e}")
                raise
        
        # Merge defaults with user config
        config_dict = ConfigLoader.DEFAULT_CONFIG.copy()
        config_dict.update(user_config)
        
        # Validate and convert to Config object
        config = ConfigLoader._create_config(config_dict)

        # Setup logging with config level
        logger = setup_logging(log_level=config.log_level)
        logger.info("=" * 60)
        logger.info("Starting Backup Sync addon")
        logger.info("=" * 60)
        
        # Log configuration (without sensitive info)
        logger.info(f"Configuration loaded: USB device='{config.usb_device}'")
        logger.info(f"  Max copies: {config.max_copies}")
        logger.info(f"  Wait time: {config.wait_time}s")
        logger.info(f"  Sync existing: {config.sync_existing_on_start}")
        logger.info(f"  Max retries: {config.max_retries}")
        logger.info(f"  Retry delay: {config.retry_delay}s")
        logger.info(f"  Log level: {config.log_level}")
        logger.info(f"  Notify service: {config.notify_service}")
        
        return config
    
    @staticmethod
    def _create_config(config_dict: dict) -> Config:
        """Create Config object from dictionary with validation"""
        try:
            # Ensure correct types
            config = Config(
                usb_device=str(config_dict.get("usb_device", "")),
                max_copies=int(config_dict.get("max_copies", 5)),
                wait_time=int(config_dict.get("wait_time", 300)),
                sync_existing_on_start=bool(config_dict.get("sync_existing_on_start", True)),
                max_retries=int(config_dict.get("max_retries", 3)),
                retry_delay=int(config_dict.get("retry_delay", 30)),
                log_level=str(config_dict.get("log_level", "INFO")),
                notify_service=str(config_dict.get("notify_service", "notification_channel"))
            )
            
            # Additional validation
            ConfigLoader._validate_config(config)
            
            return config
            
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid configuration value: {e}")
            raise ValueError(f"Configuration error: {e}")
    
    @staticmethod
    def _validate_config(config: Config) -> None:
        """Validate configuration values"""
        errors = []
        
        # USB device validation (if provided)
        if config.usb_device:
            if not config.usb_device.startswith(("sd", "mmc", "nvme")):
                errors.append(f"Invalid USB device name: {config.usb_device}")
        
        # Numeric validations
        if config.max_copies < 1:
            errors.append(f"max_copies must be >= 1, got {config.max_copies}")
        
        if config.wait_time < 0:
            errors.append(f"wait_time must be >= 0, got {config.wait_time}")
        
        if config.max_retries < 1:
            errors.append(f"max_retries must be >= 1, got {config.max_retries}")
        
        if config.retry_delay < 0:
            errors.append(f"retry_delay must be >= 0, got {config.retry_delay}")
        
        valid_log_levels = ["OFF", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]  # Добавить OFF
        if config.log_level.upper() not in valid_log_levels:
            errors.append(f"log_level must be one of {valid_log_levels}, got {config.log_level}")
        
        if errors:
            error_msg = "; ".join(errors)
            logger.error(f"Configuration validation failed: {error_msg}")
            raise ValueError(f"Invalid configuration: {error_msg}")
    
    @staticmethod
    def get_raw_config(config_path: str = "/data/options.json") -> dict:
        """
        Get raw configuration dictionary (for debugging)
        
        Args:
            config_path: Path to options.json
            
        Returns:
            Raw configuration dictionary
        """
        config_file = Path(config_path)
        
        if not config_file.exists():
            return {}
        
        try:
            with open(config_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to read raw config: {e}")
            return {}