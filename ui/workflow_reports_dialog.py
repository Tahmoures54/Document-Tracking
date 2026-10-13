# -*- coding: utf-8 -*-
"""پنجره گزارش زمان رسیدگی صورتجلسات."""
from __future__ import annotations

import logging
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from security.permissions import PERM_REPORT_READ, can
from services.workflow_report import WorkflowOverviewReportGenerator, WorkflowReportGenerator

logger = logging.getLogger(__name__)


class WorkflowReportsDialog(QDialog):
    """فهرست صورتجلسات و دو مسیر گزارش: جزئیات یک پرونده یا گزارش تجمیعی."""

    def __init__(self, db, session, parent=None):
        super().__init__(parent)
        self.db = db
        self.session = session
        self.meetings = []
        self.setWindowTitle("گزارش زمان رسیدگی صورتجلسات")
        self.resize(1120, 680)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setStyleSheet("""
            QDialog { background:#f3f6fb; color:#172033; font-family:Tahoma; font-size:10pt; }
            QLabel#title { font-size:18pt; font-weight:bold; color:#12354a; padding:4px; }
            QLabel#hint { color:#64748b; padding:2px 4px; }
            QLineEdit,QComboBox { background:white; border:1px solid #cbd5e1; border-radius:8px; padding:8px; min-height:20px; }
            QTableWidget { background:white; border:1px solid #dbe4ef; border-radius:10px; gridline-color:#e2e8f0; }
            QHeaderView::section { background:#17384d; color:white; border:0; padding:9px; font-weight:bold; }
            QTableWidget::item { padding:7px; }
            QPushButton { border:0; border-radius:8px; padding:10px 14px; font-weight:bold; background:#e2e8f0; color:#24364b; }
            QPushButton#primary { background:#0f766e; color:white; }
            QPushButton#secondary { background:#dbeafe; color:#1e40af; }
        """)
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(10)

        title = QLabel("⏱ گزارش زمان رسیدگی")
        title.setObjectName("title")
        root.addWidget(title)
        hint = QLabel("مدت رسیدگی کل و زمان هر مرحله را بررسی کنید؛ گزارش‌ها در قالب HTML و قابل چاپ هستند.")
        hint.setObjectName("hint")
        root.addWidget(hint)

        filters = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("جستجو در شماره، موضوع، کارفرما یا پیمانکار…")
        self.search.setClearButtonEnabled(True)
        self.status_filter = QComboBox()
        self.status_filter.addItems(["همه وضعیت‌ها", "در دست بررسی", "در انتظار تأیید", "تکمیل شده", "لغو شده", "بازگشت داده شده"])
        filters.addWidget(self.search, 1)
        filters.addWidget(QLabel("وضعیت:"))
        filters.addWidget(self.status_filter)
        root.addLayout(filters)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["شماره صورتجلسه", "موضوع", "کارفرما", "پیمانکار", "وضعیت", "مدت سپری‌شده"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        root.addWidget(self.table, 1)

        buttons = QHBoxLayout()
        self.btn_detail = QPushButton("📄 گزارش کامل صورتجلسه انتخاب‌شده")
        self.btn_detail.setObjectName("primary")
        self.btn_overview = QPushButton("📊 گزارش تجمیعی همه صورتجلسات")
        self.btn_overview.setObjectName("secondary")
        self.btn_refresh = QPushButton("↻ بروزرسانی")
        self.btn_close = QPushButton("بستن")
        buttons.addWidget(self.btn_detail)
        buttons.addWidget(self.btn_overview)
        buttons.addStretch()
        buttons.addWidget(self.btn_refresh)
        buttons.addWidget(self.btn_close)
        root.addLayout(buttons)

        self.search.textChanged.connect(self._render_rows)
        self.status_filter.currentTextChanged.connect(self._render_rows)
        self.table.itemDoubleClicked.connect(lambda _item: self.open_selected_report())
        self.btn_detail.clicked.connect(self.open_selected_report)
        self.btn_overview.clicked.connect(self.open_overview_report)
        self.btn_refresh.clicked.connect(self.load_data)
        self.btn_close.clicked.connect(self.accept)
        self.load_data()

    @staticmethod
    def _elapsed_text(meeting, steps):
        from datetime import date
        start_candidates = [s.entry_date for s in steps if s.entry_date]
        start = min(start_candidates) if start_candidates else (meeting.entry_date or meeting.created_at)
        if not start:
            return "شروع ثبت نشده"
        if hasattr(start, "date") and not isinstance(start, date):
            start = start.date()
        end = meeting.sent_to_contractor_date or meeting.closing_date
        if end and hasattr(end, "date") and not isinstance(end, date):
            end = end.date()
        end = end or date.today()
        days = max(0, (end - start).days)
        label = "کمتر از یک روز" if days == 0 else f"{days:,} روز"
        return label if (meeting.sent_to_contractor_date or meeting.closing_date) else f"{label} · در جریان"

    def load_data(self):
        if not can(self.session, PERM_REPORT_READ):
            QMessageBox.warning(self, "دسترسی غیرمجاز", "شما اجازه مشاهده گزارش‌ها را ندارید.")
            self.reject()
            return
        try:
            all_meetings = []
            offset = 0
            page_size = 500
            while True:
                rows, total = self.db.query_meetings_page({}, "", "id", "DESC", page_size, offset)
                all_meetings.extend(rows)
                offset += len(rows)
                if not rows or offset >= total:
                    break
            self.meetings = all_meetings
            self._render_rows()
        except Exception as exc:
            logger.exception("Could not load workflow reports")
            QMessageBox.critical(self, "خطا در بارگذاری", f"بارگذاری فهرست صورتجلسات انجام نشد:\n{exc}")

    def _filtered_meetings(self):
        needle = self.search.text().strip().casefold()
        status = self.status_filter.currentText()
        filtered = []
        for meeting in self.meetings:
            if status != "همه وضعیت‌ها" and (meeting.status or "") != status:
                continue
            searchable = " ".join(str(v or "") for v in (
                meeting.meeting_number, meeting.subject, meeting.employer, meeting.contractor
            )).casefold()
            if needle and needle not in searchable:
                continue
            filtered.append(meeting)
        return filtered

    def _render_rows(self):
        if not hasattr(self, "table"):
            return
        rows = self._filtered_meetings()
        self.table.setRowCount(len(rows))
        for row, meeting in enumerate(rows):
            try:
                steps = self.db.get_workflow_steps(meeting.id)
                duration = self._elapsed_text(meeting, steps)
            except Exception:
                logger.exception("Could not calculate meeting duration: %s", meeting.id)
                duration = "خطا در محاسبه"
            values = [
                meeting.meeting_number or "—", meeting.subject or "—",
                meeting.employer or "—", meeting.contractor or "—",
                meeting.status or "—", duration,
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                item.setData(Qt.ItemDataRole.UserRole, meeting.id)
                self.table.setItem(row, col, item)
        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(1, max(220, self.table.columnWidth(1)))
        self.table.setColumnWidth(5, 150)
        self.btn_detail.setEnabled(bool(rows))
        self.btn_overview.setText(f"📊 گزارش تجمیعی همه صورتجلسات ({len(self.meetings):,})")

    def _selected_meeting(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        meeting_id = item.data(Qt.ItemDataRole.UserRole) if item else None
        return next((m for m in self.meetings if m.id == meeting_id), None)

    def open_selected_report(self):
        meeting = self._selected_meeting()
        if not meeting:
            QMessageBox.information(self, "انتخاب صورتجلسه", "ابتدا یک صورتجلسه را انتخاب کنید.")
            return
        try:
            steps = self.db.get_workflow_steps(meeting.id)
            path = WorkflowReportGenerator(meeting, steps, self).generate_and_open()
            if path:
                self.status_filter.setToolTip(f"گزارش ذخیره شد: {path}")
        except Exception as exc:
            logger.exception("Could not generate individual workflow report")
            QMessageBox.critical(self, "خطای گزارش", f"ساخت گزارش انجام نشد:\n{exc}")

    def open_overview_report(self):
        try:
            steps_by_meeting = {
                meeting.id: self.db.get_workflow_steps(meeting.id)
                for meeting in self.meetings
            }
            path = WorkflowOverviewReportGenerator(
                self.meetings, steps_by_meeting, self
            ).generate_and_open()
            if path:
                QMessageBox.information(self, "گزارش آماده است", f"گزارش تجمیعی HTML ساخته شد و در مرورگر باز شد.\n\n{path}")
        except Exception as exc:
            logger.exception("Could not generate overview report")
            QMessageBox.critical(self, "خطای گزارش", f"ساخت گزارش تجمیعی انجام نشد:\n{exc}")
