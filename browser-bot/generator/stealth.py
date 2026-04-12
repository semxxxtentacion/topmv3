"""
Stealth JavaScript injection for Playwright.
Patches browser APIs to avoid automation detection.
Adapted for DESKTOP profiles.
"""

from __future__ import annotations


def build_stealth_js(profile: dict) -> str:
    """Build stealth JS that patches navigator, WebGL, canvas, etc."""
    fp = profile.get("fingerprints", {})
    nav = fp.get("navigator", {})
    screen = fp.get("screen", {})
    webgl = fp.get("webgl", {})
    audio = fp.get("audio", {})
    canvas_seed = fp.get("canvas_seed", 0)
    battery = fp.get("battery", {})
    fonts = fp.get("fonts", [])

    # Берем реальную ОС из корня профиля (Windows или macOS)
    os_name = profile.get("platform", "Windows")

    ua = nav.get("userAgent", "")
    platform = nav.get("platform", "Win32") # По умолчанию десктоп
    hw_concurrency = nav.get("hardwareConcurrency", 8)
    device_memory = nav.get("deviceMemory", 8)
    languages = nav.get("languages", ["ru-RU", "ru", "en-US", "en"])
    max_touch = nav.get("maxTouchPoints", 0) # Десктоп = 0

    webgl_vendor = webgl.get("vendor", "Google Inc. (NVIDIA)")
    webgl_renderer = webgl.get("renderer", "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_11_0, D3D11)")

    audio_noise = audio.get("noise", 0.0001)

    screen_w = screen.get("width", 1920)
    screen_h = screen.get("height", 1080)
    color_depth = screen.get("colorDepth", 24)

    battery_charging = "true" if battery.get("charging", True) else "false"
    battery_level = battery.get("level", 1.0)
    battery_discharge_raw = battery.get("dischargingTime")
    battery_discharge = "Infinity" if battery_discharge_raw is None else battery_discharge_raw

    fonts_js = ", ".join(f'"{f}"' for f in fonts) if fonts else ""

    return f"""
(() => {{
    // --- Navigator ---
    const navProps = {{
        webdriver: {{ get: () => undefined }},
        hardwareConcurrency: {{ get: () => {hw_concurrency} }},
        deviceMemory: {{ get: () => {device_memory} }},
        platform: {{ get: () => "{platform}" }},
        maxTouchPoints: {{ get: () => {max_touch} }},
        languages: {{ get: () => {languages} }},
    }};
    for (const [key, desc] of Object.entries(navProps)) {{
        try {{ Object.defineProperty(navigator, key, desc); }} catch(e) {{}}
    }}

    // Remove webdriver traces
    delete navigator.__proto__.webdriver;

    // --- Chrome object ---
    if (!window.chrome) {{
        window.chrome = {{ runtime: {{}} }};
    }}

    // --- Client Hints (userAgentData) Masking ---
    // Критически важно для подмены ОС (Mac -> Win или Win -> Mac)
    if (navigator.userAgentData) {{
        Object.defineProperty(navigator.userAgentData, 'platform', {{
            get: () => "{os_name}"
        }});
        Object.defineProperty(navigator.userAgentData, 'mobile', {{
            get: () => false
        }});
    }}

    // --- Permissions ---
    const originalQuery = window.navigator.permissions?.query;
    if (originalQuery) {{
        window.navigator.permissions.query = (params) => {{
            if (params.name === 'notifications') {{
                return Promise.resolve({{ state: Notification.permission }});
            }}
            return originalQuery(params);
        }};
    }}

    // --- WebGL ---
    const getParamOrig = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(param) {{
        if (param === 37445) return "{webgl_vendor}";
        if (param === 37446) return "{webgl_renderer}";
        return getParamOrig.call(this, param);
    }};
    const getParamOrig2 = WebGL2RenderingContext.prototype.getParameter;
    WebGL2RenderingContext.prototype.getParameter = function(param) {{
        if (param === 37445) return "{webgl_vendor}";
        if (param === 37446) return "{webgl_renderer}";
        return getParamOrig2.call(this, param);
    }};

    // --- Canvas fingerprint noise ---
    const origToBlob = HTMLCanvasElement.prototype.toBlob;
    const origToDataURL = HTMLCanvasElement.prototype.toDataURL;
    const seed = {canvas_seed};

    function noiseCanvas(canvas) {{
        try {{
            const ctx = canvas.getContext('2d');
            if (!ctx) return;
            const img = ctx.getImageData(0, 0, canvas.width, canvas.height);
            const d = img.data;
            for (let i = 0; i < d.length; i += 4) {{
                d[i] = d[i] ^ ((seed + i) & 1);
            }}
            ctx.putImageData(img, 0, 0);
        }} catch(e) {{}}
    }}

    HTMLCanvasElement.prototype.toBlob = function(...args) {{
        noiseCanvas(this);
        return origToBlob.apply(this, args);
    }};
    HTMLCanvasElement.prototype.toDataURL = function(...args) {{
        noiseCanvas(this);
        return origToDataURL.apply(this, args);
    }};

    // --- Screen ---
    const screenProps = {{
        width: {{ get: () => {screen_w} }},
        height: {{ get: () => {screen_h} }},
        availWidth: {{ get: () => {screen_w} }},
        availHeight: {{ get: () => {screen_h - 40} }}, // Минус таскбар
        colorDepth: {{ get: () => {color_depth} }},
        pixelDepth: {{ get: () => {color_depth} }},
    }};
    for (const [key, desc] of Object.entries(screenProps)) {{
        try {{ Object.defineProperty(screen, key, desc); }} catch(e) {{}}
    }}

    // --- AudioContext fingerprint noise ---
    const origGetChannelData = AudioBuffer.prototype.getChannelData;
    AudioBuffer.prototype.getChannelData = function(channel) {{
        const data = origGetChannelData.call(this, channel);
        if (!this._noised) {{
            for (let i = 0; i < data.length; i++) {{
                data[i] += {audio_noise} * (Math.random() * 2 - 1);
            }}
            this._noised = true;
        }}
        return data;
    }};

    // --- Battery API ---
    if (navigator.getBattery) {{
        navigator.getBattery = () => Promise.resolve({{
            charging: {battery_charging},
            chargingTime: {battery_charging} ? 0 : Infinity,
            dischargingTime: {battery_discharge},
            level: {battery_level},
            addEventListener: () => {{}},
            removeEventListener: () => {{}},
        }});
    }}

    // --- ВНИМАНИЕ: Блок с подменой plugins и mimeTypes УДАЛЕН ---
    // Теперь браузер будет отдавать свои настоящие десктопные плагины,
    // что кардинально повышает траст профиля.

    // --- Automation flags ---
    const automationProps = [
        'callPhantom', '_phantom', '__nightmare', 'buffer',
        'emit', 'spawn', 'domAutomation', 'domAutomationController',
        'webdriver', '_Selenium_IDE_Recorder', '_selenium',
        'callSelenium', '__webdriver_script_fn',
    ];
    for (const prop of automationProps) {{
        try {{ delete window[prop]; }} catch(e) {{}}
    }}
}})();
"""
