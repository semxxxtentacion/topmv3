import re
from playwright.async_api import BrowserContext, Page

# Умный JS-блокер: он сам проверяет, где находится
METRIKA_JS_BLOCK = """
(function() {
    // ЕСЛИ МЫ НА КАПЧЕ - ВЫКЛЮЧАЕМ БЛОКИРОВКУ (иначе Яндекс нас не пустит)
    if (window.location.href.includes('showcaptcha')) {
        return; 
    }

    // 1. Подменяем window.ym на пустышку
    window.ym = function() {};
    Object.defineProperty(window, 'ym', {
        get: function() { return function() {}; },
        set: function() {},
        configurable: false
    });

    // 2. Блокируем fetch к mc.yandex
    const origFetch = window.fetch;
    window.fetch = function(url) {
        if (url && url.toString().includes('mc.yandex')) {
            return Promise.resolve(new Response('', {status: 200}));
        }
        return origFetch.apply(this, arguments);
    };

    // 3. Блокируем XMLHttpRequest к mc.yandex
    const origOpen = XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open = function(method, url) {
        if (url && url.toString().includes('mc.yandex')) {
            this._blocked = true;
        }
        return origOpen.apply(this, arguments);
    };
    const origSend = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.send = function() {
        if (this._blocked) return;
        return origSend.apply(this, arguments);
    };

    // 4. Блокируем Image beacon к mc.yandex
    const OrigImage = window.Image;
    window.Image = new Proxy(OrigImage, {
        construct(target, args) {
            const img = new target(...args);
            const descriptor = Object.getOwnPropertyDescriptor(HTMLImageElement.prototype, 'src');
            const origSrcSetter = descriptor.set;
            Object.defineProperty(img, 'src', {
                set(value) {
                    if (value && value.toString().includes('mc.yandex')) return;
                    origSrcSetter.call(this, value);
                },
                get() {
                    return descriptor.get.call(this);
                }
            });
            return img;
        }
    });

    // 5. Блокируем navigator.sendBeacon к mc.yandex
    const origBeacon = navigator.sendBeacon;
    navigator.sendBeacon = function(url, data) {
        if (url && url.toString().includes('mc.yandex')) return true;
        return origBeacon.apply(this, arguments);
    };

})();
"""

async def apply_stealth(context: BrowserContext = None, page: Page = None):
    """
    Умная блокировка Яндекс Метрики.
    Пропускает метрику только на страницах с капчей.
    """
    if context is None and page is None:
        raise ValueError("Передайте context или page")

    async def block_network(route, request):
        url = request.url
        
        # Безопасно получаем URL страницы
        page_url = ""
        try:
            if request.frame and request.frame.page:
                page_url = request.frame.page.url
        except:
            pass

        # ИСКЛЮЧЕНИЕ: Если мы на странице капчи - пропускаем Метрику для сбора мышки
        if "showcaptcha" in page_url or "smartcaptcha" in url:
            await route.continue_()
            return

        # БЛОКИРОВКА: Жестко режем Метрику на поиске и сайтах
        if "mc.yandex" in url or "metrika.yandex" in url:
            await route.abort()
            return

        await route.continue_()

    if context:
        await context.route("**/*", block_network)
        await context.add_init_script(METRIKA_JS_BLOCK)
    else:
        await page.route("**/*", block_network)
        await page.add_init_script(METRIKA_JS_BLOCK)
