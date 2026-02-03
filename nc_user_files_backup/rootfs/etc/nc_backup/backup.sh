#!/bin/bash
# Strict mode:
# -e  exit on error
# -u  error on undefined variables
# -o pipefail  fail pipelines correctly
set -euo pipefail

# ---------------------------------------------------------------------
# Logging helpers
# Provides colored log_* functions
# ---------------------------------------------------------------------
source /etc/nc_backup/logging.sh

# ---------------------------------------------------------------------
# Runtime lock
# Prevents parallel or overlapping backup runs
# ---------------------------------------------------------------------
LOCKFILE="/config/backup.lock"

# If lock exists:
# - remove it if older than 3 hours (stale run)
# - otherwise exit silently
if [ -e "$LOCKFILE" ]; then
    if [ "$(find "$LOCKFILE" -mmin +180 2>/dev/null)" ]; then
        log_yellow "Stale lock detected, removing"
        rm -f "$LOCKFILE"
    else
        log_yellow "Backup already running, exiting"
        exit 0
    fi
fi

# Create lock and ensure cleanup on exit
touch "$LOCKFILE"
trap 'rm -f "$LOCKFILE"' EXIT

# ---------------------------------------------------------------------
# Load validated configuration
# config.sh:
# - parses options.json
# - validates required parameters
# - exports runtime variables
# ---------------------------------------------------------------------
source /etc/nc_backup/config.sh || {
    log_red "Failed to load configuration library (config.sh)"
    exit 1
}

# ---------------------------------------------------------------------
# Header / environment info
# ---------------------------------------------------------------------
log_blue "-----------------------------------------------------------"
log_blue "Date $(_ts)"
log_blue "Starting backup of Nextcloud user files"
log_blue "-----------------------------------------------------------"

log "System: $(uname -s) $(uname -r)"
log "Architecture: $(uname -m)"
log "Timezone: $TIMEZONE"
log "Backup destination: $MOUNT_POINT_BACKUP"
log "Nextcloud data source: $NEXTCLOUD_DATA_PATH"
log "Backup disk power management enabled: $POWER_ENABLED"
log "Backup disk power switch entity: $DISC_SWITCH_SELECT"
log "Notifications enabled: $NOTIFICATIONS_ENABLED"
log "Home Assistant notify service: $NOTIFICATION_SERVICE_SELECT"
log "-----------------------------------------------------------"

# ---------------------------------------------------------------------
# Home Assistant Supervisor API helper
#
# Used for:
# - switch control
# - notifications
# - unmount requests
#
# Output is intentionally suppressed (>/dev/null)
# to avoid JSON arrays ([]), which Supervisor returns
# and which pollute logs.
# ---------------------------------------------------------------------
ha_api_call() {
    local endpoint="$1"
    local payload="${2:-}"

    curl -s \
        -H "Authorization: Bearer $SUPERVISOR_TOKEN" \
        -H "Content-Type: application/json" \
        -X POST \
        -d "$payload" \
        "http://supervisor/core/api/$endpoint" \
        >/dev/null
}

# ---------------------------------------------------------------------
# Unified final handler
#
# Responsibilities:
# - choose correct final message
# - send notification (if enabled)
# - log final status
# - exit with correct code
#
# IMPORTANT:
# - final_msg may be empty
# - ERROR_MESSAGE is used as fallback
# ---------------------------------------------------------------------
handle_final_result() {
    local success="$1"
    local final_msg="$2"

    # Fallback to configured error message if none provided
    if [ "$success" != true ] && [ -z "$final_msg" ]; then
        final_msg="$ERROR_MESSAGE"
    fi

    # Send notification if enabled
    if [ "$NOTIFICATIONS_ENABLED" = "true" ]; then
        PAYLOAD=$(jq -n --arg msg "$final_msg" '{"message":$msg}')
        ha_api_call "services/notify/$NOTIFICATIONS_SERVICE" "$PAYLOAD" \
            && log_green "Notification sent via $NOTIFICATION_SERVICE_SELECT" \
            || log_red "Failed to send notification via $NOTIFICATION_SERVICE_SELECT"
    fi

    # Final log output
    [ "$success" = true ] && log_green "$final_msg" || log_red "$final_msg"

    # Add-on stays alive (cron scheduler)
    log_green "-----------------------------------------------------------"
    log_green "Backup scheduler started, waiting for scheduled time"

    exit $([ "$success" = "true" ] && echo 0 || echo 1)
}

# ---------------------------------------------------------------------
# Sanity check: source disk must be mounted
# Fail fast before any power or rsync actions
# ---------------------------------------------------------------------
log_green "Starting backup process"

if ! mountpoint -q "$NEXTCLOUD_DATA_PATH"; then
    handle_final_result false "Nextcloud data disk is not mounted"
fi

# ---------------------------------------------------------------------
# Power ON backup disk (optional)
#
# Flow:
# - turn switch ON
# - poll entity state
# - wait for disk initialization
# ---------------------------------------------------------------------
if [ "$POWER_ENABLED" = "true" ]; then
    log "Turning ON backup disk power"
    ha_api_call "services/switch/turn_on" \
        "$(jq -n --arg e "$DISC_SWITCH_SELECT" '{entity_id:$e}')"

    STATE="unknown"
    for i in {1..10}; do
        STATE=$(curl -s \
            -H "Authorization: Bearer $SUPERVISOR_TOKEN" \
            http://supervisor/core/api/states/$DISC_SWITCH_SELECT \
            | jq -r '.state // "unknown"' || echo "unknown")

        if [ "$STATE" = "on" ]; then
            log_green "Disk power is ON"
            break
        fi

        log "Waiting for disk power ($i/30), state=$STATE"
        sleep 2
    done

    [ "$STATE" != "on" ] && handle_final_result false "Backup disk power management failed"

    log "Waiting 30 seconds for disk initialization"
    sleep 30
fi

# ---------------------------------------------------------------------
# Backup destination validation
# ---------------------------------------------------------------------
[ ! -d "$MOUNT_POINT_BACKUP" ] && handle_final_result false "Backup destination disk is not mounted"

# Check write access
if touch "$MOUNT_POINT_BACKUP/.test" 2>/dev/null; then
    rm -f "$MOUNT_POINT_BACKUP/.test"
    log "Backup disk writable"
else
    handle_final_result false "Backup destination disk is not writable"
fi

# Ensure Nextcloud data directory exists
[ ! -d "$NEXTCLOUD_DATA_PATH" ] && handle_final_result false "No Nextcloud users with files found"

# ---------------------------------------------------------------------
# Detect Nextcloud users
# A valid user directory must contain 'files/'
# ---------------------------------------------------------------------
log "Searching Nextcloud users..."

USERS=$(
    find "$NEXTCLOUD_DATA_PATH" \
        -mindepth 1 -maxdepth 1 \
        -type d \
        -exec bash -c '
            for d; do
                [ -d "$d/files" ] && basename "$d"
            done
        ' bash {} +
)

if [ -z "$USERS" ]; then
    handle_final_result false "No Nextcloud users with files directory found"
fi

log_yellow "Users found: $(echo "$USERS" | paste -sd ', ')"

# ---------------------------------------------------------------------
# Backup loop (per user)
# ---------------------------------------------------------------------
log_green "Starting rsync file copy process"

SUCCESS=true

for user in $USERS; do
    SRC="$NEXTCLOUD_DATA_PATH/$user/files/"
    DST="$MOUNT_POINT_BACKUP/$user/"

    [ ! -d "$SRC" ] && log_yellow "User $user has no files, skipping" && continue

    mkdir -p "$DST"
    log_blue "Copying files for user: $user"

    if [ "$TEST_MODE" = "true" ]; then
        sleep 5
        log_purple "TEST MODE: simulated backup for $user"
    else
        if rsync $RSYNC_OPTIONS "$SRC" "$DST/"; then
            FILES=$(find "$DST" -type f | wc -l)
            log_green "User $user files backed up ($FILES files)"
        else
            log_red "Failed to back up files for user $user"
            SUCCESS=false
        fi
    fi
done

# ---------------------------------------------------------------------
# Unmount disk and power OFF (optional)
# ---------------------------------------------------------------------
if [ "$POWER_ENABLED" = "true" ]; then
    log "Unmounting backup disk"
    curl -s -X POST \
        -H "Authorization: Bearer $SUPERVISOR_TOKEN" \
        -H "Content-Type: application/json" \
        -d "{\"device\":\"$MOUNT_POINT_BACKUP\"}" \
        http://supervisor/host/umount >/dev/null || log_yellow "Unmount failed"

    log "Turning OFF backup disk power"
    ha_api_call "services/switch/turn_off" \
        "$(jq -n --arg e "$DISC_SWITCH_SELECT" '{entity_id:$e}')"
fi

# ---------------------------------------------------------------------
# Final result
# ---------------------------------------------------------------------
[ "$SUCCESS" = true ] \
    && handle_final_result true "$SUCCESS_MESSAGE" \
    || handle_final_result false ""
