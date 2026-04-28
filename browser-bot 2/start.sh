#!/bin/bash
# ============================================================
# browser-bot startup script
# Запускает 3 компонента как фоновые процессы:
#   1. Generator API + auto-warmup  (порт 8090)
#   2. Yandex-bot API server        (порт 8082)
#   3. Dispatcher                   (polling loop)
#
# БД уже работает в Docker — скрипт только ждёт её готовность.
# Логи пишутся в logs/
# ============================================================

set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$PROJECT_DIR/.venv"
PYTHON="$VENV/bin/python"
LOG_DIR="$PROJECT_DIR/logs"
PID_DIR="$PROJECT_DIR/pids"

# ---------- Цвета ----------
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[start]${NC} $1"; }
warn() { echo -e "${YELLOW}[warn]${NC} $1"; }
err()  { echo -e "${RED}[error]${NC} $1"; }

# ---------- Подготовка директорий ----------
mkdir -p "$LOG_DIR" "$PID_DIR"

# ---------- Виртуальное окружение ----------
if [ ! -f "$PYTHON" ]; then
    log "Создаю виртуальное окружение..."
    python3 -m venv "$VENV"
    "$VENV/bin/pip" install --upgrade pip -q
    "$VENV/bin/pip" install -r "$PROJECT_DIR/requirements.txt" -q
    "$VENV/bin/pip" install -r "$PROJECT_DIR/yandex-bot/requirements.txt" -q
    log "Устанавливаю Playwright Chromium..."
    "$PYTHON" -m playwright install chromium --with-deps
    log "Окружение готово."
fi

# ---------- Чистые логи при старте ----------
> "$LOG_DIR/generator.log"
> "$LOG_DIR/yandex-bot.log"
> "$LOG_DIR/dispatcher.log"

# ---------- .env для генератора (DATABASE_URL) ----------
export DATABASE_URL="postgresql+asyncpg://admin:s5YX15RUJv6B3vsjr4@5.129.206.79:5432/acc_generator"

# ---------- PostgreSQL ----------
log "PostgreSQL: 5.129.206.79:5432 (работает в Docker)"

# ---------- Функция запуска процесса ----------
start_process() {
    local name="$1"
    local pid_file="$PID_DIR/$name.pid"
    local log_file="$LOG_DIR/$name.log"
    shift

    # Убить старый процесс если есть
    if [ -f "$pid_file" ]; then
        local old_pid
        old_pid=$(cat "$pid_file")
        if kill -0 "$old_pid" 2>/dev/null; then
            warn "Останавливаю старый $name (PID $old_pid)..."
            kill "$old_pid" 2>/dev/null || true
            sleep 1
        fi
        rm -f "$pid_file"
    fi

    nohup "$@" >> "$log_file" 2>&1 &
    local pid=$!
    disown "$pid"
    echo "$pid" > "$pid_file"
    log "$name запущен (PID $pid), лог: $log_file"
}

# ---------- 1. Generator API + warmup (порт 8090) ----------
start_process "generator" \
    "$PYTHON" -m uvicorn generator.server:app --host 0.0.0.0 --port 8090

# ---------- 2. Yandex-bot API server (порт 8082) ----------
cd "$PROJECT_DIR/yandex-bot"
start_process "yandex-bot" \
    "$PYTHON" -m uvicorn api:app --host 0.0.0.0 --port 8082
cd "$PROJECT_DIR"

# ---------- 3. Ждём готовность yandex-bot API ----------
log "Ожидание yandex-bot API на порту 8082..."
for i in $(seq 1 30); do
    if ss -tln | grep -q ':8082 '; then
        log "yandex-bot API готов."
        break
    fi
    if [ "$i" -eq 30 ]; then
        err "yandex-bot не поднялся за 30 сек. Диспатчер не запущен."
        exit 1
    fi
    sleep 1
done

# ---------- 4. Dispatcher ----------
cd "$PROJECT_DIR/yandex-bot"
start_process "dispatcher" \
    "$PYTHON" dispatcher.py
cd "$PROJECT_DIR"

# ---------- Итог ----------
echo ""
log "=== Все компоненты запущены ==="
echo "  Generator API:   http://0.0.0.0:8090  (PID $(cat $PID_DIR/generator.pid))"
echo "  Yandex-bot API:  http://0.0.0.0:8082  (PID $(cat $PID_DIR/yandex-bot.pid))"
echo "  Dispatcher:      polling loop          (PID $(cat $PID_DIR/dispatcher.pid))"
echo ""
echo "  Логи:  $LOG_DIR/"
echo "  Стоп:  $PROJECT_DIR/stop.sh"
