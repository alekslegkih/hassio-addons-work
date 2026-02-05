#!/usr/bin/env python3
"""
Command Line Interface for Backup Sync addon.
Provides manual control and debugging capabilities.
"""

import sys
import json
import logging
from pathlib import Path
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

@cli.group()
def config():
    """Configuration commands"""
    pass

@config.command(name="show")
def config_show():
    """Show current configuration"""
    try:
        config = ConfigLoader.load()
        click.echo("Current Configuration:")
        click.echo(f"  USB Device: {config.usb_device or 'Not configured'}")
        click.echo(f"  Max Copies: {config.max_copies}")
        click.echo(f"  Wait Time: {config.wait_time}s")
        click.echo(f"  Sync Existing: {config.sync_existing_on_start}")
        click.echo(f"  Max Retries: {config.max_retries}")
        click.echo(f"  Retry Delay: {config.retry_delay}s")
    except Exception as e:
        click.echo(f"Error loading config: {e}", err=True)
        sys.exit(1)

@config.command(name="validate")
def config_validate():
    """Validate configuration"""
    try:
        config = ConfigLoader.load()
        
        errors = []
        
        if not config.usb_device:
            errors.append("USB device not configured")
        
        if config.max_copies < 1:
            errors.append("max_copies must be at least 1")
        
        if config.wait_time < 0:
            errors.append("wait_time cannot be negative")
        
        if config.max_retries < 1:
            errors.append("max_retries must be at least 1")
        
        if config.retry_delay < 0:
            errors.append("retry_delay cannot be negative")
        
        if errors:
            click.echo("Configuration validation failed:")
            for error in errors:
                click.echo(f"  ❌ {error}")
            sys.exit(1)
        else:
            click.echo("✅ Configuration is valid")
            
    except Exception as e:
        click.echo(f"Error validating config: {e}", err=True)
        sys.exit(1)

@cli.group()
def disks():
    """Disk management commands"""
    pass

@disks.command(name="list")
@click.option('--all', '-a', is_flag=True, help='Show all disks, not just USB')
def disks_list(all):
    """List available disks"""
    scanner = DiskScanner()
    
    if all:
        # Get all block devices (simplified)
        click.echo("All block devices:")
        success, stdout, stderr = run_command(["lsblk", "-o", "NAME,SIZE,TYPE,MOUNTPOINT"])
        if success:
            click.echo(stdout)
        else:
            click.echo("Error listing disks", err=True)
    else:
        # Show USB disks only
        usb_disks = scanner.scan_usb_disks()
        
        if not usb_disks:
            click.echo("No USB disks found")
            return
        
        click.echo(f"Found {len(usb_disks)} USB disk(s):")
        click.echo("")
        
        for i, disk in enumerate(usb_disks, 1):
            size_gb = f"{disk.size_gb:.1f}GB" if disk.size_gb >= 1 else f"{disk.size_gb*1024:.0f}MB"
            fs_info = disk.filesystem if disk.filesystem else "Unknown"
            
            click.echo(f"{i}. {disk.name} ({size_gb}, {fs_info})")
            if disk.label:
                click.echo(f"   Label: {disk.label}")
            if disk.uuid:
                click.echo(f"   UUID: {disk.uuid}")
            if disk.mountpoint:
                click.echo(f"   Mounted at: {disk.mountpoint}")
            click.echo("")

@disks.command(name="info")
@click.argument('device')
def disks_info(device):
    """Get detailed information about a disk"""
    scanner = DiskScanner()
    disk_info = scanner.get_disk_by_name(device)
    
    if not disk_info:
        click.echo(f"Device {device} not found", err=True)
        sys.exit(1)
    
    click.echo(f"Information for {device}:")
    click.echo(f"  Device Path: {disk_info.device_path}")
    click.echo(f"  Size: {disk_info.size_gb:.1f} GB")
    click.echo(f"  Filesystem: {disk_info.filesystem or 'Unknown'}")
    click.echo(f"  Label: {disk_info.label or 'None'}")
    click.echo(f"  UUID: {disk_info.uuid or 'None'}")
    click.echo(f"  Mount Point: {disk_info.mountpoint or 'Not mounted'}")
    click.echo(f"  Is USB: {'Yes' if disk_info.is_usb else 'No'}")
    click.echo(f"  Is Partition: {'Yes' if disk_info.is_partition else 'No'}")
    if disk_info.is_partition:
        click.echo(f"  Parent Disk: {disk_info.parent_disk}")

@disks.command(name="mount")
@click.argument('device')
@click.option('--mount-point', '-m', default='/media/backups', help='Mount point')
def disks_mount(device, mount_point):
    """Mount a USB disk"""
    mounter = DiskMounter(Path(mount_point))
    result = mounter.mount_usb_device(device)
    
    if result.success:
        click.echo(f"✅ Successfully mounted {device} to {mount_point}")
        click.echo(f"   Filesystem: {result.filesystem}")
        if result.was_already_mounted:
            click.echo("   (Was already mounted)")
    else:
        click.echo(f"❌ Failed to mount {device}: {result.error}", err=True)
        sys.exit(1)

@disks.command(name="unmount")
@click.argument('device')
def disks_unmount(device):
    """Unmount a USB disk"""
    mounter = DiskMounter()
    success = mounter.unmount_device(device)
    
    if success:
        click.echo(f"✅ Successfully unmounted {device}")
    else:
        click.echo(f"❌ Failed to unmount {device}", err=True)
        sys.exit(1)

@cli.group()
def storage():
    """Storage commands"""
    pass

@storage.command(name="info")
@click.argument('path', default='/media/backups')
def storage_info(path):
    """Get storage information"""
    validator = StorageValidator()
    storage_path = Path(path)
    
    if not storage_path.exists():
        click.echo(f"Path {path} does not exist", err=True)
        sys.exit(1)
    
    info = validator.get_storage_info(storage_path)
    
    click.echo(f"Storage information for {path}:")
    click.echo(f"  Total: {info.total_gb:.1f} GB")
    click.echo(f"  Used: {info.used_gb:.1f} GB")
    click.echo(f"  Free: {info.free_gb:.1f} GB ({info.free_percent:.1f}%)")
    click.echo(f"  Is Mount Point: {'Yes' if info.is_mount_point else 'No'}")
    click.echo(f"  Is Writable: {'Yes' if info.is_writable else 'No'}")
    if info.filesystem:
        click.echo(f"  Filesystem: {info.filesystem}")

@storage.command(name="validate")
@click.argument('path', default='/media/backups')
def storage_validate(path):
    """Validate storage for backups"""
    validator = StorageValidator()
    storage_path = Path(path)
    
    is_valid, warnings = validator.validate_for_backups(storage_path)
    
    if is_valid:
        click.echo(f"✅ Storage {path} is valid for backups")
        if warnings:
            click.echo("Warnings:")
            for warning in warnings:
                click.echo(f"  ⚠️  {warning}")
    else:
        click.echo(f"❌ Storage {path} is NOT valid for backups", err=True)
        sys.exit(1)

@cli.group()
def backup():
    """Backup management commands"""
    pass

@backup.command(name="list")
@click.option('--source', '-s', is_flag=True, help='List source backups')
@click.option('--destination', '-d', is_flag=True, help='List destination backups')
@click.option('--json', '-j', is_flag=True, help='Output as JSON')
def backup_list(source, destination, json):
    """List backup files"""
    config = ConfigLoader.load()
    
    source_dir = Path("/backup")
    dest_dir = Path("/media/backups")
    
    results = {}
    
    if source or (not source and not destination):
        source_files = list(source_dir.glob("*.tar"))
        source_files.sort(key=lambda x: x.stat().st_mtime)
        results["source"] = [
            {
                "name": f.name,
                "size": f.stat().st_size,
                "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat()
            }
            for f in source_files
        ]
    
    if destination or (not source and not destination):
        if dest_dir.exists():
            dest_files = list(dest_dir.glob("*.tar"))
            dest_files.sort(key=lambda x: x.stat().st_mtime)
            results["destination"] = [
                {
                    "name": f.name,
                    "size": f.stat().st_size,
                    "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat()
                }
                for f in dest_files
            ]
        else:
            results["destination"] = []
    
    if json:
        click.echo(json.dumps(results, indent=2))
    else:
        if "source" in results:
            click.echo("Source backups (/backup):")
            for file_info in results["source"]:
                size_mb = file_info["size"] / (1024*1024)
                click.echo(f"  {file_info['name']} ({size_mb:.1f} MB)")
            click.echo("")
        
        if "destination" in results:
            click.echo("Destination backups (/media/backups):")
            if results["destination"]:
                for file_info in results["destination"]:
                    size_mb = file_info["size"] / (1024*1024)
                    click.echo(f"  {file_info['name']} ({size_mb:.1f} MB)")
            else:
                click.echo("  No backups found")

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

@backup.command(name="cleanup")
@click.option('--force', '-f', is_flag=True, help='Force cleanup even if under limit')
@click.option('--dry-run', '-n', is_flag=True, help='Show what would be deleted')
def backup_cleanup(force, dry_run):
    """Clean up old backups"""
    config = ConfigLoader.load()
    cleaner = CleanupManager(config.max_copies, Path("/media/backups"))
    
    if dry_run:
        plan = cleaner.get_cleanup_plan()
        
        if plan["needed"]:
            click.echo("Cleanup would delete:")
            for file_info in plan["to_delete"]:
                click.echo(f"  - {file_info['name']} ({file_info['size_formatted']})")
            click.echo(f"Total freed: {plan['freed_space_formatted']}")
        else:
            click.echo("No cleanup needed")
    else:
        deleted = cleaner.cleanup_old_backups(force=force)
        
        if deleted:
            click.echo(f"✅ Deleted {len(deleted)} backup(s):")
            for backup_name in deleted:
                click.echo(f"  - {backup_name}")
        else:
            click.echo("No backups deleted")

@backup.command(name="stats")
@click.option('--json', '-j', is_flag=True, help='Output as JSON')
def backup_stats(json):
    """Show backup statistics"""
    config = ConfigLoader.load()
    cleaner = CleanupManager(config.max_copies, Path("/media/backups"))
    
    stats = cleaner.get_backup_stats()
    storage_info = cleaner.get_storage_usage()
    
    if json:
        result = {
            "backups": stats,
            "storage": storage_info
        }
        click.echo(json.dumps(result, indent=2))
    else:
        click.echo("Backup Statistics:")
        click.echo(f"  Backup Count: {stats['count']}")
        click.echo(f"  Total Size: {stats['total_size_formatted']}")
        if stats['oldest']:
            click.echo(f"  Oldest: {stats['oldest']}")
        if stats['newest']:
            click.echo(f"  Newest: {stats['newest']}")
        
        click.echo("\nStorage Usage:")
        click.echo(f"  Total: {storage_info['total_formatted']}")
        click.echo(f"  Used: {storage_info['used_formatted']}")
        click.echo(f"  Free: {storage_info['free_formatted']} ({storage_info['free_percent']:.1f}%)")

@cli.group()
def notification():
    """Notification commands"""
    pass

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

@cli.command()
def version():
    """Show version information"""
    click.echo("Backup Sync CLI")
    click.echo("Version: 0.1.0")
    click.echo("Home Assistant Addon")

@cli.command()
def status():
    """Show overall system status"""
    click.echo("Backup Sync System Status")
    click.echo("=" * 40)
    
    # Load config
    try:
        config = ConfigLoader.load()
        click.echo(f"Config: {'✅ Loaded' if config.usb_device else '⚠️  First run needed'}")
    except Exception as e:
        click.echo(f"Config: ❌ Error: {e}")
    
    # Check source directory
    source_dir = Path("/backup")
    if source_dir.exists():
        source_files = len(list(source_dir.glob("*.tar")))
        click.echo(f"Source (/backup): ✅ {source_files} backup(s)")
    else:
        click.echo("Source (/backup): ❌ Not accessible")
    
    # Check destination
    dest_dir = Path("/media/backups")
    if dest_dir.exists():
        dest_files = len(list(dest_dir.glob("*.tar")))
        click.echo(f"Destination (/media/backups): ✅ {dest_files} backup(s)")
    else:
        click.echo("Destination (/media/backups): ❌ Not accessible")
    
    # Check USB mount
    if config.usb_device:
        mounter = DiskMounter()
        mounted = mounter._is_mounted_correctly(config.usb_device)
        click.echo(f"USB Mount: {'✅ Mounted' if mounted else '❌ Not mounted'}")
    
    click.echo("=" * 40)

# Helper function for shell commands
def run_command(cmd):
    """Run a shell command and return result"""
    import subprocess
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return True, result.stdout.strip(), result.stderr.strip()
    except subprocess.CalledProcessError as e:
        return False, e.stdout.strip(), e.stderr.strip()
    except Exception as e:
        return False, "", str(e)

if __name__ == "__main__":
    cli()