# -*- coding: utf-8 -*-
"""
main
نقطه ورود اصلی و راه‌انداز سامانه Document & MOM Tracking System
تسهیل فرآیند بوت، هماهنگ با اسپلش اسکرین پیشرفته، سیستم مانیتورینگ قفل و هماهنگی تم
"""
from __future__ import annotations

from typing import Optional

import logging
import os
import sys
from argparse import ArgumentParser

from PyQt6.QtCore import QLockFile, QSettings, Qt
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QApplication, QMessageBox

from config import APP_NAME, ORG_NAME
from core.logging_config import setup_logging
from db.manager import DatabaseManager

logger = logging.getLogger(__name__)


def _get_default_db_path() -> str:
    """محاسبه آدرس فیزیکی پیش‌فرض دیتابیس برنامه در مسیر فایل اجرایی."""
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
    else:
        exe_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(exe_dir, "meetings.db")


def _parse_arguments() -> Optional[str]:
    """پارس آرگومان‌های خط فرمان جهت دریافت مسیر دیتابیس سفارشی."""
    parser = ArgumentParser(description="Document & MOM Tracking System")
    parser.add_argument(
        "--db", "--database",
        dest="db_path",
        help="مسیر دلخواه فایل دیتابیس SQLite (.db)",
        default=None,
    )
    args, _ = parser.parse_known_args()
    return args.db_path


def _setup_application_metadata() -> None:
    """ثبت متادیتای هویتی برنامه در هسته Qt برای کارکرد صحیح QSettings."""
    QApplication.setOrganizationName(ORG_NAME)
    QApplication.setApplicationName(APP_NAME)
    
    try:
        from config import APP_VERSION
        QApplication.setApplicationVersion(APP_VERSION)
    except ImportError:
        QApplication.setApplicationVersion("3.0")


def _add_file_log_handler() -> None:
    """افزودن لاگر چرخشی فایل برای ذخیره خطاها در پوشه logs."""
    try:
        import logging.handlers
        log_dir = "logs"
        os.makedirs(log_dir, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            os.path.join(log_dir, "app.log"),
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.WARNING)
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(funcName)s:%(lineno)d | %(message)s"
        )
        file_handler.setFormatter(formatter)
        logging.getLogger().addHandler(file_handler)
    except Exception as exc:
        logger.warning("Could not instantiate file logger: %s", exc)


def main() -> int:
    """تابع اصلی راه‌اندازی و بوت فریم‌ورک نرم‌افزار."""
    # ۱. پیکربندی سیستم ثبت رویدادها (Logging)
    setup_logging(logging.INFO)
    _add_file_log_handler()

    # ۲. اعمال بهینه‌سازی‌های High-DPI پیش از ساخت QApplication
    try:
        QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
    except AttributeError:
        pass

    try:
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)
    except AttributeError:
        pass

    # ۳. نمونه‌سازی موتور اصلی برنامه Qt
    app = QApplication(sys.argv)
    app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

    # ۴. ساخت و نمایش اسپلش اسکرین ارتقا یافته با نوار پیشرفت (۱۰٪)
    from ui.splash import AppSplash
    splash = AppSplash()
    splash.show()
    splash.message("در حال مقداردهی اولیه فریم‌ورک سامانه…", progress=10)

    _setup_metadata_settings = QSettings(ORG_NAME, APP_NAME)
    _setup_application_metadata()

    # ۵. محاسبه مسیر فیزیکی دیتابیس (پشتیبانی از آرگومان ترمینال یا تنظیمات ذخیره شده)
    cmd_db_path = _parse_arguments()
    if cmd_db_path:
        db_path = cmd_db_path.strip()
        if not os.path.isabs(db_path):
            db_path = os.path.abspath(db_path)
    else:
        settings = QSettings()
        db_path = str(settings.value("db_path", "", type=str) or "").strip()
        if not db_path or not os.path.isabs(db_path):
            db_path = _get_default_db_path()

    db_dir = os.path.dirname(db_path)

    # ایجاد پوشه والد دیتابیس در صورت عدم وجود (۳۰٪)
    splash.message("پیکربندی ساختار فایل‌های سیستمی…", progress=30)
    if db_dir and not os.path.exists(db_dir):
        try:
            os.makedirs(db_dir, exist_ok=True)
        except Exception as exc:
            splash.close()
            logger.critical("Failed to create database directory structure: %s", exc)
            QMessageBox.critical(
                None,
                "خطای سیستم فایل",
                f"ایجاد پوشه دیتابیس نرم‌افزار در مسیر زیر ممکن نشد:\n{db_dir}\n\nخطا: {exc}"
            )
            return 1

    # ۶. سیستم مانیتورینگ قفل تک‌نسخه‌ای (Single Instance Monitor) - (۵۰٪)
    splash.message("بررسی اجرای همزمان نرم‌افزار (Single Instance)…", progress=50)
    lock = QLockFile(os.path.join(db_dir or ".", "app.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        splash.close()
        QMessageBox.warning(
            None,
            "سامانه در حال اجرا است",
            "یک نسخه دیگر از برنامه Document & MOM Tracking System هم‌اکنون در حال اجرا می‌باشد.\n\n"
            "لطفاً پنجره قبلی را ببندید یا از نوار ابزار سیستم به آن مراجعه کنید."
        )
        return 0

    # ذخیره مسیر نهایی و استاندارد دیتابیس در تنظیمات
    settings = QSettings()
    settings.setValue("db_path", db_path)

    # ۷. همگام‌سازی تم بصری قبل از لود دیالوگ ورود (۷۰٪)
    splash.message("بارگذاری تنظیمات ظاهری و تم انتخابی…", progress=70)
    try:
        from ui.styles import apply_theme
        dark_mode = settings.value("dark_mode", False, type=bool)
        apply_theme(app, dark_mode=dark_mode)
    except ImportError:
        logger.warning("Custom styles module not found; using fallback visual engine.")

    # ۸. اتصال امن به موتور پایگاه داده SQLite و بررسی مایگریشن‌ها (۹۰٪)
    splash.message("برقراری اتصال امن با پایگاه داده…", progress=90)
    try:
        db = DatabaseManager(db_path)
    except Exception as exc:
        splash.close()
        lock.unlock()
        logger.exception("Failed to connect to database at path: %s", db_path)
        QMessageBox.critical(
            None,
            "خطای اتصال به دیتابیس",
            f"اتصال به دیتابیس SQLite با شکست مواجه شد:\n{exc}\n\n"
            "لطفاً دسترسی فیزیکی به دیتابیس و سالم بودن فایل را بررسی کنید."
        )
        return 1

    # ۹. پایان فرآیند راه‌اندازی و بستن اسپلش اسکرین (۱۰۰٪)
    splash.message("راه‌اندازی با موفقیت انجام شد.", progress=100)
    splash.close()

    # ۱۰. نمایش پنجره ورود کارشناسان (Login Screen)
    from ui.login_dialog import LoginDialog
    login = LoginDialog(db)
    if login.exec() != LoginDialog.DialogCode.Accepted or not login.session:
        lock.unlock()
        return 0

    # ۱۱. راه‌اندازی پنجره اصلی نرم‌افزار با دسترسی اختصاصی کارشناس لاگین شده
    from ui.main_window import MainWindow
    win = MainWindow(db, login.session)
    win.showMaximized()

    # اجرای حلقه رویدادهای اصلی سیستم عامل
    exit_code = app.exec()

    # آزادسازی قفل سخت‌افزاری و پایان برنامه
    lock.unlock()
    return exit_code


if __name__ == "__main__":
    # جلوگیری از ایجاد استثناهای بیهوده در پایان اجرا
    raise SystemExit(main())
