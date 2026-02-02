#!/bin/bash

# Logging helper for Nextcloud User Files Backup add-on
#
# - Outputs colored logs to stdout (Home Assistant logs)
# - Writes plain text logs to a persistent log file

# Path to persistent log file
LOG_FILE="/config/backup.log"

# Ensure log directory and file exist
mkdir -p "$(dirname "$LOG_FILE")"
touch "$LOG_FILE"

# ANSI color definitions for console output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
PURPLE='\033[0;35m'
NC='\033[0m'

# Timestamp helper
# Returns current timestamp in a consistent log format
_ts() {
    date '+%Y-%m-%d %H:%M:%S'
}

# Core logging function
# Arguments:
#   $1 - colored message (for stdout)
#   $2 - plain message (for log file)
# Behavior:
# - Writes colored output to stdout
# - Writes uncolored output to LOG_FILE
_log_raw() {
    local colored="$1"
    local plain="$2"

    [ -z "$plain" ] && return 0

    echo -e "$(_ts) $colored"
    echo "$(_ts) $plain" >> "$LOG_FILE"
}

# Public logging helpers
# Each function logs to stdout (with color) and to file (plain)
log() {
    _log_raw "$1" "$1"
}

log_green() {
    _log_raw "${GREEN}$1${NC}" "$1"
}

log_yellow() {
    _log_raw "${YELLOW}$1${NC}" "$1"
}

log_red() {
    _log_raw "${RED}$1${NC}" "$1"
}

log_blue() {
    _log_raw "${BLUE}$1${NC}" "$1"
}

log_cyan() {
    _log_raw "${CYAN}$1${NC}" "$1"
}

log_purple() {
    _log_raw "${PURPLE}$1${NC}" "$1"
}

