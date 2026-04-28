"""E2E парсер v2 — ВСЁ в одном видимом окне.

Парсер сам:
  1. Открывает Yandex поиск
  2. Если капча — кликает «Я не робот» (фаза 1)
  3. Если эскалация до картинки — снимает body+instructions screenshot
  4. Шлёт в /solve_image → получает координаты
  5. Кликает по координатам в СВОЁМ окне
  6. Жмёт «Отправить»
  7. Продолжает парсинг

Никакого второго окна solver — solver работает как чистый прокси к Rucaptcha.

Запуск:
    python e2e_yandex_parser_v2.py --query "ремонт квартир одинцово" --pages 20
"""
import argparse
import asyncio
import base64
import csv
import json
import random
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx
from playwright.async_api import async_playwright

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SOLVER = "http://localhost:8080/solve_image"

# Селекторы Yandex CheckboxCaptcha + AdvancedCaptcha
SEL_CHECKBOX = "#js-button.CheckboxCaptcha-Button, [data-testid='checkbox-captcha'] input[type='button']"
SEL_ADV_IMAGE = ".AdvancedCaptcha-ImageWrapper"
SEL_ADV_INSTR = ".AdvancedCaptcha-SilhouetteTask, .AdvancedCaptcha-Footer"
SEL_SUBMIT = "button.CaptchaButton.CaptchaButton_view_action, button[data-testid='submit']"
SEL_ANY_CAPTCHA = ".CheckboxCaptcha, .AdvancedCaptcha, [data-testid='checkbox-captcha']"


async def is_captcha(page) -> bool:
    if "captcha" in page.url.lower():
        return True
    return await page.query_selector(SEL_ANY_CAPTCHA) is not None


async def human_click(page, selector: str) -> bool:
    el = await page.query_selector(selector)
    if not el:
        return False
    try:
        box = await el.bounding_box()
        if not box:
            return False
        tx = box["x"] + box["width"] / 2 + random.uniform(-3, 3)
        ty = box["y"] + box["height"] / 2 + random.uniform(-2, 2)
        sx, sy = tx + random.uniform(-200, 200), ty + random.uniform(-150, 150)
        await page.mouse.move(sx, sy, steps=1)
        await page.wait_for_timeout(int(random.uniform(200, 500)))
        for i in range(1, 11):
            t = i / 10
            eased = 1 - (1 - t) ** 3
            x = sx + (tx - sx) * eased + random.uniform(-2, 2)
            y = sy + (ty - sy) * eased + random.uniform(-2, 2)
            await page.mouse.move(x, y, steps=1)
            await asyncio.sleep(random.uniform(0.02, 0.08))
        await page.wait_for_timeout(int(random.uniform(300, 700)))
        await page.mouse.down()
        await asyncio.sleep(random.uniform(0.05, 0.12))
        await page.mouse.up()
        return True
    except Exception:
        return False


async def solve_captcha_inline(page, dump_dir: Path) -> bool:
    """Решить капчу прямо в этом окне. True если прошло."""
    print("    [captcha] phase 1: click 'I'm not a robot'")
    if not await human_click(page, SEL_CHECKBOX):
        print("    [captcha] no checkbox button found")
        return False

    # Ждём либо успех либо эскалацию до картинки
    await page.wait_for_timeout(2000)
    for _ in range(20):  # 10 сек
        await asyncio.sleep(0.5)
        if not await is_captcha(page):
            print("    [captcha] phase 1 PASSED — Yandex didn't escalate")
            return True
        if await page.query_selector(SEL_ADV_IMAGE):
            print("    [captcha] escalated to image phase")
            break

    if not await page.query_selector(SEL_ADV_IMAGE):
        print("    [captcha] no image and no success — stuck")
        return False

    # === Phase 2: image ===
    for attempt in range(1, 4):
        print(f"    [captcha] phase 2 attempt {attempt}/3")
        attempt_dir = dump_dir / f"a{attempt}"
        attempt_dir.mkdir(parents=True, exist_ok=True)

        # ВАЖНО: дождаться РЕАЛЬНОЙ стимул-картинки `.TaskImage`.
        # У Яндекса в `.AdvancedCaptcha-ImageWrapper` есть несколько <img>: маленькие
        # силуэты-маркеры (грузятся быстро) + главная TaskImage (грузится дольше).
        # Если ждать любой <img> — попадаем на маленький маркер и снимаем пустую
        # стимул-картинку.
        try:
            await page.wait_for_selector(SEL_ADV_IMAGE, state="visible", timeout=15000)
            # Главная картинка задания — должна быть реально большой (>= 250px по ширине)
            await page.wait_for_function("""() => {
                const wrap = document.querySelector('.AdvancedCaptcha-ImageWrapper');
                if (!wrap) return false;
                // ищем именно главное изображение task'а
                const main = wrap.querySelector('.TaskImage, img.AdvancedCaptcha__image, img[src]');
                if (!main) return false;
                // <img> либо <div style="background-image">
                if (main.tagName === 'IMG') {
                    return main.complete && main.naturalWidth >= 250;
                }
                // div с background — проверим computed style
                const bg = getComputedStyle(main).backgroundImage || '';
                return bg.includes('url') && main.offsetWidth >= 250;
            }""", timeout=15000)
            # После загрузки картинки — ещё ждём чтобы силуэты внизу (instructions)
            # тоже появились и анимации завершились
            await page.wait_for_timeout(1500)
        except Exception as e:
            print(f"    [captcha] image still not loaded after 15s: {e}")
            # Дополнительная страховка
            await page.wait_for_timeout(2000)

        click_area = await page.query_selector(SEL_ADV_IMAGE)
        instr_area = await page.query_selector(SEL_ADV_INSTR)
        if not click_area:
            print("    [captcha] image area gone")
            return False
        click_box = await click_area.bounding_box()
        body_bytes = await click_area.screenshot()
        (attempt_dir / "body.png").write_bytes(body_bytes)
        body_b64 = base64.b64encode(body_bytes).decode("ascii")
        instr_b64 = None
        if instr_area:
            instr_bytes = await instr_area.screenshot()
            (attempt_dir / "instructions.png").write_bytes(instr_bytes)
            instr_b64 = base64.b64encode(instr_bytes).decode("ascii")

        # Прочитаем инструкцию для chamber
        instruction = await page.evaluate("""() => {
            const cs = [];
            document.querySelectorAll('.AdvancedCaptcha *, form *').forEach(el => {
                const t = (el.innerText || '').trim();
                if (!t || t.length < 5 || t.length > 200) return;
                if (/нажм|кликн|выбер|порядк|укаж|тако/i.test(t)) cs.push(t);
            });
            return cs.sort((a,b) => a.length - b.length)[0] || '';
        }""")
        comment = (
            "Yandex SmartCaptcha silhouette task. "
            "На главной картинке (BODY) спрятаны те же предметы что в эталоне (imgInstructions). "
            "Найдите их на главной картинке и кликните по ним В ТОМ ЖЕ ПОРЯДКЕ слева направо."
        )
        if instruction:
            comment += f" Инструкция Яндекса: «{instruction}»."
        (attempt_dir / "comment.txt").write_text(comment, encoding="utf-8")

        # Шлём в solver
        print(f"    [captcha] POST /solve_image (body={len(body_b64)}b, instr={'+' if instr_b64 else '-'})")
        t0 = time.time()
        try:
            with httpx.Client(timeout=180) as c:
                r = c.post(SOLVER, json={
                    "body_b64": body_b64,
                    "instructions_b64": instr_b64,
                    "comment": comment,
                })
        except Exception as e:
            print(f"    [captcha] solver call err: {e}")
            return False
        elapsed = time.time() - t0
        if r.status_code != 200:
            print(f"    [captcha] solver HTTP {r.status_code}: {r.text[:200]}")
            return False
        data = r.json()
        coords = [(p["x"], p["y"]) for p in data.get("coordinates", [])]
        print(f"    [captcha] got {len(coords)} coords in {elapsed:.1f}s: {coords}")
        (attempt_dir / "coords.json").write_text(
            json.dumps(coords, indent=2), encoding="utf-8"
        )

        # Визуализация на body.png — для проверки
        try:
            from PIL import Image, ImageDraw
            img = Image.open(attempt_dir / "body.png").convert("RGB")
            draw = ImageDraw.Draw(img)
            for i, (x, y) in enumerate(coords, 1):
                r_ = 14
                draw.ellipse((x - r_, y - r_, x + r_, y + r_), outline=(255, 0, 0), width=3)
                draw.text((x + r_ + 2, y - r_), str(i), fill=(255, 0, 0))
            img.save(attempt_dir / "clicks_overlay.png")
        except Exception:
            pass

        # Кликаем в нашем окне по абсолютным координатам страницы
        for x, y in coords:
            abs_x = click_box["x"] + x + random.uniform(-2, 2)
            abs_y = click_box["y"] + y + random.uniform(-2, 2)
            await page.mouse.move(abs_x, abs_y, steps=random.randint(8, 18))
            await page.wait_for_timeout(int(random.uniform(200, 500)))
            await page.mouse.click(abs_x, abs_y)
            await page.wait_for_timeout(int(random.uniform(400, 900)))

        # Пауза перед submit
        await page.wait_for_timeout(int(random.uniform(1500, 2500)))
        # Жмём «Отправить» (НЕ крестик)
        submit_clicked = False
        for sel in [
            "button.CaptchaButton.CaptchaButton_view_action",
            "button[data-testid='submit']",
            "button.Button2_view_action",
        ]:
            try:
                loc = page.locator(sel).filter(visible=True).first
                await loc.wait_for(state="visible", timeout=2000)
                cls = (await loc.get_attribute("class")) or ""
                if "view_clear" in cls.lower():
                    continue
                await loc.click()
                print(f"    [captcha] clicked submit ({sel})")
                submit_clicked = True
                break
            except Exception:
                continue
        if not submit_clicked:
            print("    [captcha] no submit found — relying on widget auto-submit")

        # Ждём результата
        await page.wait_for_timeout(3000)
        # Капчи больше нет?
        if not await is_captcha(page):
            await page.screenshot(path=str(attempt_dir / "PASSED.png"), full_page=True)
            print(f"    [captcha] ✅ PASSED on attempt {attempt}")
            return True
        # Проверим — может новая картинка для retry?
        await page.wait_for_timeout(1500)
        if await page.query_selector(SEL_ADV_IMAGE):
            await page.screenshot(path=str(attempt_dir / "FAILED_new_image.png"), full_page=True)
            print(f"    [captcha] ❌ wrong clicks → new image, retry attempt {attempt + 1}")
            continue
        await page.screenshot(path=str(attempt_dir / "FAILED.png"), full_page=True)
        print("    [captcha] ❌ stuck after submit, no new image")
        return False
    return False


async def extract_organics(page) -> list[dict]:
    return await page.evaluate("""() => {
        const items = [];
        document.querySelectorAll('.serp-item').forEach(el => {
            const dataFast = el.getAttribute('data-fast-name') || '';
            if (dataFast.includes('ad') || dataFast.includes('entity_search')) return;
            const a = el.querySelector('a.OrganicTitle-Link, a.Link[href^="http"], h2 a[href^="http"]');
            if (!a || a.href.includes('yandex.')) return;
            const sn = el.querySelector('.OrganicTextContentSpan, .Text');
            items.push({
                title: (a.innerText || '').trim(),
                url: a.href,
                snippet: sn ? (sn.innerText || '').trim().slice(0, 250) : '',
            });
        });
        return items;
    }""")


async def main(query: str, pages: int, out_csv: str):
    run_dir = Path("data/parser_runs") / datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)  # видимое окно
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
            locale="ru-RU",
            viewport={"width": 1366, "height": 768},
        )
        page = await ctx.new_page()

        all_results = []
        captchas_total = 0
        captchas_solved = 0

        for p in range(pages):
            url = f"https://yandex.ru/search/?text={query.replace(' ', '+')}&p={p}"
            print(f"\n[page {p+1}/{pages}] {url}")
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                await page.wait_for_timeout(800)
            except Exception as e:
                print(f"  goto err: {e}")
                continue

            # Решаем капчу если есть
            tries = 0
            while await is_captcha(page) and tries < 2:
                tries += 1
                captchas_total += 1
                cap_dir = run_dir / f"page{p+1}_cap{tries}"
                cap_dir.mkdir(parents=True, exist_ok=True)
                ok = await solve_captcha_inline(page, cap_dir)
                if ok:
                    captchas_solved += 1
                    # После прохождения — попробуем снова на нашу страницу
                    try:
                        await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                        await page.wait_for_timeout(1000)
                    except Exception:
                        pass
                else:
                    print("  ✗ capture didn't pass, skipping page")
                    break

            if await is_captcha(page):
                print("  ✗ still on captcha, skip")
                continue

            organics = await extract_organics(page)
            print(f"  ✓ собрано {len(organics)} результатов")
            for o in organics:
                o["page"] = p + 1
                all_results.append(o)
            await page.wait_for_timeout(1500)

        await browser.close()

        if all_results:
            csv_path = Path(out_csv)
            with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["page", "title", "url", "snippet"])
                w.writeheader()
                w.writerows(all_results)
            print(f"\n💾 {len(all_results)} → {csv_path}")

        print(f"\n=== ИТОГ ===")
        print(f"  Запрос:     {query}")
        print(f"  Страниц:    {pages}")
        print(f"  Результатов:{len(all_results)}")
        print(f"  Капч/решено:{captchas_total}/{captchas_solved}")
        print(f"  Дампы капч: {run_dir}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", default="ремонт квартир одинцово")
    ap.add_argument("--pages", type=int, default=20)
    ap.add_argument("--out", default="yandex_serp_v2.csv")
    args = ap.parse_args()
    asyncio.run(main(args.query, args.pages, args.out))
