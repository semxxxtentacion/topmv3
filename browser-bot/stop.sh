#!/bin/bash
# Останавливает все компоненты browser-bot

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
PID_DIR="$PROJECT_DIR/pids"

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

if [ ! -d "$PID_DIR" ]; then
    echo -e "${RED}Нет запущенных процессов.${NC}"
    exit 0
fi

for pid_file in "$PID_DIR"/*.pid; do
    [ -f "$pid_file" ] || continue
    name=$(basename "$pid_file" .pid)
    pid=$(cat "$pid_file")

    if kill -0 "$pid" 2>/dev/null; then
        kill "$pid"
        echo -e "${GREEN}[stop]${NC} $name (PID $pid) остановлен."
    else
        echo -e "${RED}[stop]${NC} $name (PID $pid) уже не работает."
    fi
    rm -f "$pid_file"
done

echo "Все процессы остановлены."
