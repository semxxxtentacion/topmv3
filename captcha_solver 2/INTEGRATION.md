# Интеграция captcha-solver в парсер

Этот документ — для команды, которая встраивает модуль в свой парсер. Описана **одна кнопка**: как от URL страницы с капчей получить готовый токен и использовать его в своём коде.

## Как это работает в двух словах

1. Ваш парсер натыкается на Яндекс SmartCaptcha на какой-то странице
2. Парсер делает **один HTTP-запрос** к нашему модулю: `POST /solve {"url": "..."}`
3. Модуль сам открывает браузер, детектит капчу, решает (клик или через 2Captcha), возвращает **токен**
4. Парсер подставляет токен в свою форму / POST-запрос / куда нужно и отправляет
5. Яндекс валидирует токен, пропускает

Сам модуль работает как **отдельный сервис** на VPS. Парсер не содержит логики решения капчи — только один HTTP-вызов.

## Развёртывание

### Вариант 1. Docker (рекомендуемый)

На VPS / любом сервере с Docker:

```bash
git clone <repo-url> captcha-solver
cd captcha-solver
cp .env.example .env
# В .env прописать CAPTCHA_API_KEY=<ваш ключ 2Captcha/RuCaptcha>
docker compose up -d --build
```

Проверка:
```bash
curl http://localhost:8080/healthz
# {"status":"ok"}
```

Готово. Модуль слушает:
- REST: `http://<vps>:8080`
- gRPC: `<vps>:50051`

### Вариант 2. Локальный запуск (для разработки)

```bash
python -m venv .venv
source .venv/bin/activate  # или .venv\Scripts\activate на Windows
pip install -e .
playwright install chromium
export CAPTCHA_API_KEY=<ваш ключ>
python -m captcha_solver
```

## Интеграция из парсера — Python

### Способ А — через ваш браузер (Playwright/Selenium)

Это если ваш парсер уже использует браузер и у него своя сессия / cookies.

```python
import httpx
from playwright.async_api import async_playwright

async def scrape_with_captcha(target_url: str):
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page()
        await page.goto(target_url)
        
        # Если на странице есть SmartCaptcha — решаем через наш сервис
        if await page.query_selector("[data-sitekey], .smartcaptcha"):
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "http://your-vps:8080/solve",
                    json={"url": target_url},
                    timeout=180,
                )
                token = resp.json()["token"]
            
            # Вставляем токен в виджет Яндекса на НАШЕЙ странице
            await page.evaluate(f"""
                if (window.smartCaptcha) {{
                    window.smartCaptcha.setToken('{token}');
                }}
                const ta = document.querySelector('[name="smart-token"]');
                if (ta) {{ ta.value = '{token}'; ta.dispatchEvent(new Event('change', {{bubbles:true}})); }}
            """)
            
            # Дальше ваш обычный флоу — сабмит формы / клик кнопки
            await page.click("button[type=submit]")
        
        # Парсим что нужно...
        content = await page.content()
        await browser.close()
        return content
```

### Способ Б — без браузера (requests / httpx)

Это если ваш парсер работает на HTTP-запросах без рендера.

```python
import httpx
import re

TARGET = "https://example.com/protected-page"
SOLVER = "http://your-vps:8080"

def scrape():
    with httpx.Client() as http:
        # 1. Получить страницу с капчей
        page = http.get(TARGET).text
        # (опционально) извлечь sitekey — для отладки
        sitekey = re.search(r'data-sitekey="([^"]+)"', page).group(1)
        
        # 2. Запросить решение у нашего сервиса
        solve = http.post(
            f"{SOLVER}/solve",
            json={"url": TARGET},
            timeout=180,
        ).json()
        
        if not solve["solved"]:
            raise RuntimeError(f"captcha failed: {solve['error']}")
        
        token = solve["token"]
        
        # 3. Отправить форму с токеном
        # Параметр "smart-token" — стандартное имя для SmartCaptcha
        result = http.post(
            "https://example.com/form-endpoint",
            data={
                "smart-token": token,
                # ... остальные поля формы ...
            },
        )
        return result.text
```

## Интеграция из Node.js

```javascript
import axios from 'axios';

async function solveAndSubmit(targetUrl) {
  const solve = await axios.post('http://your-vps:8080/solve', {
    url: targetUrl
  }, { timeout: 180000 });
  
  if (!solve.data.solved) {
    throw new Error(`captcha failed: ${solve.data.error}`);
  }
  
  const token = solve.data.token;
  
  // Использовать token в вашем запросе к Яндексу
  const result = await axios.post('https://example.com/form-endpoint', {
    'smart-token': token,
    // ... остальное ...
  });
  
  return result.data;
}
```

## Интеграция через gRPC (production)

Когда готовы к prod-интеграции — gRPC быстрее REST и строго типизирован.

```bash
# 1. Сгенерировать stubs в вашем проекте парсера
python -m grpc_tools.protoc \
  -I path/to/captcha-solver/proto \
  --python_out=. --grpc_python_out=. \
  captcha.proto
```

```python
import grpc
import captcha_pb2, captcha_pb2_grpc

async def solve(url: str) -> str:
    async with grpc.aio.insecure_channel('your-vps:50051') as ch:
        stub = captcha_pb2_grpc.CaptchaSolverStub(ch)
        resp = await stub.Solve(captcha_pb2.SolveRequest(url=url))
        if not resp.solved:
            raise RuntimeError(resp.error)
        return resp.token
```

## Формат ответа `/solve`

```json
{
  "type": "click",                // "click" | "coordinate" | "none"
  "solved": true,
  "token": "dD0xNzc2NzE3...",     // валидный токен Yandex SmartCaptcha (base64)
  "coordinates": [],              // заполнен если type=coordinate
  "duration_seconds": 24.7,
  "error": ""                      // если solved=false, тут причина
}
```

**Что делать с полями в вашем коде:**
- `solved: true` + `token` → вставить токен в форму, отправить
- `solved: false` → проверить `error`, возможно повторить запрос
- `type: "coordinate"` → модуль уже кликнул по координатам в своём браузере, ваш токен, скорее всего, в поле `token` (после эскалации с click). `coordinates` — для отладки.
- `type: "none"` → капчи на странице не оказалось, ничего решать не надо

## Timeout и ретраи

Один запрос `/solve` может занять до 2 минут (ждём пока 2Captcha-воркер решит). В вашем клиенте ставьте `timeout=180`.

Ретраи не обязательны — сервис сам ретраит внутри. Если пришёл `solved: false`, это уже финальная ошибка (например, 2Captcha не смог или ключ кончился).

## Баланс и стоимость

Один запрос `/solve` стоит на балансе 2Captcha/RuCaptcha:
- **Простой click** (без эскалации) — ~0.056 ₽
- **С эскалацией до картинки** — ~0.16 ₽
- Это **одна оплата** за полный цикл, не две

При 1000 запросов/день на RuCaptcha — ориентир **1 700–4 800 ₽/мес** (зависит от того, насколько часто Яндекс эскалирует).

Баланс проверять через их API:
```bash
curl "https://rucaptcha.com/res.php?key=$KEY&action=getbalance&json=1"
```

## Мониторинг

Healthcheck на `/healthz` — можно завести в prometheus/uptime monitor:
```
GET /healthz → {"status":"ok"}
```

Логи контейнера — стандартный `docker compose logs -f`. Каждое решение пишет:
- Тип капчи
- Sitekey (обрезанный)
- ID задачи в 2Captcha
- Результат (токен получен / ошибка)

## Типичные проблемы

| Симптом | Причина | Решение |
|---|---|---|
| `error: CAPTCHA_API_KEY is empty` | Не задан ключ | Прописать в `.env` |
| `error: ERROR_ZERO_BALANCE` | Баланс на 2Captcha кончился | Пополнить |
| `type: none`, `solved: true` | Капчи на странице не нашлось | Сайт может не показывать капчу для этого IP/сессии |
| `duration_seconds > 120` | 2Captcha перегружен или воркеры долго решают | Норма в пиковые часы |
| `captcha still present after token injection` (в логах) | Токен вставили, но виджет не обновился визуально | Обычно это ок для демо / некоторых сайтов — проверяйте, принял ли сервер токен при сабмите |

## Безопасность

- API-ключ 2Captcha держать только в `.env`, не коммитить в git
- Если сервис доступен из интернета — поставить за reverse proxy (nginx) с basic auth или IP whitelist
- Модуль не хранит токены и URL дольше одного запроса — нет сессионного состояния
