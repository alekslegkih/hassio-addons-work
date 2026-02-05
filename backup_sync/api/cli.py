#!/usr/bin/env python3
"""
Command Line Interface for Backup Sync addon.
Provides manual control and debugging capabilities.
"""

import sys
import json
import logging
from pathlib import Path
from typing import Optional
from datetime import datetime

import click

from config.loader import ConfigLoader
from discovery.disk_scanner import DiskScanner
from discovery.first_run_helper import FirstRunHelper
from storage.disk_mounter import DiskMounter
from storage.storage_validator import StorageValidator, StorageInfo
from backup.backup_orchestrator import BackupOrchestrator
from backup.cleanup_manager import CleanupManager
from notification.notify_sender import NotifySender
from core.logger import setup_logging, get_logger

# Configure logging for CLI
logger = get_logger(__name__)

@click.group()
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose logging')
def cli(verbose):
    """Backup Sync CLI - Manual control and debugging tools"""
    if verbose:
        logger.setLevel(logging.DEBUG)
        logger.debug("Verbose logging enabled")

# ... остальной код остается таким же до функции backup_copy ...

@backup.command(name="copy")
@click.argument('backup_file')
@click.option('--force', '-f', is_flag=True, help='Force copy even if exists')
def backup_copy(backup_file, force):
    """Copy a specific backup file"""
    config = ConfigLoader.load()
    notifier = NotifySender(notify_service=config.get('notify_service', ''))
    
    source_path = Path("/backup") / backup_file
    dest_dir = Path("/media/backups")
    
    if not source_path.exists():
        click.echo(f"Backup file not found: {backup_file}", err=True)
        sys.exit(1)
    
    # Check if already exists
    dest_path = dest_dir / backup_file
    if dest_path.exists() and not force:
        click.echo(f"Backup already exists at destination. Use --force to overwrite.")
        sys.exit(1)
    
    # Initialize processor
    from backup.backup_processor import BackupProcessor
    processor = BackupProcessor(config, notifier, Path("/backup"), dest_dir)
    
    click.echo(f"Copying {backup_file}...")
    result = processor.process_backup(source_path)
    
    if result.success:
        click.echo(f"✅ Successfully copied {backup_file}")
        click.echo(f"   Size: {result.source_size / (1024*1024):.1f} MB")
        click.echo(f"   Duration: {result.duration:.1f}s")
        click.echo(f"   Attempts: {result.attempts}")
    else:
        click.echo(f"❌ Failed to copy {backup_file}: {result.error}", err=True)
        sys.exit(1)

@backup.command(name="sync-existing")
def backup_sync_existing():
    """Sync all existing backups"""
    config = ConfigLoader.load()
    notifier = NotifySender(notify_service=config.get('notify_service', ''))
    
    # Mount disk first if needed
    if config.usb_device:
        mounter = DiskMounter()
        mount_result = mounter.mount_usb_device(config.usb_device)
        if not mount_result.success:
            click.echo(f"Failed to mount USB device: {mount_result.error}", err=True)
            sys.exit(1)
    
    # Initialize orchestrator
    orchestrator = BackupOrchestrator(
        config=config,
        notifier=notifier,
        source_dir=Path("/backup"),
        dest_dir=Path("/media/backups")
    )
    
    click.echo("Syncing existing backups...")
    synced = orchestrator.sync_existing_backups()
    
    if synced:
        click.echo(f"✅ Synced {len(synced)} backup(s):")
        for backup_name in synced:
            click.echo(f"  - {backup_name}")
    else:
        click.echo("No backups needed syncing")

# ... код продолжается до notification.command ...

@notification.command(name="test")
@click.argument('message')
@click.option('--title', '-t', default='Test Notification')
@click.option('--level', '-l', type=click.Choice(['info', 'warning', 'error']), default='info')
def notification_test(message, title, level):
    """Send a test notification"""
    config = ConfigLoader.load()
    notifier = NotifySender(notify_service=config.get('notify_service', ''))
    
    # Используем новый API NotifySender
    success = notifier.send(title, message, level)
    
    if success:
        click.echo(f"✅ Test notification sent: {title}")
    else:
        click.echo("❌ Failed to send notification (check notify_service configuration)", err=True)
        sys.exit(1)

@notification.command(name="services")
def notification_services():
    """List available notification services"""
    try:
        # Для CLI мы не можем использовать HA API без SUPERVISOR_TOKEN
        # Поэтому просто показываем конфигурацию
        config = ConfigLoader.load()
        notify_service = config.get('notify_service', '')
        
        if notify_service:
            click.echo(f"Configured notification service: notify.{notify_service}")
            click.echo("Note: In CLI mode, notification service availability cannot be checked")
            click.echo("without SUPERVISOR_TOKEN and Home Assistant API access.")
        else:
            click.echo("No notification service configured (notify_service is empty)")
            
        click.echo("\nTo configure notifications, set 'notify_service' in config.yaml:")
        click.echo("Example: notify_service: 'telegram'")
        click.echo("Available services depend on your Home Assistant setup.")
        
    except Exception as e:
        click.echo(f"❌ Error checking notification services: {e}", err=True)

# ... остальной код остается без изменений ...