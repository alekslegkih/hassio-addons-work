#!/usr/bin/env python3
"""
Command Line Interface for Backup Sync addon.
Provides manual control and debugging capabilities.
"""

from __future__ import annotations

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
from storage.storage_validator import StorageValidator
from backup.backup_orchestrator import BackupOrchestrator
from backup.backup_processor import BackupProcessor
from backup.cleanup_manager import CleanupManager
from notification.notify_sender import NotifySender
from utils.shell_executor import run_command
from core.logger import setup_logging, get_logger

# Constants (HA specific paths)
SOURCE_DIR = Path("/backup")
DEST_DIR = Path("/media/backups")

# Logging
logger = get_logger(__name__)

# CLI root
@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
def cli(verbose: bool):
    """Backup Sync CLI - Manual control and debugging tools"""
    setup_logging(verbose=verbose)

    if verbose:
        logger.debug("Verbose logging enabled")

# Config commands
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
        click.echo(f"  USB Device: {config.get('usb_device') or 'Not configured'}")
        click.echo(f"  Max Copies: {config.get('max_copies')}")
        click.echo(f"  Wait Time: {config.get('wait_time')}s")
        click.echo(f"  Sync Existing: {config.get('sync_existing_on_start')}")
        click.echo(f"  Max Retries: {config.get('max_retries')}")
        click.echo(f"  Retry Delay: {config.get('retry_delay')}s")

    except Exception as e:
        click.echo(f"Error loading config: {e}", err=True)
        sys.exit(1)

@config.command(name="validate")
def config_validate():
    """Validate configuration"""
    try:
        config = ConfigLoader.load()
        errors: list[str] = []

        if not config.get("usb_device"):
            errors.append("USB device not configured")

        if config.get("max_copies", 0) < 1:
            errors.append("max_copies must be at least 1")

        if config.get("wait_time", 0) < 0:
            errors.append("wait_time cannot be negative")

        if config.get("max_retries", 0) < 1:
            errors.append("max_retries must be at least 1")

        if config.get("retry_delay", 0) < 0:
            errors.append("retry_delay cannot be negative")

        if errors:
            click.echo("Configuration validation failed:")
            for error in errors:
                click.echo(f"  ❌ {error}")
            sys.exit(1)

        click.echo("✅ Configuration is valid")

    except Exception as e:
        click.echo(f"Error validating config: {e}", err=True)
        sys.exit(1)

# Disk commands
@cli.group()
def disks():
    """Disk management commands"""
    pass

@disks.command(name="list")
@click.option("--all", "-a", is_flag=True, help="Show all disks, not just USB")
def disks_list(all: bool):
    """List available disks"""
    scanner = DiskScanner()

    if all:
        click.echo("All block devices:")
        success, stdout, stderr = run_command(
            ["lsblk", "-o", "NAME,SIZE,TYPE,MOUNTPOINT"]
        )
        if success:
            click.echo(stdout)
        else:
            click.echo(stderr, err=True)
        return

    usb_disks = scanner.scan_usb_disks()

    if not usb_disks:
        click.echo("No USB disks found")
        return

    click.echo(f"Found {len(usb_disks)} USB disk(s):\n")

    for i, disk in enumerate(usb_disks, 1):
        size = (
            f"{disk.size_gb:.1f}GB"
            if disk.size_gb >= 1
            else f"{disk.size_gb * 1024:.0f}MB"
        )

        click.echo(f"{i}. {disk.name} ({size}, {disk.filesystem or 'Unknown'})")

        if disk.label:
            click.echo(f"   Label: {disk.label}")
        if disk.uuid:
            click.echo(f"   UUID: {disk.uuid}")
        if disk.mountpoint:
            click.echo(f"   Mounted at: {disk.mountpoint}")

        click.echo("")

@disks.command(name="mount")
@click.argument("device")
@click.option("--mount-point", "-m", default=str(DEST_DIR), help="Mount point")
def disks_mount(device: str, mount_point: str):
    """Mount a USB disk"""
    mounter = DiskMounter(Path(mount_point))
    result = mounter.mount_usb_device(device)

    if result.success:
        click.echo(f"✅ Mounted {device} to {mount_point}")
    else:
        click.echo(f"❌ Failed to mount {device}: {result.error}", err=True)
        sys.exit(1)

@disks.command(name="unmount")
@click.argument("device")
def disks_unmount(device: str):
    """Unmount a USB disk"""
    mounter = DiskMounter()

    if mounter.unmount_device(device):
        click.echo(f"✅ Unmounted {device}")
    else:
        click.echo(f"❌ Failed to unmount {device}", err=True)
        sys.exit(1)

# Storage commands
@cli.group()
def storage():
    """Storage commands"""
    pass

@storage.command(name="info")
@click.argument("path", default=str(DEST_DIR))
def storage_info(path: str):
    """Get storage information"""
    storage_path = Path(path)

    if not storage_path.exists():
        click.echo(f"Path {path} does not exist", err=True)
        sys.exit(1)

    validator = StorageValidator()
    info = validator.get_storage_info(storage_path)

    click.echo(f"Storage information for {path}:")
    click.echo(f"  Total: {info.total_gb:.1f} GB")
    click.echo(f"  Used: {info.used_gb:.1f} GB")
    click.echo(f"  Free: {info.free_gb:.1f} GB ({info.free_percent:.1f}%)")
    click.echo(f"  Mount point: {'Yes' if info.is_mount_point else 'No'}")
    click.echo(f"  Writable: {'Yes' if info.is_writable else 'No'}")

# Backup commands
@cli.group()
def backup():
    """Backup management commands"""
    pass


@backup.command(name="list")
@click.option("--json", "-j", is_flag=True, help="Output as JSON")
def backup_list(json: bool):
    """List backup files"""
    results = {}

    source_files = sorted(
        SOURCE_DIR.glob("*.tar"), key=lambda f: f.stat().st_mtime
    )

    results["source"] = [
        {
            "name": f.name,
            "size": f.stat().st_size,
            "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
        }
        for f in source_files
    ]

    if DEST_DIR.exists():
        dest_files = sorted(
            DEST_DIR.glob("*.tar"), key=lambda f: f.stat().st_mtime
        )
        results["destination"] = [
            {
                "name": f.name,
                "size": f.stat().st_size,
                "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
            }
            for f in dest_files
        ]
    else:
        results["destination"] = []

    if json:
        click.echo(json.dumps(results, indent=2))
        return

    click.echo("Source backups (/backup):")
    for f in results["source"]:
        click.echo(f"  {f['name']}")

    click.echo("\nDestination backups (/media/backups):")
    if results["destination"]:
        for f in results["destination"]:
            click.echo(f"  {f['name']}")
    else:
        click.echo("  No backups found")

@backup.command(name="copy")
@click.argument("backup_file")
@click.option("--force", "-f", is_flag=True, help="Force overwrite")
def backup_copy(backup_file: str, force: bool):
    """Copy a specific backup file"""
    config = ConfigLoader.load()
    notifier = NotifySender(config.get("notify_service", ""))

    source_path = SOURCE_DIR / backup_file
    dest_path = DEST_DIR / backup_file

    if not source_path.exists():
        click.echo("Backup file not found", err=True)
        sys.exit(1)

    if dest_path.exists() and not force:
        click.echo("Backup already exists. Use --force.")
        sys.exit(1)

    processor = BackupProcessor(config, notifier, SOURCE_DIR, DEST_DIR)
    result = processor.process_backup(source_path)

    if result.success:
        click.echo(f"✅ Copied {backup_file}")
    else:
        click.echo(f"❌ Failed: {result.error}", err=True)
        sys.exit(1)

# Meta commands
@cli.command()
def version():
    """Show version"""
    config = ConfigLoader.load()
    click.echo("Backup Sync CLI")
    click.echo(f"Version: {config.get('version', 'unknown')}")
    click.echo("Home Assistant Add-on")

@cli.command()
def status():
    """Show overall system status"""
    config = ConfigLoader.load()

    click.echo("Backup Sync Status")
    click.echo("=" * 40)

    click.echo(f"Config: {'✅ OK' if config.get('usb_device') else '⚠️  First run'}")

    click.echo(
        f"Source: {'✅' if SOURCE_DIR.exists() else '❌'} "
        f"({len(list(SOURCE_DIR.glob('*.tar')))} backups)"
    )

    click.echo(
        f"Destination: {'✅' if DEST_DIR.exists() else '❌'} "
        f"({len(list(DEST_DIR.glob('*.tar')))} backups)"
    )

    if config.get("usb_device"):
        mounter = DiskMounter()
        mounted = mounter.is_mounted(config.get("usb_device"))
        click.echo(f"USB Mount: {'✅' if mounted else '❌'}")

    click.echo("=" * 40)

if __name__ == "__main__":
    cli()
