#!/bin/bash
set -euo pipefail

# -----------------------------------------------------------
# Load logging helpers
# -----------------------------------------------------------
source /etc/nc_backup/logging.sh

log_blue "-----------------------------------------------------------"
log_section  " Starting Nextcloud User Files Backup Add-on"
log_blue "-----------------------------------------------------------"

# -----------------------------------------------------------
# Load backup configuration
# -----------------------------------------------------------
CONFIG_FILE="/etc/nc_backup/config.sh"

if [ -f "$CONFIG_FILE" ]; then
    log "Loading configuration: $CONFIG_FILE"
    source "$CONFIG_FILE"
else
    log_red "Config file not found: $CONFIG_FILE"
    exit 1
fi

# -----------------------------------------------------------
# Load and validate config
# -----------------------------------------------------------
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
# Load cron schedule from addon options
# -----------------------------------------------------------
CRON=$(jq -r '.cron // empty' /data/options.json)

if [ -z "$CRON" ]; then
    log_red "Cron schedule is not set in addon options"
    exit 1
fi

log "Cron schedule from options: '$CRON'"

# -----------------------------------------------------------
# Validate cron format (busybox requires 5 fields)
# -----------------------------------------------------------
CRON_FIELDS=$(echo "$CRON" | awk '{print NF}')
if [ "$CRON_FIELDS" -ne 5 ]; then
    log_red "Invalid cron format: '$CRON'"
    log_yellow "Expected format: minute hour day month weekday"
    log_yellow "Example: 0 3 * * *"
    exit 1
fi

log_green "Cron format validation passed"

# -----------------------------------------------------------
# Install cron job
# -----------------------------------------------------------
CRON_FILE="/etc/crontabs/root"

log_blue "Installing cron job"
log "Cron file: $CRON_FILE"

cat > "$CRON_FILE" <<EOF
$CRON /backup.sh
EOF

chmod 600 "$CRON_FILE"

log_green "Starting cron daemon..."
exec crond -f -l 8

log_green "Cron job installed successfully"

# -----------------------------------------------------------
# Start cron daemon
# -----------------------------------------------------------
log_green "Starting cron daemon (foreground mode)"
exec crond -f -l 8
