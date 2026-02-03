#!/bin/bash
set -euo pipefail

# Load logging helpers

# Provides colored logging functions and section formatting
source /etc/nc_backup/logging.sh

log_blue "====================================================="
log_blue "Starting Nextcloud User Files Backup Add-on"
log_blue "====================================================="

# Load backup configuration file
# This file is generated from settings.yaml and contains
# shell variables used by the add-on runtime
source /etc/nc_backup/config.sh || {
    log_red "Failed to load configuration library (config.sh)"
    exit 1
}

# Validate configuration
# load_config performs:
# - parsing of settings.yaml
# - validation of required parameters
# - environment preparation
#
# Exit codes:
#   0 - configuration is valid
#   2 - first run detected (settings.yaml created)
#   1 - configuration error

log "Loading and validating backup configuration"

load_config
CONFIG_EXIT_CODE=$?

case "$CONFIG_EXIT_CODE" in
    0)
        log_green "Backup configuration loaded and validated successfully"
        ;;
    2)
        log_yellow "-----------------------------------------------------------"
        log_yellow " First run detected"
        log_yellow " Default settings.yaml has been created"
        log_yellow " Please edit the file and restart the add-on"
        log_yellow "-----------------------------------------------------------"
        exit 0
        ;;
    *)
        log_red "-----------------------------------------------------------"
        log_red " Configuration validation failed"
        log_red " Add-on startup has been aborted. See logs above for details"
        log_red "-----------------------------------------------------------"
        exit 1
        ;;
esac

# Install cron job
# The cron job triggers the backup script according to
# the schedule defined in settings.yaml
CRON_FILE="/etc/crontabs/root"

log "Installing cron job"
log_blue "Schedule: $BACKUP_SCHEDULE"
log "Cron file: $CRON_FILE"

cat > "$CRON_FILE" <<EOF
$BACKUP_SCHEDULE /backup.sh
EOF

chmod 600 "$CRON_FILE"

log_green "Cron job installed successfully"

# Start cron daemon
# Run cron in foreground so the container remains alive
log_green "Starting cron daemon"

exec crond -f -l 8