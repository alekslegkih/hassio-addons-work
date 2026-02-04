#!/bin/bash

# Загружаем настройки из конфигурации
SOURCE_DIR=${SOURCE_DIR:-"/backup"}
DEST_DIR=${DEST_DIR:-"/media/Backup"}
MAX_COPIES=${MAX_COPIES:-5}
WAIT_TIME=${WAIT_TIME:-300}
CHECK_EXISTING=${CHECK_EXISTING:-true}

# Экспортируем переменные для Python скрипта
export SOURCE_DIR
export DEST_DIR
export MAX_COPIES
export WAIT_TIME
export CHECK_EXISTING

# Запускаем Python скрипт
exec python3 /usr/local/bin/backup_sync.py \
    --source-dir "$SOURCE_DIR" \
    --dest-dir "$DEST_DIR" \
    --max-copies "$MAX_COPIES" \
    --wait-time "$WAIT_TIME" \
    $( [ "$CHECK_EXISTING" = "true" ] && echo "--check-existing" )