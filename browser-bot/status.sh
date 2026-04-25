#!/bin/bash
# Проверяет статус всех компонентов browser-bot

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
PID_DIR="$PROJECT_DIR/pids"

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

if [ ! -d "$PID_DIR" ]; then
    echo "Нет данных о процессах."
    exit 0
fi

for pid_file in "$PID_DIR"/*.pid; do
    [ -f "$pid_file" ] || continue
    name=$(basename "$pid_file" .pid)
    pid=$(cat "$pid_file")

    if kill -0 "$pid" 2>/dev/null; then
        echo -e "${GREEN}[OK]${NC}   $name (PID $pid)"
    else
        echo -e "${RED}[DEAD]${NC} $name (PID $pid)"
    fi
done
