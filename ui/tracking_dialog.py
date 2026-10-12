# -*- coding: utf-8 -*-
"""
ui.tracking_dialog
دیالوگ هوشمند پیگیری پرونده، تعیین کارشناس مسئول و رصد زنده عودت‌های گردش کار
نسخه نهایی هماهنگ با ساختار جدید:
    - حذف کامل فیلدهای منسوخ وضعیت پاسخ پیمانکار
    - همگام‌سازی با قانون طلایی «ارسال به پیمانکار = اتمام کار»
    - ذخیره کارشناس منتخب دقیقاً روی گام ۳ (کارشناس اصلی رسیدگی‌کننده)
      تا در صفحه اصلی و داشبورد به‌درستی نمایش داده شود
    - اعتبارسنجی دقیق تاریخ شمسی و پشتیبانی از تقویم رسمی
"""
from __future__ import annotations

import logging
import re
from datetime import date
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont
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

from db.manager import DatabaseManager
from db.models import Meeting, WorkflowStep, User
from utils.date_utils import to_gregorian, to_shamsi, today_shamsi

logger = logging.getLogger(__name__)

# 🎯 گام کلیدی: کارشناس اصلی رسیدگی‌کننده در گام ۳ (ورود به دفتر کارشناس) ذخیره می‌شود
SPECIALIST_STEP_ORDER = 3

# الگوی معتبر تاریخ شمسی
SHAMSI_DATE_PATTERN = re.compile(r"^1[34]\d{2}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$")


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

        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setWindowTitle(f"📈 پیگیری پرونده صورتجلسه: {meeting.meeting_number}")
        self.resize(720, 640)
        self.setMinimumSize(620, 540)

        self._fields: Dict[str, QWidget] = {}

        self._build_ui()
        self._load_live_data()
        self._apply_style()

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
        self.lbl_workflow_step_info.setStyleSheet("font-size: 12.5px; font-weight: bold; color: #1e293b;")
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
        warn_title.setStyleSheet("font-weight: bold; color: #991b1b; font-size: 12px;")
        self.lbl_return_reason = QLabel("توضیحی ثبت نشده است.")
        self.lbl_return_reason.setWordWrap(True)
        self.lbl_return_reason.setStyleSheet("color: #7f1d1d; font-size: 12px; font-style: italic;")

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
        self.lbl_num.setStyleSheet("font-weight: bold; font-size: 13px; color: #0f172a;")
        self.lbl_subject = QLabel(self.meeting.subject)
        self.lbl_subject.setWordWrap(True)
        self.lbl_employer = QLabel(self.meeting.employer or "—")
        self.lbl_contractor = QLabel(self.meeting.contractor or "—")

        m_date = to_shamsi(self.meeting.meeting_date.isoformat()) if self.meeting.meeting_date else "—"
        d_date = to_shamsi(self.meeting.due_date.isoformat()) if self.meeting.due_date else "—"
        self.lbl_dates = QLabel(f"تاریخ صورتجلسه: {m_date}  |  مهلت اقدام: {d_date}")
        self.lbl_dates.setStyleSheet("color: #0369a1; font-weight: bold;")

        self.cb_responsible_user = QComboBox()
        self.cb_responsible_user.setMinimumHeight(30)
        self.cb_responsible_user.setToolTip(
            "کارشناس منتخب دپارتمان جهت رسیدگی و پاسخگویی این پرونده.\n"
            "این نام در صفحه اصلی و داشبورد به عنوان مسئول اصلی نمایش داده خواهد شد."
        )

        # راهنمای زیر منوی انتخاب کارشناس
        hint_expert = QLabel("💡 این کارشناس در گام ۳ گردش کار (کارشناس اصلی) ثبت می‌شود.")
        hint_expert.setStyleSheet("color: #64748b; font-size: 10.5px; font-style: italic;")

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
        self.ed_sent_date.setToolTip("تاریخی که سند برای پیمانکار صادر و ابلاغ شد (این تاریخ پایان کار است)")

        # دکمه سریع برای درج امروز
        today_btn = QPushButton("📅 امروز")
        today_btn.setObjectName("btn_today")
        today_btn.setToolTip("درج سریع تاریخ امروز")
        today_btn.setFixedWidth(80)
        today_btn.clicked.connect(lambda: self.ed_sent_date.setText(today_shamsi()))

        sent_row = QHBoxLayout()
        sent_row.setSpacing(6)
        sent_row.addWidget(self.ed_sent_date, stretch=1)
        sent_row.addWidget(today_btn)
        sent_container = QWidget()
        sent_container.setLayout(sent_row)

        hint = QLabel(
            "💡 با ثبت تاریخ ارسال، پرونده به‌طور خودکار «تکمیل شده» و تمام گام‌های باقی‌مانده گردش کار بسته می‌شوند."
        )
        hint.setStyleSheet("color: #16a34a; font-size: 11px; font-style: italic;")
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
    # بارگذاری هوشمند اطلاعات زنده
    # ─────────────────────────────────────────────
    def _load_live_data(self) -> None:
        """بارگذاری هوشمند اطلاعات پرونده، کاربران سیستم و محاسبات وضعیت زنده."""
        # ۱. پر کردن تاریخ ارسال در صورت وجود
        if self.meeting.sent_to_contractor_date:
            self.ed_sent_date.setText(to_shamsi(self.meeting.sent_to_contractor_date.isoformat()))

        # ۲. واکشی کاربران فعال جهت پر کردن منوی کارشناسان
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
                steps = sess.query(WorkflowStep).filter(
                    WorkflowStep.meeting_id == self.meeting.id
                ).order_by(WorkflowStep.step_order.asc()).all()

                current_step = next((s for s in steps if s.status in ("pending", "in_progress")), None)
                rejected_step = next((s for s in reversed(steps) if s.status == "rejected"), None)

                # 🎯 اولویت اصلی: نمایش کارشناس گام ۳ در کومبوباکس (کارشناس اصلی رسیدگی‌کننده)
                specialist_step = next(
                    (s for s in steps if s.step_order == SPECIALIST_STEP_ORDER),
                    None
                )
                assigned_expert = None
                if specialist_step and specialist_step.responsible_person:
                    assigned_expert = specialist_step.responsible_person.strip()

                # اگر گام ۳ کارشناس نداشت، از گام فعال یا آخرین گام استفاده کن
                if not assigned_expert:
                    fallback_step = current_step if current_step else (steps[-1] if steps else None)
                    if fallback_step and fallback_step.responsible_person:
                        assigned_expert = fallback_step.responsible_person.strip()

                # تنظیم کومبوباکس روی کارشناس یافت‌شده
                if assigned_expert:
                    idx = self.cb_responsible_user.findText(assigned_expert)
                    if idx >= 0:
                        self.cb_responsible_user.setCurrentIndex(idx)
                    else:
                        self.cb_responsible_user.addItem(assigned_expert)
                        self.cb_responsible_user.setCurrentText(assigned_expert)

                # ۴. محاسبه وضعیت زنده هماهنگ با قانون طلایی
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

                self._update_status_badge(live_status)

                # ۵. توضیح متنی وضعیت گردش کار
                if self.meeting.sent_to_contractor_date is not None:
                    sent_date_sh = to_shamsi(self.meeting.sent_to_contractor_date.isoformat())
                    self.lbl_workflow_step_info.setText(
                        f"✅ سند در تاریخ {sent_date_sh} به پیمانکار ابلاغ و پرونده مختومه شده است."
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
                    self.lbl_workflow_step_info.setText("پرونده در جریان رسیدگی قرار دارد.")
                else:
                    self.lbl_workflow_step_info.setText("گردش کار برای این پرونده هنوز راه‌اندازی نشده است.")

                # ۶. نمایش هشدار عودت (در صورت وجود و عدم ابلاغ نهایی)
                if rejected_step and self.meeting.sent_to_contractor_date is None:
                    self.lbl_return_reason.setText(
                        f"توسط کارشناس «{rejected_step.responsible_person or 'نامشخص'}» "
                        f"در گام «{rejected_step.step_name}» برگشت داده شده است.\n"
                        f"📝 علت عودت: {rejected_step.notes or 'توضیحی ثبت نشده است.'}"
                    )
                    self.return_warning_widget.setVisible(True)
                else:
                    self.return_warning_widget.setVisible(False)

        except Exception as exc:
            logger.exception("Failed to query live status card data")
            self.lbl_workflow_step_info.setText("⚠️ خطا در برقراری ارتباط زنده با بخش گردش کار!")

    def _update_status_badge(self, status: str) -> None:
        """تغییر بصری بَج وضعیت بر اساس استاندارد سیستم."""
        self.lbl_meeting_status_badge.setText(status)

        styles = {
            "تکمیل شده": "background-color: #dcfce7; color: #15803d; border: 1px solid #bbf7d0;",
            "در دست بررسی": "background-color: #fef3c7; color: #b45309; border: 1px solid #fde68a;",
            "در انتظار تأیید": "background-color: #e0f2fe; color: #0369a1; border: 1px solid #bae6fd;",
            "لغو شده": "background-color: #fee2e2; color: #b91c1c; border: 1px solid #fecaca;",
            "بازگشت داده شده": "background-color: #ffedd5; color: #c2410c; border: 1px solid #fed7aa; font-weight: bold;",
        }

        default_style = "background-color: #f1f5f9; color: #475569; border: 1px solid #e2e8f0;"
        style = styles.get(status, default_style)
        self.lbl_meeting_status_badge.setStyleSheet(f"border-radius: 4px; font-weight: bold; {style}")

    # ─────────────────────────────────────────────
    # ذخیره اطلاعات
    # ─────────────────────────────────────────────
    def _save_data(self) -> None:
        """
        ثبت تاریخ ارسال و کارشناس مسئول جدید در پایگاه داده.
        کارشناس منتخب دقیقاً در گام ۳ (کارشناس اصلی) ذخیره می‌شود تا در صفحه اصلی نمایش داده شود.
        """
        sent_raw = self.ed_sent_date.text().strip()
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
            if not SHAMSI_DATE_PATTERN.match(sent_raw):
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

                # ۱. ثبت تاریخ ارسال و همگام‌سازی با تاریخ پاسخ پیمانکار
                m_obj.sent_to_contractor_date = g_sent
                if g_sent:
                    m_obj.contractor_response_date = g_sent
                    # طبق قانون طلایی، تاریخ بسته شدن نیز هم‌زمان ثبت می‌شود
                    if not m_obj.closing_date:
                        m_obj.closing_date = g_sent

                # ۲. 🎯 ذخیره کارشناس منتخب دقیقاً روی گام ۳ (کارشناس اصلی رسیدگی‌کننده)
                # این گام همان جایی است که در صفحه اصلی و داشبورد به عنوان کارشناس اصلی نمایش داده می‌شود
                specialist_step = sess.query(WorkflowStep).filter(
                    WorkflowStep.meeting_id == self.meeting.id,
                    WorkflowStep.step_order == SPECIALIST_STEP_ORDER
                ).first()

                if specialist_step:
                    specialist_step.responsible_person = selected_expert
                else:
                    logger.warning(
                        "Specialist step (order=%s) not found for meeting %s; workflow may not be initialized.",
                        SPECIALIST_STEP_ORDER, self.meeting.id
                    )

                # ۳. اگر گام فعالی داریم که هنوز مسئول نداشته، آن را نیز به همین کارشناس نسبت بده
                active_step = sess.query(WorkflowStep).filter(
                    WorkflowStep.meeting_id == self.meeting.id,
                    WorkflowStep.status.in_(["pending", "in_progress"])
                ).order_by(WorkflowStep.step_order.asc()).first()

                if active_step and not (active_step.responsible_person or "").strip():
                    active_step.responsible_person = selected_expert

                sess.commit()

            # ۴. ثبت لاگ ممیزی
            self.db.audit(
                None, self.current_user, "MEETING_TRACKING_UPDATE",
                f"Assigned expert='{selected_expert}' | sent_date={g_sent} for MOM ID: {self.meeting.id}",
                meeting_id=self.meeting.id
            )

            # ۵. پیام موفقیت
            msg_parts = [f"کارشناس مسئول: «{selected_expert}»"]
            if g_sent:
                msg_parts.append(f"تاریخ ارسال به پیمانکار: {sent_raw}")
                msg_parts.append("⚠️ پرونده به وضعیت «تکمیل شده» تغییر یافت.")

            QMessageBox.information(
                self, "✅ ذخیره موفق",
                "اطلاعات پیگیری با موفقیت ذخیره شد:\n\n" + "\n".join(msg_parts)
            )
            self.accept()

        except Exception as exc:
            logger.exception("Failed to save tracking details")
            QMessageBox.critical(
                self, "خطا در ذخیره‌سازی",
                f"ذخیره‌سازی اطلاعات با شکست مواجه شد:\n{exc}"
            )

    # ─────────────────────────────────────────────
    # اعمال استایل مدرن
    # ─────────────────────────────────────────────
    def _apply_style(self) -> None:
        self.setStyleSheet("""
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
            QLineEdit:focus, QComboBox:focus {
                border: 2px solid #0284c7;
                background: #f8fdff;
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
            }
            QPushButton#btn_today:hover {
                background-color: #a7f3d0;
                color: #064e3b;
            }
        """)