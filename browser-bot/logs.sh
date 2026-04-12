#!/bin/bash
# Просмотр логов browser-bot
#
# Использование:
#   ./logs.sh              — все логи вместе (tail -f)
#   ./logs.sh generator    — только генератор
#   ./logs.sh yandex-bot   — только бот
#   ./logs.sh dispatcher   — только диспатчер
#   ./logs.sh last          — последние 50 строк каждого лога

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$PROJECT_DIR/logs"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

if [ ! -d "$LOG_DIR" ] || [ -z "$(ls "$LOG_DIR"/*.log 2>/dev/null)" ]; then
    echo -e "${YELLOW}Нет логов. Сначала запустите ./start.sh${NC}"
    exit 1
fi

case "${1:-all}" in
    generator|yandex-bot|dispatcher)
        if [ ! -f "$LOG_DIR/$1.log" ]; then
            echo -e "${YELLOW}Лог $1.log не найден.${NC}"
            exit 1
        fi
        echo -e "${GREEN}=== $1 (Ctrl+C для выхода) ===${NC}"
        tail -f "$LOG_DIR/$1.log"
        ;;
    last)
        for log_file in "$LOG_DIR"/*.log; do
            name=$(basename "$log_file" .log)
            echo -e "\n${CYAN}=== $name (последние 50 строк) ===${NC}"
            tail -n 50 "$log_file"
        done
        ;;
    all)
        echo -e "${GREEN}=== Все логи (Ctrl+C для выхода) ===${NC}"
        tail -f "$LOG_DIR"/generator.log "$LOG_DIR"/yandex-bot.log "$LOG_DIR"/dispatcher.log
        ;;
    *)
        echo "Использование: ./logs.sh [generator|yandex-bot|dispatcher|last|all]"
        ;;
esac
