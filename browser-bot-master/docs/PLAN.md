# План развития acc-generator

## Текущее состояние

CLI-утилита на Python + Playwright, которая:
- Генерирует мобильные Android-отпечатки (23 устройства, 12 Chrome-версий, 23 города РФ)
- Фармит куки на Яндекс-сервисах (ya.ru, поиск, новости, погода и т.д.)
- Обходит автоматизацию через stealth-скрипты + human-like поведение
- Поддерживает прокси (3proxy / файл)
- Сохраняет результат в JSON

## Проблемы текущей реализации

1. **Отпечатки** — фиксированные пулы данных, нет уникальности canvas/webgl/audio
2. **Нет БД** — всё в JSON-файлах, нет управления жизненным циклом аккаунтов
3. **Нет прогрева** — аккаунты создаются один раз и не обновляются
4. **Нет API** — только CLI, нельзя интегрировать с другими сервисами

---

## Рекомендации

### По отпечаткам: покупать или рандомить?

**Рекомендация: комбинированный подход.**

Текущий рандомайзер — нормальная база, но есть слабые места:
- **Canvas fingerprint** — сейчас просто `canvas_seed`, этого мало. Яндекс/Google проверяют реальный canvas hash. Нужно либо инжектить шум в canvas API (что уже частично делает stealth), либо использовать реальные отпечатки.
- **WebGL** — рандомные GPU-модели OK для мобильных, но комбинация GPU + device должна быть реалистичной (Snapdragon → Adreno, MediaTek → Mali).
- **Audio fingerprint** — текущий `noise` подход работает, но нужно проверить что он реально применяется через stealth.js.
- **TLS fingerprint (JA3/JA4)** — Chromium Playwright даёт одинаковый JA3 для всех. Это палево. Решение: использовать разные версии Chromium или camoufox.

**Что стоит докрутить (бесплатно):**
- [ ] Связать device model ↔ GPU ↔ chipset реалистично
- [ ] Добавить рандомизацию `navigator.plugins`, `navigator.languages`
- [ ] Рандомить `screen.availWidth/Height` (отступ от taskbar)
- [ ] Добавить реалистичный `battery` API (если мобильный)

**Что имеет смысл купить:**
- Резидентные мобильные прокси (РФ) — без них Яндекс банит за datacenter IP
- Если бюджет позволяет — можно использовать antidetect-решения типа Camoufox (бесплатный) или GoLogin API

### По прогреву аккаунтов: нужен ли?

**Да, однозначно нужен.** Причины:

1. **Куки протухают** — Яндекс-куки живут 30-90 дней, без обновления профиль "мёртвый"
2. **История поведения** — Яндекс доверяет профилям с историей. Один визит ≠ "живой пользователь"
3. **Разнообразие кук** — чем больше сервисов посещено и localStorage наполнен, тем реалистичнее отпечаток
4. **Yandex.Metrika** — трекает повторные визиты, профиль без истории подозрителен

**Стратегия прогрева:**
- Раз в 1-3 дня: зайти на ya.ru, выполнить 1-2 поисковых запроса
- Раз в неделю: посетить 2-3 Яндекс-сервиса (новости, погода, маркет)
- Раз в 2 недели: посетить внешние сайты (новостные, маркетплейсы)
- Ротировать поисковые запросы (не повторять одинаковые)

---

## Шаги реализации

### Шаг 1: Улучшение отпечатков ✅
- [x] Реалистичные связки device ↔ GPU ↔ viewport ↔ chipset (29 устройств)
- [x] Chrome 120-133 (14 версий)
- [x] Вариативность navigator: languages, battery, screen.avail*
- [x] Provider-паттерн: `source="builtin"` / `source="external"` с флагом `--source`
- Файл: `fingerprints.py`

### Шаг 2: SQL-схема ✅
- [x] `schema.sql` — profiles, profile_cookies, warmup_history
- [x] ENUM типы, индексы, вьюхи (profile_latest_cookies, profiles_needing_warmup)

### Шаг 3: Слой БД ✅
- [x] `database.py` — asyncpg pool, CRUD для профилей
- [x] `config.py` — конфигурация через env-переменные
- [x] insert/get/list/delete профилей, update_after_warmup

### Шаг 4: FastAPI сервер ✅
- [x] `server.py` — полный API
- [x] `POST /profiles/generate` — генерация + опциональный фарминг (background)
- [x] `GET /profiles` — список с фильтрами
- [x] `GET /profiles/{id}` — профиль с куками
- [x] `POST /profiles/{id}/warmup` — ручной прогрев
- [x] `DELETE /profiles/{id}` — удаление
- [x] `GET /stats` — статистика
- [x] `POST /warmup/run` — запуск батч-прогрева

### Шаг 5: Крон-джоба прогрева ✅
- [x] `warmup.py` — APScheduler (каждые N часов)
- [x] Лёгкий прогрев: ya.ru + 1 поиск + 1-2 сервиса
- [x] Глубокий прогрев: каждый 4-й раз — 3-5 сервисов
- [x] Обновление кук и localStorage в БД после прогрева
- [x] Пометка "мёртвых" профилей (3 captcha подряд)

### Шаг 6: Мониторинг и качество
- [ ] Логирование в структурированном формате
- [ ] Метрики: % тёплых, % с captcha, среднее количество кук
- [ ] Алерты если качество падает

---

## Схема БД (предварительная)

```
profiles          — основная таблица профилей
├── id (UUID PK)
├── fingerprints (JSONB) — весь объект отпечатков
├── viewport (JSONB)
├── geo (JSONB)
├── mouse_config (JSONB)
├── proxy_used (TEXT)
├── status (ENUM: new/warm/partial/dead)
├── cookies_count (INT)
├── is_captcha (BOOL)
├── created_at (TIMESTAMP)
├── last_warmup_at (TIMESTAMP)
└── warmup_count (INT)

profile_cookies   — куки профиля (отдельно для удобства обновления)
├── id (SERIAL PK)
├── profile_id (UUID FK → profiles)
├── cookies (JSONB)
├── localstorage (JSONB)
├── collected_at (TIMESTAMP)
└── source (TEXT) — 'initial' / 'warmup'

warmup_history    — лог прогревов
├── id (SERIAL PK)
├── profile_id (UUID FK → profiles)
├── warmup_type (TEXT) — 'light' / 'deep'
├── sites_visited (JSONB)
├── cookies_before (INT)
├── cookies_after (INT)
├── captcha_hit (BOOL)
├── duration_sec (INT)
└── created_at (TIMESTAMP)
```

---

## Приоритеты

1. **БД + сохранение профилей** — без этого всё остальное бессмысленно
2. **API-сервер** — чтобы можно было интегрировать
3. **Крон прогрева** — чтобы профили не протухали
4. **Улучшение отпечатков** — итеративно
