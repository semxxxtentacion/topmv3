# Yandex PF Bot

Автоматизированный браузерный бот для поведенческих факторов (ПФ) в Яндексе.

Работает через Playwright (headless Chromium) с антидетект-защитой, уникальными fingerprint-профилями из БД и HTTP-прокси через 3proxy.

---

## Архитектура

```
Telegram бот (одобрение заявки)
      │
      ▼  POST /api/task
┌─────────────────────────────────┐
│         yandex-bot API          │
│         (FastAPI :8082)         │
└──────────────┬──────────────────┘
               │ создаёт N воркеров
    ┌──────────┼──────────┐
    ▼          ▼          ▼
 Worker 1   Worker 2   Worker N
 (Chromium)  (Chromium)  (Chromium)
    │          │          │
    ▼          ▼          ▼
 3proxy (185.118.66.80)
 порт 30100 → IP #1
 порт 30101 → IP #2
 ...
 порт 30134 → IP #35
```

### Жизненный цикл одного воркера

1. Запуск Chromium с уникальным fingerprint + уникальным прокси-IP
2. **Прогрев** — посещение 2-5 случайных сайтов без Яндекс.Метрики (15-45 сек на каждый)
3. **PF-действие** — Яндекс: поиск по ключевому слову → нахождение целевого сайта в выдаче → клик → просмотр 2-5 страниц (30-120 сек)
4. Закрытие браузера (сессия уничтожена)

---

## Быстрый старт

### 1. Настройка

```bash
cd yandex-bot
cp .env.example .env
```

Заполни `.env`:

```env
# Пароль от БД с профилями (mother DB)
PROFILES_DB_PASSWORD=your_password_here

# Количество параллельных браузеров
# Каждый ~300-500MB RAM. Формула: RAM (ГБ) × 2
MAX_WORKERS=5
```

### 2. Запуск через Docker Compose (рекомендуется)

Из корня проекта `top-bot/`:

```bash
docker compose up -d yandex-bot
```

Проверить что работает:

```bash
curl http://localhost:8082/api/health
```

### 3. Запуск без Docker (для разработки/отладки)

```bash
cd yandex-bot
pip install -r requirements.txt
playwright install chromium

# API-сервер (основной режим)
python main.py

# Или батч-режим из tasks.json
python main.py --cli
```

---

## Интеграция с Telegram-ботом

Работает автоматически. Когда админ нажимает **"Принять в работу"** на заявке:

1. Бот обновляет статус заявки → `accepted`
2. Бот достаёт ключевые слова из заявки
3. Бот отправляет `POST /api/task` в yandex-bot
4. yandex-bot запускает воркеры в фоне
5. Админ видит в Telegram: `🚀 PF запущен: 5 задач (id: a1b2c3d4)`

### Проверка статуса задачи

```bash
curl http://localhost:8082/api/task/a1b2c3d4
```

Ответ:
```json
{
  "task_id": "a1b2c3d4",
  "status": "running",
  "total": 5,
  "done": 2,
  "success": 1,
  "not_found": 1,
  "captcha": 0,
  "errors": 0
}
```

---

## API Endpoints

| Метод | URL | Описание |
|-------|-----|----------|
| `GET` | `/api/health` | Статус сервиса (прокси, профили, воркеры) |
| `POST` | `/api/task` | Создать PF-задачу |
| `GET` | `/api/task/{id}` | Прогресс выполнения задачи |

### POST /api/task — формат запроса

```json
{
  "site": "example.com",
  "keywords": ["купить велосипед", "велосипед москва"],
  "region": "москва",
  "count_per_keyword": 1,
  "secret": ""
}
```

- `site` — целевой домен (без http/www)
- `keywords` — список ключевых слов для поиска в Яндексе
- `region` — регион (опционально)
- `count_per_keyword` — сколько раз выполнить ПФ на каждый ключ (по умолчанию 1)
- `secret` — секретный ключ (если настроен в `.env`)

---

## Ручной режим (CLI)

Для тестирования без Telegram-бота:

### 1. Создай tasks.json

```json
[
  {
    "site": "example.com",
    "keyword": "купить велосипед москва",
    "count": 3
  },
  {
    "site": "example.com",
    "keyword": "велосипед интернет магазин",
    "count": 2
  }
]
```

### 2. Запусти

```bash
python main.py --cli
```

Результаты сохраняются в `results.json`.

---

## Конфигурация (.env)

### Прокси (3proxy)

```env
PROXY_HOST=185.118.66.80       # IP сервера с 3proxy
PROXY_PORT_FIRST=30100         # Первый порт
PROXY_PORT_LAST=30134          # Последний порт (= 35 IP)
PROXY_USER=admin               # Логин
PROXY_PASS=pass                # Пароль
```

Каждый порт = уникальный исходящий IP из купленной сети. Ротация каждые 30 минут.

### Воркеры

```env
MAX_WORKERS=5       # Параллельных браузеров
TASK_TIMEOUT=300    # Таймаут на задачу (сек)
```

Рекомендация по `MAX_WORKERS`:

| RAM сервера | MAX_WORKERS |
|-------------|-------------|
| 4 GB | 5-8 |
| 8 GB | 10-16 |
| 16 GB | 25-35 |
| 32 GB | 50-70 |

Максимум уникальных IP = 35 (по числу прокси-портов).

### Прогрев

```env
WARMUP_ENABLED=true     # Включить прогрев
WARMUP_MIN_SITES=2      # Мин. сайтов для прогрева
WARMUP_MAX_SITES=5      # Макс. сайтов
WARMUP_MIN_TIME=15      # Мин. секунд на сайт
WARMUP_MAX_TIME=45      # Макс. секунд на сайт
```

Сайты для прогрева — в файле `warmup_sites.txt` (один URL на строку). Должны быть **без Яндекс.Метрики**.

### Сценарий Яндекс

```env
YANDEX_MAX_SERP_PAGES=10    # Макс. страниц выдачи для поиска сайта
MIN_TIME_ON_SITE=30          # Мин. секунд на целевом сайте
MAX_TIME_ON_SITE=120         # Макс. секунд
MIN_PAGES_ON_SITE=2          # Мин. страниц для просмотра
MAX_PAGES_ON_SITE=5          # Макс. страниц
```

---

## Структура файлов

```
yandex-bot/
├── main.py              # Точка входа (API-сервер или CLI)
├── api.py               # FastAPI — HTTP API для приёма задач
├── config.py            # Конфигурация из .env
├── db.py                # Загрузка профилей из PostgreSQL
├── proxy_manager.py     # Пул прокси из 3proxy (порты 30100-30134)
├── stealth.py           # JS-инъекции антидетекта
├── human.py             # Имитация человека (мышь, клавиатура, скролл)
├── warmup.py            # Прогрев: посещение сайтов без Метрики
├── scenario.py          # Сценарий: Яндекс поиск → клик → сёрфинг
├── worker.py            # Запуск браузера с профилем + прокси
├── warmup_sites.txt     # Сайты для прогрева (без Метрики)
├── Dockerfile           # Docker-образ с Chromium
├── requirements.txt     # Python-зависимости
├── .env.example         # Пример конфигурации
└── tasks.json.example   # Пример задач для CLI-режима
```

---

## Антидетект

Что скрывается от обнаружения:

- `navigator.webdriver` → `undefined`
- Chrome runtime object (window.chrome)
- Navigator plugins (не пустой массив)
- WebGL vendor/renderer (случайный из пула Intel/NVIDIA)
- Canvas fingerprint (шум на пиксельном уровне)
- Hardware concurrency, device memory (рандом)
- Языки → `ru-RU, ru, en-US, en`
- User-Agent из профиля БД
- Viewport/разрешение из профиля
- Геолокация/таймзона из профиля

## Имитация человека

- Движения мыши по кривым Безье (не прямые линии)
- Набор текста с переменными задержками (гауссово распределение)
- Плавный скролл с разной скоростью
- Случайные паузы между действиями
- Idle-движения мыши при "чтении" страницы
