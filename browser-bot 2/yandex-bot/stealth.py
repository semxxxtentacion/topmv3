"""
Anti-detection JavaScript injections for Playwright.
Applies real fingerprint data from the profile DB instead of random values.
"""

import json

# Base patches that always apply (hiding automation signals)
_BASE_JS = """
(() => {
    // --- Hide webdriver flag ---
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

    // --- Chrome runtime ---
    if (!window.chrome) {
        window.chrome = { runtime: {} };
    }

    // --- Permissions API ---
    const origPermQuery = navigator.permissions.query.bind(navigator.permissions);
    navigator.permissions.query = (params) => {
        if (params.name === 'notifications') {
            return Promise.resolve({ state: Notification.permission });
        }
        return origPermQuery(params);
    };

    // --- Plugins (non-empty) ---
    Object.defineProperty(navigator, 'plugins', {
        get: () => {
            const arr = [
                { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format', length: 1 },
                { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '', length: 1 },
                { name: 'Native Client', filename: 'internal-nacl-plugin', description: '', length: 1 },
            ];
            arr.refresh = () => {};
            try { Object.setPrototypeOf(arr, PluginArray.prototype); } catch(e) {}
            return arr;
        },
    });

    // --- Canvas fingerprint noise (unique per profile via seed) ---
    const _seed = CANVAS_SEED;
    const origToDataURL = HTMLCanvasElement.prototype.toDataURL;
    const origToBlob    = HTMLCanvasElement.prototype.toBlob;
    HTMLCanvasElement.prototype.toDataURL = function() {
        const ctx = this.getContext('2d');
        if (ctx && this.width > 0 && this.height > 0) {
            try {
                const d = ctx.getImageData(0, 0, Math.min(this.width, 16), Math.min(this.height, 16));
                for (let i = 0; i < d.data.length; i += 97) d.data[i] = d.data[i] ^ (_seed & 0xFF);
                ctx.putImageData(d, 0, 0);
            } catch(e) {}
        }
        return origToDataURL.apply(this, arguments);
    };
    HTMLCanvasElement.prototype.toBlob = function() {
        const ctx = this.getContext('2d');
        if (ctx && this.width > 0 && this.height > 0) {
            try {
                const d = ctx.getImageData(0, 0, Math.min(this.width, 16), Math.min(this.height, 16));
                for (let i = 0; i < d.data.length; i += 97) d.data[i] = d.data[i] ^ (_seed & 0xFF);
                ctx.putImageData(d, 0, 0);
            } catch(e) {}
        }
        return origToBlob.apply(this, arguments);
    };

    // --- Iframe contentWindow.chrome ---
    try {
        const desc = Object.getOwnPropertyDescriptor(HTMLIFrameElement.prototype, 'contentWindow');
        if (desc && desc.get) {
            Object.defineProperty(HTMLIFrameElement.prototype, 'contentWindow', {
                get: function() {
                    const w = desc.get.call(this);
                    if (w && !w.chrome) try { w.chrome = window.chrome; } catch(e) {}
                    return w;
                }
            });
        }
    } catch(e) {}

    // --- Connection rtt ---
    if (navigator.connection) {
        try { Object.defineProperty(navigator.connection, 'rtt', { get: () => CONNECTION_RTT }); } catch(e) {}
    }

    // --- Mouse tracking ---
    window.__mouseX = 0;
    window.__mouseY = 0;
    document.addEventListener('mousemove', e => {
        window.__mouseX = e.clientX;
        window.__mouseY = e.clientY;
    }, { passive: true });
})();
"""

# Profile-specific overrides — values injected from fingerprints JSON
_PROFILE_JS = """
(() => {
    const FP = FINGERPRINT_JSON;

    // --- navigator overrides ---
    const nav = FP.navigator || FP;

    const navProps = {
        'platform':             nav.platform,
        'hardwareConcurrency':  nav.hardwareConcurrency || nav.hardware_concurrency,
        'deviceMemory':         nav.deviceMemory || nav.device_memory,
        'maxTouchPoints':       nav.maxTouchPoints ?? nav.max_touch_points ?? 0,
        'doNotTrack':           nav.doNotTrack ?? nav.do_not_track ?? null,
    };
    for (const [key, val] of Object.entries(navProps)) {
        if (val !== undefined && val !== null) {
            try { Object.defineProperty(navigator, key, { get: () => val }); } catch(e) {}
        }
    }

    // Languages
    const langs = nav.languages || nav.language
        ? (Array.isArray(nav.languages) ? nav.languages : [nav.language || 'ru-RU', 'ru', 'en-US', 'en'])
        : ['ru-RU', 'ru', 'en-US', 'en'];
    Object.defineProperty(navigator, 'languages', { get: () => langs });
    if (langs[0]) {
        Object.defineProperty(navigator, 'language', { get: () => langs[0] });
    }

    // --- Screen overrides ---
    const scr = FP.screen || FP;
    const scrProps = {
        'width':       scr.screen_width  || scr.screenWidth  || scr.width,
        'height':      scr.screen_height || scr.screenHeight || scr.height,
        'colorDepth':  scr.colorDepth    || scr.color_depth  || 24,
        'pixelDepth':  scr.pixelDepth    || scr.pixel_depth  || 24,
    };
    for (const [key, val] of Object.entries(scrProps)) {
        if (val) {
            try { Object.defineProperty(screen, key, { get: () => val }); } catch(e) {}
        }
    }
    if (scrProps.width) {
        try {
            Object.defineProperty(screen, 'availWidth',  { get: () => scrProps.width });
            Object.defineProperty(screen, 'availHeight', { get: () => (scrProps.height || 1080) - 40 });
        } catch(e) {}
    }

    // --- WebGL ---
    const gl = FP.webgl || FP;
    const glVendor   = gl.webgl_vendor   || gl.vendor   || gl.unmaskedVendor;
    const glRenderer = gl.webgl_renderer || gl.renderer || gl.unmaskedRenderer;
    if (glVendor || glRenderer) {
        function patchGL(proto) {
            const orig = proto.getParameter;
            proto.getParameter = function(p) {
                if (p === 37445 && glVendor)   return glVendor;
                if (p === 37446 && glRenderer) return glRenderer;
                return orig.call(this, p);
            };
        }
        if (typeof WebGLRenderingContext  !== 'undefined') patchGL(WebGLRenderingContext.prototype);
        if (typeof WebGL2RenderingContext !== 'undefined') patchGL(WebGL2RenderingContext.prototype);
    }

    // --- AudioContext ---
    const audio = FP.audio || FP.audioContext;
    if (audio && audio.noise !== undefined) {
        const noise = audio.noise;
        const origGetFloat = AnalyserNode.prototype.getFloatFrequencyData;
        AnalyserNode.prototype.getFloatFrequencyData = function(array) {
            origGetFloat.call(this, array);
            for (let i = 0; i < array.length; i++) array[i] += noise;
        };
    }

    // --- Fonts ---
    const fonts = FP.fonts;
    if (Array.isArray(fonts) && fonts.length > 0) {
        const fontSet = new Set(fonts.map(f => f.toLowerCase()));
        const origCheck = document.fonts.check.bind(document.fonts);
        document.fonts.check = function(font, text) {
            const family = font.replace(/^[\\d.]+[a-z]+\\s+/i, '').replace(/['"]/g, '').trim().toLowerCase();
            if (fontSet.has(family)) return true;
            return origCheck(font, text);
        };
    }
})();
"""


def _canvas_seed_from_pid(pid) -> int:
    """Deterministic seed per profile so canvas noise is consistent."""
    if pid is None:
        import random
        return random.randint(1, 255)
    return (hash(str(pid)) & 0xFFFFFFFF) % 255 + 1


def build_stealth_js(profile: dict) -> str:
    """
    Build complete stealth JS from a profile dict.
    Uses real values from fingerprints/cookies/platform fields.
    """
    pid = profile.get('pid')
    fp = profile.get('fingerprints')
    if not isinstance(fp, dict):
        fp = {}

    # Merge top-level profile fields into fingerprints for JS access
    merged = dict(fp)
    if 'platform' not in merged and profile.get('platform'):
        merged['platform'] = profile['platform']
    if not merged.get('hardwareConcurrency') and not merged.get('hardware_concurrency'):
        merged['hardware_concurrency'] = 4

    canvas_seed = _canvas_seed_from_pid(pid)
    rtt = 50 + (canvas_seed * 3) % 150

    base = _BASE_JS.replace('CANVAS_SEED', str(canvas_seed)).replace('CONNECTION_RTT', str(rtt))
    profile_js = _PROFILE_JS.replace('FINGERPRINT_JSON', json.dumps(merged, ensure_ascii=False))

    return base + '\n' + profile_js
