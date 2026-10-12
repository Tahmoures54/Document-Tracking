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
APP_VERSION = "3.0.0"

LOG_FILENAME = "app.log"
DB_FILENAME = "meetings.db"
LOCK_FILENAME = "app.lock"
BACKUP_PREFIX = "backup_meetings"

# ─────────────────────────────────────────────
# تنظیمات اسکن شبکه و فایل‌های مدارک
# ─────────────────────────────────────────────
DEFAULT_SCAN_PATH = r"\\192.168.200.6\technical office\_MOM\_Scan"
SCAN_FILE_EXTENSIONS: Tuple[str, ...] = (
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".tif",
    ".tiff",
)

# ─────────────────────────────────────────────
# تنظیمات صفحه‌بندی و کنترل‌های UI
# ─────────────────────────────────────────────
DEFAULT_PAGE_SIZE = 500
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
    ADMIN = "admin"        # مدیر ارشد سامانه (دسترسی کامل)
    MANAGER = "manager"    # مدیر پروژه / واحد
    EDITOR = "editor"      # کارشناس / ویرایشگر صورتجلسات
    USER = "user"          # کاربر استاندارد
    VIEWER = "viewer"      # مشاهده‌گر صرف (فقط خواندنی)

    def __str__(self) -> str:
        return self.value

    @classmethod
    def from_string(cls, role_str: str, default: Optional[Roles] = None) -> Roles:
        """
        تبدیل امن رشته به عضو Enum با امکان تعیین مقدار پیش‌فرض در صورت خطا.
        """
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
        """لیست مقادیر رشته‌ای تمام نقش‌ها."""
        return [role.value for role in cls]

    @classmethod
    def display_names(cls) -> List[Tuple[str, str]]:
        """لیست تاپل‌های (عنوان فارسی، مقدار شناسه) جهت استفاده در کمبوباکس‌ها."""
        mapping = {
            cls.ADMIN: "مدیر سیستم (دسترسی کامل)",
            cls.MANAGER: "مدیر پروژه / واحد",
            cls.EDITOR: "کارشناس و ویرایشگر",
            cls.USER: "کاربر استاندارد",
            cls.VIEWER: "مشاهده‌گر (فقط خواندنی)",
        }
        return [(mapping.get(role, role.value), role.value) for role in cls]


# ─────────────────────────────────────────────
# توابع استاندارد مسیردهی (Path Utilities)
# ─────────────────────────────────────────────
def get_app_dir() -> Path:
    """
    دریافت مسیر ریشه برنامه.
    سازگار با حالت اجرایی معمولی و بسته‌بندی‌شده (PyInstaller Frozen).
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def get_log_dir() -> Path:
    """دریافت و ایجاد خودکار پوشه لاگ‌ها."""
    log_dir = get_app_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def get_attachments_dir() -> Path:
    """دریافت و ایجاد خودکار پوشه ذخیره‌سازی پیوست‌ها."""
    att_dir = get_app_dir() / "attachments"
    att_dir.mkdir(parents=True, exist_ok=True)
    return att_dir


def get_default_db_path() -> Path:
    """دریافت مسیر کامل فایل پیش‌فرض دیتابیس SQLite."""
    return get_app_dir() / DB_FILENAME


def get_default_db_path_str() -> str:
    """دریافت مسیر رشته‌ای فایل پیش‌فرض دیتابیس (جهت سازگاری با توابع C/Qt)."""
    return str(get_default_db_path())