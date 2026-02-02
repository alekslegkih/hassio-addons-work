#!/bin/bash
set -euo pipefail


# -----------------------------------------------------------
# Load logging helpers
# -----------------------------------------------------------
# Provides colored logging functions and section formatting
source /etc/nc_backup/logging.sh
log_section  " Starting Nextcloud User Files Backup Add-on"

# -----------------------------------------------------------
# Load backup configuration file
# -----------------------------------------------------------
# This file is generated from settings.yaml and contains
# shell variables used by the add-on runtime
CONFIG_FILE="/etc/nc_backup/config.sh"

if [ -f "$CONFIG_FILE" ]; then
   # log "Loading configuration: $CONFIG_FILE"
    source "$CONFIG_FILE"
else
    log_red "Config file not found: $CONFIG_FILE"
    exit 1
fi

# -----------------------------------------------------------
# Validate configuration
# -----------------------------------------------------------
# load_config performs:
# - parsing of settings.yaml
# - validation of required parameters
# - environment preparation
#
# Exit codes:
#   0 - configuration is valid
#   2 - first run detected (settings.yaml created)
#   1 - configuration error
load_config
CONFIG_EXIT_CODE=$?

case "$CONFIG_EXIT_CODE" in
    0)
        log_green "Backup configuration OK"
        ;;
    2)
        log_yellow "-----------------------------------------------------------"
        log_yellow " First run detected"
        log_yellow " settings.yaml has been created"
        log_yellow " Please edit it and restart the addon"
        log_yellow "-----------------------------------------------------------"
        exit 0
        ;;
    *)
        log_red "-----------------------------------------------------------"
        log_red " Configuration error detected"
        log_red " Add-on stopped. See logs above for details"
        log_red "-----------------------------------------------------------"
        exit 1
        ;;
esac

# -----------------------------------------------------------
# Config load
# -----------------------------------------------------------
if [[ "${CONFIG_LOADED:-false}" != "true" ]]; then
    log_red "Configuration not loaded"
    exit 1
fi

# -----------------------------------------------------------
# Install cron job
# -----------------------------------------------------------
# The cron job triggers the backup script according to
# the schedule defined in settings.yaml
CRON_FILE="/etc/crontabs/root"

log_blue "Installing cron job $BACKUP_SCHEDULE"
log "Cron file: $CRON_FILE"

cat > "$CRON_FILE" <<EOF
$BACKUP_SCHEDULE /backup.sh
EOF

chmod 600 "$CRON_FILE"

log_green "Cron job installed successfully"

# -----------------------------------------------------------
# Start cron daemon
# -----------------------------------------------------------
# Run cron in foreground so the container remains alive
log_green "Starting cron daemon"
exec crond -f -l 8