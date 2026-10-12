# -*- coding: utf-8 -*-
"""
ui.operations_dashboard
داشبورد مانیتورینگ و کنترل لحظه‌ای گردش صورتجلسات
نسخه نهایی هماهنگ با ساختار جدید:
    - حذف کامل وابستگی به فیلد منسوخ contractor_response_status
    - همگام‌سازی با قانون طلایی «ارسال به پیمانکار = اتمام کار»
    - نمایش کارشناس مسئول (گام ۳) در فهرست‌های عملیاتی
    - پشتیبانی کامل از تاریخ شمسی و طراحی مدرن SaaS
    - 📤 صدور گزارش HTML مدیریتی جهت ارسال به مدیران ارشد
"""
from __future__ import annotations

import logging
import os
import tempfile
from datetime import date, datetime, timedelta
from html import escape
from typing import Any, Dict, List, Optional, Tuple

from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtGui import QColor, QDesktopServices, QFont
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from db.manager import DatabaseManager
from db.models import (
    Meeting,
    WorkflowStep,
    STATUS_AWAITING,
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_PENDING,
)
from ui.meeting_dialog import MeetingDialog
from utils.date_utils import to_shamsi, today_shamsi

logger = logging.getLogger(__name__)

# وضعیت‌های باز (نیازمند پیگیری)
try:
    from db.models import STATUS_RETURNED
    OPEN_STATUSES = [STATUS_PENDING, STATUS_AWAITING, STATUS_RETURNED]
except ImportError:
    STATUS_RETURNED = "بازگشت داده شده"
    OPEN_STATUSES = [STATUS_PENDING, STATUS_AWAITING, STATUS_RETURNED]

# رنگ‌های اختصاصی کارت‌ها
CARD_THEMES = {
    "total":              {"bg": "#f8fafc", "border": "#cbd5e1", "text": "#334155", "accent": "#64748b"},
    "open":               {"bg": "#eff6ff", "border": "#bfdbfe", "text": "#1d4ed8", "accent": "#3b82f6"},
    "overdue":            {"bg": "#fef2f2", "border": "#fecaca", "text": "#b91c1c", "accent": "#ef4444"},
    "due_3":              {"bg": "#fffbeb", "border": "#fde68a", "text": "#b45309", "accent": "#f59e0b"},
    "waiting_contractor": {"bg": "#faf5ff", "border": "#e9d5ff", "text": "#7e22ce", "accent": "#a855f7"},
    "answered":           {"bg": "#f0fdf4", "border": "#bbf7d0", "text": "#15803d", "accent": "#22c55e"},
    "completed":          {"bg": "#ecfdf5", "border": "#a7f3d0", "text": "#047857", "accent": "#10b981"},
}


class MetricCard(QFrame):
    """کارت شاخص آماری با حاشیه رنگی و مقادیر برجسته."""

    def __init__(
        self,
        title: str,
        key: str,
        icon: str = "",
        theme_key: str = "total",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("metric_card")
        self.key = key
        theme = CARD_THEMES.get(theme_key, CARD_THEMES["total"])

        self.setStyleSheet(f"""
            QFrame#metric_card {{
                background-color: {theme['bg']};
                border: 1px solid {theme['border']};
                border-top: 3.5px solid {theme['accent']};
                border-radius: 10px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(4)

        # عنوان کارت
        lbl_title = QLabel(f"{icon} {title}".strip())
        lbl_title.setStyleSheet(f"font-size: 11.5px; font-weight: bold; color: {theme['text']};")
        layout.addWidget(lbl_title)

        # مقدار عددی
        self.lbl_value = QLabel("0")
        self.lbl_value.setObjectName(key)
        self.lbl_value.setStyleSheet(
            f"font-size: 26px; font-weight: 900; color: {theme['text']}; font-variant-numeric: tabular-nums;"
        )
        layout.addWidget(self.lbl_value)

    def set_value(self, val: int) -> None:
        self.lbl_value.setText(f"{val:,}")


class OperationsDashboard(QDialog):
    """دیالوگ داشبورد عملیاتی برای پایش بلادرنگ وضعیت صورتجلسات."""

    REFRESH_INTERVAL_MS = 30_000  # هر ۳۰ ثانیه
    LIST_LIMIT = 35
    EXPORT_LIST_LIMIT = 100  # در خروجی HTML رکوردهای بیشتری نمایش داده می‌شود

    def __init__(self, db: DatabaseManager, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.db = db
        self.cards: Dict[str, MetricCard] = {}
        self._last_metrics: Dict[str, int] = {}
        self._last_overdue: List[Meeting] = []
        self._last_due: List[Meeting] = []
        self._last_waiting: List[Meeting] = []
        self._last_specialists: Dict[int, str] = {}

        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setWindowTitle("داشبورد عملیاتی و پایش بلادرنگ | MOM Tracking")
        self.resize(1100, 720)
        self.setMinimumSize(950, 600)

        self._build_ui()
        self.refresh()

        # تایمر بروزرسانی خودکار
        self.timer = QTimer(self)
        self.timer.setInterval(self.REFRESH_INTERVAL_MS)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()

    # ─────────────────────────────────────────────────────────────
    # ساخت رابط کاربری
    # ─────────────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 18)
        root.setSpacing(16)

        # ── نوار سربرگ ──
        header_layout = QHBoxLayout()

        title_block = QVBoxLayout()
        title_block.setSpacing(2)

        lbl_title = QLabel("📊 داشبورد عملیاتی و کنترل جریان کار صورتجلسات")
        lbl_title.setObjectName("dash_title")
        lbl_title.setStyleSheet("font-size: 18px; font-weight: 800; color: #0f172a; padding: 2px 0;")

        lbl_sub = QLabel("پایش مهلت‌های بحرانی، پرونده‌های در جریان و ابلاغیه‌های ارسال‌شده به پیمانکاران")
        lbl_sub.setStyleSheet("font-size: 11.5px; color: #64748b; padding-top: 2px;")

        title_block.addWidget(lbl_title)
        title_block.addWidget(lbl_sub)
        header_layout.addLayout(title_block)
        header_layout.addStretch()

        self.lbl_last_update = QLabel("")
        self.lbl_last_update.setStyleSheet("font-size: 11px; color: #475569; background: #f1f5f9; border: 1px solid #e2e8f0; border-radius: 8px; padding: 7px 10px; margin-left: 8px;")
        header_layout.addWidget(self.lbl_last_update)

        # 📤 دکمه جدید: خروجی HTML برای مدیریت
        self.btn_export_html = QPushButton("📤 گزارش مدیریتی HTML")
        self.btn_export_html.setObjectName("btn_export")
        self.btn_export_html.setToolTip(
            "تولید گزارش کامل داشبورد به فرمت HTML جهت ارسال به مدیران ارشد\n"
            "این گزارش شامل تمام شاخص‌ها، فهرست‌های عملیاتی و آماده چاپ است."
        )
        self.btn_export_html.clicked.connect(self._export_html_report)
        header_layout.addWidget(self.btn_export_html)

        self.btn_refresh = QPushButton("🔄 بروزرسانی")
        self.btn_refresh.setObjectName("btn_secondary")
        self.btn_refresh.clicked.connect(self.refresh)
        header_layout.addWidget(self.btn_refresh)

        root.addLayout(header_layout)

        # ── کارت‌های شاخص‌های آماری ──
        grid = QGridLayout()
        grid.setSpacing(14)

        metrics_def = [
            ("کل پرونده‌ها", "total", "📁", "total"),
            ("در جریان پیگیری", "open", "⚡", "open"),
            ("دارای تاخیر زمانی", "overdue", "⚠️", "overdue"),
            ("سررسید ۳ روز آینده", "due_3", "⏳", "due_3"),
            ("منتظر ابلاغ به پیمانکار", "waiting_contractor", "📨", "waiting_contractor"),
            ("ابلاغ‌شده به پیمانکار", "answered", "📩", "answered"),
            ("تکمیل و بسته‌شده", "completed", "✅", "completed"),
        ]

        for i, (t, k, icon, theme) in enumerate(metrics_def):
            card = MetricCard(t, k, icon=icon, theme_key=theme)
            self.cards[k] = card
            grid.addWidget(card, i // 4, i % 4)

        root.addLayout(grid)

        # ── ستون‌های فهرست‌های عملیاتی ──
        lists_row = QHBoxLayout()
        lists_row.setSpacing(16)

        self.overdue_list = QListWidget()
        self.due_list = QListWidget()
        self.waiting_list = QListWidget()

        self.lbl_overdue_hdr = QLabel("⚠️ پرونده‌های دارای تاخیر")
        self.lbl_due_hdr = QLabel("⏳ نزدیک به سررسید (۳ روز آینده)")
        self.lbl_waiting_hdr = QLabel("📨 منتظر ابلاغ به پیمانکار")

        col_defs = [
            (self.overdue_list, self.lbl_overdue_hdr, "#b91c1c"),
            (self.due_list, self.lbl_due_hdr, "#b45309"),
            (self.waiting_list, self.lbl_waiting_hdr, "#7e22ce"),
        ]

        for list_widget, hdr_label, color in col_defs:
            col_box = QVBoxLayout()
            col_box.setSpacing(9)

            hdr_label.setStyleSheet(f"font-weight: 800; font-size: 12.5px; color: {color}; padding: 8px 10px; background: #ffffff; border: 1px solid #e2e8f0; border-right: 3px solid {color}; border-radius: 7px;")
            list_widget.setAlternatingRowColors(True)
            list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)

            col_box.addWidget(hdr_label)
            col_box.addWidget(list_widget, stretch=1)
            lists_row.addLayout(col_box)

        root.addLayout(lists_row, stretch=1)

        # ── نوار پایینی و دکمه بستن ──
        bottom_bar = QHBoxLayout()
        lbl_hint = QLabel("💡 راهنما: برای مشاهده یا ویرایش هر صورتجلسه، روی ردیف آن دوبار کلیک کنید.")
        lbl_hint.setStyleSheet("font-size: 11px; color: #64748b; padding: 6px 2px;")
        bottom_bar.addWidget(lbl_hint)
        bottom_bar.addStretch()

        btn_close = QPushButton("بستن")
        btn_close.setObjectName("btn_close")
        btn_close.setMinimumSize(90, 32)
        btn_close.clicked.connect(self.accept)
        bottom_bar.addWidget(btn_close)

        root.addLayout(bottom_bar)
        self._apply_style()

    def _apply_style(self) -> None:
        self.setStyleSheet("""
            QDialog {
                background-color: #f1f5f9;
                color: #0f172a;
                font-family: 'Vazirmatn', 'Segoe UI', Tahoma, sans-serif;
                font-size: 12px;
            }
            QListWidget {
                border: 1px solid #dbe4ee;
                border-radius: 10px;
                background-color: #ffffff;
                padding: 7px;
                font-size: 11.5px;
                outline: none;
            }
            QListWidget::item {
                border-radius: 5px;
                padding: 9px 10px;
                margin-bottom: 4px;
                border-bottom: 1px solid #f1f5f9;
            }
            QListWidget::item:hover {
                background-color: #f1f5f9;
            }
            QListWidget::item:selected {
                background-color: #00BFFF;
                color: #ffffff;
            }
            QPushButton {
                background-color: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                padding: 7px 17px;
                min-height: 24px;
                font-weight: bold;
                font-size: 12px;
                color: #334155;
            }
            QPushButton:hover {
                background-color: #f1f5f9;
            }
            QPushButton#btn_close {
                background-color: #00BFFF;
                color: white;
                border: none;
            }
            QPushButton#btn_close:hover {
                background-color: #0099CC;
            }
            QPushButton#btn_secondary {
                background-color: #ffffff;
                color: #0284c7;
                border-color: #bae6fd;
            }
            QPushButton#btn_secondary:hover {
                background-color: #f0f9ff;
            }
            QPushButton#btn_export {
                background-color: #ecfdf5;
                color: #047857;
                border: 1px solid #a7f3d0;
            }
            QPushButton#btn_export:hover {
                background-color: #a7f3d0;
                color: #064e3b;
                border-color: #10b981;
            }
        """)

    # ─────────────────────────────────────────────────────────────
    # واکشی نام کارشناس رسیدگی‌کننده (گام ۳ گردش کار)
    # ─────────────────────────────────────────────────────────────
    def _fetch_specialists_map(self, meeting_ids: List[int]) -> Dict[int, str]:
        """
        واکشی سریع نام کارشناس رسیدگی‌کننده اصلی (گام ۳ = ورود به دفتر کارشناس)
        برای مجموعه‌ای از صورتجلسات به صورت دسته‌ای (Bulk).
        """
        if not meeting_ids:
            return {}

        result: Dict[int, str] = {}
        try:
            with self.db.session() as sess:
                steps = (
                    sess.query(WorkflowStep)
                    .filter(
                        WorkflowStep.meeting_id.in_(meeting_ids),
                        WorkflowStep.step_order == 3,
                    )
                    .all()
                )
                for s in steps:
                    if s.responsible_person:
                        result[s.meeting_id] = s.responsible_person
        except Exception as exc:
            logger.warning("Failed to fetch specialists map: %s", exc)
        return result

    # ─────────────────────────────────────────────────────────────
    # بارگذاری و به‌روزرسانی داده‌ها
    # ─────────────────────────────────────────────────────────────
    def refresh(self) -> None:
        """واکشی آخرین اطلاعات آماری و بازسازی فهرست‌ها."""
        try:
            # ۱. به‌روزرسانی کارت‌های آماری
            metrics = self.db.operational_metrics()
            self._last_metrics = metrics
            for key, card in self.cards.items():
                card.set_value(int(metrics.get(key, 0)))

            today = date.today()
            three_days_later = today + timedelta(days=3)

            # ۲. واکشی داده‌های سه فهرست عملیاتی
            with self.db.session() as s:
                base = s.query(Meeting).filter(Meeting.is_deleted.is_(False))

                # الف) تاخیردارها: مهلت گذشته و هنوز به پیمانکار ابلاغ نشده
                overdue_rows = (
                    base.filter(
                        Meeting.due_date < today,
                        Meeting.sent_to_contractor_date.is_(None),
                        Meeting.status != STATUS_CANCELLED,
                    )
                    .order_by(Meeting.due_date.asc())
                    .limit(self.LIST_LIMIT)
                    .all()
                )

                # ب) سررسید ۳ روز آینده
                due_soon_rows = (
                    base.filter(
                        Meeting.due_date >= today,
                        Meeting.due_date <= three_days_later,
                        Meeting.sent_to_contractor_date.is_(None),
                        Meeting.status != STATUS_CANCELLED,
                    )
                    .order_by(Meeting.due_date.asc())
                    .limit(self.LIST_LIMIT)
                    .all()
                )

                # ج) منتظر ابلاغ به پیمانکار
                waiting_rows = (
                    base.filter(
                        Meeting.sent_to_contractor_date.is_(None),
                        Meeting.status != STATUS_CANCELLED,
                    )
                    .order_by(Meeting.due_date.asc())
                    .limit(self.LIST_LIMIT)
                    .all()
                )

            # ۳. واکشی دسته‌ای نام کارشناسان اصلی برای تمام رکوردهای بالا
            all_ids = list({m.id for m in (overdue_rows + due_soon_rows + waiting_rows)})
            specialists_map = self._fetch_specialists_map(all_ids)

            # ذخیره برای استفاده در گزارش HTML
            self._last_overdue = overdue_rows
            self._last_due = due_soon_rows
            self._last_waiting = waiting_rows
            self._last_specialists = specialists_map

            # ۴. پر کردن لیست‌ها
            self._populate_list(self.overdue_list, overdue_rows, mode="overdue",
                                today=today, specialists=specialists_map)
            self._populate_list(self.due_list, due_soon_rows, mode="due",
                                today=today, specialists=specialists_map)
            self._populate_list(self.waiting_list, waiting_rows, mode="waiting",
                                today=today, specialists=specialists_map)

            # ۵. به‌روزرسانی عناوین با تعداد رکوردها
            self.lbl_overdue_hdr.setText(f"⚠️ پرونده‌های دارای تاخیر ({len(overdue_rows)})")
            self.lbl_due_hdr.setText(f"⏳ نزدیک به سررسید ۳ روز آینده ({len(due_soon_rows)})")
            self.lbl_waiting_hdr.setText(f"📨 منتظر ابلاغ به پیمانکار ({len(waiting_rows)})")

            now_str = datetime.now().strftime("%H:%M:%S")
            self.lbl_last_update.setText(f"آخرین بروزرسانی: {now_str}")

        except Exception as exc:
            logger.exception("Failed to refresh OperationsDashboard")
            self.lbl_last_update.setText("⚠️ خطا در بروزرسانی")

    def _populate_list(
        self,
        list_widget: QListWidget,
        rows: List[Meeting],
        mode: str,
        today: date,
        specialists: Optional[Dict[int, str]] = None,
    ) -> None:
        """قالب‌بندی و افزودن ردیف‌های صورتجلسات با جزئیات روز و تاریخ شمسی."""
        list_widget.clear()
        specialists = specialists or {}

        if not rows:
            empty_item = QListWidgetItem("✅ موردی در این بخش وجود ندارد")
            empty_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_item.setForeground(QColor("#94a3b8"))
            empty_item.setFlags(Qt.ItemFlag.NoItemFlags)
            list_widget.addItem(empty_item)
            return

        for m in rows:
            due_shamsi = to_shamsi(str(m.due_date)) if m.due_date else "بدون مهلت"
            days_diff = (m.due_date - today).days if m.due_date else 0

            if mode == "overdue":
                status_badge = f"⛔ ({abs(days_diff)} روز تاخیر)"
            elif mode == "due":
                if days_diff == 0:
                    status_badge = "🔴 (امروز سررسید)"
                elif days_diff == 1:
                    status_badge = "🟠 (فردا سررسید)"
                else:
                    status_badge = f"🟡 ({days_diff} روز مانده)"
            else:
                contractor_name = m.contractor or "پیمانکار نامشخص"
                status_badge = f"[پیمانکار: {contractor_name}]"

            specialist = specialists.get(m.id, "").strip()
            specialist_info = f"👤 {specialist}" if specialist else "👤 کارشناس تخصیص نیافته"

            subject_preview = (m.subject or "بدون موضوع")
            if len(subject_preview) > 60:
                subject_preview = subject_preview[:60] + "…"

            display_text = (
                f"📌 {m.meeting_number} | {subject_preview}\n"
                f"     مهلت: {due_shamsi}  {status_badge}   •   {specialist_info}"
            )
            item = QListWidgetItem(display_text)
            item.setData(Qt.ItemDataRole.UserRole, m.id)
            item.setToolTip(
                f"دوبار کلیک برای باز کردن پرونده\n"
                f"─────────────────\n"
                f"شماره صورتجلسه: {m.meeting_number}\n"
                f"موضوع کامل: {m.subject or '—'}\n"
                f"پیمانکار: {m.contractor or '—'}\n"
                f"کارشناس رسیدگی‌کننده: {specialist or 'تخصیص نیافته'}\n"
                f"مهلت انجام: {due_shamsi}"
            )
            list_widget.addItem(item)

    # ─────────────────────────────────────────────────────────────
    # 📤 صدور گزارش HTML مدیریتی
    # ─────────────────────────────────────────────────────────────
    def _export_html_report(self) -> None:
        """صدور گزارش HTML جامع مدیریتی جهت ارسال به مدیران ارشد."""
        try:
            # ابتدا داده‌ها را برای گزارش کامل واکشی می‌کنیم (با محدودیت بالاتر)
            today = date.today()
            three_days_later = today + timedelta(days=3)

            with self.db.session() as s:
                base = s.query(Meeting).filter(Meeting.is_deleted.is_(False))

                overdue_rows = (
                    base.filter(
                        Meeting.due_date < today,
                        Meeting.sent_to_contractor_date.is_(None),
                        Meeting.status != STATUS_CANCELLED,
                    )
                    .order_by(Meeting.due_date.asc())
                    .limit(self.EXPORT_LIST_LIMIT)
                    .all()
                )

                due_soon_rows = (
                    base.filter(
                        Meeting.due_date >= today,
                        Meeting.due_date <= three_days_later,
                        Meeting.sent_to_contractor_date.is_(None),
                        Meeting.status != STATUS_CANCELLED,
                    )
                    .order_by(Meeting.due_date.asc())
                    .limit(self.EXPORT_LIST_LIMIT)
                    .all()
                )

                waiting_rows = (
                    base.filter(
                        Meeting.sent_to_contractor_date.is_(None),
                        Meeting.status != STATUS_CANCELLED,
                    )
                    .order_by(Meeting.due_date.asc())
                    .limit(self.EXPORT_LIST_LIMIT)
                    .all()
                )

            all_ids = list({m.id for m in (overdue_rows + due_soon_rows + waiting_rows)})
            specialists_map = self._fetch_specialists_map(all_ids)

            # ساخت محتوای HTML
            html_content = self._build_html_content(
                metrics=self._last_metrics,
                overdue_rows=overdue_rows,
                due_rows=due_soon_rows,
                waiting_rows=waiting_rows,
                specialists=specialists_map,
                today=today,
            )

            # انتخاب مسیر ذخیره
            default_name = f"MOM_Executive_Report_{date.today():%Y%m%d}_{datetime.now():%H%M}.html"
            default_path = os.path.join(os.path.expanduser("~"), "Desktop", default_name)
            if not os.path.isdir(os.path.dirname(default_path)):
                default_path = os.path.join(os.path.expanduser("~"), default_name)

            path, _ = QFileDialog.getSaveFileName(
                self,
                "ذخیره گزارش مدیریتی HTML",
                default_path,
                "HTML Files (*.html);;All Files (*)"
            )
            if not path:
                return

            if not path.lower().endswith(".html"):
                path += ".html"

            # ذخیره فایل
            with open(path, "w", encoding="utf-8") as f:
                f.write(html_content)

            # پیشنهاد باز کردن فایل
            reply = QMessageBox.question(
                self,
                "✅ گزارش تولید شد",
                f"گزارش مدیریتی با موفقیت در مسیر زیر ذخیره شد:\n\n{path}\n\n"
                "آیا مایلید فایل را در مرورگر باز کنید؟",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply == QMessageBox.StandardButton.Yes:
                QDesktopServices.openUrl(QUrl.fromLocalFile(path))

        except Exception as exc:
            logger.exception("Failed to export HTML report")
            QMessageBox.critical(
                self, "خطا در تولید گزارش",
                f"تولید گزارش HTML با خطا مواجه شد:\n\n{exc}"
            )

    def _build_html_content(
        self,
        metrics: Dict[str, int],
        overdue_rows: List[Meeting],
        due_rows: List[Meeting],
        waiting_rows: List[Meeting],
        specialists: Dict[int, str],
        today: date,
    ) -> str:
        """تولید محتوای HTML جامع و حرفه‌ای برای ارسال به مدیریت."""
        now = datetime.now()
        report_date_shamsi = today_shamsi()
        report_time = now.strftime("%H:%M:%S")

        # ساخت کارت‌های آماری در HTML
        cards_html = self._build_html_cards(metrics)

        # ساخت جداول سه‌گانه
        overdue_table = self._build_html_table(
            overdue_rows, specialists, today,
            table_type="overdue",
            title="⚠️ پرونده‌های دارای تاخیر زمانی",
            theme_color="#b91c1c",
            bg_color="#fef2f2",
        )

        due_table = self._build_html_table(
            due_rows, specialists, today,
            table_type="due",
            title="⏳ پرونده‌های نزدیک به سررسید (۳ روز آینده)",
            theme_color="#b45309",
            bg_color="#fffbeb",
        )

        waiting_table = self._build_html_table(
            waiting_rows, specialists, today,
            table_type="waiting",
            title="📨 پرونده‌های منتظر ابلاغ به پیمانکار",
            theme_color="#7e22ce",
            bg_color="#faf5ff",
        )

        # ─── نکات مدیریتی هوشمند ───
        insights_html = self._build_insights_html(metrics, overdue_rows, due_rows, waiting_rows)

        return f"""<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>گزارش مدیریتی داشبورد عملیاتی MOM - {escape(report_date_shamsi)}</title>
    <style>
        @media print {{
            body {{ margin: 0; padding: 15mm; }}
            .no-print {{ display: none !important; }}
            .page-break {{ page-break-before: always; }}
        }}
        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}
        body {{
            font-family: 'Vazirmatn', 'B Nazanin', 'Tahoma', Arial, sans-serif;
            background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%);
            color: #0f172a;
            padding: 20px;
            direction: rtl;
            line-height: 1.6;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: #ffffff;
            border-radius: 12px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.08);
            overflow: hidden;
        }}
        .header {{
            background: linear-gradient(135deg, #005f73 0%, #0a9396 50%, #00ADB5 100%);
            color: white;
            padding: 30px 40px;
            text-align: center;
            position: relative;
        }}
        .header::after {{
            content: '';
            position: absolute;
            bottom: -1px;
            left: 0;
            right: 0;
            height: 4px;
            background: linear-gradient(90deg, #fbbf24, #ef4444, #a855f7, #22c55e);
        }}
        .header h1 {{
            font-size: 24px;
            font-weight: 900;
            margin-bottom: 8px;
            text-shadow: 0 2px 4px rgba(0,0,0,0.2);
        }}
        .header .subtitle {{
            font-size: 14px;
            opacity: 0.95;
            margin-bottom: 12px;
        }}
        .header .meta {{
            display: inline-block;
            background: rgba(255,255,255,0.15);
            padding: 6px 18px;
            border-radius: 20px;
            font-size: 12px;
            backdrop-filter: blur(10px);
        }}
        .content {{
            padding: 30px 40px;
        }}
        .section-title {{
            font-size: 18px;
            font-weight: bold;
            color: #0f172a;
            margin: 30px 0 15px 0;
            padding-bottom: 10px;
            border-bottom: 2px solid #e2e8f0;
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .section-title .badge {{
            font-size: 12px;
            background: #0284c7;
            color: white;
            padding: 3px 10px;
            border-radius: 12px;
            font-weight: normal;
        }}
        .cards-grid {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 15px;
            margin: 20px 0;
        }}
        .card {{
            padding: 20px;
            border-radius: 10px;
            border: 1px solid;
            border-top: 4px solid;
            position: relative;
            transition: transform 0.2s;
        }}
        .card:hover {{
            transform: translateY(-2px);
            box-shadow: 0 8px 20px rgba(0,0,0,0.08);
        }}
        .card .card-title {{
            font-size: 12px;
            font-weight: bold;
            margin-bottom: 10px;
            opacity: 0.85;
        }}
        .card .card-value {{
            font-size: 32px;
            font-weight: 900;
            font-variant-numeric: tabular-nums;
        }}
        .insights-box {{
            background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
            border-right: 4px solid #f59e0b;
            padding: 18px 24px;
            border-radius: 8px;
            margin: 25px 0;
        }}
        .insights-box h3 {{
            color: #78350f;
            font-size: 15px;
            margin-bottom: 10px;
        }}
        .insights-box ul {{
            list-style: none;
            padding: 0;
        }}
        .insights-box li {{
            padding: 6px 0;
            color: #78350f;
            font-size: 13px;
            display: flex;
            align-items: start;
            gap: 8px;
        }}
        .insights-box li::before {{
            content: '◆';
            color: #d97706;
            font-size: 10px;
            margin-top: 6px;
        }}
        .table-wrapper {{
            background: white;
            border-radius: 10px;
            overflow: hidden;
            margin: 15px 0 30px 0;
            border: 1px solid #e2e8f0;
        }}
        .table-header {{
            padding: 14px 20px;
            font-weight: bold;
            font-size: 14px;
            color: white;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .table-header .count {{
            background: rgba(255,255,255,0.25);
            padding: 3px 12px;
            border-radius: 12px;
            font-size: 12px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 12px;
        }}
        th {{
            background: #f8fafc;
            color: #334155;
            padding: 12px 10px;
            text-align: right;
            font-weight: bold;
            border-bottom: 2px solid #e2e8f0;
            font-size: 12px;
        }}
        td {{
            padding: 10px;
            border-bottom: 1px solid #f1f5f9;
            color: #334155;
            font-size: 12px;
        }}
        tr:hover td {{
            background: #f8fafc;
        }}
        tr:nth-child(even) td {{
            background: #fafbfc;
        }}
        tr:nth-child(even):hover td {{
            background: #f1f5f9;
        }}
        .status-badge {{
            display: inline-block;
            padding: 3px 10px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: bold;
        }}
        .badge-danger {{ background: #fee2e2; color: #991b1b; }}
        .badge-warning {{ background: #fef3c7; color: #b45309; }}
        .badge-info {{ background: #dbeafe; color: #1e40af; }}
        .badge-purple {{ background: #f3e8ff; color: #7e22ce; }}
        .empty-row {{
            text-align: center;
            padding: 30px;
            color: #94a3b8;
            font-style: italic;
        }}
        .footer {{
            background: #0f172a;
            color: #cbd5e1;
            padding: 20px 40px;
            text-align: center;
            font-size: 11px;
        }}
        .footer .system-name {{
            color: #00ADB5;
            font-weight: bold;
            margin-bottom: 5px;
        }}
        .print-btn {{
            position: fixed;
            top: 20px;
            left: 20px;
            background: #0284c7;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 8px;
            cursor: pointer;
            font-family: inherit;
            font-size: 13px;
            font-weight: bold;
            box-shadow: 0 4px 12px rgba(2,132,199,0.3);
            transition: all 0.2s;
        }}
        .print-btn:hover {{
            background: #0369a1;
            transform: translateY(-2px);
        }}
        .mono {{
            font-family: 'Consolas', 'Monaco', monospace;
            direction: ltr;
            display: inline-block;
        }}
    </style>
</head>
<body>
    <button class="print-btn no-print" onclick="window.print()">🖨️ چاپ گزارش</button>

    <div class="container">
        <!-- سربرگ -->
        <div class="header">
            <h1>📊 گزارش مدیریتی داشبورد عملیاتی</h1>
            <div class="subtitle">سامانه جامع مدیریت، پیگیری هوشمند و گردش‌کار صورتجلسات (MOM)</div>
            <div class="meta">
                📅 تاریخ گزارش: {escape(report_date_shamsi)} &nbsp;|&nbsp; ⏰ ساعت: {escape(report_time)}
            </div>
        </div>

        <div class="content">
            <!-- کارت‌های آماری -->
            <div class="section-title">
                <span>📈 شاخص‌های کلیدی عملکرد (KPI)</span>
                <span class="badge">Real-Time</span>
            </div>
            {cards_html}

            <!-- نکات مدیریتی -->
            {insights_html}

            <!-- جدول تاخیرات -->
            {overdue_table}

            <!-- جدول سررسیدها -->
            {due_table}

            <!-- جدول منتظر ابلاغ -->
            {waiting_table}
        </div>

        <!-- فوتر -->
        <div class="footer">
            <div class="system-name">Document & MOM Tracking System — نسخه ۳.۰</div>
            <div>این گزارش به صورت خودکار توسط سامانه تولید شده است. | تولید در {escape(now.strftime("%Y-%m-%d %H:%M:%S"))}</div>
        </div>
    </div>
</body>
</html>
"""

    def _build_html_cards(self, metrics: Dict[str, int]) -> str:
        """ساخت کارت‌های آماری در قالب HTML."""
        cards_def = [
            ("کل پرونده‌ها", "total", "📁"),
            ("در جریان پیگیری", "open", "⚡"),
            ("دارای تاخیر زمانی", "overdue", "⚠️"),
            ("سررسید ۳ روز آینده", "due_3", "⏳"),
            ("منتظر ابلاغ به پیمانکار", "waiting_contractor", "📨"),
            ("ابلاغ‌شده به پیمانکار", "answered", "📩"),
            ("تکمیل و بسته‌شده", "completed", "✅"),
        ]

        cards_html_parts = ['<div class="cards-grid">']
        for title, key, icon in cards_def:
            theme = CARD_THEMES.get(key, CARD_THEMES["total"])
            value = int(metrics.get(key, 0))
            cards_html_parts.append(f"""
                <div class="card" style="background: {theme['bg']}; border-color: {theme['border']}; border-top-color: {theme['accent']};">
                    <div class="card-title" style="color: {theme['text']};">{icon} {escape(title)}</div>
                    <div class="card-value" style="color: {theme['text']};">{value:,}</div>
                </div>
            """)
        cards_html_parts.append('</div>')
        return "".join(cards_html_parts)

    def _build_insights_html(
        self,
        metrics: Dict[str, int],
        overdue: List[Meeting],
        due: List[Meeting],
        waiting: List[Meeting],
    ) -> str:
        """تولید بخش نکات مدیریتی هوشمند و تحلیل‌های خودکار."""
        insights = []

        total = int(metrics.get("total", 0))
        overdue_count = int(metrics.get("overdue", 0))
        due3_count = int(metrics.get("due_3", 0))
        completed = int(metrics.get("completed", 0))
        waiting_count = int(metrics.get("waiting_contractor", 0))

        # تحلیل تاخیرات
        if overdue_count > 0:
            pct = (overdue_count / total * 100) if total else 0
            insights.append(
                f"<strong>{overdue_count:,}</strong> پرونده ({pct:.1f}٪ از کل) از مهلت انجام عبور کرده و نیازمند اقدام فوری است."
            )

        # تحلیل سررسیدهای نزدیک
        if due3_count > 0:
            insights.append(
                f"<strong>{due3_count:,}</strong> پرونده در ۳ روز آینده سررسید می‌شود و باید در اولویت رسیدگی قرار گیرد."
            )

        # تحلیل نرخ تکمیل
        if total > 0:
            completion_rate = (completed / total * 100)
            if completion_rate >= 80:
                insights.append(
                    f"✅ نرخ تکمیل پرونده‌ها <strong>{completion_rate:.1f}٪</strong> است که وضعیت مطلوبی را نشان می‌دهد."
                )
            elif completion_rate >= 50:
                insights.append(
                    f"⚡ نرخ تکمیل پرونده‌ها <strong>{completion_rate:.1f}٪</strong> است؛ نیاز به شتاب‌بخشی در فرآیندها احساس می‌شود."
                )
            else:
                insights.append(
                    f"⚠️ نرخ تکمیل پرونده‌ها <strong>{completion_rate:.1f}٪</strong> است که پایین‌تر از حد استاندارد بوده و نیازمند بازنگری فرآیندهاست."
                )

        # تحلیل حجم انتظار
        if waiting_count > 10:
            insights.append(
                f"📨 <strong>{waiting_count:,}</strong> پرونده در انتظار ابلاغ به پیمانکار قرار دارد که حجم قابل توجهی محسوب می‌شود."
            )

        # پیشنهاد مدیریتی
        if overdue_count == 0 and due3_count == 0:
            insights.append(
                "🎯 در حال حاضر هیچ پرونده تاخیرداری وجود ندارد. عملکرد تیم مطلوب ارزیابی می‌شود."
            )

        if not insights:
            return ""

        items_html = "".join(f"<li>{item}</li>" for item in insights)
        return f"""
        <div class="insights-box">
            <h3>💡 نکات مدیریتی و تحلیل هوشمند</h3>
            <ul>{items_html}</ul>
        </div>
        """

    def _build_html_table(
        self,
        rows: List[Meeting],
        specialists: Dict[int, str],
        today: date,
        table_type: str,
        title: str,
        theme_color: str,
        bg_color: str,
    ) -> str:
        """ساخت جدول HTML برای هر یک از سه فهرست عملیاتی."""
        badge_class = {
            "overdue": "badge-danger",
            "due": "badge-warning",
            "waiting": "badge-purple",
        }.get(table_type, "badge-info")

        # سربرگ جدول
        table_html = f"""
        <div class="section-title">
            <span>{escape(title)}</span>
        </div>
        <div class="table-wrapper">
            <div class="table-header" style="background: {theme_color};">
                <span>جزئیات پرونده‌ها</span>
                <span class="count">تعداد: {len(rows):,}</span>
            </div>
        """

        if not rows:
            table_html += """
            <table>
                <tr><td class="empty-row">✅ در این بخش موردی برای گزارش وجود ندارد</td></tr>
            </table>
            </div>
            """
            return table_html

        # هدر جدول متناسب با نوع
        if table_type == "waiting":
            headers = ["ردیف", "شماره سند", "موضوع", "پیمانکار", "کارفرما", "مهلت انجام", "کارشناس مسئول"]
        else:
            headers = ["ردیف", "شماره سند", "موضوع", "پیمانکار", "مهلت انجام", "وضعیت زمانی", "کارشناس مسئول"]

        headers_html = "".join(f"<th>{escape(h)}</th>" for h in headers)
        table_html += f"<table><thead><tr>{headers_html}</tr></thead><tbody>"

        for idx, m in enumerate(rows, 1):
            due_shamsi = to_shamsi(str(m.due_date)) if m.due_date else "—"
            days_diff = (m.due_date - today).days if m.due_date else 0

            # بج وضعیت
            if table_type == "overdue":
                status_text = f"{abs(days_diff)} روز تاخیر"
            elif table_type == "due":
                if days_diff == 0:
                    status_text = "امروز سررسید"
                elif days_diff == 1:
                    status_text = "فردا سررسید"
                else:
                    status_text = f"{days_diff} روز مانده"
            else:
                status_text = ""

            specialist = specialists.get(m.id, "").strip() or "—"
            subject = m.subject or "—"
            if len(subject) > 80:
                subject = subject[:80] + "…"

            meeting_num = f'<span class="mono">{escape(str(m.meeting_number or "—"))}</span>'
            contractor = escape(m.contractor or "—")
            employer = escape(m.employer or "—")
            subject_esc = escape(subject)
            specialist_esc = escape(specialist)

            if table_type == "waiting":
                row_html = f"""
                <tr>
                    <td>{idx}</td>
                    <td>{meeting_num}</td>
                    <td>{subject_esc}</td>
                    <td>{contractor}</td>
                    <td>{employer}</td>
                    <td><span class="mono">{escape(due_shamsi)}</span></td>
                    <td>{specialist_esc}</td>
                </tr>
                """
            else:
                row_html = f"""
                <tr>
                    <td>{idx}</td>
                    <td>{meeting_num}</td>
                    <td>{subject_esc}</td>
                    <td>{contractor}</td>
                    <td><span class="mono">{escape(due_shamsi)}</span></td>
                    <td><span class="status-badge {badge_class}">{escape(status_text)}</span></td>
                    <td>{specialist_esc}</td>
                </tr>
                """
            table_html += row_html

        table_html += "</tbody></table></div>"
        return table_html

    # ─────────────────────────────────────────────────────────────
    # رویدادهای کاربر
    # ─────────────────────────────────────────────────────────────
    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        """باز کردن دیالوگ ویرایش صورتجلسه با دابل‌کلیک."""
        mid = item.data(Qt.ItemDataRole.UserRole)
        if not mid:
            return

        meeting = self.db.get_meeting(mid)
        if not meeting:
            QMessageBox.warning(self, "خطا", "صورتجلسه مورد نظر یافت نشد.")
            return

        dlg = MeetingDialog(self.db, parent=self, meeting=meeting)
        if dlg.exec() == MeetingDialog.DialogCode.Accepted:
            try:
                self.db.update_meeting(meeting.id, dlg.get_data())
                self.refresh()
            except Exception as exc:
                logger.exception("Failed to update meeting from dashboard")
                QMessageBox.critical(self, "خطا", f"بروزرسانی صورتجلسه ناموفق بود:\n{exc}")

    def closeEvent(self, event) -> None:
        """توقف ایمن تایمر هنگام بستن پنجره."""
        self.timer.stop()
        super().closeEvent(event)

    def reject(self) -> None:
        """توقف ایمن تایمر هنگام انصراف."""
        self.timer.stop()
        super().reject()