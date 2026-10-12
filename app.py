# -*- coding: utf-8 -*-
"""راه‌اندازی برنامه دسکتاپ Document & MOM Tracking System."""
from __future__ import annotations
import logging
import logging.handlers
import os
import sys
from argparse import ArgumentParser
from typing import Optional
from PyQt6.QtCore import QLockFile, QSettings, QStandardPaths, Qt
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QApplication, QMessageBox
from config import APP_NAME, ORG_NAME
from core.logging_config import setup_logging
from db.manager import DatabaseManager
logger = logging.getLogger(__name__)

def _local_data_dir() -> str:
    """داده‌های محلی کاربر؛ مستقل از دیتابیس مشترک شبکه."""
    path = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)
    if not path:
        path = os.path.join(os.path.expanduser("~"), ".document_tracking")
    os.makedirs(path, exist_ok=True)
    return path

def _get_default_db_path() -> str:
    return os.path.join(_local_data_dir(), "meetings.db")

def _parse_arguments() -> Optional[str]:
    parser = ArgumentParser(description="Document & MOM Tracking System")
    parser.add_argument("--db", "--database", "--db-url", dest="db_path",
        help="مسیر SQLite محلی یا URL اتصال PostgreSQL (postgresql+psycopg://...)", default=None)
    args, _ = parser.parse_known_args()
    return args.db_path

def _setup_application_metadata() -> None:
    QApplication.setOrganizationName(ORG_NAME)
    QApplication.setApplicationName(APP_NAME)
    try:
        from config import APP_VERSION
        QApplication.setApplicationVersion(APP_VERSION)
    except ImportError:
        QApplication.setApplicationVersion("3.0")

def _add_file_log_handler() -> None:
    try:
        log_dir = os.path.join(_local_data_dir(), "logs")
        os.makedirs(log_dir, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(os.path.join(log_dir, "app.log"),
            maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
        handler.setLevel(logging.WARNING)
        handler.setFormatter(logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(funcName)s:%(lineno)d | %(message)s"))
        logging.getLogger().addHandler(handler)
    except Exception as exc:
        logger.warning("Could not instantiate file logger: %s", exc)

def main() -> int:
    setup_logging(logging.INFO)
    try:
        QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    except AttributeError:
        pass
    try:
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)
    except AttributeError:
        pass
    app = QApplication(sys.argv)
    app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    _setup_application_metadata()
    _add_file_log_handler()
    from ui.splash import AppSplash
    splash = AppSplash()
    splash.show()
    splash.message("در حال آماده‌سازی سامانه…", progress=10)
    settings = QSettings(ORG_NAME, APP_NAME)
    command_db = _parse_arguments()
    env_db = os.environ.get("DOCUMENT_TRACKING_DATABASE_URL", "").strip()
    saved_db = str(settings.value("database_url", "", type=str) or "").strip()
    legacy_path = str(settings.value("db_path", "", type=str) or "").strip()
    db_value = (command_db or env_db or saved_db or legacy_path or _get_default_db_path()).strip()
    is_url = "://" in db_value
    if not is_url:
        db_value = os.path.abspath(os.path.expanduser(db_value))
        try:
            os.makedirs(os.path.dirname(db_value), exist_ok=True)
        except Exception as exc:
            splash.close()
            QMessageBox.critical(None, "خطای مسیر دیتابیس",
                f"ایجاد پوشه دیتابیس ممکن نشد:\n{os.path.dirname(db_value)}\n\nخطا: {exc}")
            return 1
    # قفل محلی است و اجرای همکاران روی رایانه‌های دیگر را مسدود نمی‌کند.
    splash.message("بررسی اجرای برنامه روی این رایانه…", progress=35)
    lock = QLockFile(os.path.join(_local_data_dir(), "app.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        splash.close()
        QMessageBox.warning(None, "سامانه در حال اجرا است",
            "یک نسخه از برنامه روی همین حساب کاربری در حال اجراست.")
        return 0
    settings.setValue("database_url", db_value)
    if not is_url:
        settings.setValue("db_path", db_value)
    splash.message("بارگذاری تنظیمات ظاهری…", progress=55)
    try:
        from ui.styles import apply_theme
        apply_theme(app, dark_mode=settings.value("dark_mode", False, type=bool))
    except ImportError:
        logger.warning("Custom styles module not found; using fallback visual engine.")
    splash.message("اتصال به پایگاه داده…", progress=80)
    try:
        db = DatabaseManager(db_value)
    except Exception as exc:
        splash.close()
        lock.unlock()
        logger.exception("Database connection failed")
        QMessageBox.critical(None, "خطای اتصال به دیتابیس",
            "اتصال به پایگاه داده انجام نشد. آدرس اتصال، دسترسی شبکه و اطلاعات ورود را بررسی کنید.\n\n"
            f"جزئیات خطا: {exc}")
        return 1
    splash.message("راه‌اندازی با موفقیت انجام شد.", progress=100)
    splash.close()
    from ui.login_dialog import LoginDialog
    login = LoginDialog(db)
    if login.exec() != LoginDialog.DialogCode.Accepted or not login.session:
        db.close()
        lock.unlock()
        return 0
    from ui.main_window import MainWindow
    win = MainWindow(db, login.session)
    win.showMaximized()
    exit_code = app.exec()
    db.close()
    lock.unlock()
    return exit_code

if __name__ == "__main__":
    raise SystemExit(main())
