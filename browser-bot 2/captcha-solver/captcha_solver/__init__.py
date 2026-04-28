"""Yandex SmartCaptcha solver — click and coordinate variants via 2Captcha."""

from captcha_solver.solver import CaptchaSolver, SolveResult, CaptchaType
from captcha_solver.config import Settings, get_settings

__all__ = ["CaptchaSolver", "SolveResult", "CaptchaType", "Settings", "get_settings"]
__version__ = "0.1.0"
