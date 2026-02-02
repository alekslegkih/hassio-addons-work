# Nextcloud User Files Backup

📘 [Прочтите README на русском](https://github.com/alekslegkih/hassio-addons/blob/main/nc_user_files_backup/README_RU.md)

Home Assistant add-on for automated backup of Nextcloud user files to an external
USB storage device.

The add-on performs scheduled incremental backups using `rsync` and is designed
to work with pre-mounted external storage devices.

## Features

- Automatic handling of external USB disks
- Incremental backups using `rsync`
- Backup scheduling using cron format
- Power control via smart switches (optional)
- Configuration validation before execution
- Test (dry-run) mode
- Notification support (Telegram, mobile notifications, etc.)

## Requirements

- Home Assistant OS
- External storage mounted using `udev` rules
- Root access to the host filesystem

## Important Notice

> [!CAUTION]
> This add-on requires access to the Home Assistant OS host root filesystem.  
> It interferes with the Supervisor-managed operating system.  
> Use this add-on **only if you fully understand the implications**.  
> The author is not responsible for any damage caused by improper use.

## License

[![Addon License: MIT](https://img.shields.io/badge/Addon%20License-MIT-green.svg)](
https://github.com/alekslegkih/hassio-addons/blob/main/LICENSE)

## Documentation

Configuration and usage instructions are available here:  
👉 [Documentation](https://github.com/alekslegkih/hassio-addons/blob/main/nc_user_files_backup/DOCS.md)
