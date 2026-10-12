# -*- coding: utf-8 -*-
"""
ui.splash
اسپلش اسکرین مدرن، سبک و با کیفیت بالا برای زمان راه‌اندازی سامانه
نسخه ارتقا یافته: رندر برداری گرادیانت، گوشه‌های گرد، پشتیبانی از درصد پیشرفت و سازگاری با High-DPI
"""
from __future__ import annotations

import os
from typing import Optional

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PyQt6.QtWidgets import QApplication, QSplashScreen

# ابعاد استاندارد و ارگونومیک پنجره اسپلش
SPLASH_WIDTH = 540
SPLASH_HEIGHT = 300

# پالت رنگی هماهنگ با هویت بصری سامانه
COLOR_BG_START = QColor("#0b1220")      # سورمه‌ای خیلی تیره
COLOR_BG_END = QColor("#0f172a")        # بادمجانی/تیره ملایم
COLOR_PRIMARY = QColor("#00BFFF")       # آبی آسمانی برند
COLOR_ACCENT = QColor("#0099CC")        # آبی تیره ملایم
COLOR_TEXT_WHITE = QColor("#ffffff")
COLOR_TEXT_MUTED = QColor("#94a3b8")
COLOR_PROGRESS_TRACK = QColor(255, 255, 255, 25)


class AppSplash(QSplashScreen):
    """
    صفحه لودینگ اولیه (Splash Screen) با طراحی اختصاصی، گرادیانت مدرن و نوار پیشرفت بارگذاری.
    """

    def __init__(self) -> None:
        self._progress: int = 0
        self._status_text: str = "در حال آماده‌سازی سامانه…"
        self._base_pixmap = self._generate_base_pixmap()

        super().__init__(self._base_pixmap, Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        # رندر اولیه
        self._update_render()

    def _get_app_icon_pixmap(self) -> Optional[QPixmap]:
        """پیدا کردن و بارگذاری امن آیکون برنامه بدون تغییر نسبت ابعاد."""
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        icon_path = os.path.join(base_dir, "app.ico")
        if os.path.isfile(icon_path):
            pix = QPixmap(icon_path)
            if not pix.isNull():
                return pix.scaled(
                    54, 54,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
        return None

    def _generate_base_pixmap(self) -> QPixmap:
        """ساخت پس‌زمینه شفاف اولیه متناسب با رزولوشن صفحه."""
        pixmap = QPixmap(SPLASH_WIDTH, SPLASH_HEIGHT)
        pixmap.fill(Qt.GlobalColor.transparent)
        return pixmap

    def _update_render(self) -> None:
        """رسم تمام عناصر بصری اسپلش اسکرین بر روی پیکسمپ اصلی."""
        pixmap = self._base_pixmap.copy()
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        rect = QRectF(0, 0, SPLASH_WIDTH, SPLASH_HEIGHT)

        # ۱. رسم بدنه اصلی با گوشه‌های گرد و گرادیانت
        path = QPainterPath()
        path.addRoundedRect(rect.adjusted(1, 1, -1, -1), 16, 16)

        grad = QLinearGradient(0, 0, SPLASH_WIDTH, SPLASH_HEIGHT)
        grad.setColorAt(0.0, COLOR_BG_START)
        grad.setColorAt(0.6, COLOR_BG_END)
        grad.setColorAt(1.0, QColor("#080d1a"))

        painter.fillPath(path, grad)

        # ۲. رسم کادر پیرامونی ظریف (Subtle Border)
        border_pen = QPen(QColor(255, 255, 255, 35), 1.2)
        painter.setPen(border_pen)
        painter.drawPath(path)

        # ۳. رسم خط تزئینی بالایی (Top Accent Highlight)
        highlight_pen = QPen(COLOR_PRIMARY, 2.5)
        highlight_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(highlight_pen)
        painter.drawLine(QPointF(35, 1.5), QPointF(110, 1.5))

        # ۴. رسم لوگو یا نماد برنامه
        icon_pix = self._get_app_icon_pixmap()
        if icon_pix:
            painter.drawPixmap(32, 34, icon_pix)
        else:
            # بج لوگوی اختصاصی در صورت نبود فایل .ico
            logo_rect = QRectF(32, 34, 52, 52)
            logo_path = QPainterPath()
            logo_path.addRoundedRect(logo_rect, 12, 12)
            painter.fillPath(logo_path, COLOR_PRIMARY)
            painter.setPen(COLOR_TEXT_WHITE)
            painter.setFont(QFont("Segoe UI", 16, QFont.Weight.Black))
            painter.drawText(logo_rect, Qt.AlignmentFlag.AlignCenter, "M")

        # ۵. رسم متون عنوان و برچسب نسخه (LTR/RTL)
        painter.setPen(COLOR_TEXT_WHITE)
        painter.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        painter.drawText(98, 58, "Document & MOM Tracking")

        painter.setPen(COLOR_PRIMARY)
        painter.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
        painter.drawText(98, 78, "ENTERPRISE SYSTEM  •  v3.0")

        # ۶. رسم عنوان فارسی سامانه
        painter.setPen(QColor("#e2e8f0"))
        painter.setFont(QFont("Vazirmatn", 11, QFont.Weight.Medium))
        farsi_title_rect = QRectF(32, 115, SPLASH_WIDTH - 64, 28)
        painter.drawText(
            farsi_title_rect,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            "سامانه جامع مدیریت، گردش کار و پیگیری اسناد و صورتجلسات"
        )

        # ۷. رسم خط جداکننده افقی ظریف
        painter.setPen(QPen(QColor(255, 255, 255, 18), 1))
        painter.drawLine(32, 155, SPLASH_WIDTH - 32, 155)

        # ۸. رسم متن وضعیت در حال انجام (Status Text)
        painter.setPen(COLOR_TEXT_MUTED)
        painter.setFont(QFont("Vazirmatn", 10))
        status_rect = QRectF(32, 195, SPLASH_WIDTH - 64, 24)
        painter.drawText(
            status_rect,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            self._status_text
        )

        # ۹. رسم نوار پیشرفت (Progress Bar)
        progress_track = QRectF(32, 235, SPLASH_WIDTH - 64, 6)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(COLOR_PROGRESS_TRACK)
        painter.drawRoundedRect(progress_track, 3, 3)

        # بخش پر شده پیشرفت
        progress_width = (SPLASH_WIDTH - 64) * (max(0, min(self._progress, 100)) / 100.0)
        if progress_width > 0:
            progress_fill = QRectF(32, 235, progress_width, 6)
            progress_grad = QLinearGradient(32, 0, SPLASH_WIDTH - 32, 0)
            progress_grad.setColorAt(0.0, COLOR_ACCENT)
            progress_grad.setColorAt(1.0, COLOR_PRIMARY)
            painter.setBrush(progress_grad)
            painter.drawRoundedRect(progress_fill, 3, 3)

        # ۱۰. متن کپی‌رایت / وضعیت حقوقی در فوتر
        painter.setPen(QColor(255, 255, 255, 90))
        painter.setFont(QFont("Segoe UI", 8))
        painter.drawText(32, 272, "© 2025 All Rights Reserved")

        painter.end()

        # به‌روزرسانی پیکسمپ نمایش داده‌شده
        self.setPixmap(pixmap)
        self.repaint()

    # ─────────────────────────────────────────────────────────────
    # متدهای عمومی کنترل اسپلش
    # ─────────────────────────────────────────────────────────────
    def message(self, text: str, progress: Optional[int] = None) -> None:
        """
        تغییر متن پیام وضعیت در حال انجام با قابلیت به‌روزرسانی درصد پیشرفت.

        Args:
            text: متن وضعیت فارسی
            progress: درصد پیشرفت از ۰ تا ۱۰۰ (اختیاری)
        """
        self._status_text = text or ""
        if progress is not None:
            self._progress = max(0, min(progress, 100))
        self._update_render()
        QApplication.processEvents()

    def set_progress(self, value: int) -> None:
        """
        تنظیم مستقیم درصد نوار پیشرفت.

        Args:
            value: عددی بین ۰ تا ۱۰۰
        """
        self._progress = max(0, min(value, 100))
        self._update_render()
        QApplication.processEvents()