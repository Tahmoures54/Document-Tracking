# -*- coding: utf-8 -*-
"""
ui.workflow_dialog
ماژول هوشمند مدیریت گردش کار صورتجلسه و مانیتورینگ پیشرفت کار تیمی
نسخه ۳: طراحی بدون تأیید خسته‌کننده، Undo هوشمند، Toast بصری
"""
from __future__ import annotations

import csv
import logging
from datetime import date
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import (
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    QSettings,
    QTimer,
    Qt,
)
from PyQt6.QtGui import (
    QAction,
    QBrush,
    QCloseEvent,
    QColor,
    QFont,
    QKeySequence,
)
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGraphicsOpacityEffect,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from config import APP_NAME, ORG_NAME
from db.manager import DatabaseManager
from db.models import Meeting, WorkflowStep, STATUS_PENDING
from security.permissions import PERM_REPORT_READ, PERM_REPORT_WRITE, can
from services.workflow_report import WorkflowReportGenerator
from utils.date_utils import to_shamsi, today_shamsi

logger = logging.getLogger(__name__)

# ── تنظیمات سراسری ───────────────────────────
UI_FONT_NAME = "Vazirmatn"
UI_FONT_SIZE = 10

UNDO_TIMEOUT_MS = 6_000  # مهلت undo به میلی‌ثانیه


def get_font(
    weight: QFont.Weight = QFont.Weight.Normal, size_offset: int = 0
) -> QFont:
    return QFont(UI_FONT_NAME, UI_FONT_SIZE + size_offset, weight)


# ── ترجمه و رنگ‌بندی وضعیت‌ها ─────────────────
STATUS_FA: Dict[str, str] = {
    "pending": "آماده اقدام",
    "in_progress": "در حال اقدام",
    "completed": "تکمیل شد",
    "rejected": "عودت برای اصلاح",
    "skipped": "رد شده / اجرا نشده",
}

# نام‌های نمایشی روشن‌تر برای پرونده‌های قدیمی؛ نام ذخیره‌شده و سوابق تغییر نمی‌کنند.
STEP_NAME_LABELS: Dict[str, str] = {
    "دریافت در دفتر کارفرما": "۱. ثبت و دریافت صورتجلسه در دفتر کارفرما",
    "ارجاع به رئیس دفتر فنی": "۲. ارجاع پرونده به رئیس دفتر فنی",
    "بررسی کارشناس": "۳. بررسی فنی و ثبت نظر کارشناس",
    "تأیید رئیس دفتر فنی": "۴. کنترل و تأیید رئیس دفتر فنی",
    "تأیید مدیر سایت": "۵. تأیید نهایی مدیر سایت",
    "ابلاغ به پیمانکار": "۶. ابلاغ رسمی به پیمانکار و بستن پرونده",
}
STATUS_ICONS: Dict[str, str] = {
    "pending": "⏳",
    "in_progress": "🔄",
    "completed": "✅",
    "rejected": "❌",
}
STATUS_COLORS: Dict[str, QColor] = {
    "pending": QColor("#f59e0b"),
    "in_progress": QColor("#3b82f6"),
    "completed": QColor("#10b981"),
    "rejected": QColor("#ef4444"),
}

# ایندکس ستون‌ها
COL_IDX = 0
COL_NAME = 1
COL_STATUS = 2
COL_ENTRY = 3
COL_EXIT = 4
COL_RESP = 5
COL_SIGN = 6
COL_NOTES = 7
COL_COUNT = 8


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
        self._lbl.setFont(get_font(QFont.Weight.Bold))
        layout.addWidget(self._lbl, stretch=1)

        self._btn_undo = QPushButton("↩️ بازگردانی")
        self._btn_undo.setFont(get_font(QFont.Weight.Bold))
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
#  PerformanceReportDialog — گزارش عملکرد
# ═══════════════════════════════════════════════


class PerformanceReportDialog(QDialog):
    """دیالوگ نمایش مصور عملکرد کارشناسان."""

    def __init__(
        self, data: List[Dict[str, Any]], parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(parent)
        self.data = data
        self.setWindowTitle("📊 گزارش عملکرد کارشناسان")
        self.resize(750, 480)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setModal(True)
        self._build_ui()

    # ── استایل مشترک ──
    _STYLE = """
        QDialog { background-color: #f8fafc; }
        QTableWidget {
            border: 1px solid #cbd5e1; border-radius: 8px;
            gridline-color: #f1f5f9; background-color: #fff; font-size: 12px;
        }
        QHeaderView::section {
            background-color: #1e293b; color: white;
            padding: 8px; border: none; font-weight: bold;
        }
        QTableWidget::item { padding: 6px; }
        QTableWidget::item:selected { background-color: #dbeafe; color: #1e40af; }
    """

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)
        self.setStyleSheet(self._STYLE)

        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(
            [
                "کاربر مسئول",
                "کل",
                "تکمیل",
                "در حال انجام",
                "انتظار",
                "رد شده",
                "میانگین (روز)",
            ]
        )
        self.table.setFont(get_font())
        self.table.horizontalHeader().setFont(get_font(QFont.Weight.Bold))
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setAlternatingRowColors(True)
        self._populate_table()
        layout.addWidget(self.table)

        btn_row = QHBoxLayout()
        btn_save = self._make_btn(
            "💾 خروجی CSV", "#10b981", self._save_csv
        )
        btn_close = self._make_btn("بستن", "#e2e8f0", self.accept, fg="#1e293b")
        btn_row.addWidget(btn_save)
        btn_row.addStretch()
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

    @staticmethod
    def _make_btn(
        text: str, bg: str, slot, fg: str = "white"
    ) -> QPushButton:
        b = QPushButton(text)
        b.setFont(get_font(QFont.Weight.Bold))
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {bg}; color: {fg};
                border: 1px solid #cbd5e1; border-radius: 6px;
                padding: 8px 20px;
            }}
            QPushButton:hover {{ opacity: 0.85; }}
        """
        )
        b.clicked.connect(slot)
        return b

    def _populate_table(self) -> None:
        self.table.setRowCount(len(self.data))
        for row, r in enumerate(self.data):
            avg = r.get("avg_days")
            avg_txt = f"{float(avg):.1f}" if avg is not None else "—"

            def _it(text, center=True, bold=False):
                item = QTableWidgetItem(str(text))
                if center:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if bold:
                    item.setFont(get_font(QFont.Weight.Bold))
                return item

            self.table.setItem(row, 0, _it(r.get("user", "—"), False, True))
            self.table.setItem(row, 1, _it(r.get("total", 0)))
            self.table.setItem(row, 2, _it(r.get("completed", 0)))
            self.table.setItem(row, 3, _it(r.get("in_progress", 0)))
            self.table.setItem(row, 4, _it(r.get("pending", 0)))
            self.table.setItem(row, 5, _it(r.get("rejected", 0)))
            self.table.setItem(row, 6, _it(avg_txt, bold=True))

    def _save_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "ذخیره گزارش", "Workflow_Performance.csv", "CSV (*.csv)"
        )
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow(
                    [
                        "کاربر",
                        "کل",
                        "تکمیل",
                        "درحال‌اقدام",
                        "انتظار",
                        "ردشده",
                        "میانگین‌روز",
                    ]
                )
                for r in self.data:
                    w.writerow(
                        [
                            r.get("user", ""),
                            r.get("total", 0),
                            r.get("completed", 0),
                            r.get("in_progress", 0),
                            r.get("pending", 0),
                            r.get("rejected", 0),
                            ""
                            if r.get("avg_days") is None
                            else f"{float(r['avg_days']):.2f}",
                        ]
                    )
            QMessageBox.information(self, "✅", f"ذخیره شد:\n{path}")
        except Exception as exc:
            logger.exception("CSV export failed")
            QMessageBox.critical(self, "خطا", str(exc))


# ═══════════════════════════════════════════════
#  WorkflowDialog — دیالوگ اصلی گردش کار
# ═══════════════════════════════════════════════


class WorkflowDialog(QDialog):
    """دیالوگ جامع مدیریت گردش کار — بدون تأیید خسته‌کننده، با Undo هوشمند."""

    def __init__(
        self,
        db: DatabaseManager,
        meeting: Meeting,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.db = db
        self.meeting = meeting
        self.steps: List[WorkflowStep] = []
        self.active_users: List[str] = []

        self.settings = QSettings(ORG_NAME, APP_NAME)
        self._selected_step_id: Optional[int] = None

        self._init_session(parent)

        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setWindowTitle(
            f"گردش کار — {meeting.meeting_number}"
        )
        self.resize(1080, 720)
        self.setMinimumSize(880, 580)
        self.setModal(True)
        self.setStyleSheet(self._STYLESHEET)

        self._build_ui()
        self._restore_geometry()
        self._load_active_users()
        self._load_steps()

    # ── استایل یکپارچه ──
    _STYLESHEET = """
        QDialog { background-color: #f8fafc; }
        QGroupBox {
            font-weight: bold; border: 1px solid #cbd5e1;
            border-radius: 8px; margin-top: 10px; padding-top: 10px;
            background-color: #fff;
        }
        QGroupBox::title {
            subcontrol-origin: margin; subcontrol-position: top right;
            padding: 0 8px; color: #0f172a;
        }
        QTableWidget {
            border: 1px solid #cbd5e1; border-radius: 8px;
            gridline-color: #f1f5f9; background-color: #fff;
        }
        QHeaderView::section {
            background-color: #1e293b; color: white;
            padding: 8px; border: none; font-weight: bold;
        }
        QTableWidget::item { padding: 6px; }
        QTableWidget::item:selected { background-color: #dbeafe; color: #1e40af; }
        QLabel { color: #0f172a; }
        QComboBox {
            border: 1px solid #cbd5e1; border-radius: 4px;
            padding: 4px; background-color: white;
        }
        QComboBox:focus { border-color: #3b82f6; }
        QComboBox::drop-down { border: none; width: 20px; }
        QComboBox QAbstractItemView {
            border: 1px solid #94a3b8; background: #fff;
            selection-background-color: #3b82f6; selection-color: #fff;
        }
    """

    # ── ساختار رابط ──

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 12)
        root.setSpacing(8)

        root.addWidget(self._build_header())
        root.addWidget(self._build_progress_bar())
        root.addWidget(self._build_table(), stretch=1)
        root.addLayout(self._build_action_buttons())
        root.addWidget(self._build_status_bar())

        self.toast = _Toast(self)

        self._connect_signals()
        self._setup_shortcuts()

    def _build_header(self) -> QGroupBox:
        box = QGroupBox("اطلاعات پرونده")
        box.setFont(get_font(QFont.Weight.Bold))
        form = QFormLayout(box)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setVerticalSpacing(4)
        form.setHorizontalSpacing(14)

        def lbl(text: str, bold: bool = False) -> QLabel:
            la = QLabel(text or "—")
            la.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            la.setFont(
                get_font(QFont.Weight.Bold if bold else QFont.Weight.Normal)
            )
            return la

        md = (
            to_shamsi(self.meeting.meeting_date.isoformat())
            if self.meeting.meeting_date
            else "—"
        )
        form.addRow("شماره:", lbl(self.meeting.meeting_number, True))
        form.addRow("موضوع:", lbl(self.meeting.subject))
        form.addRow("پیمانکار:", lbl(self.meeting.contractor or "—"))
        form.addRow("تاریخ:", lbl(md))
        tip = QLabel("روش کار: مرحله جاری را انتخاب کنید؛ «شروع اقدام» را بزنید و پس از انجام کار، «تکمیل مرحله» را ثبت کنید. اگر نقصی وجود دارد، «عودت برای اصلاح» را همراه با علت ثبت کنید.")
        tip.setStyleSheet("color: #64748b; font-size: 11px; font-style: italic;")
        tip.setWordWrap(True)
        form.addRow(tip)
        return box

    def _build_progress_bar(self) -> QProgressBar:
        self.progress = QProgressBar()
        self.progress.setFixedHeight(22)
        self.progress.setTextVisible(True)
        self.progress.setFormat("%v از %m گام (%p٪)")
        self.progress.setFont(get_font(QFont.Weight.Bold, -1))
        self.progress.setStyleSheet(
            """
            QProgressBar {
                border: 1px solid #cbd5e1; border-radius: 6px;
                background: #f1f5f9; text-align: center; color: #1e293b;
            }
            QProgressBar::chunk {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #3b82f6, stop:1 #10b981
                );
                border-radius: 5px;
            }
        """
        )
        return self.progress

    def _build_table(self) -> QTableWidget:
        self.table = QTableWidget()
        self.table.setColumnCount(COL_COUNT)
        self.table.setHorizontalHeaderLabels(
            [
                "ردیف",
                "مرحله / اقدام مورد انتظار",
                "وضعیت",
                "تاریخ شروع",
                "تاریخ پایان",
                "مسئول اقدام",
                "ثبت‌کننده / امضا",
                "یادداشت و علت عودت",
            ]
        )
        self.table.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        hdr = self.table.horizontalHeader()
        hdr.setFont(get_font(QFont.Weight.Bold))
        for col in range(COL_COUNT):
            if col == COL_NOTES:
                hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)
            elif col == COL_IDX:
                hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
                self.table.setColumnWidth(col, 42)
            elif col == COL_NAME:
                hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)
                self.table.setColumnWidth(col, 270)
            elif col == COL_STATUS:
                hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
            else:
                hdr.setSectionResizeMode(
                    col, QHeaderView.ResizeMode.ResizeToContents
                )

        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.setWordWrap(True)
        self.table.setFont(get_font())
        return self.table

    def _build_action_buttons(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(6)

        def _btn(attr, text, tip, bg="#ffffff", fg="#0f172a"):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.setFont(get_font(QFont.Weight.Bold, -1))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setSizePolicy(
                QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed
            )
            b.setMinimumHeight(36)
            b.setStyleSheet(
                f"""
                QPushButton {{
                    background: {bg}; color: {fg};
                    border: 1px solid #cbd5e1; border-radius: 6px;
                    padding: 4px 14px;
                }}
                QPushButton:hover {{ background: #e2e8f0; }}
                QPushButton:pressed {{ background: #cbd5e1; }}
                QPushButton:disabled {{
                    background: #f1f5f9; color: #94a3b8;
                    border-color: #e2e8f0;
                }}
            """
            )
            setattr(self, attr, b)
            row.addWidget(b)

        _btn(
            "btn_entry",
            "📥 شروع اقدام",
            "Ctrl+E",
            "#dbeafe",
            "#1e40af",
        )
        _btn(
            "btn_exit",
            "📤 تکمیل و امضا",
            "Ctrl+X",
            "#d1fae5",
            "#065f46",
        )
        _btn(
            "btn_prev",
            "↩️ بازگردانی",
            "لغو گام و بازگشت به مرحله قبل",
        )
        _btn(
            "btn_reopen",
            "🔄 ادامه پس از اصلاح",
            "بازگشایی مرحله عودت‌شده  Ctrl+B",
        )
        _btn(
            "btn_reject",
            "↩️ عودت برای اصلاح",
            "ثبت علت نقص و بازگرداندن مرحله جاری برای اصلاح",
            "#ffedd5",
            "#9a3412",
        )
        _btn("btn_notes", "📝 یادداشت", "Ctrl+N")
        _btn("btn_perf", "📊 عملکرد", "گزارش آماری کارشناسان")
        _btn("btn_print", "🖨️ چاپ", "Ctrl+P")
        _btn("btn_refresh", "↺ بروزرسانی", "F5")

        row.addStretch()

        _btn("btn_close", "بستن", "Escape", "#fee2e2", "#991b1b")

        return row

    def _build_status_bar(self) -> QLabel:
        self.lbl_status = QLabel("⏳ در انتظار آغاز …")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.lbl_status.setFont(get_font(QFont.Weight.Bold))
        self.lbl_status.setStyleSheet(
            """
            QLabel {
                background: #fff; border: 1px solid #cbd5e1;
                border-radius: 8px; padding: 8px 14px; color: #1d4ed8;
            }
        """
        )
        return self.lbl_status

    # ── سیگنال‌ها و میانبرها ──

    def _connect_signals(self) -> None:
        self.btn_entry.clicked.connect(self.entry_step)
        self.btn_exit.clicked.connect(self.exit_step)
        self.btn_reopen.clicked.connect(self.reopen_step)
        self.btn_reject.clicked.connect(self.reject_step)
        self.btn_prev.clicked.connect(self.go_to_previous_step)
        self.btn_notes.clicked.connect(self.edit_notes)
        self.btn_perf.clicked.connect(self.show_performance_report)
        self.btn_print.clicked.connect(self.save_and_print_report)
        self.btn_refresh.clicked.connect(self._load_steps)
        self.btn_close.clicked.connect(self.close)

        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.doubleClicked.connect(self._on_double_click)
        self.table.itemSelectionChanged.connect(self._update_status)

    def _setup_shortcuts(self) -> None:
        mapping = [
            ("Ctrl+E", self.entry_step),
            ("Ctrl+X", self.exit_step),
            ("Ctrl+N", self.edit_notes),
            ("Ctrl+P", self.save_and_print_report),
            ("Ctrl+B", self.reopen_step),
            ("F5", self._load_steps),
        ]
        for key, slot in mapping:
            a = QAction(self)
            a.setShortcut(QKeySequence(key))
            a.triggered.connect(slot)
            self.addAction(a)

    # ── ذخیره / بازیابی هندسه ──

    def _restore_geometry(self) -> None:
        g = self.settings.value("workflow_dialog_geometry")
        if g:
            self.restoreGeometry(g)

    def _save_geometry(self) -> None:
        self.settings.setValue(
            "workflow_dialog_geometry", self.saveGeometry()
        )

    def closeEvent(self, event: QCloseEvent) -> None:
        self._save_geometry()
        super().closeEvent(event)

    def reject(self) -> None:
        self._save_geometry()
        super().reject()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "toast"):
            self.toast._reposition()

    # ── دسترسی ──

    def _init_session(self, parent: Optional[QWidget]) -> None:
        ps = getattr(parent, "session", None)
        if ps:
            self.current_user: str = ps.username
            self.user_role: str = ps.role
            self.parent_session = ps
        else:
            self.current_user = "کاربر سیستم"
            self.user_role = "admin"
            self.parent_session = None

    def _has_perm(self, perm: str) -> bool:
        if self.parent_session:
            return can(self.parent_session, perm)
        return self.user_role == "admin"

    def _need_write(self) -> bool:
        if not self._has_perm(PERM_REPORT_WRITE):
            self.toast.show_message(
                "⛔ دسترسی ویرایش ندارید", color="#ef4444"
            )
            return False
        return True

    # ── بارگذاری داده ──

    def _with_wait_cursor(self, fn):
        """اجرای یک تابع با نشانگر انتظار."""
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            fn()
        finally:
            QApplication.restoreOverrideCursor()

    def _load_active_users(self) -> None:
        try:
            self.active_users = self.db.active_usernames()
        except Exception as exc:
            logger.exception("Failed to load users")
            self.active_users = []
            self.toast.show_message(
                f"خطا در خواندن کاربران: {exc}", color="#ef4444"
            )

    def _load_steps(self) -> None:
        prev = self._get_selected_step()
        self._selected_step_id = (
            prev.id if prev else self._selected_step_id
        )

        def _do():
            self._load_active_users()
            self.steps = self.db.get_workflow_steps(self.meeting.id)

        try:
            self._with_wait_cursor(_do)
        except Exception as exc:
            logger.exception("Failed to load steps")
            QMessageBox.critical(self, "خطا", str(exc))
            return

        self._populate_table()
        self._restore_selection()
        self._update_status()

    def _restore_selection(self) -> None:
        if self._selected_step_id:
            for i, s in enumerate(self.steps):
                if s.id == self._selected_step_id:
                    self.table.selectRow(i)
                    return
        ip = self._find_step("in_progress")
        if ip:
            for i, s in enumerate(self.steps):
                if s.id == ip.id:
                    self.table.selectRow(i)
                    return
        if self.steps:
            self.table.selectRow(0)

    # ── پرکردن جدول ──

    def _populate_table(self) -> None:
        self.table.setRowCount(len(self.steps))
        for i, step in enumerate(self.steps):
            self._set_row(i, step)
        self.table.resizeRowsToContents()

    @staticmethod
    def _step_label(step: WorkflowStep) -> str:
        name = (step.step_name or "").strip()
        return STEP_NAME_LABELS.get(name, name)

    def _set_row(self, row: int, step: WorkflowStep) -> None:
        sc = STATUS_COLORS.get(step.status)
        bg = QBrush(sc.lighter(185)) if sc else QBrush()
        fg = QBrush(sc.darker(160)) if sc else QBrush()

        def cell(text: str, center=True, bold=False):
            it = QTableWidgetItem(text)
            it.setFont(
                get_font(QFont.Weight.Bold if bold else QFont.Weight.Normal)
            )
            if center:
                it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if sc:
                it.setBackground(bg)
                it.setForeground(fg)
            return it

        entry = (
            to_shamsi(step.entry_date.isoformat()) if step.entry_date else ""
        )
        exit_ = (
            to_shamsi(step.exit_date.isoformat()) if step.exit_date else ""
        )
        icon = STATUS_ICONS.get(step.status, "")

        self.table.setItem(row, COL_IDX, cell(str(row + 1)))
        name_it = cell(f"{icon} {self._step_label(step)}", False, True)
        name_it.setToolTip(self._step_label(step))
        self.table.setItem(row, COL_NAME, name_it)
        status_text = STATUS_FA.get(step.status, step.status or "نامشخص")
        self.table.setItem(
            row, COL_STATUS, cell(f"{icon} {status_text}", center=True, bold=True)
        )
        self.table.setItem(row, COL_ENTRY, cell(entry))
        self.table.setItem(row, COL_EXIT, cell(exit_))
        self.table.setCellWidget(
            row, COL_RESP, self._make_resp_combo(step)
        )
        self.table.setItem(row, COL_SIGN, cell(step.signature or ""))
        notes_it = cell(step.notes or "", center=False)
        notes_it.setToolTip(step.notes or "")
        self.table.setItem(row, COL_NOTES, notes_it)

    def _make_resp_combo(self, step: WorkflowStep) -> QComboBox:
        cb = QComboBox()
        cb.setFont(get_font())
        cb.setMinimumWidth(110)
        cb.setStyleSheet(
            """
            QComboBox {
                border: none; background: transparent;
                padding: 1px 4px;
            }
            QComboBox:disabled { color: #475569; }
            QComboBox::drop-down {
                subcontrol-position: top left; width: 15px; border: none;
            }
            QComboBox QAbstractItemView {
                border: 1px solid #94a3b8; background: #fff;
                selection-background-color: #3b82f6; selection-color: #fff;
            }
        """
        )
        cb.addItem("—", "")
        for u in self.active_users:
            cb.addItem(u, u)
        cur = (step.responsible_person or "").strip()
        idx = cb.findData(cur)
        cb.setCurrentIndex(idx if idx >= 0 else 0)
        cb.setProperty("step_id", step.id)
        cb.setEnabled(
            step.status != "completed"
            and self._has_perm(PERM_REPORT_WRITE)
        )
        cb.currentIndexChanged.connect(self._on_resp_changed)
        return cb

    def _on_resp_changed(self) -> None:
        cb = self.sender()
        if not isinstance(cb, QComboBox) or cb.signalsBlocked():
            return
        if not self._need_write():
            cb.blockSignals(True)
            self._load_steps()
            cb.blockSignals(False)
            return
        step_id = cb.property("step_id")
        if not step_id:
            return
        val = (str(cb.currentData() or "")).strip() or None
        try:
            self.db.update_workflow_step(
                step_id=int(step_id), responsible_person=val
            )
        except Exception as exc:
            logger.exception("resp update failed")
            self.toast.show_message(f"خطا: {exc}", color="#ef4444")
            cb.blockSignals(True)
            self._load_steps()
            cb.blockSignals(False)
            return
        for s in self.steps:
            if s.id == int(step_id):
                s.responsible_person = val
                break
        self._update_status()
        self.toast.show_message("✅ کارشناس مسئول تغییر یافت", color="#3b82f6")

    # ── کمکی ──

    def _get_selected_step(self) -> Optional[WorkflowStep]:
        rows = self.table.selectionModel().selectedRows()
        if rows:
            idx = rows[0].row()
            if 0 <= idx < len(self.steps):
                return self.steps[idx]
        return None

    def _require_selected(self) -> Optional[WorkflowStep]:
        s = self._get_selected_step()
        if not s:
            self.toast.show_message(
                "ابتدا یک ردیف را انتخاب کنید", color="#f59e0b"
            )
            return None
        self._selected_step_id = s.id
        return s

    def _find_step(self, status: str) -> Optional[WorkflowStep]:
        for s in self.steps:
            if s.status == status:
                return s
        return None

    def _has_unfinished_before(self, step: WorkflowStep) -> bool:
        return any(
            s.step_order < step.step_order and s.status != "completed"
            for s in self.steps
        )

    # ── وضعیت و پروگرس ──

    def _update_status(self) -> None:
        completed = sum(1 for s in self.steps if s.status == "completed")
        total = len(self.steps)
        self.progress.setMaximum(total or 1)
        self.progress.setValue(completed)

        active = self._find_step("in_progress") or next(
            (
                s
                for s in sorted(self.steps, key=lambda x: x.step_order)
                if s.status == "pending"
            ),
            None,
        )
        selected = self._get_selected_step()

        # متن نوار وضعیت
        if self.steps and all(s.status == "completed" for s in self.steps):
            self.lbl_status.setText("✅ تمامی مراحل تکمیل شده است")
            self.lbl_status.setStyleSheet(
                "QLabel{background:#fff;border:1px solid #cbd5e1;"
                "border-radius:8px;padding:8px 14px;color:#15803d;"
                "font-weight:bold;}"
            )
        elif self._find_step("rejected"):
            self.lbl_status.setText("❌ جریان کار متوقف — گام رد شده وجود دارد")
            self.lbl_status.setStyleSheet(
                "QLabel{background:#fff;border:1px solid #cbd5e1;"
                "border-radius:8px;padding:8px 14px;color:#b91c1c;"
                "font-weight:bold;}"
            )
        elif active:
            ic = STATUS_ICONS.get(active.status, "")
            la = STATUS_FA.get(active.status, active.status)
            self.lbl_status.setText(
                f"{ic} مرحله جاری: {self._step_label(active)} — وضعیت: {la}"
            )
            clr = "#1d4ed8" if active.status == "in_progress" else "#b45309"
            self.lbl_status.setStyleSheet(
                f"QLabel{{background:#fff;border:1px solid #cbd5e1;"
                f"border-radius:8px;padding:8px 14px;color:{clr};"
                f"font-weight:bold;}}"
            )
        else:
            self.lbl_status.setText("⏳ در انتظار آغاز …")
            self.lbl_status.setStyleSheet(
                "QLabel{background:#fff;border:1px solid #cbd5e1;"
                "border-radius:8px;padding:8px 14px;color:#475569;"
                "font-weight:bold;}"
            )

        # فعال/غیرفعال دکمه‌ها
        hw = self._has_perm(PERM_REPORT_WRITE)
        hr = self._has_perm(PERM_REPORT_READ)
        ip = self._find_step("in_progress")

        self.btn_entry.setEnabled(
            hw
            and selected is not None
            and selected.status == "pending"
            and ip is None
        )
        self.btn_exit.setEnabled(
            hw and selected is not None and selected.status == "in_progress"
        )
        self.btn_notes.setEnabled(hw and selected is not None)
        self.btn_reopen.setEnabled(
            hw
            and selected is not None
            and selected.status == "rejected"
            and ip is None
        )
        self.btn_reject.setEnabled(
            hw and selected is not None and selected.status == "in_progress"
        )
        self.btn_prev.setEnabled(
            hw
            and selected is not None
            and selected.status in ("in_progress", "completed")
        )
        self.btn_print.setEnabled(hr)
        self.btn_perf.setEnabled(hr)

    # ══════════════════════════════════════
    #  عملیات‌ — بدون تأیید اضافی + Undo
    # ══════════════════════════════════════

    def _snapshot_step(self, step: WorkflowStep) -> Dict[str, Any]:
        """عکس فوری از گام و وضعیت ابلاغ پرونده برای Undo."""
        with self.db.session() as sess:
            meeting = sess.get(Meeting, self.meeting.id)
            meeting_state = {
                "sent_to_contractor_date": meeting.sent_to_contractor_date,
                "closing_date": meeting.closing_date,
                "contractor_response_date": meeting.contractor_response_date,
                "status": meeting.status,
            } if meeting else None
        return {
            "id": step.id,
            "entry_date": step.entry_date,
            "exit_date": step.exit_date,
            "responsible_person": step.responsible_person,
            "signature": step.signature,
            "status": step.status,
            "notes": step.notes,
            "meeting_state": meeting_state,
        }

    def _apply_snapshot(self, snap: Dict[str, Any]) -> None:
        """بازگرداندن گام و وضعیت پرونده به عکس فوری ذخیره‌شده."""
        try:
            with self.db.session() as sess:
                db_step = sess.get(WorkflowStep, snap["id"])
                if not db_step:
                    raise RuntimeError("گام یافت نشد")
                for field in (
                    "entry_date", "exit_date", "responsible_person",
                    "signature", "status", "notes",
                ):
                    setattr(db_step, field, snap[field])
                meeting_state = snap.get("meeting_state")
                meeting = sess.get(Meeting, self.meeting.id)
                if meeting and meeting_state:
                    for field, value in meeting_state.items():
                        setattr(meeting, field, value)
                sess.commit()
            self._load_steps()
            self.toast.show_message("تغییر قبلی بازگردانده شد.", color="#64748b")
        except Exception as exc:
            logger.exception("Undo failed")
            self.toast.show_message(f"خطا در بازگردانی: {exc}", color="#ef4444")

    # ── شروع اقدام ──

    def entry_step(self) -> None:
        if not self._need_write():
            return
        step = self._require_selected()
        if not step:
            return
        if step.status != "pending":
            self.toast.show_message(
                "فقط گام‌های «در انتظار» قابل شروع هستند", color="#f59e0b"
            )
            return
        if self._find_step("in_progress"):
            self.toast.show_message(
                "ابتدا گام باز فعلی را تکمیل کنید", color="#f59e0b"
            )
            return

        if self._has_unfinished_before(step):
            previous = next(
                s for s in sorted(self.steps, key=lambda item: item.step_order)
                if s.step_order < step.step_order and s.status != "completed"
            )
            self.toast.show_message(
                f"ابتدا مرحله قبلی را تکمیل کنید: {self._step_label(previous)}",
                color="#f59e0b",
                duration_ms=5000,
            )
            return

        snap = self._snapshot_step(step)
        responsible = (step.responsible_person or "").strip() or self.current_user

        try:
            self.db.update_workflow_step(
                step_id=step.id,
                entry_date=date.today(),
                exit_date=None,
                responsible_person=responsible,
                signature=None,
                status="in_progress",
            )
            self._load_steps()
            self.toast.show_message(
                f"📥 «{step.step_name}» آغاز شد — مسئول: {responsible}",
                color="#3b82f6",
                undo_callback=lambda: self._apply_snapshot(snap),
            )
        except Exception as exc:
            logger.exception("entry failed")
            self.toast.show_message(f"خطا: {exc}", color="#ef4444")

    # ── تکمیل و امضا ──

    def exit_step(self) -> None:
        if not self._need_write():
            return
        step = self._require_selected()
        if not step:
            return
        if step.status != "in_progress":
            self.toast.show_message(
                "فقط گام «در حال اقدام» قابل تکمیل است", color="#f59e0b"
            )
            return

        snap = self._snapshot_step(step)
        try:
            with self.db.session() as sess:
                db_step = sess.get(WorkflowStep, step.id)
                if not db_step:
                    raise RuntimeError("مرحله در پایگاه داده یافت نشد.")
                db_step.exit_date = date.today()
                db_step.signature = self.current_user
                db_step.status = "completed"

                # تکمیل آخرین مرحله، ابلاغ رسمی و بستن پرونده را نیز ثبت می‌کند.
                if step.step_order == max((s.step_order for s in self.steps), default=step.step_order):
                    db_meeting = sess.get(Meeting, self.meeting.id)
                    if db_meeting:
                        db_meeting.set_dispatched_to_contractor(date.today())
                sess.commit()

            if step.step_order == max((s.step_order for s in self.steps), default=step.step_order):
                self.meeting.set_dispatched_to_contractor(date.today())
                message = f"✅ «{self._step_label(step)}» تکمیل شد؛ ابلاغ ثبت و پرونده بسته شد."
            else:
                message = f"✅ «{self._step_label(step)}» تکمیل و امضا شد."

            self._load_steps()
            self.toast.show_message(
                message,
                color="#10b981",
                undo_callback=lambda: self._apply_snapshot(snap),
            )
        except Exception as exc:
            logger.exception("exit failed")
            self.toast.show_message(f"خطا: {exc}", color="#ef4444")

    # ── عودت برای اصلاح ──

    def reject_step(self) -> None:
        """ثبت عودت مرحله جاری همراه با علت روشن برای پیگیری بعدی."""
        if not self._need_write():
            return
        step = self._require_selected()
        if not step:
            return
        if step.status != "in_progress":
            self.toast.show_message(
                "برای عودت، ابتدا مرحله را شروع کنید و سپس علت نقص را ثبت کنید.",
                color="#f59e0b",
            )
            return

        reason, ok = QInputDialog.getMultiLineText(
            self,
            "عودت مرحله برای اصلاح",
            f"علت عودت «{self._step_label(step)}» را دقیق بنویسید:",
            "",
        )
        reason = (reason or "").strip()
        if not ok:
            return
        if not reason:
            QMessageBox.warning(
                self, "علت عودت الزامی است",
                "برای پیگیری شفاف، لطفاً علت عودت را وارد کنید.",
            )
            return

        snap = self._snapshot_step(step)
        existing_notes = (step.notes or "").strip()
        note = f"علت عودت: {reason}"
        notes = f"{existing_notes}\n{note}" if existing_notes else note
        try:
            self.db.update_workflow_step(
                step_id=step.id,
                exit_date=date.today(),
                signature=self.current_user,
                status="rejected",
                notes=notes,
            )
            self._load_steps()
            self.toast.show_message(
                f"↩️ «{self._step_label(step)}» عودت شد؛ علت ثبت شد.",
                color="#c2410c",
                undo_callback=lambda: self._apply_snapshot(snap),
            )
        except Exception as exc:
            logger.exception("reject step failed")
            self.toast.show_message(f"خطا در ثبت عودت: {exc}", color="#ef4444")

    # ── بازگشایی ردیف رد شده ──

    def reopen_step(self) -> None:
        if not self._need_write():
            return
        step = self._require_selected()
        if not step:
            return
        if step.status != "rejected":
            self.toast.show_message(
                "فقط گام‌های «رد شده» قابل بازگشایی‌اند", color="#f59e0b"
            )
            return
        if self._find_step("in_progress"):
            self.toast.show_message(
                "ابتدا گام باز را تکمیل کنید", color="#f59e0b"
            )
            return

        snap = self._snapshot_step(step)
        responsible = (step.responsible_person or "").strip() or self.current_user
        try:
            self.db.update_workflow_step(
                step_id=step.id,
                entry_date=date.today(),
                exit_date=None,
                responsible_person=responsible,
                signature=None,
                status="in_progress",
            )
            self._load_steps()
            self.toast.show_message(
                f"🔄 «{step.step_name}» بازگشایی شد",
                color="#3b82f6",
                undo_callback=lambda: self._apply_snapshot(snap),
            )
        except Exception as exc:
            logger.exception("reopen failed")
            self.toast.show_message(f"خطا: {exc}", color="#ef4444")

    # ── بازگردانی به مرحله قبل ──
    # ⚠️ تنها عملیاتی که هنوز تأیید می‌گیرد — چون مراحل بعدی ریست می‌شوند

    def go_to_previous_step(self) -> None:
        if not self._need_write():
            return
        step = self._require_selected()
        if not step:
            return
        if step.status not in ("in_progress", "completed"):
            self.toast.show_message(
                "فقط گام «در جریان» یا «تکمیل‌شده» قابل عودت است",
                color="#f59e0b",
            )
            return
        ip = self._find_step("in_progress")
        if step.status == "completed" and ip is not None:
            self.toast.show_message(
                "ابتدا گام باز را نهایی کنید", color="#f59e0b"
            )
            return

        # ⚠️ تأیید فقط اینجا — چون ریست زنجیره‌ای انجام می‌شود
        reply = QMessageBox.question(
            self,
            "بازگردانی گام",
            f"«{step.step_name}» و تمام گام‌های بعدی ریست می‌شوند.\nادامه می‌دهید؟",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            self._db_revert_step(step)
            self._load_steps()
            self.toast.show_message(
                f"↩️ «{step.step_name}» بازگردانی شد", color="#f59e0b"
            )
        except Exception as exc:
            logger.exception("revert failed")
            self.toast.show_message(f"خطا: {exc}", color="#ef4444")

    def _db_revert_step(self, step: WorkflowStep) -> None:
        with self.db.session() as sess:
            db_step = sess.get(WorkflowStep, step.id)
            if not db_step:
                raise RuntimeError("گام یافت نشد")
            if step.status == "completed":
                db_step.status = "in_progress"
                db_step.exit_date = None
                db_step.signature = None
                for s in (
                    sess.query(WorkflowStep)
                    .filter(
                        WorkflowStep.meeting_id == self.meeting.id,
                        WorkflowStep.step_order > step.step_order,
                    )
                    .all()
                ):
                    s.status = "pending"
                    s.entry_date = None
                    s.exit_date = None
                    s.responsible_person = None
                    s.signature = None
            elif step.status == "in_progress":
                db_step.status = "pending"
                db_step.entry_date = None
                db_step.exit_date = None
                db_step.signature = None

            if step.step_order == max((s.step_order for s in self.steps), default=step.step_order):
                meeting = sess.get(Meeting, self.meeting.id)
                if meeting:
                    meeting.sent_to_contractor_date = None
                    meeting.closing_date = None
                    meeting.contractor_response_date = None
                    meeting.status = STATUS_PENDING
            sess.commit()

    # ── ویرایش یادداشت ──

    def edit_notes(self) -> None:
        if not self._need_write():
            return
        step = self._require_selected()
        if not step:
            return
        notes, ok = QInputDialog.getMultiLineText(
            self,
            "ویرایش یادداشت",
            f"یادداشت «{step.step_name}»:",
            step.notes or "",
        )
        if not ok:
            return
        try:
            self.db.update_workflow_step(
                step_id=step.id, notes=(notes or "").strip()
            )
            self._load_steps()
            self.toast.show_message("📝 یادداشت ذخیره شد", color="#6366f1")
        except Exception as exc:
            self.toast.show_message(f"خطا: {exc}", color="#ef4444")

    # ── گزارش عملکرد ──

    def show_performance_report(self) -> None:
        if not self._has_perm(PERM_REPORT_READ):
            self.toast.show_message("دسترسی ندارید", color="#ef4444")
            return
        try:
            rows = self.db.workflow_performance_by_user()
            if not rows:
                self.toast.show_message(
                    "هنوز رکوردی ثبت نشده", color="#f59e0b"
                )
                return
            PerformanceReportDialog(data=rows, parent=self).exec()
        except Exception as exc:
            logger.exception("perf report failed")
            self.toast.show_message(f"خطا: {exc}", color="#ef4444")

    # ── چاپ ──

    def save_and_print_report(self) -> None:
        if not self._has_perm(PERM_REPORT_READ):
            self.toast.show_message("دسترسی ندارید", color="#ef4444")
            return
        try:
            gen = WorkflowReportGenerator(
                meeting=self.meeting, steps=self.steps, parent_widget=self
            )
            gen.generate_and_open()
            self.toast.show_message(
                "🖨️ سند گردش کار آماده چاپ شد — Ctrl+P در مرورگر",
                color="#10b981",
            )
        except Exception as exc:
            logger.exception("print failed")
            self.toast.show_message(f"خطا: {exc}", color="#ef4444")

    # ── منوی راست‌کلیک ──

    def _show_context_menu(self, pos: QPoint) -> None:
        item = self.table.itemAt(pos)
        if not item:
            return
        row = item.row()
        self.table.selectRow(row)
        step = self.steps[row]
        self._selected_step_id = step.id

        hw = self._has_perm(PERM_REPORT_WRITE)
        hr = self._has_perm(PERM_REPORT_READ)
        ip = self._find_step("in_progress")

        menu = QMenu(self)
        menu.setFont(get_font())
        menu.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        a_detail = menu.addAction("ℹ️ جزئیات")
        menu.addSeparator()

        a_entry = menu.addAction("📥 شروع اقدام")
        a_entry.setEnabled(
            step.status == "pending" and hw and ip is None
        )

        a_exit = menu.addAction("📤 تکمیل و امضا")
        a_exit.setEnabled(step.status == "in_progress" and hw)

        a_rev = menu.addAction("↩️ بازگردانی")
        a_rev.setEnabled(
            step.status in ("in_progress", "completed") and hw
        )

        a_reopen = menu.addAction("🔄 ادامه پس از اصلاح")
        a_reopen.setEnabled(
            step.status == "rejected" and hw and ip is None
        )

        a_reject = menu.addAction("↩️ عودت برای اصلاح")
        a_reject.setEnabled(step.status == "in_progress" and hw)

        menu.addSeparator()
        a_notes = menu.addAction("📝 یادداشت")
        a_notes.setEnabled(hw)

        menu.addSeparator()
        a_perf = menu.addAction("📊 عملکرد کارشناسان")
        a_perf.setEnabled(hr)

        chosen = menu.exec(self.table.viewport().mapToGlobal(pos))
        if not chosen:
            return

        actions = {
            a_detail: lambda: self._show_step_detail(step),
            a_entry: self.entry_step,
            a_exit: self.exit_step,
            a_rev: self.go_to_previous_step,
            a_reopen: self.reopen_step,
            a_reject: self.reject_step,
            a_notes: self.edit_notes,
            a_perf: self.show_performance_report,
        }
        fn = actions.get(chosen)
        if fn:
            fn()

    # ── دابل‌کلیک هوشمند ──

    def _on_double_click(self, index) -> None:
        row = index.row()
        if not (0 <= row < len(self.steps)):
            return
        step = self.steps[row]
        self._selected_step_id = step.id

        if self._has_perm(PERM_REPORT_WRITE):
            if step.status == "pending" and not self._find_step("in_progress"):
                self.entry_step()
                return
            if step.status == "in_progress":
                self.exit_step()
                return
            if step.status == "rejected" and not self._find_step(
                "in_progress"
            ):
                self.reopen_step()
                return

        self._show_step_detail(step)

    # ── جزئیات گام ──

    def _show_step_detail(self, step: WorkflowStep) -> None:
        entry = (
            to_shamsi(step.entry_date.isoformat())
            if step.entry_date
            else "ثبت نشده"
        )
        exit_ = (
            to_shamsi(step.exit_date.isoformat())
            if step.exit_date
            else "ثبت نشده"
        )
        ic = STATUS_ICONS.get(step.status, "")
        st = STATUS_FA.get(step.status, step.status)

        QMessageBox.information(
            self,
            "جزئیات گام",
            f"📋 {self._step_label(step)}\n"
            f"وضعیت: {ic} {st}\n\n"
            f"📅 ورود: {entry}\n"
            f"📅 خروج: {exit_}\n\n"
            f"👤 مسئول: {step.responsible_person or '—'}\n"
            f"✒️ امضا: {step.signature or '—'}\n\n"
            f"📝 یادداشت:\n{step.notes or '—'}",
        )
