#!/bin/bash
#
# Logging helper for Nextcloud User Files Backup add-on
#
# Responsibilities:
# - Provide unified logging functions for all add-on scripts
# - Output colored logs to stdout (visible in Home Assistant UI)
# - Write plain (non-colored) logs to a persistent file
#
# Design notes:
# - Timestamp support is intentionally disabled
#   (Home Assistant already timestamps logs)
# - Logging is synchronous and minimal by design
#

# ------------------------------------------------------------------
# Persistent log file
# ------------------------------------------------------------------
# This file is stored in /config so it survives container restarts.
#
LOG_FILE="/config/backup.log"

# Ensure log directory and file exist
mkdir -p "$(dirname "$LOG_FILE")"
touch "$LOG_FILE"

# ------------------------------------------------------------------
# ANSI color definitions for console output
# ------------------------------------------------------------------
# Used only for stdout (HA log viewer).
# Log file always receives plain text.
#
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
PURPLE='\033[0;35m'
NC='\033[0m'   # No Color (reset)

# ------------------------------------------------------------------
# Timestamp helper (disabled)
# ------------------------------------------------------------------
# Home Assistant already prepends timestamps to logs,
# so adding our own would create visual noise and duplication.
#
_ts() {
    date '+%Y-%m-%d %H:%M:%S'
}

# ------------------------------------------------------------------
# Internal logging primitive
# ------------------------------------------------------------------
# Arguments:
#   $1 - colored message (printed to stdout)
#   $2 - plain message (written to log file)
#
# Behavior:
# - Writes colored output to stdout
# - Writes uncolored output to LOG_FILE
# - If plain message is empty, nothing is logged
#
_log_raw() {
    local colored="$1"
    local plain="$2"

    [ -z "$plain" ] && return 0

    echo -e "$colored"
    echo "$plain" >> "$LOG_FILE"
}

# ------------------------------------------------------------------
# Public logging helpers
# ------------------------------------------------------------------
# These functions are used throughout the add-on.
# All of them:
# - log to stdout with color
# - log to file without color
#

# Generic log (no color)
log() {
    _log_raw "$1" "$1"
}

# Success / positive state
log_green() {
    _log_raw "${GREEN}$1${NC}" "$1"
}

# Warnings / non-fatal issues
log_yellow() {
    _log_raw "${YELLOW}$1${NC}" "$1"
}

# Errors / fatal conditions
log_red() {
    _log_raw "${RED}$1${NC}" "$1"
}

# Section headers / structural output
log_blue() {
    _log_raw "${BLUE}$1${NC}" "$1"
}

# Informational / secondary output
log_cyan() {
    _log_raw "${CYAN}$1${NC}" "$1"
}

# Test mode / special states
log_purple() {
    _log_raw "${PURPLE}$1${NC}" "$1"
}
