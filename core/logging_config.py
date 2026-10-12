# -*- coding: utf-8 -*-
"""
core.logging_config
پیکربندی هوشمند و چند تردی سیستم ثبت رویدادها (Logging System)
شامل ثبت در فایل چرخشی با رمزگذاری UTF-8 و نمایش رنگی در ترمینال‌های استاندارد
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional, Union

# دریافت مسیر ذخیره‌سازی از پیکربندی مرکزی سیستم
try:
    from config import LOG_FILENAME, get_log_dir
except ImportError:
    LOG_FILENAME = "app.log"
    def get_log_dir() -> Path:
        return Path(__file__).resolve().parent.parent / "logs"

# ثابت‌های پیش‌فرض
DEFAULT_MAX_BYTES = 10 * 1024 * 1024  # ۱۰ مگابایت
DEFAULT_BACKUP_COUNT = 5
DEFAULT_CONSOLE_LEVEL = logging.INFO
DEFAULT_FILE_LEVEL = logging.DEBUG

# الگوهای ساختار لاگ (Logging Formatters)
CONSOLE_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
FILE_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(funcName)s:%(lineno)d | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class _ColoredFormatter(logging.Formatter):
    """فرمت‌دهنده رنگی پیشرفته و ایمن برای ترمینال‌های دارای استاندارد ANSI."""

    COLORS = {
        logging.DEBUG: "\033[36m",      # فیروزه‌ای
        logging.INFO: "\033[32m",       # سبز
        logging.WARNING: "\033[33m",    # زرد
        logging.ERROR: "\033[31m",      # قرمز
        logging.CRITICAL: "\033[1;31m"  # قرمز پررنگ بولد
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        # کپی موقت از فیلد لول برای ممانعت از آلوده شدن لاگ‌ فایل به کدهای رنگی ترمینال
        if not getattr(self, "use_colors", False):
            return super().format(record)

        color = self.COLORS.get(record.levelno, self.RESET)
        original_levelname = record.levelname
        record.levelname = f"{color}{original_levelname}{self.RESET}"
        try:
            return super().format(record)
        finally:
            # بازگرداندن مقدار اصلی جهت ممانعت از تداخل در بقیه هندلرها
            record.levelname = original_levelname


def setup_logging(
    level: int = DEFAULT_CONSOLE_LEVEL,
    log_dir: Optional[Union[str, Path]] = None,
    log_file: str = LOG_FILENAME,
    console_level: Optional[int] = None,
    file_level: Optional[int] = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
    backup_count: int = DEFAULT_BACKUP_COUNT,
    use_colors: bool = True,
    force_reset: bool = False,
) -> logging.Logger:
    """
    راه‌اندازی و کانفیگ سراسری سیستم ثبت رویدادهای نرم‌افزار.

    Args:
        level: سطح لاگ پیش‌فرض برای نمایش در کنسول
        log_dir: مسیر دایرکتوری ذخیره فایل‌ها (در صورت None بودن از config خوانده می‌شود)
        log_file: نام فایل لاگ خروجی
        console_level: سطح اختصاصی کنسول
        file_level: سطح اختصاصی فایل متنی
        max_bytes: آستانه چرخش فایل لاگ (بایت)
        backup_count: تعداد سوابق پشتیبان نگهداری شده
        use_colors: تایید قابلیت رنگی‌سازی در ترمینال کلاینت
        force_reset: ریست و ساخت مجدد کامل هندلرها

    Returns:
        نمونه روت لاگر (Root Logger)
    """
    if console_level is None:
        console_level = level
    if file_level is None:
        file_level = DEFAULT_FILE_LEVEL

    root_logger = logging.getLogger()
    # روت لاگر را روی پایین‌ترین سطح می‌گذاریم تا هندلرها خودشان فیلتر نهایی کنند
    root_logger.setLevel(logging.DEBUG)

    # بررسی و ریست هندلرهای قدیمی جهت جلوگیری از قفل شدن یا تکرار لاگ‌ها
    if force_reset:
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
            handler.close()
    else:
        if any(
            isinstance(h, logging.StreamHandler) and getattr(h, "name", "") == "console"
            for h in root_logger.handlers
        ):
            return root_logger

    # ── ۱. ساخت هندلر کنسول (محیط ترمینال) ──
    # در محیط‌های بسته‌بندی شده ویندوزی فاقد کنسول، sys.stdout ممکن است None باشد
    if sys.stdout is not None:
        try:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(console_level)
            console_formatter = _ColoredFormatter(CONSOLE_FORMAT, datefmt=DATE_FORMAT)
            
            # فعال‌سازی رنگ فقط در ترمینال‌های دارای استاندارد تعاملی tty
            console_formatter.use_colors = (
                use_colors and hasattr(sys.stdout, "isatty") and sys.stdout.isatty()
            )
            console_handler.setFormatter(console_formatter)
            console_handler.name = "console"
            root_logger.addHandler(console_handler)
        except Exception as exc:
            # نادیده گرفتن شکست در راه‌اندازی کنسول در سیستم‌عامل‌های فاقد Shell
            logger.warning("Console logging initialization bypassed: %s", exc)

    # ── ۲. ساخت هندلر فایل چرخشی با کارایی بالا (Rotating File Handler) ──
    if log_dir is None:
        log_dir = get_log_dir()
    else:
        log_dir = Path(log_dir)

    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / log_file

        file_handler = RotatingFileHandler(
            str(log_path),
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(file_level)
        file_formatter = logging.Formatter(FILE_FORMAT, datefmt=DATE_FORMAT)
        file_handler.setFormatter(file_formatter)
        file_handler.name = "file"
        root_logger.addHandler(file_handler)
    except Exception as exc:
        # مکانیزم امنیتی Fallback: در صورت عدم امکان دسترسی به دیسک، لاگ‌ فایل غیرفعال می‌شود اما برنامه کرش نمی‌کند
        sys.stderr.write(f"CRITICAL: Failed to initialize file logger. Entering Console-Only mode. Error: {exc}\n")

    # ── ۳. آرام‌سازی و فیلتر کردن لاگ‌های کتابخانه‌های شلوغ جانبی ──
    logging.getLogger("matplotlib").setLevel(logging.WARNING)
    logging.getLogger("PIL").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    return root_logger


def get_logger(name: str) -> logging.Logger:
    """دریافت یک نمونه لاگر با نام مشخص (ترجیحاً __name__ ماژول)."""
    return logging.getLogger(name)


def basic_setup(level: int = logging.INFO) -> logging.Logger:
    """راه‌اندازی ساده و سریع سیستم با مشخصات پیش‌فرض."""
    return setup_logging(level=level)