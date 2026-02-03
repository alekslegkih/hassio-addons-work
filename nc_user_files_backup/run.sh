#!/bin/bash
set -euo pipefail

# Load logging helpers
# Provides colored logging functions and section formatting
source /etc/nc_backup/logging.sh

log_blue "====================================================="
log_blue "Starting Nextcloud User Files Backup Add-on"
log_blue "====================================================="

# Load configuration library
source /etc/nc_backup/config.sh || {
    log_red "Failed to load configuration library (config.sh)"
    exit 1
}

log "Loading and validating backup configuration"

# Load and validate configuration
load_config
CONFIG_EXIT_CODE=$?

case "$CONFIG_EXIT_CODE" in
    0)
        log_green "The configuration has been successfully verified and loaded."
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
CRON_FILE="/etc/crontabs/root"

log "-----------------------------------------------------------"
log "Installing cron job"
log_blue "Schedule: $BACKUP_SCHEDULE"

cat > "$CRON_FILE" <<EOF
$BACKUP_SCHEDULE /etc/nc_backup/backup.sh
EOF

chmod 600 "$CRON_FILE"

log_green "Cron job installed successfully"
log_green "-----------------------------------------------------------"
log_green "Backup scheduler started, waiting for scheduled time"

# Run cron daemon in foreground
exec crond -f -l 8
