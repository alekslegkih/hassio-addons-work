#!/bin/bash

# In HAOS addons, configuration is read from /data/options.json
CONFIG_FILE=/data/options.json

# Fixed source directory (always /backup in HAOS addons)
SOURCE_DIR="/backup"

# Parse JSON and extract parameters
DEST_DIR=$(jq -r '.dest_dir // "/media/Backup"' "$CONFIG_FILE")
MAX_COPIES=$(jq -r '.max_copies // 5' "$CONFIG_FILE")
WAIT_TIME=$(jq -r '.wait_time // 300' "$CONFIG_FILE")
SYNC_EXISTING=$(jq -r '.sync_existing_on_start // true' "$CONFIG_FILE")

# Validate required directories
if [ ! -d "$SOURCE_DIR" ]; then
    echo "Error: Source directory $SOURCE_DIR does not exist!"
    echo "This should never happen in HAOS. Check addon configuration."
    exit 1
fi

# Create destination directory if it doesn't exist
mkdir -p "$DEST_DIR"

echo "=== Backup Sync Configuration ==="
echo "Source directory (fixed): $SOURCE_DIR"
echo "Destination directory: $DEST_DIR"
echo "Maximum copies to keep: $MAX_COPIES"
echo "Wait before copying: $WAIT_TIME seconds"
echo "Sync existing backups: $SYNC_EXISTING"
echo "=================================="

# Build arguments for Python script
ARGS="--dest-dir \"$DEST_DIR\" --max-copies $MAX_COPIES --wait-time $WAIT_TIME"

# Add sync existing flag if enabled
if [ "$SYNC_EXISTING" = "true" ]; then
    ARGS="$ARGS --sync-existing-on-start"
fi

# Run Python script
exec python3 /usr/local/bin/backup_sync.py $ARGS