#!/bin/bash
set -e

# -----------------------------------------------------------
# Colors
# -----------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}-----------------------------------------------------------${NC}"
echo -e "${BLUE} Starting Nextcloud User Files Backup Add-on${NC}"
echo -e "${BLUE}-----------------------------------------------------------${NC}"

# -----------------------------------------------------------
# Load logging helpers
# -----------------------------------------------------------
source /etc/nc_backup/logging.sh

# -----------------------------------------------------------
# Load backup configuration
# -----------------------------------------------------------
if [ -f /etc/nc_backup/config.sh ]; then
    source /etc/nc_backup/config.sh
else
    echo -e "${RED}Config file not found: /etc/nc_backup/config.sh${NC}"
    exit 1
fi

load_config
CONFIG_EXIT_CODE=$?

case "$CONFIG_EXIT_CODE" in
    0)
        echo -e "${GREEN}Backup configuration OK${NC}"
        ;;
    2)
        echo -e "${YELLOW}-----------------------------------------------------------${NC}"
        echo -e "${YELLOW} First run detected${NC}"
        echo -e "${YELLOW} settings.yaml has been created${NC}"
        echo -e "${YELLOW} Please edit it and restart the addon${NC}"
        echo -e "${YELLOW}-----------------------------------------------------------${NC}"
        exit 0
        ;;
    *)
        echo -e "${RED}-----------------------------------------------------------${NC}"
        echo -e "${RED} Configuration error detected${NC}"
        echo -e "${RED} Add-on stopped. See logs above for details${NC}"
        echo -e "${RED}-----------------------------------------------------------${NC}"
        exit 1
        ;;
esac

# -----------------------------------------------------------
# In run.sh
# -----------------------------------------------------------
HA_TOKEN=$(jq -r '.ha_token // ""' /data/options.json)

#if [ -z "$HA_TOKEN" ]; then
#    echo -e "${RED}-----------------------------------------------------------${NC}"
#    echo -e "${RED} Home Assistant token is not set${NC}"
#    echo -e "${RED} Please configure ha_token in addon options${NC}"
#    echo -e "${RED} Add-on stopped${NC}"
#   echo -e "${RED}-----------------------------------------------------------${NC}"
#   exit 1
#fi

# -----------------------------------------------------------
# Load cron schedule from addon options
# -----------------------------------------------------------
CRON=$(jq -r '.cron // empty' /data/options.json)

if [ -z "$CRON" ]; then
    echo -e "${RED}Cron schedule is not set in addon options${NC}"
    exit 1
fi

# -----------------------------------------------------------
# Validate cron format (must be 5 fields for busybox crond)
# -----------------------------------------------------------
CRON_FIELDS=$(echo "$CRON" | awk '{print NF}')
if [ "$CRON_FIELDS" -ne 5 ]; then
    echo -e "${RED}Invalid cron format: '$CRON'${NC}"
    echo -e "${YELLOW}Expected format: minute hour day month weekday${NC}"
    echo -e "${YELLOW}Example: 0 3 * * *${NC}"
    exit 1
fi

# -----------------------------------------------------------
# Install cron job
# -----------------------------------------------------------
CRON_FILE="/etc/crontabs/root"
LOG_FILE="/config/backup.log"

touch "$LOG_FILE"

echo -e "${BLUE}Installing cron job:${NC} ${YELLOW}$CRON${NC}"

cat > "$CRON_FILE" <<EOF
$CRON /backup.sh >> $LOG_FILE 2>&1
EOF

chmod 600 "$CRON_FILE"

# -----------------------------------------------------------
# Start cron daemon
# -----------------------------------------------------------
echo -e "${GREEN}Starting cron daemon...${NC}"
exec crond -f -l 8
