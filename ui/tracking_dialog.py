# -*- coding: utf-8 -*-
"""
ui.tracking_dialog
دیالوگ هوشمند پیگیری پرونده، تعیین کارشناس مسئول و رصد زنده عودت‌های گردش کار
نسخه ۲.۱ بهسازی‌شده:
    - همگام‌سازی کامل با قانون طلایی «ارسال به پیمانکار = اتمام کار»
      (شامل حالت پاک‌سازی تاریخ ارسال)
    - رفع ناهماهنگی قبلی `closing_date` — اکنون همیشه هم‌راستا با sent_date
    - ممیزی با کاربر واقعی از session والد
    - نرمال‌سازی ارقام فارسی/عربی در ورودی تاریخ
    - دکمه «پاک کردن تاریخ ارسال» برای رفع اشتباه
    - اعتبارسنجی زنده رنگی ورودی تاریخ
    - ذخیره/بازیابی هندسه دیالوگ
    - استخراج استایل به ثابت ماژول
    - حذف importهای بی‌استفاده
"""
from __future__ import annotations

import logging
import re
from datetime import date
from typing import Dict, Optional, Tuple

from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from config import APP_NAME, ORG_NAME
from db.manager import DatabaseManager
from db.models import Meeting, WorkflowStep
from utils.date_utils import to_gregorian, to_shamsi, today_shamsi

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════
# ثابت‌های ماژول
# ══════════════════════════════════════════════════

# 🎯 گام کلیدی: کارشناس اصلی رسیدگی‌کننده در گام ۳ (ورود به دفتر کارشناس) ذخیره می‌شود
SPECIALIST_STEP_ORDER = 3

# الگوی معتبر تاریخ شمسی (پس از نرمال‌سازی ارقام)
SHAMSI_DATE_PATTERN = re.compile(
    r"^1[34]\d{2}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])$"
)

# نرمال‌سازی ارقام فارسی/عربی به ASCII
_DIGIT_TRANSLATION = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"
)


def _normalize_shamsi_input(value: str) -> str:
    """تبدیل ارقام فارسی/عربی به ASCII و حذف فاصله‌های اضافی."""
    if not value:
        return ""
    value = value.translate(_DIGIT_TRANSLATION)
    return " ".join(value.split())


def _is_valid_shamsi(text: str) -> bool:
    """اعتبارسنجی الگوی تاریخ شمسی (پس از نرمال‌سازی)."""
    return bool(SHAMSI_DATE_PATTERN.match(text or ""))


def _status_fa_to_badge_style(status: str) -> str:
    """بازگرداندن CSS رنگ برای بج وضعیت (منبع واحد)."""
    styles = {
        "تکمیل شده":         "background-color: #dcfce7; color: #15803d; border: 1px solid #bbf7d0;",
        "در دست بررسی":       "background-color: #fef3c7; color: #b45309; border: 1px solid #fde68a;",
        "در انتظار تأیید":    "background-color: #e0f2fe; color: #0369a1; border: 1px solid #bae6fd;",
        "لغو شده":            "background-color: #fee2e2; color: #b91c1c; border: 1px solid #fecaca;",
        "بازگشت داده شده":    "background-color: #ffedd5; color: #c2410c; border: 1px solid #fed7aa; font-weight: bold;",
    }
    default = "background-color: #f1f5f9; color: #475569; border: 1px solid #e2e8f0;"
    return styles.get(status, default)


# ══════════════════════════════════════════════════
# استایل دیالوگ — تنها منبع حقیقت
# ══════════════════════════════════════════════════

_DIALOG_STYLESHEET = """
    QDialog {
        background-color: #f4f7fb;
        font-family: 'Vazirmatn', 'Tahoma', Arial, sans-serif;
    }
    QGroupBox {
        font-size: 12.5px;
        font-weight: bold;
        color: #0f172a;
        border: 1px solid #d7e1ec;
        border-radius: 12px;
        margin-top: 16px;
        padding: 20px 14px 12px 14px;
        background-color: #ffffff;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        subcontrol-position: top right;
        right: 15px;
        padding: 0 8px;
        color: #0369a1;
        background-color: #ffffff;
    }
    QWidget#WarningWidget {
        background-color: #fef2f2;
        border: 1px solid #fca5a5;
        border-radius: 6px;
    }
    QLabel {
        font-size: 12.5px;
        color: #334155;
        padding-top: 2px;
        padding-bottom: 2px;
    }
    QLineEdit, QComboBox {
        border: 1px solid #cbd5e1;
        border-radius: 9px;
        padding: 7px 11px;
        min-height: 30px;
        background: #ffffff;
        color: #0f172a;
        font-size: 12.5px;
    }
    QLineEdit:hover, QComboBox:hover {
        border-color: #94a3b8;
    }
    QLineEdit:focus, QComboBox:focus {
        border: 2px solid #0284c7;
        background: #f8fdff;
    }
    QLineEdit[dateState="ok"] {
        border: 1px solid #10b981;
        background: #ecfdf5;
    }
    QLineEdit[dateState="err"] {
        border: 1px solid #ef4444;
        background: #fef2f2;
    }
    QComboBox QAbstractItemView {
        border: 1px solid #94a3b8;
        background-color: #ffffff;
        color: #000000;
        selection-background-color: #0284c7;
        selection-color: #ffffff;
        outline: none;
    }
    QPushButton {
        font-size: 13px;
        font-weight: bold;
        border-radius: 9px;
        padding: 8px 18px;
        min-height: 32px;
    }
    QPushButton#btn_primary {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0284c7, stop:1 #0369a1);
        color: #ffffff;
        border: none;
    }
    QPushButton#btn_primary:hover {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0369a1, stop:1 #1d4ed8);
    }
    QPushButton#btn_primary:pressed {
        background: #1e3a8a;
    }
    QPushButton#btn_secondary {
        background-color: #ffffff;
        border: 1px solid #cbd5e1;
        color: #475569;
    }
    QPushButton#btn_secondary:hover {
        background-color: #f1f5f9;
        color: #0f172a;
        border-color: #94a3b8;
    }
    QPushButton#btn_today {
        background-color: #ecfdf5;
        color: #047857;
        border: 1px solid #a7f3d0;
        font-size: 12px;
        padding: 5px 10px;
        min-height: 28px;
    }
    QPushButton#btn_today:hover {
        background-color: #a7f3d0;
        color: #064e3b;
    }
    QPushButton#btn_clear {
        background-color: #fef3c7;
        color: #b45309;
        border: 1px solid #fde68a;
        font-size: 12px;
        padding: 5px 10px;
        min-height: 28px;
    }
    QPushButton#btn_clear:hover {
        background-color: #fde68a;
        color: #78350f;
    }
"""


# ══════════════════════════════════════════════════
# دیالوگ اصلی
# ══════════════════════════════════════════════════

class TrackingDialog(QDialog):
    """دیالوگ مدرن پیگیری هوشمند و تعیین کارشناس مسئول پرونده."""

    def __init__(
        self,
        db: DatabaseManager,
        meeting: Meeting,
        current_user: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.db = db
        self.meeting = meeting
        self.current_user = current_user
        self.settings = QSettings(ORG_NAME, APP_NAME)

        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setWindowTitle(f"📈 پیگیری پرونده صورتجلسه: {meeting.meeting_number}")
        self.resize(720, 640)
        self.setMinimumSize(620, 540)

        self._fields: Dict[str, QWidget] = {}
        self._last_live_status: str = "نامشخص"

        self._build_ui()
        self._restore_geometry()
        self._load_live_data()
        self.setStyleSheet(_DIALOG_STYLESHEET)

    # ─────────────────────────────────────────────
    # ساخت رابط کاربری
    # ─────────────────────────────────────────────
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 15)
        root.setSpacing(12)

        header = QLabel("📈 جزئیات پیگیری، تعیین کارشناس و بازخوانی زنده وضعیت پرونده")
        header.setStyleSheet("font-size: 15px; font-weight: bold; color: #0284c7;")
        root.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll_content = QWidget()
        self.form_layout = QVBoxLayout(scroll_content)
        self.form_layout.setContentsMargins(0, 0, 0, 0)
        self.form_layout.setSpacing(12)

        self.form_layout.addWidget(self._build_live_status_card())
        self.form_layout.addWidget(self._build_info_group())
        self.form_layout.addWidget(self._build_dispatch_group())

        scroll.setWidget(scroll_content)
        root.addWidget(scroll, stretch=1)

        root.addLayout(self._build_action_buttons())

    def _build_live_status_card(self) -> QGroupBox:
        """کارت نمایش زنده وضعیت گردش کار و علت عودت احتمالی سند."""
        box = QGroupBox("📡 رصد زنده وضعیت گردش کار (بدون نیاز به ورود دستی)")
        box.setObjectName("StatusCardBox")
        layout = QVBoxLayout(box)
        layout.setSpacing(10)

        state_row = QHBoxLayout()
        self.lbl_meeting_status_badge = QLabel("نامشخص")
        self.lbl_meeting_status_badge.setObjectName("StatusBadge")
        self.lbl_meeting_status_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_meeting_status_badge.setFixedSize(160, 28)

        self.lbl_workflow_step_info = QLabel("در حال واکشی اطلاعات...")
        self.lbl_workflow_step_info.setStyleSheet(
            "font-size: 12.5px; font-weight: bold; color: #1e293b;"
        )
        self.lbl_workflow_step_info.setWordWrap(True)

        state_row.addWidget(self.lbl_meeting_status_badge)
        state_row.addWidget(self.lbl_workflow_step_info, stretch=1)
        layout.addLayout(state_row)

        # پنل هشدار عودت
        self.return_warning_widget = QWidget()
        self.return_warning_widget.setObjectName("WarningWidget")
        warn_layout = QVBoxLayout(self.return_warning_widget)
        warn_layout.setContentsMargins(12, 12, 12, 12)
        warn_layout.setSpacing(6)

        warn_title = QLabel("⚠️ هشدار عودت سند جهت اصلاح:")
        warn_title.setStyleSheet(
            "font-weight: bold; color: #991b1b; font-size: 12px;"
        )
        self.lbl_return_reason = QLabel("توضیحی ثبت نشده است.")
        self.lbl_return_reason.setWordWrap(True)
        self.lbl_return_reason.setStyleSheet(
            "color: #7f1d1d; font-size: 12px; font-style: italic;"
        )

        warn_layout.addWidget(warn_title)
        warn_layout.addWidget(self.lbl_return_reason)
        layout.addWidget(self.return_warning_widget)
        self.return_warning_widget.setVisible(False)

        return box

    def _build_info_group(self) -> QGroupBox:
        box = QGroupBox("📋 مشخصات شناسنامه‌ای و تعیین کارشناس مسئول")
        form = QFormLayout(box)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(12)

        self.lbl_num = QLabel(self.meeting.meeting_number)
        self.lbl_num.setStyleSheet(
            "font-weight: bold; font-size: 13px; color: #0f172a;"
        )
        self.lbl_subject = QLabel(self.meeting.subject)
        self.lbl_subject.setWordWrap(True)
        self.lbl_employer = QLabel(self.meeting.employer or "—")
        self.lbl_contractor = QLabel(self.meeting.contractor or "—")

        m_date = (
            to_shamsi(self.meeting.meeting_date.isoformat())
            if self.meeting.meeting_date else "—"
        )
        d_date = (
            to_shamsi(self.meeting.due_date.isoformat())
            if self.meeting.due_date else "—"
        )
        self.lbl_dates = QLabel(
            f"تاریخ صورتجلسه: {m_date}  |  مهلت اقدام: {d_date}"
        )
        self.lbl_dates.setStyleSheet("color: #0369a1; font-weight: bold;")

        self.cb_responsible_user = QComboBox()
        self.cb_responsible_user.setMinimumHeight(30)
        self.cb_responsible_user.setToolTip(
            "کارشناس منتخب دپارتمان جهت رسیدگی و پاسخگویی این پرونده.\n"
            "این نام در صفحه اصلی و داشبورد به عنوان مسئول اصلی نمایش داده خواهد شد."
        )

        hint_expert = QLabel(
            "💡 این کارشناس در گام ۳ گردش کار (کارشناس اصلی) ثبت می‌شود."
        )
        hint_expert.setStyleSheet(
            "color: #64748b; font-size: 10.5px; font-style: italic;"
        )

        form.addRow("شماره صورتجلسه:", self.lbl_num)
        form.addRow("موضوع:", self.lbl_subject)
        form.addRow("کارفرما:", self.lbl_employer)
        form.addRow("پیمانکار:", self.lbl_contractor)
        form.addRow("زمان‌بندی:", self.lbl_dates)
        form.addRow("👤 کارشناس مسئول (رسیدگی‌کننده):", self.cb_responsible_user)
        form.addRow("", hint_expert)

        return box

    def _build_dispatch_group(self) -> QGroupBox:
        """بخش ثبت تاریخ ارسال به پیمانکار (پایان کار)."""
        box = QGroupBox("📤 ثبت تاریخ ابلاغ به پیمانکار (اقدام پایانی)")
        form = QFormLayout(box)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(10)

        self.ed_sent_date = QLineEdit()
        self.ed_sent_date.setPlaceholderText("مثال: ۱۴۰۴-۰۱-۱۵")
        self.ed_sent_date.setToolTip(
            "تاریخی که سند برای پیمانکار صادر و ابلاغ شد (این تاریخ پایان کار است)"
        )
        self.ed_sent_date.textChanged.connect(self._on_sent_date_changed)

        # دکمه‌های سریع
        today_btn = QPushButton("📅 امروز")
        today_btn.setObjectName("btn_today")
        today_btn.setToolTip("درج سریع تاریخ امروز")
        today_btn.setFixedWidth(80)
        today_btn.clicked.connect(lambda: self.ed_sent_date.setText(today_shamsi()))

        clear_btn = QPushButton("🗑 پاک")
        clear_btn.setObjectName("btn_clear")
        clear_btn.setToolTip("پاک کردن تاریخ ارسال (در صورت اشتباه در ثبت)")
        clear_btn.setFixedWidth(80)
        clear_btn.clicked.connect(self._clear_sent_date)

        sent_row = QHBoxLayout()
        sent_row.setSpacing(6)
        sent_row.addWidget(self.ed_sent_date, stretch=1)
        sent_row.addWidget(today_btn)
        sent_row.addWidget(clear_btn)
        sent_container = QWidget()
        sent_container.setLayout(sent_row)

        hint = QLabel(
            "💡 با ثبت تاریخ ارسال، پرونده به‌طور خودکار «تکمیل شده» و "
            "تمام گام‌های باقی‌مانده گردش کار بسته می‌شوند."
        )
        hint.setStyleSheet(
            "color: #16a34a; font-size: 11px; font-style: italic;"
        )
        hint.setWordWrap(True)

        form.addRow("تاریخ ارسال به پیمانکار:", sent_container)
        form.addRow("", hint)

        return box

    def _build_action_buttons(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        bar.setSpacing(10)

        self.btn_save = QPushButton("💾 ذخیره تغییرات پیگیری")
        self.btn_save.setObjectName("btn_primary")
        self.btn_save.setMinimumHeight(35)
        self.btn_save.clicked.connect(self._save_data)

        self.btn_cancel = QPushButton("انصراف")
        self.btn_cancel.setObjectName("btn_secondary")
        self.btn_cancel.setMinimumHeight(35)
        self.btn_cancel.clicked.connect(self.reject)

        bar.addWidget(self.btn_save, stretch=2)
        bar.addWidget(self.btn_cancel, stretch=1)
        return bar

    # ─────────────────────────────────────────────
    # ذخیره/بازیابی هندسه
    # ─────────────────────────────────────────────

    def _restore_geometry(self) -> None:
        g = self.settings.value("tracking_dialog_geometry")
        if g:
            self.restoreGeometry(g)

    def _save_geometry(self) -> None:
        self.settings.setValue("tracking_dialog_geometry", self.saveGeometry())

    def closeEvent(self, event) -> None:
        self._save_geometry()
        super().closeEvent(event)

    def reject(self) -> None:
        self._save_geometry()
        super().reject()

    # ─────────────────────────────────────────────
    # اعتبارسنجی زنده
    # ─────────────────────────────────────────────

    def _on_sent_date_changed(self, text: str) -> None:
        """رنگ‌آمیزی زنده ورودی تاریخ بر اساس اعتبار (بدون اعمال بر DB)."""
        normalized = _normalize_shamsi_input(text)
        if not normalized:
            state = ""
        elif _is_valid_shamsi(normalized):
            state = "ok"
        else:
            state = "err"

        if self.ed_sent_date.property("dateState") == state:
            return
        self.ed_sent_date.setProperty("dateState", state)
        self.ed_sent_date.style().unpolish(self.ed_sent_date)
        self.ed_sent_date.style().polish(self.ed_sent_date)
        self.ed_sent_date.update()

    def _clear_sent_date(self) -> None:
        """پاک‌سازی تاریخ ارسال با تأیید کاربر (چون قانون طلایی را برمی‌گرداند)."""
        if not self.ed_sent_date.text().strip():
            return
        reply = QMessageBox.question(
            self,
            "پاک کردن تاریخ ارسال",
            "با پاک کردن این تاریخ:\n"
            "• پرونده از «تکمیل شده» خارج می‌شود.\n"
            "• تاریخ بسته‌شدن و پاسخ پیمانکار نیز پاک می‌شوند.\n\n"
            "ادامه می‌دهید؟",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.ed_sent_date.clear()
            self._on_sent_date_changed("")

    # ─────────────────────────────────────────────
    # بارگذاری هوشمند اطلاعات زنده
    # ─────────────────────────────────────────────
    def _load_live_data(self) -> None:
        """بارگذاری اطلاعات پرونده، کاربران سیستم و محاسبه وضعیت زنده."""
        # ۱. نمایش تاریخ ارسال فعلی (در صورت وجود)
        if self.meeting.sent_to_contractor_date:
            self.ed_sent_date.setText(
                to_shamsi(self.meeting.sent_to_contractor_date.isoformat())
            )
            self._on_sent_date_changed(self.ed_sent_date.text())

        # ۲. واکشی کاربران فعال
        try:
            usernames = self.db.active_usernames() or []
            if not usernames:
                usernames = ["admin"]
            self.cb_responsible_user.clear()
            self.cb_responsible_user.addItems(usernames)
        except Exception as exc:
            logger.warning("Failed to fetch system users list: %s", exc)
            self.cb_responsible_user.clear()
            self.cb_responsible_user.addItems(["admin"])

        # ۳. رصد زنده وضعیت گردش کار
        try:
            with self.db.session() as sess:
                steps = (
                    sess.query(WorkflowStep)
                    .filter(WorkflowStep.meeting_id == self.meeting.id)
                    .order_by(WorkflowStep.step_order.asc())
                    .all()
                )

                current_step = next(
                    (s for s in steps if s.status in ("pending", "in_progress")),
                    None,
                )
                rejected_step = next(
                    (s for s in reversed(steps) if s.status == "rejected"),
                    None,
                )

                # 🎯 اولویت: کارشناس گام ۳ (کارشناس اصلی رسیدگی‌کننده)
                specialist_step = next(
                    (s for s in steps if s.step_order == SPECIALIST_STEP_ORDER),
                    None,
                )
                assigned_expert = None
                if specialist_step and specialist_step.responsible_person:
                    assigned_expert = specialist_step.responsible_person.strip()

                # fallback: کارشناس گام فعال یا آخرین گام
                if not assigned_expert:
                    fallback = current_step if current_step else (steps[-1] if steps else None)
                    if fallback and fallback.responsible_person:
                        assigned_expert = fallback.responsible_person.strip()

                if assigned_expert:
                    idx = self.cb_responsible_user.findText(assigned_expert)
                    if idx >= 0:
                        self.cb_responsible_user.setCurrentIndex(idx)
                    else:
                        self.cb_responsible_user.addItem(assigned_expert)
                        self.cb_responsible_user.setCurrentText(assigned_expert)

                # ۴. محاسبه وضعیت زنده (اولویت قوانین)
                if self.meeting.sent_to_contractor_date is not None:
                    live_status = "تکمیل شده"
                elif rejected_step:
                    live_status = "بازگشت داده شده"
                elif steps and all(s.status in ("completed", "skipped") for s in steps):
                    live_status = "تکمیل شده"
                elif current_step:
                    live_status = "در انتظار تأیید"
                else:
                    live_status = "در دست بررسی"

                self._last_live_status = live_status
                self._update_status_badge(live_status)

                # ۵. متن توصیفی وضعیت
                if self.meeting.sent_to_contractor_date is not None:
                    sent_sh = to_shamsi(
                        self.meeting.sent_to_contractor_date.isoformat()
                    )
                    self.lbl_workflow_step_info.setText(
                        f"✅ سند در تاریخ {sent_sh} به پیمانکار ابلاغ و "
                        "پرونده مختومه شده است."
                    )
                elif current_step:
                    resp_display = current_step.responsible_person or "—"
                    if resp_display == "admin":
                        resp_display = "مدیر سیستم (admin)"
                    self.lbl_workflow_step_info.setText(
                        f"پرونده نزد کارشناس: «{resp_display}» "
                        f"در گام «{current_step.step_name}» می‌باشد."
                    )
                elif steps:
                    self.lbl_workflow_step_info.setText(
                        "پرونده در جریان رسیدگی قرار دارد."
                    )
                else:
                    self.lbl_workflow_step_info.setText(
                        "گردش کار برای این پرونده هنوز راه‌اندازی نشده است."
                    )

                # ۶. هشدار عودت (در صورت وجود و عدم ابلاغ نهایی)
                if rejected_step and self.meeting.sent_to_contractor_date is None:
                    self.lbl_return_reason.setText(
                        f"توسط کارشناس «{rejected_step.responsible_person or 'نامشخص'}» "
                        f"در گام «{rejected_step.step_name}» برگشت داده شده است.\n"
                        f"📝 علت عودت: {rejected_step.notes or 'توضیحی ثبت نشده است.'}"
                    )
                    self.return_warning_widget.setVisible(True)
                else:
                    self.return_warning_widget.setVisible(False)

        except Exception:
            logger.exception("Failed to query live status card data")
            self.lbl_workflow_step_info.setText(
                "⚠️ خطا در برقراری ارتباط زنده با بخش گردش کار!"
            )

    def _update_status_badge(self, status: str) -> None:
        """تغییر بصری بَج وضعیت (بر اساس منبع واحد رنگ‌ها)."""
        self.lbl_meeting_status_badge.setText(status)
        style = _status_fa_to_badge_style(status)
        self.lbl_meeting_status_badge.setStyleSheet(
            f"border-radius: 4px; font-weight: bold; {style}"
        )

    # ─────────────────────────────────────────────
    # ذخیره اطلاعات
    # ─────────────────────────────────────────────

    def _get_audit_user(self) -> Tuple[Optional[int], str]:
        """دریافت (user_id, username) واقعی از session والد در صورت دسترسی."""
        ps = getattr(self.parent(), "session", None)
        if ps is not None:
            return (
                getattr(ps, "user_id", None),
                getattr(ps, "username", self.current_user),
            )
        return None, self.current_user

    def _save_data(self) -> None:
        """
        ثبت تاریخ ارسال و کارشناس مسئول جدید در پایگاه داده.
        - کارشناس منتخب روی گام ۳ (کارشناس اصلی) ذخیره می‌شود.
        - قانون طلایی به‌صورت کامل با closing_date هم‌راستا می‌شود
          (هم در حالت ثبت، هم در حالت پاک‌سازی).
        """
        sent_raw = _normalize_shamsi_input(self.ed_sent_date.text())
        selected_expert = self.cb_responsible_user.currentText().strip()

        # اعتبارسنجی کارشناس
        if not selected_expert:
            QMessageBox.warning(
                self, "کارشناس نامعتبر",
                "لطفاً یک کارشناس مسئول را از فهرست انتخاب کنید."
            )
            return

        # اعتبارسنجی تاریخ ارسال (در صورت پر بودن)
        g_sent: Optional[date] = None
        if sent_raw:
            if not _is_valid_shamsi(sent_raw):
                QMessageBox.warning(
                    self, "تاریخ ارسال نامعتبر",
                    "فرمت تاریخ ارسال نامعتبر است.\n\n"
                    "الگوی صحیح: ۱۴۰۴-۰۱-۱۵ (سال-ماه-روز)"
                )
                return
            try:
                g_sent_str = to_gregorian(sent_raw)
                g_sent = date.fromisoformat(g_sent_str) if g_sent_str else None
            except Exception as exc:
                QMessageBox.warning(
                    self, "تاریخ ارسال نامعتبر",
                    f"تبدیل تاریخ شمسی به میلادی با شکست مواجه شد:\n{exc}"
                )
                return

        try:
            with self.db.session() as sess:
                m_obj = sess.get(Meeting, self.meeting.id)
                if not m_obj:
                    raise RuntimeError("پرونده در پایگاه داده یافت نشد.")

                # ۱. قانون طلایی کامل: هم در ثبت، هم در پاک‌سازی
                #    (رفع ناهماهنگی قبلی که با main_window._apply_live_status مطابقت نداشت)
                m_obj.sent_to_contractor_date = g_sent
                m_obj.closing_date = g_sent
                m_obj.contractor_response_date = g_sent

                # ۲. 🎯 ذخیره کارشناس روی گام ۳ (کارشناس اصلی)
                specialist_step = (
                    sess.query(WorkflowStep)
                    .filter(
                        WorkflowStep.meeting_id == self.meeting.id,
                        WorkflowStep.step_order == SPECIALIST_STEP_ORDER,
                    )
                    .first()
                )
                if specialist_step:
                    specialist_step.responsible_person = selected_expert
                else:
                    logger.warning(
                        "Specialist step (order=%s) not found for meeting %s; "
                        "workflow may not be initialized.",
                        SPECIALIST_STEP_ORDER, self.meeting.id,
                    )

                # ۳. اگر گام فعالی بدون مسئول داریم، به همان کارشناس نسبت بده
                active_step = (
                    sess.query(WorkflowStep)
                    .filter(
                        WorkflowStep.meeting_id == self.meeting.id,
                        WorkflowStep.status.in_(["pending", "in_progress"]),
                    )
                    .order_by(WorkflowStep.step_order.asc())
                    .first()
                )
                if active_step and not (active_step.responsible_person or "").strip():
                    active_step.responsible_person = selected_expert

                sess.commit()

            # ۴. لاگ ممیزی با کاربر واقعی
            uid, uname = self._get_audit_user()
            self.db.audit(
                uid, uname, "MEETING_TRACKING_UPDATE",
                f"Assigned expert='{selected_expert}' | sent_date={g_sent} "
                f"for MOM ID: {self.meeting.id}",
                meeting_id=self.meeting.id,
            )

            # ۵. پیام موفقیت
            msg_parts = [f"کارشناس مسئول: «{selected_expert}»"]
            if g_sent:
                msg_parts.append(f"تاریخ ارسال به پیمانکار: {sent_raw}")
                msg_parts.append("⚠️ پرونده به وضعیت «تکمیل شده» تغییر یافت.")
            else:
                msg_parts.append("ℹ️ تاریخ ارسال پاک شد؛ پرونده به چرخه پیگیری بازگشت.")

            QMessageBox.information(
                self, "✅ ذخیره موفق",
                "اطلاعات پیگیری با موفقیت ذخیره شد:\n\n" + "\n".join(msg_parts),
            )
            self.accept()

        except Exception as exc:
            logger.exception("Failed to save tracking details")
            QMessageBox.critical(
                self, "خطا در ذخیره‌سازی",
                f"ذخیره‌سازی اطلاعات با شکست مواجه شد:\n{exc}",
            )
