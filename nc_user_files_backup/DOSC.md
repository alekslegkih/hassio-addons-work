# Nextcloud User Files Backup

## Configuration

Home Assistant OS does not provide direct access to USB storage devices.
To use external disks, they must be mounted to the system in advance
and assigned unique filesystem labels.
These labels are used by the add-on to identify the devices.

## System Preparation

Configuring disk mounting requires SSH access to the Home Assistant OS host system.

[![Developer docs – Home Assistant OS Debugging](https://img.shields.io/badge/Developer%20docs-Home%20Assistant-blue?logo=home-assistant&logoColor=white&labelColor=41B3A3)](https://developers.home-assistant.io/docs/operating-system/debugging)

After obtaining SSH access:

1. Connect the external disk.
2. Assign a filesystem label to the disk partition.
3. Configure automatic mounting using the label.

Example of assigning a label to a partition:

```bash

    e2label /dev/sdb2 NC_backup
```

For automatic disk mounting, the author uses a solution based on
[udev](https://gist.github.com/microraptor/be170ea642abeb937fc030175ae89c0c).  
Solution author: [microraptor](https://gist.github.com/microraptor)  
Configure the mounting rule according to the provided instructions.

## Add-on Settings

### Configuration File

After the first start, the add-on creates the configuration file settings.yaml.  
The file must be edited according to your system configuration.

Configuration file location:

```bash

Inside the add-on:

    /config/settings.yaml

In the Home Assistant user interface:

    /addon_configs/901f89a0_nc_user_files_backup/settings.yaml
```

### Configuration Parameters

```text
general.  
General settings

- timezone (string, default: Europe/Moscow)  
  Time zone

- schedule (string, default: 0 3 * * *)  
  Backup schedule in cron format

- rsync_options (string, default: -aHAX --delete)  
  rsync command-line options

- test_mode (bool, default: false)  
  Test execution mode

storage.  
Storage settings

- mount_path (string, default: media)  
  Base directory for disk mounting

- label_backup (string, default: NC_backup)  
  Backup disk filesystem label

- label_data (string, default: Cloud)  
  Data disk filesystem label

- data_dir (string, default: data)  
  Nextcloud data directory

power.  
Power management

- enable_power (bool, default: true)  
  Enable disk power control

- disc_switch (string, default: usb_disk_power)  
  Power switch entity ID without the switch domain

notifications.  
Notifications

- enable_notifications (bool, default: true)  
  Enable notifications

- notification_service (string, default: send_message)  
  Notification service name without the notify domain

- success_message (string)  
  Message sent on successful completion

- error_message (string)  
  Message sent on error
```

### Example Configuration

```yaml
    general:
      timezone: Europe/Moscow
      schedule: 0 3 * * *
      rsync_options: -aHAX --delete
      test_mode: false

    storage:
      mount_path: media
      label_backup: NC_backup
      label_data: Data
      data_dir: data

    power:
      enable_power: true
      disc_switch: usb_disk_power

    notifications:
      enable_notifications: false
      notification_service: telegram_cannel_system
      success_message: Nextcloud user files backup completed successfully!
      error_message: Nextcloud backup completed with errors!
```

Configuration changes are applied on the next add-on start.

## Operation Flow

When executed, the add-on performs the following steps:

1. Enables power to the backup disk (if power control is enabled)
2. Mounts the backup disk
3. Performs incremental backup using rsync
4. Unmounts the disk
5. Disables disk power (if enabled)
6. Sends a notification with the execution result

### First Start

On the first start, the add-on creates the configuration file and exits
without performing a backup.
After editing settings.yaml, the add-on is ready for use.

### Subsequent Starts

On subsequent starts, the add-on initializes the cron scheduler and waits
for the configured execution time.

### Test Mode

When test_mode is enabled, the add-on does not perform actual data copying.
All steps are simulated without modifying any files.

## Common Issues

- Configuration validation failed  
  Check the syntax and required parameters in settings.yaml.

- Backup disk not mounted  
  Verify filesystem labels and udev rules.