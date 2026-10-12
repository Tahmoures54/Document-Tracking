# -*- coding: utf-8 -*-
"""
Alias module: ui.style  →  ui.styles
پل سازگاری برای importهای قدیمی که از `ui.style` استفاده می‌کنند.

منبع اصلی: `ui.styles` (نسخه بهسازی‌شده با قالب Template).
این ماژول نباید هیچ منطقی اضافه کند — فقط re-export خالص.
"""
from __future__ import annotations

from ui.styles import *  # noqa: F401,F403
from ui.styles import __all__ as _styles_all  # noqa: F401

# صریح‌سازی API عمومی این alias برای ابزارهای IDE و type-checkerها
__all__ = list(_styles_all)
