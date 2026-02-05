#!/usr/bin/env python3
"""
Simulation test for Backup Sync addon.
Tests the main components without actual hardware.
"""

import tempfile
import shutil
from pathlib import Path
import sys

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

def test_config_loader():
    """Test configuration loading"""
    print("Testing ConfigLoader...")
    from config.loader import ConfigLoader
    
    # Create temp config file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        config_data = {
            "usb_device": "sdb1",
            "max_copies": 3,
            "wait_time": 10,
            "sync_existing_on_start": True,
            "max_retries": 2,
            "retry_delay": 5
        }
        import json
        json.dump(config_data, f)
        config_path = f.name
    
    try:
        # Test loading
        config = ConfigLoader.load(config_path)
        print(f"  ✅ Config loaded: USB={config.usb_device}, Max copies={config.max_copies}")
        
        # Test validation
        assert config.usb_device == "sdb1"
        assert config.max_copies == 3
        print("  ✅ Config validation passed")
        
    finally:
        Path(config_path).unlink()
    
    return True

def test_disk_scanner_simulation():
    """Test disk scanner with simulation"""
    print("\nTesting DiskScanner (simulation)...")
    from discovery.disk_scanner import DiskScanner
    
    scanner = DiskScanner()
    
    # Mock some USB disks (in real test, would mock system calls)
    print("  ⚠️  Disk scanner requires system access (skipping detailed test)")
    print("  Note: In real environment, would list USB disks")
    
    return True

def test_backup_processor():
    """Test backup processor with temp files"""
    print("\nTesting BackupProcessor...")
    
    # Create temp directories
    with tempfile.TemporaryDirectory() as source_dir, \
         tempfile.TemporaryDirectory() as dest_dir:
        
        source_path = Path(source_dir)
        dest_path = Path(dest_dir)
        
        # Create a test backup file
        test_backup = source_path / "test_backup.tar"
        test_backup.write_bytes(b"fake backup data" * 1000)  # 16KB
        
        # Mock config
        from dataclasses import dataclass
        
        @dataclass
        class MockConfig:
            usb_device: str = "sdb1"
            max_copies: int = 3
            wait_time: int = 1  # Short wait for test
            sync_existing_on_start: bool = True
            max_retries: int = 2
            retry_delay: int = 1
        
        # Mock notifier
        class MockNotifier:
            def send_info_notification(self, title, message):
                print(f"  Notification: {title}")
                return True
        
        # Import and test
        from backup.backup_processor import BackupProcessor
        
        config = MockConfig()
        notifier = MockNotifier()
        processor = BackupProcessor(config, notifier, source_path, dest_path)
        
        # Process backup
        result = processor.process_backup(test_backup)
        
        if result.success:
            print(f"  ✅ Backup processed successfully")
            print(f"    Size: {result.source_size} bytes")
            print(f"    Duration: {result.duration:.2f}s")
            print(f"    Attempts: {result.attempts}")
        else:
            print(f"  ❌ Backup processing failed: {result.error}")
            return False
        
        # Check file was copied
        dest_file = dest_path / "test_backup.tar"
        if dest_file.exists():
            print(f"  ✅ File copied to destination")
        else:
            print(f"  ❌ File not found in destination")
            return False
    
    return True

def test_cleanup_manager():
    """Test cleanup manager"""
    print("\nTesting CleanupManager...")
    
    with tempfile.TemporaryDirectory() as backup_dir:
        backup_path = Path(backup_dir)
        
        # Create test backup files with different ages
        import time
        files = [
            ("old_backup_1.tar", 1000, time.time() - 3600 * 24 * 7),  # 7 days old
            ("old_backup_2.tar", 2000, time.time() - 3600 * 24 * 3),  # 3 days old
            ("recent_backup_1.tar", 1500, time.time() - 3600),        # 1 hour old
            ("recent_backup_2.tar", 1800, time.time() - 1800),        # 30 min old
        ]
        
        for filename, size, mtime in files:
            file_path = backup_path / filename
            file_path.write_bytes(b"x" * size)
            # Set modification time
            import os
            os.utime(file_path, (mtime, mtime))
        
        # Test cleanup manager
        from backup.cleanup_manager import CleanupManager
        
        # Keep only 2 backups
        cleaner = CleanupManager(max_backups=2, backup_dir=backup_path)
        
        # Get stats
        stats = cleaner.get_backup_stats()
        print(f"  Initial backups: {stats['count']}")
        print(f"  Total size: {stats['total_size_formatted']}")
        
        # Cleanup
        deleted = cleaner.cleanup_old_backups()
        print(f"  Deleted {len(deleted)} backup(s)")
        
        # Check result
        remaining = list(backup_path.glob("*.tar"))
        if len(remaining) == 2:
            print(f"  ✅ Kept {len(remaining)} backups as configured")
            for file in remaining:
                print(f"    - {file.name}")
        else:
            print(f"  ❌ Expected 2 backups, got {len(remaining)}")
            return False
    
    return True

def test_cli_commands():
    """Test basic CLI commands"""
    print("\nTesting CLI commands...")
    
    # Test that CLI can be imported and initialized
    from api.cli import cli
    
    print("  ✅ CLI module loaded successfully")
    
    # We can't easily test click commands without running them,
    # but we can verify the structure
    print("  CLI commands available:")
    for command_name, command in cli.commands.items():
        print(f"    - {command_name}")
    
    return True

def main():
    """Run all tests"""
    print("=" * 60)
    print("Backup Sync Addon - Simulation Tests")
    print("=" * 60)
    
    tests = [
        ("Config Loader", test_config_loader),
        ("Backup Processor", test_backup_processor),
        ("Cleanup Manager", test_cleanup_manager),
        ("CLI Commands", test_cli_commands),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            success = test_func()
            results.append((test_name, success, None))
        except Exception as e:
            results.append((test_name, False, str(e)))
    
    print("\n" + "=" * 60)
    print("Test Results:")
    print("=" * 60)
    
    all_passed = True
    for test_name, success, error in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status}: {test_name}")
        if error:
            print(f"     Error: {error}")
        if not success:
            all_passed = False
    
    print("\n" + "=" * 60)
    if all_passed:
        print("All simulation tests passed! ✅")
        print("The addon logic appears to be working correctly.")
    else:
        print("Some tests failed. Review the errors above.")
    
    return all_passed

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)