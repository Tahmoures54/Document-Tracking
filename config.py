# -*- coding: utf-8 -*-
"""
config
پیکربندی مرکزی و ثابت‌های سراسری سامانه Document & MOM Tracking System
مدیریت نقش‌ها، مسیرها، پارامترهای اسکن و تنظیمات رابط کاربری
"""
from __future__ import annotations

import os
import sys
from enum import Enum
from pathlib import Path
from typing import List, Optional, Set, Tuple

# ─────────────────────────────────────────────
# متادیتا و هویت سامانه (Application Metadata)
# ─────────────────────────────────────────────
ORG_NAME = "Document & MOM Tracking System"
APP_NAME = "Document & MOM Tracking System"
APP_TITLE_FA = "سامانه جامع مدیریت و پیگیری صورتجلسات و اسناد"
APP_VERSION = "3.0.2"

LOG_FILENAME = "app.log"
DB_FILENAME = "meetings.db"
LOCK_FILENAME = "app.lock"
BACKUP_PREFIX = "backup_meetings"

# ─────────────────────────────────────────────
# تنظیمات اسکن شبکه و فایل‌های مدارک
# ─────────────────────────────────────────────
_DEFAULT_SCAN = r"\\192.168.200.6\technical office\_MOM\_Scan"
DEFAULT_SCAN_PATH = os.environ.get("MOM_SCAN_PATH", _DEFAULT_SCAN).strip() or _DEFAULT_SCAN

SCAN_FILE_EXTENSIONS: Tuple[str, ...] = (
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".tif",
    ".tiff",
)

def get_scan_path() -> str:
    """
    دریافت مسیر فعلی اسکن.
    اولویت: متغیر محیطی MOM_SCAN_PATH > تنظیمات ذخیره شده > مقدار پیش‌فرض.
    """
    env = os.environ.get("MOM_SCAN_PATH", "").strip()
    if env:
        return env
    try:
        from PyQt6.QtCore import QSettings
        settings = QSettings(ORG_NAME, APP_NAME)
        saved = str(settings.value("scan_path", "", type=str) or "").strip()
        if saved:
            return saved
    except Exception:
        pass
    return DEFAULT_SCAN_PATH

# ─────────────────────────────────────────────
# تنظیمات صفحه‌بندی و کنترل‌های UI
# ─────────────────────────────────────────────
# اندازه پیش‌فرض صفحه: ۱۰۰ (قبلاً ۵۰۰) — بارگذاری و رندر جدول سریع‌تر
DEFAULT_PAGE_SIZE = 100
PAGE_SIZE_OPTIONS: List[int] = [25, 50, 100, 250, 500]

SEARCH_DEBOUNCE_MS = 300
DB_LED_INTERVAL_MS = 700
ALERT_DELAY_MS = 1200
STATS_REFRESH_INTERVAL_MS = 60_000
DASHBOARD_REFRESH_INTERVAL_MS = 30_000

# ─────────────────────────────────────────────
# فرمت‌های نمایش و ذخیره‌سازی تاریخ
# ─────────────────────────────────────────────
DATE_DISPLAY_FORMAT = "yyyy/MM/dd"
DATE_DB_FORMAT = "yyyy-MM-dd"
TIME_DISPLAY_FORMAT = "HH:mm:ss"
DATETIME_LOG_FORMAT = "%Y-%m-%d %H:%M:%S"


# ─────────────────────────────────────────────
# نقش‌های کاربری و سطوح دسترسی (Roles & Permissions)
# ─────────────────────────────────────────────
class Roles(Enum):
    """نقش‌های کاربری در سطح سامانه."""
    ADMIN = "admin"
    MANAGER = "manager"
    EDITOR = "editor"
    USER = "user"
    VIEWER = "viewer"

    def __str__(self) -> str:
        return self.value

    @classmethod
    def from_string(cls, role_str: str, default: Optional["Roles"] = None) -> "Roles":
        fallback = default if default is not None else cls.VIEWER
        if not role_str:
            return fallback
        target = str(role_str).strip().lower()
        for role in cls:
            if role.value.lower() == target:
                return role
        return fallback

    @classmethod
    def values(cls) -> List[str]:
        return [role.value for role in cls]

    @classmethod
    def display_names(cls) -> List[Tuple[str, str]]:
        mapping = {
            cls.ADMIN: "مدیر سیستم (دسترسی کامل)",
            cls.MANAGER: "مدیر پروژه / واحد",
            cls.EDITOR: "کارشناس و ویرایشگر",
            cls.USER: "کاربر استاندارد",
            cls.VIEWER: "مشاهده‌گر (فقط خواندنی)",
        }
        return [(mapping.get(role, role.value), role.value) for role in cls]


def get_app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def get_log_dir() -> Path:
    log_dir = get_app_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def get_attachments_dir() -> Path:
    att_dir = get_app_dir() / "attachments"
    att_dir.mkdir(parents=True, exist_ok=True)
    return att_dir


def get_default_db_path() -> Path:
    return get_app_dir() / DB_FILENAME


def get_default_db_path_str() -> str:
    return str(get_default_db_path())
