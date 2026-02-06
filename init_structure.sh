#!/usr/bin/env bash

set -e

BASE_DIR="backup_sync"

echo "Creating project structure in ./${BASE_DIR}"

# Directories
mkdir -p ${BASE_DIR}/{core,storage,sync,notifications,api}

# Core
touch ${BASE_DIR}/core/{config.sh,logger.sh,state.sh}

# Storage
touch ${BASE_DIR}/storage/{detect.sh,mount.sh,cleanup.sh}

# Sync
touch ${BASE_DIR}/sync/{scanner.py,watcher.py,copier.sh}

# Notifications
touch ${BASE_DIR}/notifications/ha_notify.py

# API
touch ${BASE_DIR}/api/cli.py

# Root files
touch \
  ${BASE_DIR}/run.sh \
  ${BASE_DIR}/requirements.txt \
  ${BASE_DIR}/Dockerfile \
  ${BASE_DIR}/config.yaml

# Make shell scripts executable
chmod +x \
  ${BASE_DIR}/run.sh \
  ${BASE_DIR}/core/*.sh \
  ${BASE_DIR}/storage/*.sh \
  ${BASE_DIR}/sync/*.sh

echo "Done ✅"
echo
echo "Created structure:"
find ${BASE_DIR} -type f | sort
