# -*- coding: utf-8 -*-
"""
ui.meeting_dialog
ماژول دیالوگ ثبت/ویرایش صورتجلسه
نسخه ۵: نوار پیشرفت گرادیانی + پیشنهاد خودکار مهلت انجام (۳ روز بعد) + Toast بصری
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QTimer,
    Qt,
)
from PyQt6.QtGui import QColor, QFont, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from db.manager import DatabaseManager
from db.models import DISCIPLINES, Meeting
from utils.date_utils import to_gregorian, to_shamsi, today_shamsi

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# ثابت‌های ماژول
# ─────────────────────────────────────────────

REQUIRED_FIELDS: Dict[str, str] = {
    "meeting_number": "شماره صورتجلسه",
    "subject": "موضوع",
    "meeting_date": "تاریخ صورتجلسه",
    "due_date": "مهلت انجام",
}

PROGRESS_FIELDS: Dict[str, int] = {
    "meeting_number": 2,
    "subject": 2,
    "meeting_date": 2,
    "due_date": 2,
    "employer": 1,
    "consultant": 1,
    "contractor": 1,
    "discipline": 1,
    "location": 1,
    "contract_number": 1,
    "contract_date": 1,
    "drawing_number": 1,
    "sent_to_supervision_date": 1,
    "supervision_entry_date": 1,
    "sent_to_contractor_date": 1,
    "priority": 1,
    "attachment_count": 1,
}

DATE_FIELDS: List[str] = [
    "meeting_date",
    "contract_date",
    "sent_to_supervision_date",
    "supervision_entry_date",
    "sent_to_contractor_date",
    "due_date",
]

_SHAMSI_PATTERN = re.compile(
    r"^1[34]\d{2}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])$"
)

SMART_COPY_FIELDS = {
    "employer",
    "consultant",
    "contractor",
    "discipline",
    "location",
    "contract_number",
    "contract_date",
    "drawing_number",
    "priority",
}

DEFAULT_PRIORITY = "متوسط"
UNDO_TIMEOUT_MS = 6_000


def _normalize_document_number(value: str) -> str:
    if not value:
        return ""
    trans = str.maketrans(
        "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"
    )
    value = value.translate(trans)
    return " ".join(value.replace("\u200c", "").split())


def _increment_document_number(prev_number: str) -> str:
    if not prev_number:
        return ""
    normalized = _normalize_document_number(prev_number).strip()
    if not normalized:
        return ""
    match = re.search(r"(\d+)(?!.*\d)", normalized)
    if not match:
        return normalized
    number_str = match.group(1)
    prefix = normalized[: match.start()]
    suffix = normalized[match.end() :]
    try:
        new_number = int(number_str) + 1
    except ValueError:
        return normalized
    padded = str(new_number).zfill(len(number_str))
    return f"{prefix}{padded}{suffix}"


def _is_valid_shamsi(text: str) -> bool:
    text = text.strip()
    if not _SHAMSI_PATTERN.match(text):
        return False
    try:
        y, m, d = map(int, text.split("-"))
    except ValueError:
        return False
    if y < 1300 or y > 1500:
        return False
    if m < 1 or m > 12:
        return False
    if 1 <= m <= 6:
        return 1 <= d <= 31
    elif 7 <= m <= 11:
        return 1 <= d <= 30
    elif m == 12:
        is_leap = (y % 33) in {1, 5, 9, 13, 17, 22, 26, 30}
        return 1 <= d <= (30 if is_leap else 29)
    return False


# ═══════════════════════════════════════════════
#  Toast — نوار اطلاع‌رسانی موقت با قابلیت Undo
# ═══════════════════════════════════════════════


class _Toast(QFrame):
    """نوار اطلاع‌رسانی موقتی که پایین دیالوگ ظاهر و محو می‌شود."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("toast")
        self.setFixedHeight(44)
        self.hide()

        self._opacity = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity)
        self._opacity.setOpacity(0.0)

        self._anim = QPropertyAnimation(self._opacity, b"opacity", self)
        self._anim.setDuration(350)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutCubic)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 14, 0)

        self._lbl = QLabel()
        self._lbl.setFont(QFont("Vazirmatn", 10, QFont.Weight.Bold))
        layout.addWidget(self._lbl, stretch=1)

        self._btn_undo = QPushButton("↩️ بازگردانی")
        self._btn_undo.setFont(QFont("Vazirmatn", 10, QFont.Weight.Bold))
        self._btn_undo.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_undo.setVisible(False)
        layout.addWidget(self._btn_undo)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._fade_out)

        self._undo_callback = None

    def show_message(
        self,
        text: str,
        *,
        color: str = "#10b981",
        duration_ms: int = 3500,
        undo_callback=None,
        undo_duration_ms: int = UNDO_TIMEOUT_MS,
    ) -> None:
        self._timer.stop()
        if self._undo_callback:
            try:
                self._btn_undo.clicked.disconnect()
            except TypeError:
                pass
        self._undo_callback = undo_callback

        self._lbl.setText(text)
        self.setStyleSheet(
            f"""
            #toast {{
                background-color: {color};
                border-radius: 8px;
                color: white;
            }}
            #toast QPushButton {{
                background: rgba(255,255,255,0.25);
                border: 1px solid rgba(255,255,255,0.5);
                border-radius: 5px;
                color: white;
                padding: 4px 12px;
            }}
            #toast QPushButton:hover {{
                background: rgba(255,255,255,0.45);
            }}
        """
        )

        if undo_callback:
            self._btn_undo.setVisible(True)
            self._btn_undo.clicked.connect(self._handle_undo)
            timeout = undo_duration_ms
        else:
            self._btn_undo.setVisible(False)
            timeout = duration_ms

        self._reposition()
        self.show()
        self.raise_()

        self._anim.stop()
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()

        self._timer.start(timeout)

    def _handle_undo(self) -> None:
        self._timer.stop()
        cb = self._undo_callback
        self._undo_callback = None
        try:
            self._btn_undo.clicked.disconnect()
        except TypeError:
            pass
        self._fade_out()
        if cb:
            cb()

    def _fade_out(self) -> None:
        self._undo_callback = None
        self._anim.stop()
        self._anim.setStartValue(self._opacity.opacity())
        self._anim.setEndValue(0.0)
        self._anim.finished.connect(self._on_hidden)
        self._anim.start()

    def _on_hidden(self) -> None:
        self.hide()
        try:
            self._anim.finished.disconnect(self._on_hidden)
        except TypeError:
            pass

    def _reposition(self) -> None:
        p = self.parent()
        if p:
            w = p.width() - 28
            self.setFixedWidth(w)
            self.move(14, p.height() - self.height() - 14)


# ═══════════════════════════════════════════════
#  MeetingDialog
# ═══════════════════════════════════════════════


class MeetingDialog(QDialog):
    """دیالوگ ثبت یا ویرایش صورتجلسات."""

    def __init__(
        self,
        db: DatabaseManager,
        parent: Optional[QWidget] = None,
        meeting: Optional[Meeting] = None,
    ) -> None:
        super().__init__(parent)
        self.db = db
        self.meeting = meeting
        self._result_data: Dict[str, Any] = {}
        self._fields: Dict[str, QWidget] = {}
        self._prev_snapshot: Optional[Dict[str, Any]] = None

        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setWindowTitle(
            "ثبت صورتجلسه جدید"
            if meeting is None
            else f"ویرایش صورتجلسه  {meeting.meeting_number}"
        )
        self.resize(780, 660)
        self.setMinimumSize(640, 520)

        self._build_ui()
        self._apply_style()
        self._populate_combos()

        if meeting:
            self._load_meeting()
        else:
            self._set_field_value("priority", DEFAULT_PRIORITY)

        self._connect_signals()
        self._setup_shortcuts()
        self._install_live_validators()

    # ── ساختار رابط ──

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 14)
        root.setSpacing(10)

        root.addLayout(self._build_header())
        root.addWidget(self._build_progress_bar())
        root.addWidget(self._build_form_scroll(), stretch=1)
        root.addLayout(self._build_buttons())

        self.toast = _Toast(self)

    def _build_header(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        title = QLabel("📝 فرم ثبت و ویرایش اطلاعات صورتجلسه")
        title.setObjectName("header_title")
        layout.addWidget(title)
        layout.addStretch()

        self.btn_copy_prev = QPushButton("📋 کپی هوشمند از صورتجلسه قبل")
        self.btn_copy_prev.setToolTip(
            "کپی اطلاعات ساختاری + افزایش خودکار سریال شماره سند (Ctrl+D)"
        )
        self.btn_copy_prev.setObjectName("btn_secondary")
        layout.addWidget(self.btn_copy_prev)
        return layout

    def _build_progress_bar(self) -> QProgressBar:
        self.progress = QProgressBar()
        self.progress.setFixedHeight(24)
        self.progress.setTextVisible(True)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("پیشرفت تکمیل فرم: %p٪")
        self.progress.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.progress.setFont(QFont("Vazirmatn", 9, QFont.Weight.Bold))
        self._apply_progress_style("warn")
        return self.progress

    def _apply_progress_style(self, state: str) -> None:
        gradients = {
            "empty": ("#e2e8f0", "#cbd5e1"),
            "warn": ("#f59e0b", "#fbbf24"),
            "mid": ("#3b82f6", "#60a5fa"),
            "ok": ("#3b82f6", "#10b981"),
            "full": ("#10b981", "#34d399"),
            "error": ("#ef4444", "#f87171"),
        }
        c1, c2 = gradients.get(state, gradients["warn"])
        self.progress.setStyleSheet(
            f"""
            QProgressBar {{
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                background: #f1f5f9;
                text-align: center;
                color: #1e293b;
                font-weight: bold;
            }}
            QProgressBar::chunk {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {c1}, stop:1 {c2}
                );
                border-radius: 7px;
            }}
        """
        )

    def _build_form_scroll(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        self.form_layout = QFormLayout(content)
        self.form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.form_layout.setFormAlignment(Qt.AlignmentFlag.AlignRight)
        self.form_layout.setVerticalSpacing(12)
        self.form_layout.setHorizontalSpacing(14)
        self.form_layout.setContentsMargins(6, 6, 6, 6)

        # ── متنی اجباری ──
        self._add_line_edit(
            "meeting_number",
            "شماره صورتجلسه",
            "مثال: 403-MOM-PSN-054",
            required=True,
        )
        m_edit = self._fields.get("meeting_number")
        if isinstance(m_edit, QLineEdit):
            m_edit.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
            m_edit.setAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )
            m_edit.editingFinished.connect(
                lambda: m_edit.setText(_normalize_document_number(m_edit.text()))
            )

        self._add_line_edit(
            "subject", "موضوع", "موضوع و شرح صورتجلسه", required=True
        )

        # ── تاریخ‌ها ──
        self._add_date_row("meeting_date", "تاریخ صورتجلسه", required=True)
        self._add_date_row("contract_date", "تاریخ قرارداد")
        self._add_date_row(
            "sent_to_supervision_date", "ارسال به نظارت"
        )
        self._add_date_row(
            "supervision_entry_date", "ورود به دفتر نظارت"
        )
        self._add_date_row(
            "sent_to_contractor_date", "ابلاغ به پیمانکار"
        )
        self._add_date_row("due_date", "مهلت انجام", required=True)

        # ── کمبوها ──
        self._add_combo("employer", "کارفرما")
        self._add_combo("consultant", "مشاور")
        self._add_combo("contractor", "پیمانکار")
        self._add_combo("drawing_number", "شماره نقشه")
        self._add_combo("contract_number", "شماره قرارداد")

        for k in ("drawing_number", "contract_number"):
            cb = self._fields.get(k)
            if isinstance(cb, QComboBox) and cb.lineEdit():
                cb.lineEdit().setLayoutDirection(Qt.LayoutDirection.LeftToRight)
                cb.lineEdit().setAlignment(
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                )

        self._add_combo("discipline", "دیسیپلین", DISCIPLINES)
        self._add_combo("location", "محل کار")
        self._add_combo(
            "priority", "اولویت صورتجلسه", ["بالا", "متوسط", "پایین"]
        )

        # ── تعداد پیوست ──
        self.form_layout.addRow(
            self._build_attachment_count_label(),
            self._build_attachment_count_widget(),
        )

        scroll.setWidget(content)
        return scroll

    def _build_attachment_count_label(self) -> QLabel:
        lbl = QLabel("تعداد برگه‌های پیوست:")
        lbl.setToolTip(
            "تعداد کل برگه‌های پیوست به صورتجلسه\n"
            "فایل فیزیکی توسط سیستم به‌طور خودکار جستجو می‌شود."
        )
        return lbl

    def _build_attachment_count_widget(self) -> QWidget:
        container = QWidget()
        h = QHBoxLayout(container)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)

        self.spin_attachment_count = QSpinBox()
        self.spin_attachment_count.setRange(0, 999)
        self.spin_attachment_count.setValue(0)
        self.spin_attachment_count.setMinimumHeight(30)
        self.spin_attachment_count.setMinimumWidth(120)
        self.spin_attachment_count.setSuffix(" برگ")
        self.spin_attachment_count.setAlignment(Qt.AlignmentFlag.AlignCenter)

        info = QLabel("🔎 فایل فیزیکی توسط سیستم به‌طور خودکار شناسایی می‌شود.")
        info.setStyleSheet(
            "color: #64748b; font-size: 11px; font-style: italic;"
        )
        h.addWidget(self.spin_attachment_count)
        h.addWidget(info, stretch=1)

        self._fields["attachment_count"] = self.spin_attachment_count
        return container

    def _build_buttons(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.addStretch()

        self.btn_save = QPushButton("💾 ذخیره  (Ctrl+S)")
        self.btn_save.setObjectName("btn_save")
        self.btn_save.setMinimumSize(140, 34)

        self.btn_cancel = QPushButton("انصراف  (Esc)")
        self.btn_cancel.setObjectName("btn_cancel")
        self.btn_cancel.setMinimumSize(100, 34)

        layout.addWidget(self.btn_save)
        layout.addWidget(self.btn_cancel)
        return layout

    # ── ابزار ساخت ویجت ──

    def _add_line_edit(
        self,
        key: str,
        label: str,
        placeholder: str = "",
        required: bool = False,
    ) -> QLineEdit:
        widget = QLineEdit()
        widget.setPlaceholderText(placeholder)
        widget.setMinimumHeight(30)
        text = (
            f"{label} <font color='#e53935'>*</font>" if required else f"{label}:"
        )
        self.form_layout.addRow(text, widget)
        self._fields[key] = widget
        return widget

    def _add_date_row(
        self, key: str, label: str, required: bool = False
    ) -> QWidget:
        container = QWidget()
        h = QHBoxLayout(container)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(4)

        line = QLineEdit()
        line.setPlaceholderText("۱۴۰۴-۰۱-۰۱")
        line.setMinimumHeight(30)
        line.setToolTip("فرمت: YYYY-MM-DD (شمسی)")

        btn_today = QToolButton()
        btn_today.setText("امروز")
        btn_today.setToolTip("درج تاریخ امروز")
        btn_today.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_today.clicked.connect(lambda _c, k=key: self._set_today(k))

        h.addWidget(line, stretch=1)
        h.addWidget(btn_today)

        text = (
            f"{label} <font color='#e53935'>*</font>" if required else f"{label}:"
        )
        self.form_layout.addRow(text, container)
        self._fields[key] = line
        return container

    def _add_combo(
        self, key: str, label: str, items: Optional[List[str]] = None
    ) -> QComboBox:
        combo = QComboBox()
        combo.setEditable(True)
        combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        combo.setMinimumHeight(30)
        combo.addItem("")
        if items:
            combo.addItems(items)
        self.form_layout.addRow(f"{label}:", combo)
        self._fields[key] = combo
        return combo

    def _set_today(self, key: str) -> None:
        widget = self._fields.get(key)
        if isinstance(widget, QLineEdit):
            widget.setText(today_shamsi())
            self._update_progress()

    # ── سیگنال و میانبر ──

    def _connect_signals(self) -> None:
        self.btn_save.clicked.connect(self._on_save)
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_copy_prev.clicked.connect(self._copy_previous_data)

        for widget in self._fields.values():
            if isinstance(widget, QLineEdit):
                widget.textChanged.connect(self._update_progress)
            elif isinstance(widget, QComboBox):
                widget.currentTextChanged.connect(self._update_progress)
            elif isinstance(widget, QSpinBox):
                widget.valueChanged.connect(self._update_progress)

        # اتصال سیگنال تاریخ صورتجلسه برای پیشنهاد هوشمند مهلت انجام
        m_date_widget = self._fields.get("meeting_date")
        if isinstance(m_date_widget, QLineEdit):
            m_date_widget.textChanged.connect(self._on_meeting_date_changed)

    def _setup_shortcuts(self) -> None:
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self._on_save)
        QShortcut(
            QKeySequence("Ctrl+D"), self, activated=self._copy_previous_data
        )
        QShortcut(
            QKeySequence("Ctrl+T"),
            self,
            activated=lambda: self._set_today("meeting_date"),
        )

    def _install_live_validators(self) -> None:
        """اعتبارسنجی رنگی زنده فیلدهای تاریخ."""
        for key in DATE_FIELDS:
            w = self._fields.get(key)
            if isinstance(w, QLineEdit):
                w.textChanged.connect(
                    lambda _t, k=key: self._paint_date_field(k)
                )
        self._update_progress()

    def _paint_date_field(self, key: str) -> None:
        w = self._fields.get(key)
        if not isinstance(w, QLineEdit):
            return
        val = w.text().strip()
        if not val:
            w.setStyleSheet("")
            return
        if _is_valid_shamsi(val):
            w.setStyleSheet(
                "border: 1px solid #10b981; background: #ecfdf5;"
            )
        else:
            w.setStyleSheet(
                "border: 1px solid #ef4444; background: #fef2f2;"
            )

    # ── 🎯 پیشنهاد خودکار ۳ روز بعد برای مهلت انجام ──

    def _add_days_to_shamsi(self, shamsi_str: str, days: int) -> Optional[str]:
        """افزودن تعداد روز مشخص به یک تاریخ شمسی به روش استاندارد میلادی."""
        if not _is_valid_shamsi(shamsi_str):
            return None
        try:
            greg_str = to_gregorian(shamsi_str)
            if not greg_str:
                return None
            greg_date = datetime.strptime(greg_str, "%Y-%m-%d").date()
            new_greg_date = greg_date + timedelta(days=days)
            return to_shamsi(new_greg_date.isoformat())
        except Exception as exc:
            logger.warning("Failed to add days to Shamsi date: %s", exc)
            return None

    def _on_meeting_date_changed(self) -> None:
        """وقتی تاریخ صورتجلسه تایپ شد یا تغییر کرد، مهلت انجام را ۳ روز بعد پیشنهاد بدهد."""
        m_date_widget = self._fields.get("meeting_date")
        if not isinstance(m_date_widget, QLineEdit):
            return
        m_date_str = m_date_widget.text().strip()

        if _is_valid_shamsi(m_date_str):
            suggested_due = self._add_days_to_shamsi(m_date_str, 3)
            if suggested_due:
                due_widget = self._fields.get("due_date")
                if isinstance(due_widget, QLineEdit):
                    # همواره پیشنهاد جدید را جایگزین فیلد می‌کند تا زمانی که کاربر مایل به اصلاح آن باشد
                    due_widget.setText(suggested_due)
                    self._paint_date_field("due_date")

    # ── محاسبه و نمایش نوار پیشرفت ──

    def _update_progress(self) -> None:
        """محاسبه درصد تکمیل فرم بر اساس فیلدهای پر شده و اعتبارسنجی."""
        data = self._collect_form_data()

        total_weight = sum(PROGRESS_FIELDS.values())
        filled_weight = 0

        for key, weight in PROGRESS_FIELDS.items():
            val = data.get(key)
            if key == "attachment_count":
                if isinstance(val, int) and val > 0:
                    filled_weight += weight
            else:
                if val and str(val).strip():
                    filled_weight += weight

        percent = int((filled_weight / total_weight) * 100) if total_weight else 0

        missing_required = [
            REQUIRED_FIELDS[k] for k in REQUIRED_FIELDS if not data.get(k)
        ]
        invalid_dates = [
            k for k in DATE_FIELDS
            if data.get(k) and not _is_valid_shamsi(str(data[k]))
        ]

        if invalid_dates:
            state = "error"
            fmt = f"❌ فرمت تاریخ نامعتبر — {percent}٪"
            self.btn_save.setEnabled(False)
        elif missing_required:
            if percent < 30:
                state = "empty"
            elif percent < 60:
                state = "warn"
            else:
                state = "mid"
            remain = len(missing_required)
            fmt = f"⏳ {percent}٪ تکمیل شده  •  {remain} فیلد اجباری باقیمانده"
            self.btn_save.setEnabled(False)
        elif percent >= 100:
            state = "full"
            fmt = f"✨ فرم کامل است — آماده ذخیره (%p٪)"
            self.btn_save.setEnabled(True)
        else:
            state = "ok"
            fmt = f"✅ فرم آماده ذخیره است — {percent}٪  (Ctrl+S)"
            self.btn_save.setEnabled(True)

        self.progress.setValue(percent)
        self.progress.setFormat(fmt)
        self._apply_progress_style(state)

    # ── بارگذاری داده ──

    def _populate_combos(self) -> None:
        db_columns = {
            "employer": "employer",
            "consultant": "consultant",
            "contractor": "contractor",
            "drawing_number": "drawing_number",
            "contract_number": "contract_number",
        }
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            for field_key, col_name in db_columns.items():
                try:
                    values: List[str] = self.db.distinct_values(col_name) or []
                except Exception as exc:
                    logger.warning(
                        "Auto-populate failed for '%s': %s", col_name, exc
                    )
                    continue
                combo = self._fields[field_key]
                if isinstance(combo, QComboBox):
                    current = combo.currentText()
                    combo.blockSignals(True)
                    combo.clear()
                    combo.addItem("")
                    combo.addItems([v for v in values if v])
                    idx = combo.findText(current)
                    if idx >= 0:
                        combo.setCurrentIndex(idx)
                    elif current:
                        combo.setEditText(current)
                    combo.blockSignals(False)
        finally:
            QApplication.restoreOverrideCursor()

    def _load_meeting(self) -> None:
        m = self.meeting
        if m is None:
            return
        text_values: Dict[str, str] = {
            "meeting_number": m.meeting_number or "",
            "subject": m.subject or "",
            "employer": m.employer or "",
            "consultant": m.consultant or "",
            "contractor": m.contractor or "",
            "drawing_number": m.drawing_number or "",
            "contract_number": m.contract_number or "",
            "discipline": m.discipline or "",
            "priority": m.priority or DEFAULT_PRIORITY,
        }
        for key in DATE_FIELDS:
            raw = getattr(m, key, None)
            text_values[key] = to_shamsi(raw.isoformat()) if raw else ""

        for key, val in text_values.items():
            self._set_field_value(key, val)

        attach = getattr(m, "attachment_count", None) or 0
        try:
            self.spin_attachment_count.setValue(int(attach))
        except (TypeError, ValueError):
            self.spin_attachment_count.setValue(0)

    def _set_field_value(self, key: str, value: Any) -> None:
        widget = self._fields.get(key)
        if widget is None:
            return
        text = "" if value is None else str(value)
        if isinstance(widget, QLineEdit):
            widget.setText(text)
        elif isinstance(widget, QComboBox):
            idx = widget.findText(text)
            if idx >= 0:
                widget.setCurrentIndex(idx)
            else:
                widget.setEditText(text)
        elif isinstance(widget, QSpinBox):
            try:
                widget.setValue(int(value) if value else 0)
            except (TypeError, ValueError):
                widget.setValue(0)

    # ── کپی هوشمند + Undo ──

    def _snapshot_current_form(self) -> Dict[str, Any]:
        return self._collect_form_data()

    def _restore_snapshot(self, snap: Dict[str, Any]) -> None:
        for k, v in snap.items():
            self._set_field_value(k, v)
        self._update_progress()
        self.toast.show_message("↩️ فرم به حالت قبل بازگشت", color="#6366f1")

    def _get_previous_meeting(self) -> Optional[Meeting]:
        try:
            return self.db.get_previous_meeting(
                exclude_id=self.meeting.id if self.meeting else None
            )
        except AttributeError:
            try:
                with self.db.session() as sess:
                    q = sess.query(Meeting).order_by(Meeting.id.desc())
                    if self.meeting:
                        q = q.filter(Meeting.id != self.meeting.id)
                    return q.first()
            except Exception as exc:
                logger.exception("Failed to query previous meeting: %s", exc)
                return None
        except Exception as exc:
            logger.exception("Unexpected error getting previous meeting: %s", exc)
            return None

    def _copy_previous_data(self) -> None:
        prev = self._get_previous_meeting()
        if not prev:
            self.toast.show_message(
                "هیچ صورتجلسه قبلی یافت نشد", color="#f59e0b"
            )
            return

        snapshot = self._snapshot_current_form()

        for key in SMART_COPY_FIELDS:
            raw = getattr(prev, key, None)
            if not raw:
                continue
            if key == "contract_date" and isinstance(raw, date):
                val = to_shamsi(raw.isoformat())
            else:
                val = str(raw)
            self._set_field_value(key, val)

        current_num = ""
        mw = self._fields.get("meeting_number")
        if isinstance(mw, QLineEdit):
            current_num = mw.text().strip()

        suggested = (
            _increment_document_number(prev.meeting_number)
            if prev.meeting_number
            else ""
        )
        if not current_num and suggested:
            self._set_field_value("meeting_number", suggested)

        self._update_progress()

        msg = f"📋 اطلاعات از «{prev.meeting_number}» کپی شد"
        if suggested and not current_num:
            msg += f"  •  شماره پیشنهادی: {suggested}"

        self.toast.show_message(
            msg,
            color="#3b82f6",
            undo_callback=lambda: self._restore_snapshot(snapshot),
        )

    # ── جمع‌آوری و اعتبارسنجی ──

    def _collect_form_data(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {}
        for key, widget in self._fields.items():
            if isinstance(widget, QLineEdit):
                data[key] = widget.text().strip()
            elif isinstance(widget, QComboBox):
                data[key] = widget.currentText().strip()
            elif isinstance(widget, QSpinBox):
                data[key] = int(widget.value())
        return data

    def _validate_required(self, data: Dict[str, Any]) -> Optional[str]:
        for key, label in REQUIRED_FIELDS.items():
            if not data.get(key):
                return f"فیلد «{label}» الزامی است."
        return None

    def _validate_dates(self, data: Dict[str, Any]) -> Optional[str]:
        labels = {
            "meeting_date": "تاریخ صورتجلسه",
            "contract_date": "تاریخ قرارداد",
            "sent_to_contractor_date": "تاریخ ارسال به پیمانکار",
            "due_date": "مهلت انجام",
        }
        for key, label in labels.items():
            val = data.get(key, "")
            if val and not _is_valid_shamsi(val):
                return (
                    f"ساختار تاریخ «{label}» نامعتبر است. الگو: YYYY-MM-DD"
                )
        return None

    def _convert_dates(self, data: Dict[str, Any]) -> Optional[str]:
        for key in DATE_FIELDS:
            val = data.get(key, "")
            if not val:
                data[key] = None
                continue
            greg = to_gregorian(val)
            if not greg:
                label = REQUIRED_FIELDS.get(key, key)
                return f"تبدیل تاریخ «{label}» به میلادی ناموفق بود."
            try:
                data[key] = datetime.strptime(greg, "%Y-%m-%d").date()
            except ValueError:
                return f"تاریخ نامعتبر: {greg}"
        return None

    def _validate_date_logic(self, data: Dict[str, Any]) -> Optional[str]:
        md = data.get("meeting_date")
        dd = data.get("due_date")
        sd = data.get("sent_to_contractor_date")
        if md and dd and dd < md:
            return "مهلت انجام نمی‌تواند قبل از تاریخ صورتجلسه باشد."
        if md and sd and sd < md:
            return "تاریخ ارسال به پیمانکار نمی‌تواند قبل از تاریخ صورتجلسه باشد."
        return None

    def _validate_duplicate(self, meeting_number: str) -> bool:
        try:
            return self.db.is_duplicate_meeting_number(
                number=meeting_number,
                exclude_id=self.meeting.id if self.meeting else None,
            )
        except AttributeError:
            try:
                with self.db.session() as sess:
                    q = sess.query(Meeting).filter(
                        Meeting.meeting_number == meeting_number
                    )
                    if self.meeting:
                        q = q.filter(Meeting.id != self.meeting.id)
                    return q.first() is not None
            except Exception as exc:
                logger.exception("Duplicate check failed: %s", exc)
                return False

    # ── ذخیره ──

    def _on_save(self) -> None:
        try:
            data = self._collect_form_data()
            data["meeting_number"] = _normalize_document_number(
                data.get("meeting_number", "")
            )

            for validator in (
                self._validate_required,
                self._validate_dates,
            ):
                err = validator(data)
                if err:
                    self.toast.show_message(f"⚠️ {err}", color="#f59e0b")
                    return

            err = self._convert_dates(data)
            if err:
                self.toast.show_message(f"⚠️ {err}", color="#f59e0b")
                return

            err = self._validate_date_logic(data)
            if err:
                self.toast.show_message(f"⚠️ {err}", color="#f59e0b")
                return

            if self._validate_duplicate(data["meeting_number"]):
                self.toast.show_message(
                    f"❌ شماره «{data['meeting_number']}» قبلاً ثبت شده",
                    color="#ef4444",
                )
                return

            # ── هشدار شباهت (احتمال تکرار / تقلب پیمانکار) ──
            if not self._confirm_no_duplicate_work(data):
                return

            sent = data.get("sent_to_contractor_date")
            data["closing_date"] = sent
            data["contractor_response_date"] = sent

            if not data.get("priority"):
                data["priority"] = DEFAULT_PRIORITY
            if not data.get("discipline"):
                data["discipline"] = None

            data["file_link"] = (
                self.meeting.file_link if self.meeting else None
            )
            # entry_date = ورود به کارفرما؛ فقط اگر خالی بود برای رکورد جدید پر شود
            if self.meeting and self.meeting.entry_date:
                data["entry_date"] = self.meeting.entry_date
            elif not data.get("entry_date"):
                data["entry_date"] = date.today()
            data["status"] = (
                self.meeting.status if self.meeting else "در دست بررسی"
            )

            self._result_data = data
            logger.info(
                "Meeting saved: %s (status=%s, priority=%s)",
                data["meeting_number"],
                data["status"],
                data["priority"],
            )
            self.accept()

        except Exception as exc:
            logger.exception("Save exception")
            QMessageBox.critical(
                self, "خطای مهلک", f"خطای داخلی:\n{exc}"
            )

    def _confirm_no_duplicate_work(self, data: Dict[str, Any]) -> bool:
        """
        اگر صورتجلسه مشابه (پیمانکار + محل/نقشه) یافت شد، هشدار بده.
        کاربر می‌تواند ادامه دهد؛ در صورت ادامه، در ممیزی ثبت می‌شود.
        """
        try:
            similar = self.db.find_similar_meetings(
                contractor=data.get("contractor"),
                location=data.get("location"),
                drawing_number=data.get("drawing_number"),
                subject=data.get("subject"),
                exclude_id=self.meeting.id if self.meeting else None,
                days_window=90,
                limit=8,
            )
        except Exception as exc:
            logger.warning("Similarity check failed: %s", exc)
            return True

        if not similar:
            return True

        lines = []
        for m in similar:
            loc = (m.location or "—").strip()
            draw = (m.drawing_number or "—").strip()
            subj = (m.subject or "—").strip()
            if len(subj) > 40:
                subj = subj[:40] + "…"
            lines.append(
                f"• {m.meeting_number} | محل: {loc} | نقشه: {draw} | {subj}"
            )
        detail = "\n".join(lines)
        msg = (
            f"⚠️ احتمال تکرار کار / صورتجلسه مشابه\n\n"
            f"برای این پیمانکار در همین محل یا شماره نقشه، "
            f"{len(similar)} مورد مشابه یافت شد:\n\n"
            f"{detail}\n\n"
            f"اگر کار واقعاً جدید است OK بزنید.\n"
            f"در غیر این صورت Cancel و پرونده قبلی را بررسی کنید."
        )
        reply = QMessageBox.warning(
            self,
            "هشدار شباهت صورتجلسه",
            msg,
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Ok:
            return False

        # ثبت در ممیزی که کاربر با وجود هشدار ادامه داده
        try:
            nums = ", ".join(m.meeting_number for m in similar[:5])
            self.db.audit(
                None,
                "user",
                "SIMILARITY_OVERRIDE",
                f"new={data.get('meeting_number')} similar=[{nums}] "
                f"contractor={data.get('contractor')} location={data.get('location')} "
                f"drawing={data.get('drawing_number')}",
            )
        except Exception as exc:
            logger.warning("Audit similarity override failed: %s", exc)
        return True

    def get_data(self) -> Dict[str, Any]:
        return self._result_data

    # ── رویدادها ──

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "toast"):
            self.toast._reposition()

    # ── استایل ──

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QDialog {
                background-color: #f4f6fb;
                font-family: 'Vazirmatn', 'Tahoma', Arial, sans-serif;
            }
            QLabel#header_title {
                font-size: 15px;
                font-weight: bold;
                color: #1a5276;
            }
            QLineEdit, QComboBox, QSpinBox {
                border: 1px solid #c5cae9;
                border-radius: 6px;
                padding: 4px 10px;
                background: #ffffff;
                font-size: 12.5px;
                color: #1e293b;
                selection-background-color: #b3d4f5;
            }
            QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
                border-color: #00BFFF;
                background: #f0fbff;
            }
            QLineEdit:read-only {
                background: #f1f3f6;
                color: #555;
            }
            QSpinBox {
                font-weight: bold;
                color: #0369a1;
            }
            QLabel {
                color: #374151;
                font-size: 12.5px;
            }
            QPushButton {
                background-color: #ffffff;
                border: 1px solid #c5cae9;
                border-radius: 6px;
                padding: 6px 18px;
                font-size: 12.5px;
                font-weight: bold;
                color: #1e293b;
                min-height: 30px;
            }
            QPushButton:hover   { background-color: #e8eaf6; }
            QPushButton:pressed { background-color: #c5cae9; }
            QPushButton:disabled {
                background: #f1f5f9;
                color: #94a3b8;
                border-color: #e2e8f0;
            }
            QPushButton#btn_save {
                background-color: #00BFFF;
                color: #ffffff;
                border: none;
            }
            QPushButton#btn_save:hover   { background-color: #0099CC; }
            QPushButton#btn_save:pressed { background-color: #007AAA; }
            QPushButton#btn_save:disabled {
                background: #cbd5e1;
                color: #ffffff;
            }
            QPushButton#btn_cancel { color: #555; }
            QPushButton#btn_secondary {
                background-color: #f8fafc;
                border-color: #94a3b8;
                color: #334155;
                font-weight: normal;
            }
            QPushButton#btn_secondary:hover { background-color: #e2e8f0; }
            QToolButton {
                background-color: #f0f4f8;
                border: 1px solid #c5cae9;
                border-radius: 5px;
                padding: 3px 8px;
                font-size: 12px;
                color: #334155;
            }
            QToolButton:hover   { background-color: #dce4f0; }
            QToolButton:pressed { background-color: #c5cae9; }
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical {
                background: #f1f5f9; width: 8px; border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: #94a3b8; border-radius: 4px;
            }
            QScrollBar::handle:vertical:hover { background: #64748b; }
            """
        )
