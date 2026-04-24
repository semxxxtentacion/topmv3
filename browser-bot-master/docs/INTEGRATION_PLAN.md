# План интеграции acc-generator + yandex-bot

## Текущее состояние

- **acc-generator** (корень) — генерирует мобильные профили, фармит куки, хранит в PostgreSQL, прогревает по расписанию
- **yandex-bot/** — отдельный подпроект для ПФ (поведенческих факторов), ходит в Яндекс по ключевым словам, кликает по целевым сайтам
- Оба проекта работают независимо, имеют дублированный код (stealth.py, human.py, proxy логика)
- yandex-bot уже умеет загружать профили из БД (db.py), но конфиг указывает на отдельную базу

---

## Шаг 1. Актуальные версии Chrome (из интернета)

**Проблема:** в `fingerprints.py` захардкожены версии 120–133, которые уже устарели (март 2026).

**Решение:**
- Создать утилиту `chrome_versions.py` в корне
- Парсить актуальные стабильные версии Chrome для Android с публичного API:
  - Основной: `https://versionhistory.googleapis.com/v1/chrome/platforms/android/channels/stable/versions` (официальный Google API, отдает JSON)
  - Фолбэк: `https://chromiumdash.appspot.com/fetch/milestones`
- Кэшировать в файл `chrome_versions_cache.json` (TTL 24 часа)
- Брать последние 10–14 версий (major), для каждой — последний патч
- В `fingerprints.py` заменить хардкод на вызов `get_chrome_versions()`
- В `yandex-bot/worker.py` — аналогично использовать актуальные версии

**Файлы:**
- `chrome_versions.py` — новый файл, ~80 строк
- `fingerprints.py` — заменить `CHROME_VERSIONS` на вызов функции

---

## Шаг 2. Единый конфиг: общая БД + общие прокси

**Проблема:** yandex-bot имеет свой config.py, свою БД (89.169.45.73) и свои прокси-настройки.

**Решение:**
- yandex-bot берёт профили **только из БД** (убрать `PROFILES_SOURCE=file`, JSON-фолбэк)
- yandex-bot/config.py: читать `DATABASE_URL` из корневого `.env` как единый источник
- yandex-bot/config.py: прокси брать из тех же настроек, что и генератор (корневой `.env`)
- Убрать из yandex-bot/db.py загрузку из JSON файлов

**Файлы:**
- `yandex-bot/config.py` — единый `DATABASE_URL`, общие прокси
- `yandex-bot/db.py` — убрать JSON-загрузку, только БД

---

## Шаг 3. Независимый запуск каждого компонента

**Принцип:** генератор и бот-ходок — два отдельных приложения. Каждый запускается самостоятельно, но оба используют общую БД и общие прокси.

### 3a. Генератор аккаунтов (как сейчас)

```bash
# Генерация профилей + фарм куков → сохранение в БД
python -m profile_generator --count 100 --workers 10

# Сервер (API + автопрогрев)
python -m profile_generator server
```

Без изменений — уже работает.

### 3b. Бот-ходок (CLI для тестирования и продакшена)

```bash
# Один ходок, одно ключевое слово:
python -m yandex_bot --keyword "купить диван" --site "example.com" --region 213

# Несколько ключей:
python -m yandex_bot --keyword "купить диван" --keyword "диван москва" --site "example.com"

# Визуальная отладка:
python -m yandex_bot --keyword "тест" --site "example.com" --headless false --workers 1

# API-сервер (для внешних запросов):
python -m yandex_bot server
```

- Профили — **только из БД**
- Прокси — общие с генератором (из корневого `.env`)
- `--headless false` для визуальной отладки
- Лог в реальном времени

**Файлы:**
- `yandex-bot/__main__.py` — точка входа CLI + server mode

---

## Шаг 4. Интеграция модулей (убрать дубли)

**Проблема:** stealth.py и human.py дублированы в корне и yandex-bot/.

**Решение:** пока НЕ объединяем (они немного различаются и заточены под разные задачи). Но делаем так:
- yandex-bot импортирует `chrome_versions.py` из корня (через sys.path)
- Общие настройки через единый `.env`

Полное объединение — отдельный этап, когда всё стабильно работает.

---

## Порядок реализации

| # | Задача | Файлы | Статус |
|---|--------|-------|--------|
| 1 | chrome_versions.py — парсинг актуальных версий | `chrome_versions.py` | DONE |
| 2 | fingerprints.py — динамические версии Chrome | `fingerprints.py` | DONE |
| 3 | yandex-bot/worker.py — динамические версии Chrome | `yandex-bot/worker.py` | DONE |
| 4 | Единый конфиг БД + прокси | `yandex-bot/config.py`, `yandex-bot/db.py` | DONE |
| 5 | yandex-bot/__main__.py — CLI запуск | `yandex-bot/__main__.py` | DONE |
| 6 | yandex-bot/api.py — убрать JSON-загрузку | `yandex-bot/api.py` | DONE |
| 7 | yandex-bot/main.py — убрать JSON-загрузку | `yandex-bot/main.py` | DONE |

---

## Решённые вопросы

- **Прокси:** берём те же что у генератора (корневой `.env`, 3proxy)
- **Профили:** только из БД, никаких JSON файлов

## Открытые вопросы

1. **Регион Яндекса:** дефолт 213 (Москва) или параметризировать?
2. **Капча:** CapMonster ключ уже есть и работает?
