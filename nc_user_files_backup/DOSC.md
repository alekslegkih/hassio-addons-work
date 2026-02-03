# Nextcloud User Files Backup

## Configuration

Home Assistant OS does not provide direct access to USB storage devices.
To use external disks, they must be mounted into the system in advance
and assigned unique filesystem labels.
These labels are used by the add-on to identify devices.

## System Preparation

Configuring disk mounting requires SSH access to the Home Assistant OS host system.

[![Developer docs – Home Assistant OS Debugging](https://img.shields.io/badge/Developer%20docs-Home%20Assistant-blue?logo=home-assistant&logoColor=white&labelColor=41B3A3)](https://developers.home-assistant.io/docs/operating-system/debugging)

After obtaining access:

1. Connect the external disk.
2. Assign a filesystem label to the partition.
3. Configure automatic mounting using the label.

Example of assigning a filesystem label:

```bash

  e2label /dev/sdb2 NC_backup
```

For automatic disk mounting, the author uses a solution based on
[udev](https://gist.github.com/microraptor/be170ea642abeb937fc030175ae89c0c).
Solution author: [microraptor](https://gist.github.com/microraptor).  
Configure the mounting rule according to the provided instructions.

---

## Configuration Parameters

### General Settings

- **Timezone (`timezone`)**  
  Time zone used by the add-on for task scheduling and logging.

- **Schedule (`schedule`)**  
  Backup execution schedule in cron format  
  (minute, hour, day of month, month, day of week).

- **Rsync options (`rsync_options`)**  
  Options passed to the `rsync` utility during backup execution.  
  Used to control file copy and synchronization behavior.

- **Test mode (`test_mode`)**  
  When enabled, the backup process is simulated without actual  
  data copying.  
  Used to verify configuration and add-on logic.

### Storage Settings (`storage`)

- **Mount root (`mount_root`)**  
  Base directory where mounted external disks are available  
  (for example: `media`).

- **Backup disk label (`backup_disk_label`)**  
  Filesystem label of the external disk used to store backups.

- **Data disk label (`data_disk_label`)**  
  Filesystem label of the disk that contains Nextcloud data.

- **Nextcloud data directory (`nextcloud_data_dir`)**  
  Directory inside the data disk that contains Nextcloud user files.

### Power Management (`power`)

- **Enable power management (`enabled`)**  
  Enables power control of the external backup disk  
  using a smart switch.

- **Disk power switch (`disk_switch`)**  
  Home Assistant switch entity ID **without the `switch.` domain**  
  (for example: `usb_disk_power`).

> [!WARNING]  
> If power management is enabled (`enabled: true`),  
> the `disk_switch` parameter is **required**.  
> If the switch is not specified, the add-on will not start.

### Notifications (`notifications`)

- **Enable notifications (`enabled`)**  
  Enables sending notifications about the backup result.

- **Notification service (`service`)**  
  Home Assistant notification service **without the `notify.` domain**  
  (for example: `send_message`, `telegram`).

- **Success message (`success_message`)**  
  Notification text sent when the backup completes successfully.

- **Error message (`error_message`)**  
  Notification text sent when the backup fails.

> [!WARNING]  
> If notifications are enabled (`enabled: true`),  
> the `service` parameter is **required**.  
> If the service is not specified, the add-on will not start.

---

## Operation Flow

When started, the add-on performs the following steps:

1. Turns on power to the external disk (if power management is enabled)
2. Mounts the backup disk
3. Performs incremental backup using rsync
4. Unmounts the disk
5. Turns off disk power (if enabled)
6. Sends a notification with the execution result

On startup, the add-on initializes the cron scheduler and waits
for the configured execution time.

---

### Test Mode

When test_mode is enabled, the add-on does not perform actual data copying.
Instead, all steps are simulated without modifying any files.

---

## Common Issues

- Backup disk not mounted  
  Check filesystem labels and udev rules.

- Configuration validation failed  
  Verify the add-on settings in the Home Assistant user interface.
