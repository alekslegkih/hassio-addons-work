#!/bin/bash

# Если есть аргументы, запускаем CLI

if [ $# -gt 0 ]; then
    exec python3 /usr/local/bin/backup_sync/api/cli.py "$@"
fi

# Иначе запускаем основной режим аддона
exec python3 /usr/local/bin/backup_sync/main.py