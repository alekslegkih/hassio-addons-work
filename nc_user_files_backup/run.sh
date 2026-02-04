#!/bin/bash
set -euo pipefail
#
# Entry point for the add-on container.
#
# Responsibilities:
# - Load and validate add-on configuration (options.json)
# - Install cron job according to schedule
# - Start cron daemon in foreground to keep container alive
#

# Load logging helpers
# Provides colored logging functions and timestamp helpers
source /etc/nc_backup/logging.sh

# Header
log_blue "====================================================="
log_blue "Starting Nextcloud User Files Backup Add-on"
log_blue "====================================================="

# Load configuration library
# config.sh contains:
# - load_config() function
# - validation logic
# - export of runtime environment variables
source /etc/nc_backup/config.sh || {
    log_red "Failed to load configuration library (config.sh)"
    exit 1
}

# Load and validate configuration
# Expected return codes:
#   0 - configuration valid
#   1 - configuration error
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

# ------------------------------------------------------------------
# Cron configuration
# ------------------------------------------------------------------
# The add-on uses system cron to schedule backup execution.
# Cron runs /etc/nc_backup/backup.sh at the configured schedule.
#

CRON_FILE="/etc/crontabs/root"

log "-----------------------------------------------------------"
log "Installing cron job"
log_blue "Schedule: $BACKUP_SCHEDULE"

# Overwrite root cron file with a single job
# This is intentional: the container is dedicated to this add-on
cat > "$CRON_FILE" <<EOF
$BACKUP_SCHEDULE /etc/nc_backup/backup.sh
EOF

# Secure cron file permissions
chmod 600 "$CRON_FILE"

log_green "Cron job installed successfully"

# ------------------------------------------------------------------
# Start cron daemon
# ------------------------------------------------------------------
# Cron must run in foreground so the container does not exit.
#

log_green "-----------------------------------------------------------"
log_green "Backup scheduler started, waiting for scheduled time"

# Run cron daemon in foreground with verbose logging
exec crond -f -l 8
