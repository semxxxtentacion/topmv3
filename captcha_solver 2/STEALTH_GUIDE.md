# Снижение частоты капчи Яндекса в парсере

Этот гайд про то как **уменьшить число вызовов captcha-solver** в 5-10 раз
за счёт правильной настройки парсера. Каждый необойдённый запрос — это
сэкономленные деньги на Rucaptcha + ускорение сбора данных.

## TL;DR — что точно работает

| Мера | Эффект | Сложность |
|---|---|---|
| Anti-detect Chromium args + init script | x2–3 реже капча | low (готовый модуль `stealth.py`) |
| Resident/мобильные прокси | x3–5 реже | mid (платные сервисы) |
| Прогрев сессии (главная yandex.ru до поиска) | x1.3 реже | low |
| Сохранение `storage_state` между запусками | x2 реже | low |
| Human-like pacing (паузы 3-7s + движения мыши) | x1.5 реже | low |
| Ротация прокси раз в 10-20 запросов | x1.5 реже | mid |
| **Все вместе** | **x10–15 реже** | mid |

## Готовый модуль

В `captcha_solver/stealth.py` лежат три функции:

```python
from captcha_solver.stealth import make_stealthy_context, human_pacing, warm_up

async with async_playwright() as pw:
    browser, ctx = await make_stealthy_context(
        pw,
        proxy="http://login:pass@residential-proxy:port",
        storage_state="data/sessions/yandex.json",  # если есть прошлая сессия
    )
    page = await ctx.new_page()
    await warm_up(page)                            # прогрев на главной

    for query in queries:
        await page.goto(f"https://yandex.ru/search/?text={query}")
        # ... парсинг ...
        await human_pacing(page)                   # пауза перед следующим

    # Сохраним сессию для следующего запуска
    await ctx.storage_state(path="data/sessions/yandex.json")
```

## Что делает `make_stealthy_context`

### 1. Chromium-аргументы

```
--disable-blink-features=AutomationControlled   # убирает navigator.webdriver
--disable-features=IsolateOrigins,site-per-process
--disable-webrtc                                # WebRTC может слить реальный IP
--no-default-browser-check
--no-first-run
```

### 2. Init script (выполняется ДО любого скрипта страницы)

- `navigator.webdriver` → `undefined` (главный маркер)
- `navigator.plugins` → 3 правдоподобных плагина (PDF Viewer и т.п.)
- `navigator.languages` → `['ru-RU', 'ru', 'en-US', 'en']`
- `RTCPeerConnection` → `undefined` (анти-WebRTC)
- `permissions.query` для `notifications` → возвращает `prompt` как у пользователя
- WebGL `getParameter` → `Intel Inc.` / `Intel Iris OpenGL Engine`
- `window.chrome.runtime` → `{}` (у настоящего Chrome он есть)

### 3. Контекст

- `locale="ru-RU"`, `timezone_id="Europe/Moscow"`
- `viewport` рандомный из `[(1366,768), (1536,864), (1920,1080)]`
- `user_agent` рандомный из пула свежих Chrome 130+
- `extra_http_headers` с `Accept-Language: ru-RU,ru;q=0.9,en;q=0.8` и `DNT: 1`
- `device_scale_factor=1` (важно для совпадения скриншотов и bounding box)

### 4. Блокировка трекеров

Глобальный route abort на:
- `**/*metrika*`
- `**/*mc.yandex.ru*`
- `**/*an.yandex.ru*`
- `**/*adfox*`
- `**/yastatic.net/metrika*`
- `**/*googletagmanager*`
- `**/*google-analytics*`

Без этого Яндекс отправляет fingerprint в свою аналитику и привязывает к нашему IP.

## Что делает `human_pacing`

Между запросами:
1. 2-5 случайных движений мыши в произвольные точки страницы
2. С вероятностью 50% — скролл вниз на 200-1200 пикселей
3. Финальная пауза 2-6 секунд (рандом)

Боты делают запросы с интервалом 0.1-0.5 сек. Человек 3-15 сек. Эта функция
делает паттерн похожим на человеческий.

## Что делает `warm_up`

Заходит на `https://yandex.ru/` главную, ждёт 1.5-3.5 сек, скроллит немного.
Яндекс считает «прогретые» сессии менее подозрительными — yandexuid выдаётся
сразу, и в дальнейшем поисковые запросы отрабатывают без капчи в первые 5-10 раз.

## Дополнительно — что вне модуля

### Резидентные прокси (главный фактор)

Датацентровые прокси Яндекс палит по диапазонам ASN. Жирный эффект даёт
переход на:
- **Bright Data** (Luminati) — ~$15-30/ГБ, лучшее качество
- **IPRoyal** — ~$5-15/ГБ
- **Soax** — ~$10-25/ГБ
- **Mobile прокси** — ~$50-150/мес безлимит, на 1 канал (ваши SIM-карты)

В коде:
```python
browser, ctx = await make_stealthy_context(
    pw, proxy="http://customer-USR:PASS@gate.residential-proxy.com:7777"
)
```

### Сессионный кэш

Сохраняйте cookies+localStorage между запусками. Каждый перезапуск с пустого
браузера = +1 капча гарантированно.

```python
SESSION_FILE = "data/sessions/yandex.json"

# Загрузить если есть
storage = SESSION_FILE if Path(SESSION_FILE).exists() else None
browser, ctx = await make_stealthy_context(pw, storage_state=storage)

# ... работа парсера ...

# Сохранить перед выходом
await ctx.storage_state(path=SESSION_FILE)
```

### Ротация прокси

Раз в 10-20 запросов меняйте прокси. После 20-30 запросов с одного IP даже
резидентного, Яндекс начинает давить.

```python
PROXIES = ["http://...:1", "http://...:2", "http://...:3"]
i = 0
for batch in chunks(queries, 15):
    proxy = PROXIES[i % len(PROXIES)]
    browser, ctx = await make_stealthy_context(pw, proxy=proxy)
    # ... обработать batch ...
    await ctx.storage_state(path=f"data/sessions/yandex_{i}.json")
    await ctx.close()
    await browser.close()
    i += 1
```

Каждая «новая личность» (новый прокси + свежий контекст) тратит ~5 запросов
на «разогрев» прежде чем Яндекс начнёт показывать капчу.

### Параллельность

Не делайте N параллельных потоков с одного IP. Если нужна скорость —
N прокси × 1 поток на каждый. Параллельные потоки с одного IP Яндекс
детектит мгновенно.

### Headless vs headful

В headless режиме Chromium имеет специфические CSS feature signatures —
Яндекс это видит. На VPS это не лечится (нет дисплея). Решение:
**xvfb** (виртуальный дисплей) под Linux, тогда Playwright можно запускать
с `headless=False` и Яндекс думает что окно настоящее.

```bash
# на сервере
sudo apt install xvfb
xvfb-run -a python parser.py
```

## Что НЕ помогает

- **Случайный User-Agent без обновления Chrome args** — конфликт фингерпринта
- **Повтор того же запроса с задержкой** — Яндекс помнит IP+fingerprint
- **`time.sleep(X)` без движений мыши** — паттерн всё равно ботский
- **VPN типа NordVPN/Surfshark** — IP-диапазоны давно в чёрных списках
- **Изменение `navigator.userAgent` через JS после загрузки страницы** — Яндекс
  снимает fingerprint до выполнения user-скриптов

## Замер эффекта

Сделайте контрольный прогон:

```python
# Без stealth
results_a = await parse_pages(query, pages=20, use_stealth=False)

# Со stealth
results_b = await parse_pages(query, pages=20, use_stealth=True)

print(f"Без stealth: капч {results_a.captchas}/{20}")
print(f"Со stealth:  капч {results_b.captchas}/{20}")
```

Ожидаемая разница на чистом datacenter IP без прокси:
- Без stealth: 18-20 капч из 20 (~95%)
- Со stealth (без прокси): 6-12 капч (~30-60%)
- Со stealth + резидентный прокси: 0-3 капчи (~0-15%)
- Со stealth + резидентный + warm_up + storage_state: 0-1 капч (~0-5%)

## Финальный recommended stack

```python
import asyncio
from pathlib import Path

from playwright.async_api import async_playwright
from captcha_solver.stealth import make_stealthy_context, human_pacing, warm_up


SESSION_FILE = Path("data/sessions/yandex.json")
PROXIES = [
    "http://login:pass@residential1.example.com:7777",
    "http://login:pass@residential2.example.com:7777",
]


async def parse_with_proxy(proxy: str, queries: list[str]):
    storage = str(SESSION_FILE) if SESSION_FILE.exists() else None
    async with async_playwright() as pw:
        browser, ctx = await make_stealthy_context(
            pw, proxy=proxy, headless=True, storage_state=storage,
        )
        page = await ctx.new_page()
        await warm_up(page)

        results = []
        for q in queries:
            url = f"https://yandex.ru/search/?text={q.replace(' ', '+')}"
            await page.goto(url, wait_until="domcontentloaded")
            # ... ваша логика парсинга + вызов captcha-solver если капча всё-таки есть ...
            results.append(...)
            await human_pacing(page)

        SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
        await ctx.storage_state(path=str(SESSION_FILE))
        await browser.close()
        return results


async def main(all_queries: list[str]):
    chunk_size = 15  # сколько запросов на одну прокси-сессию
    for i in range(0, len(all_queries), chunk_size):
        proxy = PROXIES[(i // chunk_size) % len(PROXIES)]
        chunk = all_queries[i : i + chunk_size]
        await parse_with_proxy(proxy, chunk)


if __name__ == "__main__":
    asyncio.run(main(["query1", "query2", ...]))
```

С таким стеком на 1000 запросов вы получите ~50 капч → ~10 ₽ на Rucaptcha.
Без stealth те же 1000 запросов = 800-900 капч → ~150 ₽.
