# -*- coding: utf-8 -*-
"""
ui.splash
اسپلش اسکرین مدرن، سبک و با کیفیت بالا برای زمان راه‌اندازی سامانه
نسخه ۳.۱ بهسازی‌شده:
    - جداسازی لایه استاتیک (پس‌زمینه، برند، لوگو) از لایه داینامیک (progress + status)
      برای عملکرد بهینه در هر آپدیت پیشرفت
    - کش کردن فونت‌ها و آیکون برنامه (بدون I/O مکرر)
    - حذف processEvents() از متدهای داخلی (مسئولیت فراخوان)
    - محافظ در برابر آپدیت پس از بسته‌شدن (finish/close)
    - خواندن نسخه و سال از config/زمان (بدون هاردکد)
    - انتقال رنگ‌ها به رشته‌های immutable (QColor on-demand)
    - استفاده از update() به‌جای repaint() برای redraw ناهمگام
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Dict, Optional, Tuple

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
from PyQt6.QtWidgets import QSplashScreen

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════
# ثابت‌های هندسی و متنی
# ══════════════════════════════════════════════════

SPLASH_WIDTH = 540
SPLASH_HEIGHT = 300
SPLASH_CORNER_RADIUS = 16
SPLASH_PADDING = 32

# هندسه نوار پیشرفت (یک منبع حقیقت)
PROGRESS_X = SPLASH_PADDING
PROGRESS_Y = 235
PROGRESS_WIDTH = SPLASH_WIDTH - 2 * SPLASH_PADDING
PROGRESS_HEIGHT = 6
PROGRESS_RADIUS = 3

# برند
BRAND_TITLE_EN = "Document & MOM Tracking"
BRAND_SUBTITLE_TEMPLATE = "ENTERPRISE SYSTEM  •  {version}"
BRAND_TITLE_FA = "سامانه جامع مدیریت، گردش کار و پیگیری اسناد و صورتجلسات"
DEFAULT_STATUS_TEXT = "در حال آماده‌سازی سامانه…"
COPYRIGHT_TEMPLATE = "© {year} All Rights Reserved"

# ══════════════════════════════════════════════════
# پالت رنگی — به‌صورت رشته‌های immutable
# (QColor mutable است؛ ساخت on-demand ایمن‌تر است)
# ══════════════════════════════════════════════════

COLOR_BG_START = "#0b1220"
COLOR_BG_MID = "#0f172a"
COLOR_BG_END = "#080d1a"
COLOR_PRIMARY = "#00BFFF"
COLOR_ACCENT = "#0099CC"
COLOR_TEXT_WHITE = "#ffffff"
COLOR_TEXT_MUTED = "#94a3b8"
COLOR_TEXT_FA = "#e2e8f0"
COLOR_TEXT_COPYRIGHT = "rgba(255, 255, 255, 90)"  # نگه‌داری برای مستندسازی
COLOR_BORDER = "rgba(255, 255, 255, 35)"
COLOR_DIVIDER = "rgba(255, 255, 255, 18)"


# ══════════════════════════════════════════════════
# کش فونت‌ها (ساخت QFont گران است)
# ══════════════════════════════════════════════════

_FONT_CACHE: Dict[Tuple[str, int, int], QFont] = {}


def _get_font(family: str, size: int, weight: QFont.Weight) -> QFont:
    """دریافت QFont کش‌شده — جلوگیری از ساخت مکرر."""
    key = (family, size, int(weight.value))
    cached = _FONT_CACHE.get(key)
    if cached is not None:
        return cached
    f = QFont(family, size)
    try:
        f.setWeight(weight)
    except Exception:
        logger.debug("Failed to set font weight", exc_info=True)
    _FONT_CACHE[key] = f
    return f


# ══════════════════════════════════════════════════
# کلاس اسپلش
# ══════════════════════════════════════════════════

class AppSplash(QSplashScreen):
    """
    صفحه لودینگ اولیه (Splash Screen) با طراحی اختصاصی، گرادیانت مدرن و نوار پیشرفت.

    معماری رندر:
        - لایه استاتیک (پس‌زمینه، برند، لوگو) فقط یک بار ساخته می‌شود.
        - لایه داینامیک (نوار پیشرفت + متن وضعیت) روی نسخه‌ای از استاتیک کشیده می‌شود.
        این جداسازی، هزینه هر آپدیت پیشرفت را به مقدار ناچیزی کاهش می‌دهد.
    """

    def __init__(
        self,
        version: Optional[str] = None,
        parent=None,
    ) -> None:
        # -- آماده‌سازی داده‌های ثابت
        self._progress: int = 0
        self._status_text: str = DEFAULT_STATUS_TEXT
        self._finished: bool = False
        self._version: str = (version or "3.1").strip()

        # -- کش آیکون برنامه (فقط یک بار خوانده و scale می‌شود)
        self._icon_pixmap: Optional[QPixmap] = self._load_app_icon_pixmap()

        # -- پیش‌رندر لایه استاتیک (بدون وابستگی به progress/status)
        self._static_pixmap: QPixmap = self._render_static_layer()

        # -- QSplashScreen با pixmap استاتیک + dynamic روی آن
        pixmap = self._static_pixmap.copy()
        super().__init__(
            pixmap,
            Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        # رندر اولیه لایه داینامیک
        self._refresh_display()

    # ─────────────────────────────────────────────
    # بارگذاری منابع
    # ─────────────────────────────────────────────

    @staticmethod
    def _load_app_icon_pixmap() -> Optional[QPixmap]:
        """بارگذاری یک‌باره آیکون برنامه از دیسک."""
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        icon_path = os.path.join(base_dir, "app.ico")
        if not os.path.isfile(icon_path):
            return None
        pix = QPixmap(icon_path)
        if pix.isNull():
            logger.warning("app.ico یافت شد ولی بارگذاری نشد: %s", icon_path)
            return None
        return pix.scaled(
            54, 54,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

    # ─────────────────────────────────────────────
    # رندر لایه استاتیک (یک‌بار در طول عمر)
    # ─────────────────────────────────────────────

    def _render_static_layer(self) -> QPixmap:
        """رندر تمام عناصر ثابت: پس‌زمینه، برند، لوگو، عنوان‌ها، کپی‌رایت."""
        pixmap = QPixmap(SPLASH_WIDTH, SPLASH_HEIGHT)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        try:
            self._paint_background(painter)
            self._paint_logo(painter)
            self._paint_brand_texts(painter)
            self._paint_divider(painter)
            self._paint_copyright(painter)
        finally:
            painter.end()

        return pixmap

    @staticmethod
    def _paint_background(painter: QPainter) -> None:
        """پس‌زمینه گرادیانی با گوشه‌های گرد."""
        rect = QRectF(0, 0, SPLASH_WIDTH, SPLASH_HEIGHT)
        path = QPainterPath()
        path.addRoundedRect(
            rect.adjusted(1, 1, -1, -1),
            SPLASH_CORNER_RADIUS,
            SPLASH_CORNER_RADIUS,
        )

        grad = QLinearGradient(0, 0, SPLASH_WIDTH, SPLASH_HEIGHT)
        grad.setColorAt(0.0, QColor(COLOR_BG_START))
        grad.setColorAt(0.6, QColor(COLOR_BG_MID))
        grad.setColorAt(1.0, QColor(COLOR_BG_END))
        painter.fillPath(path, grad)

        # کادر ظریف پیرامونی
        border_pen = QPen(QColor(255, 255, 255, 35), 1.2)
        painter.setPen(border_pen)
        painter.drawPath(path)

        # خط تزئینی بالا (accent)
        highlight_pen = QPen(QColor(COLOR_PRIMARY), 2.5)
        highlight_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(highlight_pen)
        painter.drawLine(QPointF(35, 1.5), QPointF(110, 1.5))

    def _paint_logo(self, painter: QPainter) -> None:
        """آیکون برنامه یا بج پیش‌فرض."""
        if self._icon_pixmap is not None:
            painter.drawPixmap(32, 34, self._icon_pixmap)
            return

        # بج پیش‌فرض
        logo_rect = QRectF(32, 34, 52, 52)
        logo_path = QPainterPath()
        logo_path.addRoundedRect(logo_rect, 12, 12)
        painter.fillPath(logo_path, QColor(COLOR_PRIMARY))

        painter.setPen(QColor(COLOR_TEXT_WHITE))
        painter.setFont(_get_font("Segoe UI", 16, QFont.Weight.Black))
        painter.drawText(logo_rect, Qt.AlignmentFlag.AlignCenter, "M")

    def _paint_brand_texts(self, painter: QPainter) -> None:
        """نام برند، زیرنویس نسخه، و عنوان فارسی."""
        # برند انگلیسی
        painter.setPen(QColor(COLOR_TEXT_WHITE))
        painter.setFont(_get_font("Segoe UI", 16, QFont.Weight.Bold))
        painter.drawText(98, 58, BRAND_TITLE_EN)

        # زیرنویس نسخه
        painter.setPen(QColor(COLOR_PRIMARY))
        painter.setFont(_get_font("Segoe UI", 9, QFont.Weight.DemiBold))
        subtitle = BRAND_SUBTITLE_TEMPLATE.format(version=f"v{self._version}")
        painter.drawText(98, 78, subtitle)

        # عنوان فارسی
        painter.setPen(QColor(COLOR_TEXT_FA))
        painter.setFont(_get_font("Vazirmatn", 11, QFont.Weight.Medium))
        title_rect = QRectF(
            SPLASH_PADDING, 115,
            SPLASH_WIDTH - 2 * SPLASH_PADDING, 28,
        )
        painter.drawText(
            title_rect,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            BRAND_TITLE_FA,
        )

    @staticmethod
    def _paint_divider(painter: QPainter) -> None:
        """خط جداکننده افقی ظریف."""
        painter.setPen(QPen(QColor(255, 255, 255, 18), 1))
        painter.drawLine(SPLASH_PADDING, 155, SPLASH_WIDTH - SPLASH_PADDING, 155)

    @staticmethod
    def _paint_copyright(painter: QPainter) -> None:
        """متن کپی‌رایت با سال جاری."""
        painter.setPen(QColor(255, 255, 255, 90))
        painter.setFont(_get_font("Segoe UI", 8, QFont.Weight.Normal))
        text = COPYRIGHT_TEMPLATE.format(year=datetime.now().year)
        painter.drawText(SPLASH_PADDING, 272, text)

    # ─────────────────────────────────────────────
    # رندر لایه داینامیک (progress + status)
    # ─────────────────────────────────────────────

    def _render_dynamic_layer(self) -> QPixmap:
        """ساخت نسخه جدید از pixmap نهایی شامل متن وضعیت و نوار پیشرفت."""
        pixmap = self._static_pixmap.copy()
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        try:
            self._paint_status_text(painter)
            self._paint_progress_bar(painter)
        finally:
            painter.end()

        return pixmap

    def _paint_status_text(self, painter: QPainter) -> None:
        """متن وضعیت در حال انجام."""
        painter.setPen(QColor(COLOR_TEXT_MUTED))
        painter.setFont(_get_font("Vazirmatn", 10, QFont.Weight.Normal))
        status_rect = QRectF(
            SPLASH_PADDING, 195,
            SPLASH_WIDTH - 2 * SPLASH_PADDING, 24,
        )
        painter.drawText(
            status_rect,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            self._status_text,
        )

    def _paint_progress_bar(self, painter: QPainter) -> None:
        """نوار پیشرفت با گرادیانت و گوشه‌های گرد."""
        track_rect = QRectF(
            PROGRESS_X, PROGRESS_Y, PROGRESS_WIDTH, PROGRESS_HEIGHT,
        )

        # پس‌زمینه (track)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 255, 255, 25))
        painter.drawRoundedRect(track_rect, PROGRESS_RADIUS, PROGRESS_RADIUS)

        # بخش پر شده
        progress = max(0, min(int(self._progress), 100))
        if progress <= 0:
            return

        fill_width = PROGRESS_WIDTH * (progress / 100.0)
        fill_rect = QRectF(
            PROGRESS_X, PROGRESS_Y, fill_width, PROGRESS_HEIGHT,
        )
        grad = QLinearGradient(PROGRESS_X, 0, PROGRESS_X + PROGRESS_WIDTH, 0)
        grad.setColorAt(0.0, QColor(COLOR_ACCENT))
        grad.setColorAt(1.0, QColor(COLOR_PRIMARY))
        painter.setBrush(grad)
        painter.drawRoundedRect(fill_rect, PROGRESS_RADIUS, PROGRESS_RADIUS)

    # ─────────────────────────────────────────────
    # به‌روزرسانی نمایش
    # ─────────────────────────────────────────────

    def _refresh_display(self) -> None:
        """به‌روزرسانی pixmap نمایشی — با update() ناهمگام."""
        if self._finished:
            return
        try:
            self.setPixmap(self._render_dynamic_layer())
        except Exception:
            logger.exception("Failed to refresh splash display")

    # ─────────────────────────────────────────────
    # API عمومی
    # ─────────────────────────────────────────────

    def message(
        self,
        text: str,
        progress: Optional[int] = None,
    ) -> None:
        """
        تغییر متن پیام وضعیت با قابلیت به‌روزرسانی درصد پیشرفت.

        Args:
            text: متن وضعیت فارسی. اگر خالی باشد، متن پیش‌فرض نمایش داده می‌شود.
            progress: درصد پیشرفت (۰ تا ۱۰۰). اختیاری.
        """
        if self._finished:
            return

        self._status_text = text.strip() if text else DEFAULT_STATUS_TEXT
        if progress is not None:
            self._progress = max(0, min(int(progress), 100))
        self._refresh_display()

    def set_progress(self, value: int) -> None:
        """
        تنظیم مستقیم درصد نوار پیشرفت.

        Args:
            value: عددی بین ۰ تا ۱۰۰
        """
        if self._finished:
            return
        self._progress = max(0, min(int(value), 100))
        self._refresh_display()

    def finish(self, widget) -> None:
        """
        بستن ایمن اسپلش و غیرفعال‌سازی آپدیت‌های بعدی.
        باید به‌جای `close()` مستقیم استفاده شود تا از آپدیت پس از بسته‌شدن جلوگیری شود.

        Args:
            widget: ویجت اصلی برنامه که focus به آن داده می‌شود.
        """
        if self._finished:
            return
        self._finished = True
        try:
            super().finish(widget)
        except Exception:
            logger.exception("Failed to finish splash cleanly")

    def closeEvent(self, event) -> None:
        """غیرفعال‌سازی آپدیت پس از بسته‌شدن."""
        self._finished = True
        super().closeEvent(event)

    # ─────────────────────────────────────────────
    # ویژگی‌های خواندنی
    # ─────────────────────────────────────────────

    @property
    def progress(self) -> int:
        """درصد فعلی نوار پیشرفت (۰ تا ۱۰۰)."""
        return self._progress

    @property
    def is_finished(self) -> bool:
        """آیا اسپلش بسته شده است؟"""
        return self._finished
