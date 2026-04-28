# Деплой acc-generator

## Требования к серверу

| Параметр | Минимум | Рекомендация |
|----------|---------|--------------|
| CPU | 2 vCPU | 4 vCPU |
| RAM | 4 GB | 8 GB |
| Диск | 20 GB SSD | 40 GB SSD |
| ОС | Ubuntu 22.04+ / Debian 12 | Ubuntu 24.04 |

Каждый Chromium ~300-500 MB RAM. При 3 воркерах = ~1.5 GB на браузеры + PostgreSQL + система.

---

## 1. Подготовка сервера

```bash
# Обновить систему
sudo apt update && sudo apt upgrade -y

# Установить Docker + Docker Compose
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# Перелогиниться чтобы группа подхватилась
```

## 2. Загрузить проект на сервер

```bash
# Вариант 1: git clone (если есть репо)
git clone <repo-url> /opt/acc-generator
cd /opt/acc-generator

# Вариант 2: scp с локальной машины
scp -r ./acc-generator user@server:/opt/acc-generator
```

## 3. Настроить .env

```bash
cd /opt/acc-generator
cp .env .env.local  # бэкап

# Обязательно сменить пароль БД
nano .env
```

Ключевые параметры в `.env`:
```
DB_PASSWORD=сюда_сложный_пароль
API_PORT=8000
WARMUP_INTERVAL_HOURS=8
WARMUP_BATCH_SIZE=20
WARMUP_WORKERS=3
PROXY_FILE=proxies.txt
```

## 4. Положить прокси

Файл `proxies.txt` уже должен быть в корне проекта.
Формат: `ip:port:login:password:refresh_link` — по одному на строку.

## 5. Запуск

```bash
# Собрать и запустить
docker compose up -d --build

# Проверить что всё поднялось
docker compose ps
docker compose logs -f app
```

## 6. Проверка

```bash
# Статистика
curl http://localhost:8000/stats

# Сгенерировать 10 профилей с фармом
curl -X POST http://localhost:8000/profiles/generate \
  -H "Content-Type: application/json" \
  -d '{"count": 10, "farm": true, "workers": 3}'

# Посмотреть профили
curl http://localhost:8000/profiles?limit=10

# Ротировать IP на всех прокси
curl -X POST http://localhost:8000/proxies/refresh

# Запустить ручной прогрев
curl -X POST http://localhost:8000/warmup/run \
  -H "Content-Type: application/json" \
  -d '{"batch_size": 20, "workers": 3}'
```

## 7. Полезные команды

```bash
# Логи в реальном времени
docker compose logs -f app

# Перезапуск
docker compose restart app

# Обновить код (после git pull)
docker compose up -d --build

# Остановить всё
docker compose down

# Остановить + удалить данные БД
docker compose down -v
```

## 8. Автозапуск при ребуте

Docker compose с `restart: unless-stopped` уже настроен — контейнеры поднимутся автоматически после перезагрузки сервера (если Docker-демон включён):

```bash
sudo systemctl enable docker
```

---

## Что работает автоматически

- **Прогрев** — каждые 8 часов (настраивается через `WARMUP_INTERVAL_HOURS`)
- **Прокси** — round-robin по 10 прокси из `proxies.txt`
- **Dead-детект** — 3 капчи подряд = профиль помечается мёртвым
- **PostgreSQL** — данные сохраняются в docker volume `pgdata`
