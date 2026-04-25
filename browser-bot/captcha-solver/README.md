# captcha-solver

Yandex SmartCaptcha solver — handles both click and coordinate variants via 2Captcha (or RuCaptcha / Anti-Captcha — same API). Ships as a Python library, a REST server, and a gRPC server backed by the same core.

## Quick start

```bash
python -m venv .venv
.venv/Scripts/activate          # Windows
# source .venv/bin/activate     # Linux/macOS
pip install -e '.[dev]'
playwright install chromium
cp .env.example .env            # put your CAPTCHA_API_KEY in .env
```

### REST

```bash
python -m captcha_solver
# -> http://localhost:8080/healthz
# -> POST http://localhost:8080/solve  {"url": "https://example.com/page"}
```

Response:
```json
{
  "type": "click",
  "solved": true,
  "token": "dD0xNjU0MTA5...",
  "coordinates": [],
  "duration_seconds": 24.7,
  "error": ""
}
```

Coordinate variant returns `coordinates: [{x,y}, ...]` instead of a token — the solver has already clicked them inside its own browser, so downstream code only uses the return value as a receipt.

### gRPC

```bash
bash scripts/gen_proto.sh          # regenerate stubs after proto edits
python -m captcha_solver.api.grpc_server
# -> captcha.CaptchaSolver/Solve on :50051
```

Proto at `proto/captcha.proto` — consumers in any language generate stubs from there.

### Library

```python
from captcha_solver import CaptchaSolver

result = await CaptchaSolver().solve("https://example.com/protected")
if result.solved:
    print(result.token or result.coordinates)
```

## Config (env)

| var | default | meaning |
|---|---|---|
| `CAPTCHA_API_KEY` | — | 2Captcha key (required) |
| `CAPTCHA_SERVICE_HOST` | `2captcha.com` | swap to `rucaptcha.com` or `anti-captcha.com` |
| `CAPTCHA_POLL_INTERVAL` | `5` | seconds between polls |
| `CAPTCHA_POLL_MAX_TRIES` | `24` | max poll attempts (2 min default) |
| `HEADLESS` | `true` | headless Chromium |
| `HTTP_PROXY` | — | optional Playwright proxy |
| `PORT` | `8080` | REST port |
| `GRPC_PORT` | `50051` | gRPC port |

## How it works

1. Open the target URL in a fresh Playwright context (Yandex tracking scripts blocked, anti-fingerprint init script).
2. Detect the captcha type:
   - **click** — presence of `.smartcaptcha` / `[data-sitekey]` / SmartCaptcha iframe
   - **coordinate** — captcha image element + Russian/English "click" instruction text
3. Dispatch:
   - **click** → extract sitekey → `2captcha.com/in.php?method=yandex` → poll `res.php` → inject token via `window.smartCaptcha.setToken()` / hidden textarea / callback → submit form
   - **coordinate** → screenshot image element → `2captcha.com/in.php?method=base64&coordinatescaptcha=1` → poll → replay clicks with human-like mouse movement and jitter → submit form
4. Verify captcha disappeared; return structured result.

## Deploy on VPS

```bash
git clone <repo> && cd captcha_solver
cp .env.example .env && nano .env     # set CAPTCHA_API_KEY
docker compose up -d --build
# REST:  http://<vps>:8080/solve
# gRPC:  <vps>:50051
```

## Tests

```bash
pytest -q
```

14 tests cover the 2Captcha client (happy path, polling, rejections, timeout, coordinate parsing) and the REST layer (health, click / coordinate responses, solver error → 502).

Browser-path tests are excluded — Playwright live runs belong in staging, not unit tests.

## Project layout

```
captcha_solver/
  __init__.py           # public API: CaptchaSolver, SolveResult, CaptchaType
  __main__.py           # `python -m captcha_solver` → REST
  config.py             # Settings (pydantic-settings)
  two_captcha.py        # 2Captcha HTTP client (submit + poll)
  browser.py            # Playwright context factory with anti-detection
  solver.py             # detection + click / coordinate handlers
  api/
    rest.py             # FastAPI app
    grpc_server.py      # grpc.aio server
  proto/                # generated gRPC stubs land here
proto/captcha.proto     # service definition
tests/
```

## Notes

- Selectors in `solver.py` are tuned to the live Yandex DOM at time of writing — if Yandex changes markup the `detect()` / `_extract_sitekey()` helpers are the places to adjust.
- Each `/solve` call spins up a fresh browser context. For high throughput, run several replicas behind a load balancer — cheaper than pooling contexts (Yandex correlates long-lived fingerprints).
- When `CAPTCHA_API_KEY` is unset the server still starts and answers `/healthz`; `/solve` returns 502 with a clear error.
