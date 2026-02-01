#!/bin/bash

#Red color for errors
RED='\033[0;31m'
NC='\033[0m'

echo "=== Starting Nextcloud User Files Backup Addon ==="

# Load configuration
if [ -f /etc/nc_backup/config.sh ]; then
    source /etc/nc_backup/config.sh
else
    echo -e "${RED}Config file not found: /etc/nc_backup/config.sh${NC}"
    exit 1
fi

load_config
CONFIG_EXIT_CODE=$?

if [ $CONFIG_EXIT_CODE -eq 2 ]; then
    exit 0
elif [ $CONFIG_EXIT_CODE -ne 0 ]; then
    echo -e "${RED}Failed to load configuration${NC}"
    exit 1
fi

# Start main backup script
exec /backup.sh