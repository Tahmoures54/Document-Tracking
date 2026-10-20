# -*- coding: utf-8 -*-
"""
ui.main_window
پنجره اصلی برنامه Document & MOM Tracking System
نسخه ۳.۱: تحلیل‌شده و اصلاح‌شده
- ادغام رنگ‌ها در ثابت‌های ماژول (theme constants)
- تراکنش اتمیک در همگام‌سازی سراسری
- بسته‌شدن هدفمند گام‌ها بر اساس قانون طلایی ابلاغ به پیمانکار
- تخمین عرض ستون با QFontMetrics برای متون فارسی
- حذف کد مرده و importهای بی‌استفاده
- هشدارهای غیرمزاحم در StatusBar
"""
from __future__ import annotations

import csv
import logging
import math
import os
from datetime import date
from functools import lru_cache
from typing import Any, Callable, Dict, List, Optional, Tuple

from PyQt6.QtCore import (
    Qt,
    QAbstractTableModel,
    QModelIndex,
    QPropertyAnimation,
    QRectF,
    QSettings,
    QThreadPool,
    QTimer,
    QUrl,
    QEasingCurve,
    pyqtProperty,
)
from PyQt6.QtGui import (
    QAction,
    QBrush,
    QCloseEvent,
    QColor,
    QDesktopServices,
    QFontMetrics,
    QKeySequence,
    QPainter,
    QRadialGradient,
    QPalette,
)
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMenuBar,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QStyle,
    QStyleOptionViewItem,
    QStyledItemDelegate,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from config import (
    APP_NAME, DEFAULT_PAGE_SIZE, ORG_NAME, SEARCH_DEBOUNCE_MS,
    DEFAULT_SCAN_PATH, SCAN_FILE_EXTENSIONS,
)
from db.manager import DatabaseManager
from db.models import Meeting, DISCIPLINES, WorkflowStep
from security.permissions import (
    PERM_DB_PUBLISH,
    PERM_REPORT_EXPORT,
    PERM_REPORT_READ,
    PERM_REPORT_WRITE,
    PERM_USER_ADMIN,
    can,
)
from security.session import UserSession
from utils.date_utils import to_gregorian, to_shamsi, today_shamsi
from services.workflow_status import derive_workflow_state

logger = logging.getLogger(__name__)


def _has_matplotlib() -> bool:
    try:
        from ui.chart_dialog import HAS_MATPLOTLIB
        return bool(HAS_MATPLOTLIB)
    except Exception:
        return False


# ─────────────────────────────────────────────
# ثابت‌های سراسری UI
# ─────────────────────────────────────────────
COLOR_SKY_BLUE = "#00BFFF"
COLOR_SKY_DARK = "#0099CC"
COLOR_SELECTION_BG = "#E0F7FA"
COLOR_SELECTION_FG = "#004D40"
COLOR_TEXT_MAIN = "#1E293B"

FILTER_ALL_LABEL = "همه"

# ─────────────────────────────────────────────
# وضعیت‌ها و اولویت‌ها
# ─────────────────────────────────────────────
STATUS_PENDING = "در دست بررسی"
STATUS_AWAITING = "در انتظار تأیید"
STATUS_COMPLETED = "تکمیل شده"
STATUS_CANCELLED = "لغو شده"
STATUS_RETURNED = "بازگشت داده شده"

STATUSES: List[str] = [
    STATUS_PENDING,
    STATUS_AWAITING,
    STATUS_COMPLETED,
    STATUS_CANCELLED,
    STATUS_RETURNED,
]

PRIORITY_HIGH = "بالا"
PRIORITY_MEDIUM = "متوسط"
PRIORITY_LOW = "پایین"
PRIORITIES: List[str] = [PRIORITY_HIGH, PRIORITY_MEDIUM, PRIORITY_LOW]

OPEN_STATUSES: List[str] = [STATUS_PENDING, STATUS_AWAITING, STATUS_RETURNED]

try:
    from security.permissions import PERM_MEETING_DELETE  # type: ignore
except ImportError:
    PERM_MEETING_DELETE = PERM_REPORT_WRITE

DATE_COLUMNS: frozenset = frozenset([
    "ارسال به نظارت", "ورود به نظارت", "ورود به کارفرما",
    "تاریخ صورتجلسه", "تاریخ قرارداد", "تاریخ ثبت / ورود به کارفرما",
    "تاریخ ارسال به پیمانکار", "مهلت رسیدگی", "مهلت انجام", "تاریخ بسته شدن", "تاریخ پاسخ پیمانکار",
])

HEADER_TO_DB_COL: Dict[str, str] = {
    "ردیف": "id",
    "ارسال به نظارت": "sent_to_supervision_date",
    "ورود به نظارت": "supervision_entry_date",
    "تاریخ ثبت / ورود به کارفرما": "entry_date",
    "ورود به کارفرما": "entry_date",
    "تاریخ صورتجلسه": "meeting_date",
    "شماره صورتجلسه": "meeting_number",
    "کارفرما": "employer", "مشاور": "consultant", "پیمانکار": "contractor",
    "شماره قرارداد": "contract_number", "تاریخ قرارداد": "contract_date",
    "موضوع": "subject", "دیسیپلین": "discipline", "محل کار": "location",
    "وضعیت": "status", "اولویت": "priority",
    "مهلت رسیدگی": "due_date", "مهلت انجام": "due_date",
    "تاریخ بسته شدن": "closing_date",
    "تاریخ ارسال به پیمانکار": "sent_to_contractor_date",
    "تاریخ پاسخ پیمانکار": "contractor_response_date",
}

# ─────────────────────────────────────────────
# پالت رنگ مرکزی (theme) — تنها منبع حقیقت برای رنگ‌های وضعیت
# ─────────────────────────────────────────────
WORKFLOW_STATE_COLORS: Dict[str, Tuple[str, str]] = {
    "completed":   ("#DCFCE7", "#166534"),
    "in_progress": ("#DBEAFE", "#1D4ED8"),
    "pending":     ("#FEF3C7", "#92400E"),
    "returned":    ("#FEE2E2", "#991B1B"),
    "cancelled":   ("#F3F4F6", "#4B5563"),
    "unknown":     ("#F3F4F6", "#374151"),
}

STATUS_BG_COLORS: Dict[str, str] = {
    STATUS_COMPLETED: "#DCFCE7",
    STATUS_PENDING:   "#FEF3C7",
    STATUS_AWAITING:  "#E0F2FE",
    STATUS_CANCELLED: "#FEE2E2",
    STATUS_RETURNED:  "#FFEDD5",
}

OVERDUE_BG, OVERDUE_FG = "#FEE2E2", "#991B1B"
WARNING_BG, WARNING_FG = "#FEF3C7", "#92400E"
WARNING_DAYS = 3
DEFAULT_FG = "#1E293B"
SELECTION_ROW_BG = "#BAE6FD"
SELECTION_ROW_FG = "#0C4A6E"

LEGEND_ITEMS: List[Tuple[str, str, str]] = [
    ("در حال انجام",       "#DBEAFE", "#1D4ED8"),
    ("در انتظار",          "#FEF3C7", "#92400E"),
    ("برگشت برای اصلاح",   "#FFE4E6", "#9F1239"),
    ("تکمیل و ابلاغ‌شده",   "#D1FAE5", "#166534"),
    ("لغوشده / نامشخص",    "#F3F4F6", "#4B5563"),
]


@lru_cache(maxsize=4096)
def _cached_to_shamsi(value: str) -> str:
    try:
        return to_shamsi(value) or value
    except Exception:
        return value


@lru_cache(maxsize=2048)
def _cached_days_until(shamsi_date: str) -> Optional[int]:
    try:
        g = to_gregorian(shamsi_date)
        if not g:
            return None
        return (date.fromisoformat(g) - date.today()).days
    except Exception:
        return None


# ─────────────────────────────────────────────
# دکمه انیمیشنی گردش کار
# ─────────────────────────────────────────────
class MeteorButton(QPushButton):
    """دکمه لوکس با افکت انیمیشن شهاب‌سنگ روی لبه‌ها."""

    ANIMATION_DURATION_MS = 3200
    TRAIL_COUNT = 10
    TRAIL_ANGLE_STEP = 4

    def __init__(self, text: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(text, parent)
        self._angle: float = 0.0
        self._running: bool = True

        self._anim = QPropertyAnimation(self, b"meteorAngle", self)
        self._anim.setDuration(self.ANIMATION_DURATION_MS)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(360.0)
        self._anim.setLoopCount(-1)
        self._anim.setEasingCurve(QEasingCurve.Type.Linear)
        self._anim.start()

    def _get_angle(self) -> float:
        return self._angle

    def _set_angle(self, val: float) -> None:
        self._angle = val
        self.update()

    meteorAngle = pyqtProperty(float, _get_angle, _set_angle)

    def _point_on_rect(self, angle_deg: float) -> Tuple[float, float]:
        w, h = self.width(), self.height()
        cx, cy = w / 2.0, h / 2.0
        rad = math.radians(angle_deg)
        dx, dy = math.cos(rad), math.sin(rad)
        hw, hh = cx - 1, cy - 1

        if abs(dx) < 1e-9:
            return cx, (cy + hh) if dy > 0 else (cy - hh)
        if abs(dy) < 1e-9:
            return (cx + hw) if dx > 0 else (cx - hw), cy

        scale = min(hw / abs(dx), hh / abs(dy))
        return cx + dx * scale, cy + dy * scale

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if not self._running or not self.isEnabled():
            return

        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            self._draw_trail(painter)
            self._draw_meteor_head(painter)
        finally:
            painter.end()

    def _draw_trail(self, painter: QPainter) -> None:
        for i in range(self.TRAIL_COUNT, 0, -1):
            a = self._angle - i * self.TRAIL_ANGLE_STEP
            px, py = self._point_on_rect(a)
            frac = 1.0 - i / (self.TRAIL_COUNT + 1)
            alpha = int(180 * frac)
            r = 2.2 * frac
            if r < 0.3:
                continue

            grad = QRadialGradient(px, py, r + 2)
            grad.setColorAt(0, QColor(0, 255, 240, alpha))
            grad.setColorAt(1, QColor(0, 180, 255, 0))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(grad))
            painter.drawEllipse(QRectF(px - r - 2, py - r - 2, (r + 2) * 2, (r + 2) * 2))

    def _draw_meteor_head(self, painter: QPainter) -> None:
        mx, my = self._point_on_rect(self._angle)
        glow = QRadialGradient(mx, my, 7)
        glow.setColorAt(0, QColor(255, 255, 255, 150))
        glow.setColorAt(1, QColor(0, 240, 255, 0))
        painter.setBrush(QBrush(glow))
        painter.drawEllipse(QRectF(mx - 7, my - 7, 14, 14))

        core = QRadialGradient(mx, my, 2.5)
        core.setColorAt(0, QColor(255, 255, 255, 255))
        core.setColorAt(1, QColor(0, 170, 255, 0))
        painter.setBrush(QBrush(core))
        painter.drawEllipse(QRectF(mx - 2.5, my - 2.5, 5, 5))

    def stop_meteor(self) -> None:
        self._running = False
        self._anim.stop()
        self.update()

    def start_meteor(self) -> None:
        self._running = True
        self._anim.start()


# ─────────────────────────────────────────────
# Table model
# ─────────────────────────────────────────────
class MeetingsPageModel(QAbstractTableModel):
    """مدل جدول نمایش اطلاعات با رنگ‌بندی داینامیک وضعیت‌ها."""

    def __init__(self) -> None:
        super().__init__()
        self._orig_headers: List[str] = Meeting.headers()
        self.headers: List[str] = ["#"] + self._orig_headers + ["کارشناس رسیدگی‌کننده", "مرحله جاری"]
        self.rows: List[List[Any]] = []
        # وضعیت واقعی گردش‌کار، جدا از وضعیت عمومی پرونده نگهداری می‌شود.
        # کلیدها شناسه پرونده‌اند تا هیچ ستون داخلی به جدول نمایشی اضافه نشود.
        self.workflow_states: Dict[int, str] = {}

        self._col_status = self._find("وضعیت")
        self._col_due = self._find("مهلت رسیدگی")
        self._col_id = self._find("ردیف")
        self._col_meeting_number = self._find("شماره صورتجلسه")
        self._col_drawing_number = self._find("شماره نقشه")
        self._col_contract_number = self._find("شماره قرارداد")

        self._col_responsible = len(self._orig_headers)
        self._col_stage = len(self._orig_headers) + 1

    def _find(self, name: str) -> int:
        try:
            return self._orig_headers.index(name)
        except ValueError:
            return -1

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self.rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self.headers)

    def headerData(self, section: int, orientation: Qt.Orientation,
                   role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if (orientation == Qt.Orientation.Horizontal
                and role == Qt.ItemDataRole.DisplayRole
                and 0 <= section < len(self.headers)):
            return self.headers[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        row, col = index.row(), index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            return self._display_value(row, col)

        if role in (Qt.ItemDataRole.BackgroundRole, Qt.ItemDataRole.ForegroundRole):
            return self._color(row, role)

        if role == Qt.ItemDataRole.TextAlignmentRole:
            return Qt.AlignmentFlag.AlignCenter

        return None

    def _display_value(self, row: int, col: int) -> str:
        if col == 0:
            return str(row + 1)
        if col == self._col_responsible + 1:
            val = self._cell(row, self._col_responsible)
            if val == "admin":
                return "مدیر سیستم (admin)"
            return str(val or "—")

        if col == self._col_stage + 1:
            return str(self._cell(row, self._col_stage) or "—")

        v = self._cell(row, col - 1)
        if v is None:
            return ""

        col_idx = col - 1
        if col_idx in (self._col_meeting_number, self._col_drawing_number, self._col_contract_number):
            return f"\u200e{v}"

        return str(v)

    def set_rows(self, rows: List[List[Any]]) -> None:
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()

    def set_workflow_states(self, states: Dict[int, str]) -> None:
        """تنظیم وضعیت واقعی گردش‌کار برای رنگ‌بندی ردیف‌ها."""
        self.workflow_states = dict(states)
        if self.rows:
            left = self.index(0, 0)
            right = self.index(len(self.rows) - 1, max(0, self.columnCount() - 1))
            self.dataChanged.emit(
                left, right,
                [Qt.ItemDataRole.BackgroundRole, Qt.ItemDataRole.ForegroundRole],
            )

    def _cell(self, r: int, c: int) -> Any:
        try:
            return self.rows[r][c]
        except (IndexError, TypeError):
            return None

    def _color(self, row: int, role: int) -> Optional[QBrush]:
        is_bg = role == Qt.ItemDataRole.BackgroundRole

        # ۱. رنگ ردیف از وضعیت واقعی گام‌ها (اولویت اول)
        meeting_id = self.get_row_id(row)
        workflow_state = self.workflow_states.get(meeting_id) if meeting_id is not None else None
        colors = WORKFLOW_STATE_COLORS.get(workflow_state or "")
        if colors:
            return QBrush(QColor(colors[0] if is_bg else colors[1]))

        # ۲. رنگ از وضعیت ذخیره‌شده در DB
        if self._col_status >= 0:
            v = self._cell(row, self._col_status)
            status = str(v).strip() if v else None
            if status:
                bg = STATUS_BG_COLORS.get(status) if is_bg else None
                if bg:
                    return QBrush(QColor(bg))
                if not is_bg:
                    return QBrush(QColor(DEFAULT_FG))

        # ۳. هشدار سررسید
        if self._col_due >= 0:
            v = self._cell(row, self._col_due)
            due_str = str(v).strip() if v else None
            if due_str:
                days = _cached_days_until(due_str)
                if days is not None:
                    if days < 0:
                        return QBrush(QColor(OVERDUE_BG if is_bg else OVERDUE_FG))
                    if days <= WARNING_DAYS:
                        return QBrush(QColor(WARNING_BG if is_bg else WARNING_FG))

        if not is_bg:
            return QBrush(QColor(DEFAULT_FG))
        return None

    def get_row_id(self, row: int) -> Optional[int]:
        if self._col_id < 0:
            return None
        try:
            return int(self.rows[row][self._col_id])
        except (IndexError, TypeError, ValueError):
            return None


class StatusRowDelegate(QStyledItemDelegate):
    """رسم صریح پس‌زمینه تمام سلول‌های ردیف بر اساس وضعیت پرونده."""

    def paint(self, painter, option, index) -> None:
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)

        bg = index.data(Qt.ItemDataRole.BackgroundRole)
        if isinstance(bg, QBrush):
            bg_color = bg.color()
        elif isinstance(bg, QColor):
            bg_color = bg
        else:
            bg_color = QColor("#FFFFFF")

        selected = bool(opt.state & QStyle.StateFlag.State_Selected)
        # پس‌زمینه را خود delegate رسم می‌کند تا استایل عمومی برنامه نتواند
        # رنگ وضعیت را با رنگ سفید/هاور جایگزین کند.
        painter.save()
        painter.fillRect(opt.rect, QColor(SELECTION_ROW_BG) if selected else bg_color)
        painter.restore()

        # جلوگیری از نقاشی دوباره پس‌زمینه توسط QStyle
        opt.backgroundBrush = QBrush()
        opt.state &= ~QStyle.StateFlag.State_Selected
        opt.state &= ~QStyle.StateFlag.State_MouseOver

        fg_data = index.data(Qt.ItemDataRole.ForegroundRole)
        if selected:
            fg = QColor(SELECTION_ROW_FG)
        elif isinstance(fg_data, QBrush):
            fg = fg_data.color()
        else:
            fg = QColor(DEFAULT_FG)

        opt.palette.setColor(QPalette.ColorRole.Text, fg)
        opt.palette.setColor(QPalette.ColorRole.Highlight, QColor(SELECTION_ROW_BG))
        opt.palette.setColor(QPalette.ColorRole.HighlightedText, QColor(SELECTION_ROW_FG))
        style = opt.widget.style() if opt.widget is not None else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)


# ─────────────────────────────────────────────
# Main Window
# ─────────────────────────────────────────────
class MainWindow(QMainWindow):
    """پنجره مدیریت ارشد سیستم پیگیری اسناد و صورتجلسات."""

    ALERT_DELAY_MS = 1200
    DB_LED_INTERVAL_MS = 700
    STATS_REFRESH_INTERVAL_MS = 60_000

    def __init__(self, db: DatabaseManager, session: UserSession) -> None:
        super().__init__()
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        self.db = db
        self.session = session
        self.settings = QSettings(ORG_NAME, APP_NAME)
        self.thread_pool = QThreadPool.globalInstance()

        self.dark_mode: bool = False
        self._columns_initialized: bool = False
        self._import_progress: Optional[QProgressDialog] = None

        self.page: int = 0
        self.page_size: int = DEFAULT_PAGE_SIZE
        self.total: int = 0
        self.order_by: str = "id"
        self.order_dir: str = "DESC"

        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(SEARCH_DEBOUNCE_MS)
        self.search_timer.timeout.connect(self._on_filters_changed)

        self.menuBar().setVisible(False)

        self._build_ui()
        self._build_menu()
        self._init_status_bar()
        self._setup_shortcuts()
        self._restore_settings()
        self._apply_rtl_details()
        self._apply_access()
        self.reload_meta()
        self.reload_page()
        self._update_title()
        self._apply_style()

        QTimer.singleShot(self.ALERT_DELAY_MS, self._show_operational_alerts)

    def _restore_settings(self) -> None:
        g = self.settings.value("geometry")
        if g:
            self.restoreGeometry(g)
        s = self.settings.value("header_state")
        if s:
            self.view.horizontalHeader().restoreState(s)
        self.dark_mode = self.settings.value("dark_mode", False, type=bool)
        if self.dark_mode:
            self._toggle_dark_mode(True)

    def _save_settings(self) -> None:
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("header_state", self.view.horizontalHeader().saveState())
        self.settings.setValue("dark_mode", self.dark_mode)

    def closeEvent(self, e: QCloseEvent) -> None:
        self._save_settings()
        e.accept()

    def _setup_shortcuts(self) -> None:
        shortcuts: List[Tuple[str, Callable]] = [
            ("Ctrl+N", self.new_meeting),
            ("Ctrl+E", self.edit_selected),
            ("Delete", self.delete_selected),
            ("F5", self.reload_page),
            ("Ctrl+F", lambda: self.search.setFocus()),
            ("Ctrl+Shift+E", self.export_excel),
            ("Ctrl+W", self.open_workflow),
            ("Ctrl+Shift+S", self.open_scanned_document),
            ("Ctrl+Shift+C", self.copy_selected_number),
        ]
        for key, slot in shortcuts:
            action = QAction(self)
            action.setShortcut(QKeySequence(key))
            action.triggered.connect(slot)
            self.addAction(action)

    def _apply_rtl_details(self) -> None:
        if hasattr(self, "lbl_db"):
            self.lbl_db.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
            self.lbl_db.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        if hasattr(self, "search"):
            self.search.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            self.search.setAlignment(Qt.AlignmentFlag.AlignRight)

    def _init_status_bar(self) -> None:
        sb = self.statusBar()
        sb.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        self.lbl_db_led = QLabel("●")
        self.lbl_db_led.setFixedWidth(18)
        self.lbl_db_led.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_db_led.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lbl_db_led.mousePressEvent = lambda _: self._open_db_folder()

        self.lbl_db = QLabel()
        self.lbl_db.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.lbl_db.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lbl_db.mousePressEvent = lambda _: self._open_db_folder()

        self.lbl_scan = QLabel()
        self.lbl_scan.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.lbl_scan.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lbl_scan.mousePressEvent = lambda _: self.open_scan_folder()
        self.lbl_scan.setToolTip("وضعیت مسیر اسکن — برای باز کردن پوشه کلیک کنید")

        self._db_led_on = True
        self._db_led_timer = QTimer(self)
        self._db_led_timer.setInterval(self.DB_LED_INTERVAL_MS)
        self._db_led_timer.timeout.connect(self._tick_db_led)
        self._db_led_timer.start()

        dw = QWidget()
        dl = QHBoxLayout(dw)
        dl.setContentsMargins(2, 0, 8, 0)
        dl.setSpacing(5)
        dl.addWidget(self.lbl_db_led)
        dl.addWidget(self.lbl_db)

        self.lbl_stats = QLabel()
        self.lbl_stats.setObjectName("lbl_stats")
        self.lbl_stats.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.lbl_date = QLabel(today_shamsi())
        self.lbl_date.setObjectName("lbl_date")
        self.lbl_date.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        sb.addWidget(dw)
        sb.addPermanentWidget(self.lbl_scan)
        sb.addPermanentWidget(self.lbl_stats, stretch=1)
        sb.addPermanentWidget(self.lbl_date)

        self._refresh_db_label()
        self._update_stats()

        self._stats_timer = QTimer(self)
        self._stats_timer.setInterval(self.STATS_REFRESH_INTERVAL_MS)
        self._stats_timer.timeout.connect(self._update_stats)
        self._stats_timer.start()

    def _db_path_exists(self) -> bool:
        try:
            p = str(getattr(self.db, "db_path", "") or "")
            return bool(p) and os.path.isfile(p)
        except Exception:
            logger.debug("DB path check failed", exc_info=True)
            return False

    def _tick_db_led(self) -> None:
        self._db_led_on = not self._db_led_on
        self._apply_db_led_style()

    def _apply_db_led_style(self) -> None:
        ok = self._db_path_exists()
        on = self._db_led_on
        c = ("#16a34a" if ok else "#dc2626") if on else "transparent"
        fg = "#ddd" if self.dark_mode else "#333"
        self.lbl_db_led.setStyleSheet(
            f"color:{c};font-size:12px;font-weight:900;background:transparent;"
        )
        self.lbl_db_led.setToolTip("دیتابیس متصل ✓" if ok else "فایل دیتابیس یافت نشد")
        self.lbl_db.setStyleSheet(f"background:transparent;color:{fg};")

    def _refresh_db_label(self) -> None:
        full = str(getattr(self.db, "db_path", "") or "")
        disp = f"DB: {full}" if full else "DB: نامشخص"
        fm = QFontMetrics(self.lbl_db.font())
        self.lbl_db.setText(fm.elidedText(disp, Qt.TextElideMode.ElideMiddle, 650))
        self.lbl_db.setToolTip(full or "مسیر نامشخص")
        self._apply_db_led_style()

    def _update_stats(self) -> None:
        try:
            from sqlalchemy import case, func as sa_func
            today = date.today()
            with self.db.session() as s:
                row = (
                    s.query(
                        sa_func.count(Meeting.id),
                        sa_func.sum(
                            case((Meeting.status == STATUS_PENDING, 1), else_=0)
                        ),
                        sa_func.sum(
                            case(
                                (
                                    (Meeting.due_date < today)
                                    & (Meeting.status.in_(OPEN_STATUSES)),
                                    1,
                                ),
                                else_=0,
                            )
                        ),
                    )
                    .filter(Meeting.is_deleted.is_(False))
                    .one()
                )
                total = int(row[0] or 0)
                pending = int(row[1] or 0)
                delayed = int(row[2] or 0)
        except Exception:
            logger.exception("Stats update failed")
            total = pending = delayed = 0

        self.lbl_stats.setText(
            f"کل: {total} | در دست بررسی: {pending} | تاخیردار: {delayed}"
        )
        self.lbl_date.setText(today_shamsi())
        self._refresh_scan_status()

    def _open_db_folder(self) -> None:
        try:
            f = os.path.dirname(str(getattr(self.db, "db_path", "") or ""))
            if f and os.path.isdir(f):
                QDesktopServices.openUrl(QUrl.fromLocalFile(f))
        except Exception:
            logger.debug("Cannot open DB folder", exc_info=True)

    def _show_operational_alerts(self) -> None:
        """
        نمایش هشدارهای عملیاتی به شکل غیرمزاحم:
        - برای تأخیرهای بحرانی (بیش از ۵ مورد): یک MessageBox اطلاع‌رسانی می‌شود.
        - در غیر این صورت: پیام در نوار وضعیت به مدت ۱۰ ثانیه نمایش داده می‌شود.
        """
        try:
            m = self.db.operational_metrics()
            overdue = int(m.get("overdue", 0) or 0)
            due_3 = int(m.get("due_3", 0) or 0)

            if overdue >= 5:
                QMessageBox.warning(
                    self, "⚠️ هشدار پیگیری بحرانی",
                    f"{overdue} صورتجلسه از مهلت انجام عبور کرده است.\n\n"
                    "از «داشبورد عملیاتی MOM» برای پیگیری استفاده کنید."
                )
            elif overdue > 0:
                self.statusBar().showMessage(
                    f"⚠️ {overdue} صورتجلسه از مهلت انجام عبور کرده است.", 10000
                )
            elif due_3 > 0:
                self.statusBar().showMessage(
                    f"⏳ {due_3} صورتجلسه در ۳ روز آینده سررسید می‌شود.", 10000
                )
        except Exception:
            logger.exception("Operational alert failed")

    def _update_title(self) -> None:
        self.setWindowTitle(
            f"Document & MOM Tracking System — "
            f"{self.session.username} ({self.session.role}) — {today_shamsi()}"
        )

    # ─────────────────────────────────────────
    # ساخت رابط کاربری (UI)
    # ─────────────────────────────────────────
    def _build_ui(self) -> None:
        c = QWidget()
        c.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setCentralWidget(c)

        root = QVBoxLayout(c)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.top_banner = self._build_turquoise_banner()
        root.addWidget(self.top_banner)

        self.custom_menu_bar = QMenuBar()
        self.custom_menu_bar.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        root.addWidget(self.custom_menu_bar)

        body_layout = QVBoxLayout()
        body_layout.setContentsMargins(14, 12, 14, 12)
        body_layout.setSpacing(10)

        body_layout.addLayout(self._build_filters_and_actions())
        body_layout.addLayout(self._build_search_bar())
        body_layout.addWidget(self._build_status_legend())
        body_layout.addWidget(self._build_table(), stretch=1)
        body_layout.addLayout(self._build_pager())

        root.addLayout(body_layout)
        self._connect_signals()

    def _build_turquoise_banner(self) -> QWidget:
        banner = QWidget()
        banner.setObjectName("TopTurquoiseBanner")
        banner.setFixedHeight(44)

        layout = QHBoxLayout(banner)
        layout.setContentsMargins(18, 0, 18, 0)
        layout.setSpacing(12)

        title_label = QLabel("✨ سامانه جامع مدیریت، پیگیری هوشمند و گردش‌کار صورتجلسات")
        title_label.setStyleSheet("""
            color: #ffffff;
            font-size: 13.5px;
            font-weight: bold;
            font-family: 'B Yekan', 'Vazir', 'Segoe UI', Tahoma;
            background: transparent;
        """)

        info_label = QLabel("پایش مداوم اسناد کارگاهی | نسخه ۳.۱")
        info_label.setStyleSheet("""
            color: rgba(255, 255, 255, 0.95);
            font-size: 11px;
            font-family: 'Segoe UI', Tahoma;
            background: transparent;
        """)

        layout.addWidget(title_label)
        layout.addStretch()
        layout.addWidget(info_label)

        banner.setStyleSheet("""
            QWidget#TopTurquoiseBanner {
                background: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:0,
                    stop:0 #005f73, 
                    stop:0.4 #0a9396, 
                    stop:0.8 #00ADB5, 
                    stop:1 #3a0ca3
                );
                border-bottom: 2px solid #005f73;
            }
        """)
        return banner

    def _build_filters_and_actions(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        bar.setSpacing(8)

        def _combo(width: int, tip: str) -> QComboBox:
            cb = QComboBox()
            cb.setFixedWidth(width)
            cb.setToolTip(tip)
            cb.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            return cb

        self.status_filter = _combo(140, "فیلتر وضعیت")
        self.priority_filter = _combo(110, "فیلتر اولویت")
        self.discipline_filter = _combo(120, "فیلتر دیسیپلین")
        self.employer_filter = _combo(150, "فیلتر کارفرما")
        self.contractor_filter = _combo(150, "فیلتر پیمانکار")

        filters_layout = [
            ("وضعیت:", self.status_filter),
            ("اولویت:", self.priority_filter),
            ("دیسیپلین:", self.discipline_filter),
            ("کارفرما:", self.employer_filter),
            ("پیمانکار:", self.contractor_filter),
        ]
        for label, combo in filters_layout:
            bar.addWidget(QLabel(label))
            bar.addWidget(combo)

        bar.addStretch()

        def _btn(text: str, tip: str, name_obj: str = "btn_secondary") -> QPushButton:
            b = QPushButton(text)
            b.setToolTip(tip)
            b.setObjectName(name_obj)
            return b

        self.btn_new = _btn("➕ جدید", "تعریف صورتجلسه جدید (Ctrl+N)", "btn_primary")
        self.btn_edit = _btn("✏️ ویرایش", "ویرایش صورتجلسه انتخاب شده (Ctrl+E)", "btn_secondary")
        self.btn_del = _btn("🗑️ حذف", "حذف منطقی پرونده (Delete)", "btn_danger")

        self.btn_workflow = MeteorButton("🔄 گردش کار")
        self.btn_workflow.setToolTip("مدیریت گردش کار (Ctrl+W)")

        self.btn_refresh = _btn("⚡ بروزرسانی", "بروزرسانی داده‌های جدول (F5)", "btn_secondary")
        self.btn_dashboard = _btn("📊 نمودار", "نمودار تحلیلی آماری", "btn_secondary")
        self.btn_export = _btn("📥 خروجی", "خروجی اکسل پیشرفته (Ctrl+Shift+E)", "btn_secondary")
        self.btn_template = _btn("📝 قالب", "دانلود قالب اکسل ورود اطلاعات", "btn_secondary")
        self.btn_scan = _btn("🔍 مدرک اسکن‌شده", "جستجو و باز کردن خودکار مدرک اسکن‌شده در پوشه شبکه", "btn_secondary")
        self.btn_tracking = _btn("📈 پیگیری پرونده", "مشاهده پاسخ پیمانکار، تاریخچه و بازخوانی گردش کار زنده", "btn_primary")

        for b in (self.btn_new, self.btn_edit, self.btn_del, self.btn_workflow,
                  self.btn_refresh, self.btn_dashboard, self.btn_export,
                  self.btn_template, self.btn_scan, self.btn_tracking):
            bar.addWidget(b)

        return bar

    def _build_pager(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        bar.setSpacing(10)

        self.btn_prev = QPushButton("▶ قبلی")
        self.btn_prev.setObjectName("btn_pager")
        self.btn_next = QPushButton("بعدی ◀")
        self.btn_next.setObjectName("btn_pager")

        self.lbl_page = QLabel()
        self.lbl_page.setObjectName("lbl_page")

        self.page_size_combo = QComboBox()
        self.page_size_combo.addItems([str(v) for v in (25, 50, 100, 250, 500)])
        self.page_size_combo.setCurrentText(str(self.page_size))
        self.page_size_combo.setFixedWidth(80)
        self.page_size_combo.setToolTip("تعداد ردیف در هر صفحه")
        self.page_size_combo.currentTextChanged.connect(self._change_page_size)

        self.lbl_page.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)

        bar.addWidget(self.btn_prev)
        bar.addWidget(self.btn_next)
        bar.addSpacing(15)
        bar.addWidget(self.lbl_page)
        bar.addStretch()
        bar.addWidget(QLabel("اندازه صفحه:"))
        bar.addWidget(self.page_size_combo)
        return bar

    def _build_search_bar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        bar.setSpacing(8)

        self.search = QLineEdit()
        self.search.setPlaceholderText("🔎 جستجو در شماره، موضوع، کارفرما، پیمانکار و دیسیپلین...")
        self.search.setClearButtonEnabled(True)
        self.search.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.search.setAlignment(Qt.AlignmentFlag.AlignRight)

        bar.addWidget(QLabel("جستجوی سریع:"))
        bar.addWidget(self.search, stretch=1)
        self.btn_workflow_report = QPushButton("⏱ گزارش زمان رسیدگی")
        self.btn_workflow_report.setObjectName("btn_primary")
        self.btn_workflow_report.setToolTip("گزارش HTML مدت کل رسیدگی و زمان صرف‌شده در هر مرحله")
        bar.addWidget(self.btn_workflow_report)
        return bar

    def _build_status_legend(self) -> QWidget:
        """راهنمای رنگ‌ها همراه با شمارش زنده تمام صورتجلسات هر وضعیت."""
        legend = QWidget()
        legend.setObjectName("status_legend")
        layout = QHBoxLayout(legend)
        layout.setContentsMargins(12, 7, 12, 7)
        layout.setSpacing(10)

        title = QLabel("راهنمای وضعیت و تعداد صورتجلسات:")
        title.setObjectName("legend_title")
        layout.addWidget(title)

        self._legend_count_labels: Dict[str, QLabel] = {}
        for label, bg, fg in LEGEND_ITEMS:
            chip = QLabel(f"●  {label} (—)")
            chip.setObjectName("status_legend_item")
            chip.setToolTip("تعداد کل صورتجلسات فعال در این وضعیت؛ مستقل از فیلتر و صفحه جاری")
            chip.setStyleSheet(
                f"QLabel#status_legend_item {{ background:{bg}; color:{fg}; "
                "border:1px solid rgba(100,116,139,0.28); border-radius:10px; "
                "padding:5px 10px; font-weight:600; }}"
            )
            self._legend_count_labels[label] = chip
            layout.addWidget(chip)
        layout.addStretch(1)
        return legend

    def _refresh_status_legend_counts(self) -> None:
        """شمارش تمام صورتجلسات فعال بر اساس همان منطق وضعیت رنگی جدول."""
        if not getattr(self, "_legend_count_labels", None):
            return

        try:
            with self.db.session() as sess:
                meetings = (
                    sess.query(Meeting.id, Meeting.status, Meeting.sent_to_contractor_date)
                    .filter(Meeting.is_deleted.is_(False))
                    .all()
                )
                meeting_ids = [int(row[0]) for row in meetings]
                workflow_map: Dict[int, List[str]] = {}
                if meeting_ids:
                    steps = (
                        sess.query(WorkflowStep.meeting_id, WorkflowStep.status)
                        .filter(WorkflowStep.meeting_id.in_(meeting_ids))
                        .order_by(WorkflowStep.meeting_id, WorkflowStep.step_order.asc())
                        .all()
                    )
                    for meeting_id, step_status in steps:
                        workflow_map.setdefault(int(meeting_id), []).append(str(step_status or ""))

            counts = {
                "in_progress": 0,
                "pending": 0,
                "returned": 0,
                "completed": 0,
                "cancelled": 0,
                "unknown": 0,
            }
            for meeting_id, meeting_status, dispatched_at in meetings:
                state = derive_workflow_state(
                    meeting_status,
                    workflow_map.get(int(meeting_id), []),
                    dispatched_at is not None,
                )
                counts[state if state in counts else "unknown"] += 1

            display_counts = {
                "در حال انجام": counts["in_progress"],
                "در انتظار": counts["pending"],
                "برگشت برای اصلاح": counts["returned"],
                "تکمیل و ابلاغ‌شده": counts["completed"],
                "لغوشده / نامشخص": counts["cancelled"] + counts["unknown"],
            }
            for label, value in display_counts.items():
                chip = self._legend_count_labels.get(label)
                if chip is not None:
                    chip.setText(f"●  {label} ({value:,})")
                    chip.setToolTip(
                        f"{value:,} صورتجلسه فعال در وضعیت «{label}»؛ "
                        "شمارش مستقل از فیلترها و صفحه جاری"
                    )
        except Exception:
            logger.exception("Failed to refresh status legend counts")
            for label, chip in self._legend_count_labels.items():
                chip.setText(f"●  {label} (—)")
                chip.setToolTip("محاسبه تعداد وضعیت‌ها ناموفق بود؛ برای تلاش دوباره بروزرسانی کنید")

    def _build_table(self) -> QTableView:
        self.view = QTableView()
        self.view.setObjectName("meetings_table")
        self.view.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        # هر سلول رنگ وضعیت را از مدل می‌گیرد و delegate آن را صریح رسم می‌کند.
        self.view.setAlternatingRowColors(False)
        self.view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.view.setSelectionMode(QTableView.SelectionMode.ExtendedSelection)
        self.view.setSortingEnabled(False)
        self.view.setWordWrap(False)
        self.view.setShowGrid(False)
        self.view.setMouseTracking(True)
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self._show_table_context_menu)

        # اسکرول افقی نرم و قابل‌اعتماد
        self.view.setHorizontalScrollMode(QTableView.ScrollMode.ScrollPerPixel)
        self.view.setVerticalScrollMode(QTableView.ScrollMode.ScrollPerPixel)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        hdr = self.view.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        hdr.setStretchLastSection(False)
        hdr.setMinimumSectionSize(56)
        hdr.setDefaultSectionSize(110)
        hdr.setSortIndicatorShown(True)
        hdr.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        hdr.sectionClicked.connect(self._on_header_clicked)

        self.view.verticalHeader().setDefaultSectionSize(38)
        self.view.verticalHeader().setVisible(False)

        self.model = MeetingsPageModel()
        self.view.setModel(self.model)
        self.view.setItemDelegate(StatusRowDelegate(self.view))
        self.view.doubleClicked.connect(self.edit_selected)
        return self.view

    def _connect_signals(self) -> None:
        self.search.textChanged.connect(self.search_timer.start)
        for cb in (self.status_filter, self.priority_filter, self.employer_filter,
                   self.contractor_filter, self.discipline_filter):
            cb.currentTextChanged.connect(self._on_filters_changed)

        self.btn_new.clicked.connect(self.new_meeting)
        self.btn_edit.clicked.connect(self.edit_selected)
        self.btn_del.clicked.connect(self.delete_selected)
        self.btn_workflow.clicked.connect(self.open_workflow)
        self.btn_refresh.clicked.connect(self.reload_page)
        self.btn_dashboard.clicked.connect(self.open_dashboard)
        self.btn_export.clicked.connect(self.export_excel)
        self.btn_template.clicked.connect(self.download_import_template)
        self.btn_scan.clicked.connect(self.open_scanned_document)
        self.btn_tracking.clicked.connect(self.open_tracking)
        self.btn_workflow_report.clicked.connect(self.open_workflow_reports)
        self.btn_prev.clicked.connect(self.prev_page)
        self.btn_next.clicked.connect(self.next_page)

    # ─────────────────────────────────────────
    # منوی سفارشی
    # ─────────────────────────────────────────
    def _build_menu(self) -> None:
        mb = self.custom_menu_bar

        # منوی فایل
        mf = mb.addMenu("فایل")
        self.act_change_db = self._act("تغییر دیتابیس…", self.change_database)
        self.act_export_excel = self._act("خروجی اکسل…", self.export_excel)
        self.act_import = self._act("واردات از اکسل/CSV…", self.import_data)
        self.act_backup = self._act("پشتیبان‌گیری…", self.backup_db)
        self.act_publish = self._act("انتشار دیتابیس…", self.publish_db)
        ae = self._act("خروج", self.close)
        for a in (self.act_change_db, None, self.act_export_excel, self.act_import,
                  None, self.act_backup, self.act_publish, None, ae):
            if a is None:
                mf.addSeparator()
            else:
                mf.addAction(a)

        # منوی مدیریت
        ma = mb.addMenu("مدیریت")
        self.act_users = self._act("مدیریت کاربران…", self.open_user_admin)
        ma.addAction(self.act_users)

        # منوی نمایش
        mv = mb.addMenu("نمایش")
        mv.addAction(self._act("داشبورد عملیاتی MOM", self.open_operational_dashboard))
        self.act_dark = QAction("حالت شب/روز", self, checkable=True)
        self.act_dark.setChecked(self.dark_mode)
        self.act_dark.triggered.connect(self._toggle_dark_mode)
        mv.addAction(self.act_dark)
        mv.addSeparator()
        mv.addAction(self._act("بازنشانی ستون‌ها", self._reset_column_sizes))
        mv.addAction(self._act("همگام‌سازی وضعیت‌ها با گردش کار", self.sync_all_statuses))

        # منوی تنظیمات
        ms = mb.addMenu("تنظیمات")
        ms.addAction(self._act("مسیر اسکن مدارک…", self.configure_scan_path))
        ms.addAction(self._act("باز کردن پوشه اسکن", self.open_scan_folder))
        ms.addSeparator()
        ms.addAction(self._act("بررسی مسیر اسکن", self.check_scan_path))

        # منوی راهنما
        mh = mb.addMenu("راهنما")
        mh.addAction(self._act("راهنمای کاربر", self._open_user_guide))
        mh.addSeparator()
        mh.addAction(self._act("درباره…", self._show_about))

    def _act(self, text: str, slot: Callable) -> QAction:
        a = QAction(text, self)
        a.triggered.connect(slot)
        return a

    # ─────────────────────────────────────────
    # اعمال استایل
    # ─────────────────────────────────────────
    def _apply_style(self) -> None:
        if self.dark_mode:
            bg_m, bg_t, bg_a = "#0F172A", "#1E293B", "#334155"
            bg_h, fg_m, fg_h = "#1E293B", "#E2E8F0", "#F1F5F9"
            brd, inp, sbb = "#475569", "#1E293B", "#1E293B"
            bd, sf = "#64748B", COLOR_SKY_BLUE
            tf = "#E2E8F0"
            focus_bg = "#263F4D"
            secondary_bg, secondary_hover, secondary_pressed = "#334155", "#475569", "#64748B"
            secondary_fg, secondary_hover_fg = "#E2E8F0", "#FFFFFF"
            danger_bg, danger_border, danger_fg = "#7F1D1D", "#B91C1C", "#FEE2E2"
            pager_bg, pager_fg, pager_hover = "#1E293B", "#E2E8F0", "#334155"
            selection_bg, selection_fg = "#075985", "#F0F9FF"

            menu_style = """
                QMenuBar { background-color: #1E293B; color: #E2E8F0; border-bottom: 1px solid #334155; font-size: 12px; }
                QMenuBar::item { background: transparent; padding: 5px 12px; color: #E2E8F0; }
                QMenuBar::item:selected { background: #00ADB5; color: #ffffff; border-radius: 4px; }
                QMenu { background-color: #1E293B; color: #E2E8F0; border: 1px solid #475569; }
                QMenu::item { padding: 6px 20px; }
                QMenu::item:selected { background-color: #00ADB5; color: #ffffff; }
            """
        else:
            bg_m, bg_t, bg_a = "#F8FAFC", "#FFFFFF", "#F1F5F9"
            bg_h, fg_m, fg_h = "#E2E8F0", "#0F172A", "#0F172A"
            brd, inp, sbb = "#CBD5E1", "#FFFFFF", "#FFFFFF"
            bd, sf = "#94A3B8", "#0284C7"
            tf = "#1E293B"
            focus_bg = "#F0FDFA"
            secondary_bg, secondary_hover, secondary_pressed = "#FFFFFF", "#F1F5F9", "#E2E8F0"
            secondary_fg, secondary_hover_fg = "#334155", "#0F172A"
            danger_bg, danger_border, danger_fg = "#FEE2E2", "#FCA5A5", "#991B1B"
            pager_bg, pager_fg, pager_hover = "#FFFFFF", "#334155", "#F1F5F9"
            selection_bg, selection_fg = "#BAE6FD", "#0C4A6E"

            menu_style = """
                QMenuBar { background-color: #FFFFFF; color: #1E293B; border-bottom: 1px solid #E2E8F0; font-size: 12px; }
                QMenuBar::item { background: transparent; padding: 5px 12px; color: #1E293B; }
                QMenuBar::item:selected { background: #00ADB5; color: #FFFFFF; border-radius: 4px; }
                QMenu { background-color: #FFFFFF; color: #1E293B; border: 1px solid #CBD5E1; }
                QMenu::item { padding: 6px 20px; }
                QMenu::item:selected { background-color: #00ADB5; color: #FFFFFF; }
            """

        self.setStyleSheet(f"""
            {menu_style}
            QMainWindow {{ background:{bg_m}; }}
            QTableView#meetings_table {{
                background:{bg_t};
                alternate-background-color:{bg_a};
                border: 1px solid {brd};
                border-radius:10px;
                color:{tf};
                selection-background-color:{selection_bg};
                selection-color:{selection_fg};
                gridline-color:transparent;
                font-size:12.5px;
                outline:0;
            }}
            QTableView#meetings_table::item {{
                padding:8px 10px;
                border-bottom:1px solid rgba(148,163,184,0.18);
            }}
            QTableView#meetings_table::item:hover {{
                border-bottom:1px solid #38BDF8;
            }}
            QHeaderView::section {{
                background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #0E7490,stop:1 #155E75);
                color:#FFFFFF;
                border:none;
                border-left:1px solid rgba(255,255,255,0.18);
                border-bottom:3px solid #22D3EE;
                padding:10px 8px;
                font-weight:bold;
                font-size:12px;
            }}
            QWidget#status_legend {{
                background:{bg_t};
                border:1px solid {brd};
                border-radius:9px;
            }}
            QLabel#legend_title {{
                color:{sf};
                font-weight:bold;
                padding:2px 5px;
            }}
            QLineEdit, QComboBox {{
                border:1px solid {brd}; border-radius:7px;
                padding:5px 10px; background:{inp};
                color:{fg_m}; font-size:12.5px; min-height:26px;
            }}
            QLineEdit:focus, QComboBox:focus {{
                border-color: #00ADB5;
                background: {focus_bg};
            }}
            QLabel {{ color:{fg_m}; font-size:12.5px; }}

            QPushButton {{
                font-size: 12px;
                font-weight: bold;
                border-radius: 5px;
                padding: 6px 14px;
                min-height: 28px;
            }}
            QPushButton#btn_primary {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0284C7, stop:1 #0369A1);
                color: #FFFFFF;
                border: none;
            }}
            QPushButton#btn_primary:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0369A1, stop:1 #1D4ED8);
            }}
            QPushButton#btn_primary:pressed {{
                background: #1E3A8A;
            }}
            QPushButton#btn_secondary {{
                background-color: {secondary_bg};
                border: 1px solid {brd};
                color: {secondary_fg};
            }}
            QPushButton#btn_secondary:hover {{
                background-color: {secondary_hover};
                border-color: {bd};
                color: {secondary_hover_fg};
            }}
            QPushButton#btn_secondary:pressed {{
                background-color: {secondary_pressed};
            }}
            QPushButton#btn_danger {{
                background-color: {danger_bg};
                border: 1px solid {danger_border};
                color: {danger_fg};
            }}
            QPushButton#btn_danger:hover {{
                background-color: #EF4444;
                border-color: #DC2626;
                color: #FFFFFF;
            }}
            QPushButton#btn_danger:pressed {{
                background-color: #991B1B;
            }}
            QPushButton#btn_pager {{
                background-color: {pager_bg};
                border: 1px solid {brd};
                color: {pager_fg};
                min-width: 60px;
            }}
            QPushButton#btn_pager:hover {{
                background-color: {pager_hover};
                color: {secondary_hover_fg};
            }}
            QStatusBar {{ background:{sbb}; border-top: 1px solid {brd}; }}
            QStatusBar QLabel {{ background:transparent; color:{fg_m}; }}
            #lbl_stats, #lbl_date, #lbl_page {{ color:{sf}; font-weight:bold; }}
        """)
        self._apply_db_led_style()

    def _toggle_dark_mode(self, checked: bool) -> None:
        self.dark_mode = checked
        if hasattr(self, "act_dark"):
            self.act_dark.setChecked(checked)
        self._apply_style()

    # ─────────────────────────────────────────
    # 🎯 هسته هوشمند: محاسبه خودکار وضعیت زنده سند
    # ─────────────────────────────────────────
    def _compute_live_status(self, meeting_id: int) -> str:
        """
        محاسبه وضعیت زنده از روی شناسه پرونده (کوئری کامل).
        این متد نقطه‌ی ورودی امن برای استفاده‌های تک‌پرونده‌ای است
        (مثل `_apply_live_status`) که لیست گام‌ها را از قبل در دست ندارد.
        """
        try:
            with self.db.session() as sess:
                meeting = sess.get(Meeting, meeting_id)
                if not meeting:
                    return STATUS_PENDING

                if meeting.status == STATUS_CANCELLED:
                    return STATUS_CANCELLED

                steps = (
                    sess.query(WorkflowStep)
                    .filter(WorkflowStep.meeting_id == meeting_id)
                    .order_by(WorkflowStep.step_order.asc())
                    .all()
                )
                return self._compute_live_status_from_steps(meeting, steps)
        except Exception as exc:
            logger.warning(
                "Live status computation failed for meeting %s: %s", meeting_id, exc
            )
            return STATUS_PENDING

    def _compute_live_status_from_steps(
        self, meeting: Meeting, steps: List[WorkflowStep]
    ) -> str:
        """
        محاسبه وضعیت از روی لیست لود شده گام‌ها (سریع، بدون کوئری دیتابیس).

        ترتیب اولویت قوانین:
        1) لغو شده → همان لغو
        2) ابلاغ به پیمانکار (قانون طلایی) → تکمیل شده
        3) وجود گام rejected → بازگشت داده شده
        4) همه گام‌ها completed/skipped → تکمیل شده
        5) وجود گام in_progress → در انتظار تأیید
        6) در غیر این صورت → در دست بررسی
        """
        if meeting.status == STATUS_CANCELLED:
            return STATUS_CANCELLED

        # 👑 قانون طلایی: به محض پر شدن تاریخ ارسال به پیمانکار → کل کار تکمیل شده است
        if meeting.sent_to_contractor_date is not None:
            return STATUS_COMPLETED

        if not steps:
            return STATUS_PENDING

        rejected_step = next((s for s in reversed(steps) if s.status == "rejected"), None)
        if rejected_step:
            return STATUS_RETURNED

        if all(s.status in ("completed", "skipped") for s in steps):
            return STATUS_COMPLETED

        if any(s.status == "in_progress" for s in steps):
            return STATUS_AWAITING

        return STATUS_PENDING

    def _apply_live_status(self, meeting_id: int) -> None:
        """
        اعمال وضعیت زنده محاسبه‌شده روی رکورد پایگاه داده.
        در صورت ابلاغ به پیمانکار (قانون طلایی)، گام‌های **پیش از ابلاغ** بسته می‌شوند.
        گام‌هایی که conceptاً «پس از ابلاغ» هستند (پاسخ پیمانکار و مشابه) دست‌نخورده می‌مانند.
        """
        new_status = self._compute_live_status(meeting_id)
        try:
            with self.db.session() as sess:
                meeting = sess.get(Meeting, meeting_id)
                if not meeting:
                    return

                if new_status == STATUS_COMPLETED and meeting.sent_to_contractor_date is not None:
                    # همگام‌سازی: تاریخ بسته شدن و پاسخ پیمانکار با تاریخ ابلاغ
                    meeting.closing_date = meeting.sent_to_contractor_date
                    meeting.contractor_response_date = meeting.sent_to_contractor_date

                    # شناسایی گام «ارسال به پیمانکار» (اگر وجود داشته باشد)
                    contractor_step_order = None
                    steps_all = (
                        sess.query(WorkflowStep)
                        .filter(WorkflowStep.meeting_id == meeting_id)
                        .order_by(WorkflowStep.step_order.asc())
                        .all()
                    )
                    for s in steps_all:
                        name = (s.step_name or "")
                        if "پیمانکار" in name and ("ارسال" in name or "ابلاغ" in name):
                            contractor_step_order = s.step_order
                            break

                    # فقط گام‌های قبل یا هم‌تراز با ابلاغ بسته می‌شوند
                    for s in steps_all:
                        if s.status == "completed":
                            continue
                        if contractor_step_order is None or s.step_order <= contractor_step_order:
                            s.status = "completed"
                            s.exit_date = meeting.sent_to_contractor_date

                if meeting.status != new_status:
                    old_status = meeting.status
                    meeting.status = new_status
                    logger.info(
                        "Live status updated for meeting %s: %s → %s",
                        meeting_id, old_status, new_status,
                    )

                sess.commit()
        except Exception:
            logger.exception("Failed to persist live status for meeting %s", meeting_id)

    def sync_all_statuses(self) -> None:
        """همگام‌سازی سراسری تمام رکوردهای فعال با منطق جدید گردش کار (اتمیک)."""
        reply = QMessageBox.question(
            self, "همگام‌سازی وضعیت‌ها",
            "آیا می‌خواهید وضعیت تمام صورتجلسات فعال با گردش کار همگام شود؟\n"
            "این عملیات ممکن است چند ثانیه به طول انجامد.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        updated = 0
        try:
            # ⚡ کل همگام‌سازی در یک تراکنش اتمیک انجام می‌شود.
            with self.db.session() as sess:
                meetings = (
                    sess.query(Meeting)
                    .filter(Meeting.is_deleted.is_(False))
                    .all()
                )
                meeting_ids = [m.id for m in meetings]

                # بارگذاری گروهی گام‌ها (یک کوئری)
                steps_by_meeting: Dict[int, List[WorkflowStep]] = {}
                if meeting_ids:
                    steps = (
                        sess.query(WorkflowStep)
                        .filter(WorkflowStep.meeting_id.in_(meeting_ids))
                        .order_by(WorkflowStep.meeting_id, WorkflowStep.step_order.asc())
                        .all()
                    )
                    for s in steps:
                        steps_by_meeting.setdefault(s.meeting_id, []).append(s)

                for m in meetings:
                    m_steps = steps_by_meeting.get(m.id, [])
                    new_status = self._compute_live_status_from_steps(m, m_steps)

                    if new_status == STATUS_COMPLETED and m.sent_to_contractor_date is not None:
                        m.closing_date = m.sent_to_contractor_date
                        m.contractor_response_date = m.sent_to_contractor_date

                        contractor_step_order = None
                        for s in m_steps:
                            name = (s.step_name or "")
                            if "پیمانکار" in name and ("ارسال" in name or "ابلاغ" in name):
                                contractor_step_order = s.step_order
                                break

                        for s in m_steps:
                            if s.status == "completed":
                                continue
                            if contractor_step_order is None or s.step_order <= contractor_step_order:
                                s.status = "completed"
                                s.exit_date = m.sent_to_contractor_date

                    if m.status != new_status:
                        m.status = new_status
                    updated += 1

                sess.commit()

            QMessageBox.information(
                self, "همگام‌سازی انجام شد",
                f"وضعیت {updated} صورتجلسه به‌روزرسانی شد."
            )
            self.reload_page()
        except Exception as exc:
            logger.exception("Bulk status sync failed")
            QMessageBox.critical(self, "خطا", f"همگام‌سازی با خطا مواجه شد:\n{exc}")

    # ─────────────────────────────────────────
    # سایر متدها
    # ─────────────────────────────────────────
    def _reset_column_sizes(self) -> None:
        h = self.view.horizontalHeader()
        for i in range(self.model.columnCount()):
            h.resizeSection(i, 110)
        h.setStretchLastSection(True)
        self._columns_initialized = False

    def _auto_size_columns(self) -> None:
        """
        تخمین دقیق عرض ستون‌ها با QFontMetrics (سازگار با فارسی و DPI).
        """
        if self._columns_initialized:
            return

        h = self.view.horizontalHeader()
        fm_body = QFontMetrics(self.view.font())
        fm_header = QFontMetrics(h.font())

        for c in range(self.model.columnCount()):
            header_text = str(
                self.model.headerData(c, Qt.Orientation.Horizontal) or ""
            )
            # برای هدر یک مقدار پایه
            width = fm_header.horizontalAdvance(header_text) + 24

            # برای متن‌های بدنه
            sample_limit = min(self.model.rowCount(), 40)
            for r in range(sample_limit):
                t = self.model.data(
                    self.model.index(r, c), Qt.ItemDataRole.DisplayRole
                )
                if t:
                    width = max(width, fm_body.horizontalAdvance(str(t)) + 22)

            # محدوده معقول تا اسکرول افقی ممکن بماند
            h.resizeSection(c, max(56, min(width, 280)))

        h.setStretchLastSection(False)
        self._columns_initialized = True

    def _get_filters(self) -> Dict[str, str]:
        f: Dict[str, str] = {}
        for key, cb in [
            ("status", self.status_filter),
            ("priority", self.priority_filter),
            ("employer", self.employer_filter),
            ("contractor", self.contractor_filter),
            ("discipline", self.discipline_filter),
        ]:
            v = cb.currentText()
            if v and v != FILTER_ALL_LABEL:
                f[key] = v
        return f

    def _on_filters_changed(self) -> None:
        self.page = 0
        self.reload_page()

    def reload_meta(self) -> None:
        def _fill(cb: QComboBox, vals: List[str]) -> None:
            cur = cb.currentText()
            cb.blockSignals(True)
            cb.clear()
            cb.addItem(FILTER_ALL_LABEL)
            cb.addItems([v for v in vals if v])
            i = cb.findText(cur)
            cb.setCurrentIndex(i if i >= 0 else 0)
            cb.blockSignals(False)

        _fill(self.status_filter, STATUSES)
        _fill(self.priority_filter, PRIORITIES)
        _fill(self.employer_filter, self.db.distinct_values("employer"))
        _fill(self.contractor_filter, self.db.distinct_values("contractor"))
        _fill(
            self.discipline_filter,
            list(dict.fromkeys(DISCIPLINES + self.db.distinct_values("discipline"))),
        )
        self._update_stats()

    def _query_page(self) -> Tuple[List[Meeting], int]:
        return self.db.query_meetings_page(
            filters=self._get_filters(),
            search=self.search.text().strip(),
            order_by=self.order_by,
            order_dir=self.order_dir,
            limit=self.page_size,
            offset=self.page * self.page_size,
        )

    def reload_page(self) -> None:
        try:
            rows, total = self._query_page()
        except Exception:
            logger.exception("reload failed")
            QMessageBox.critical(self, "خطا", "بارگذاری ناموفق.")
            return

        self.total = int(total or 0)
        self.model.set_rows(self._to_rows(rows))

        s = self.page * self.page_size + 1 if self.total else 0
        e = min((self.page + 1) * self.page_size, self.total)
        self.lbl_page.setText(f"نمایش {s}–{e} از {self.total} | صفحه {self.page + 1}")

        self.btn_prev.setEnabled(self.page > 0)
        self.btn_next.setEnabled(e < self.total)

        self._hide_id_column()
        self._auto_size_columns()
        self._update_stats()
        self._refresh_status_legend_counts()
        self._update_title()

    def _to_rows(self, meetings: List[Meeting]) -> List[List[Any]]:
        hdrs = self.model._orig_headers
        date_indices = [i for i, h in enumerate(hdrs) if h in DATE_COLUMNS]
        status_index = hdrs.index("وضعیت") if "وضعیت" in hdrs else -1
        result: List[List[Any]] = []
        workflow_states: Dict[int, str] = {}

        if not meetings:
            self.model.set_workflow_states(workflow_states)
            return result

        # ⚡ بارگذاری گروهی گردش‌کار تمام سطرها با یک کوئری
        meeting_ids = [m.id for m in meetings]
        workflow_map: Dict[int, List[WorkflowStep]] = {}
        workflow_loaded = True
        try:
            with self.db.session() as sess:
                steps = (
                    sess.query(WorkflowStep)
                    .filter(WorkflowStep.meeting_id.in_(meeting_ids))
                    .order_by(WorkflowStep.meeting_id, WorkflowStep.step_order.asc())
                    .all()
                )
                for s in steps:
                    workflow_map.setdefault(s.meeting_id, []).append(s)
        except Exception as exc:
            workflow_loaded = False
            logger.warning("Failed to bulk fetch workflow steps: %s", exc)

        for m in meetings:
            row = m.to_row(hdrs)

            for i in date_indices:
                if row[i]:
                    row[i] = _cached_to_shamsi(str(row[i]))

            m_steps = workflow_map.get(m.id, [])

            workflow_states[m.id] = derive_workflow_state(
                m.status,
                (step.status for step in m_steps),
                m.sent_to_contractor_date is not None,
                workflow_loaded=workflow_loaded,
            )

            if status_index >= 0:
                live_status = self._compute_live_status_from_steps(m, m_steps)
                row[status_index] = live_status

            responsible, stage = self._resolve_workflow_step_from_list(m, m_steps)
            row.append(responsible or "—")
            row.append(stage or "—")
            result.append(row)

        self.model.set_workflow_states(workflow_states)
        return result

    def _resolve_workflow_step_from_list(
        self, meeting: Meeting, steps: List[WorkflowStep]
    ) -> Tuple[str, str]:
        """محاسبه سریع مرحله و کارشناس رسیدگی‌کننده فعال از لیست لود شده."""
        # کارشناس اصلی: مسئول گام ۳ (ورود به دفتر کارشناس)
        specialist_step = next((s for s in steps if s.step_order == 3), None) if steps else None
        specialist_name = specialist_step.responsible_person if specialist_step else None

        # حالت ۱: پرونده ابلاغ شده
        if meeting.sent_to_contractor_date is not None:
            return specialist_name or "—", "گردش کار به اتمام رسیده (ابلاغ شده به پیمانکار)"

        # حالت ۲: گامی وجود ندارد
        if not steps:
            return specialist_name or "—", "—"

        # پیدا کردن گام فعال
        step = next(
            (s for s in steps if s.status in ("pending", "in_progress")), None
        )
        if not step:
            step = steps[-1]

        status_map = {
            "pending": "در انتظار انجام",
            "in_progress": "در حال انجام",
            "completed": "تکمیل شده",
            "skipped": "عبور شده",
            "rejected": "برگشت داده شده",
        }
        status_fa = status_map.get(step.status, step.status)
        current_resp = f" [{step.responsible_person}]" if step.responsible_person else ""
        stage_info = f"{step.step_name} ({status_fa}){current_resp}"

        responsible = specialist_name or step.responsible_person or "—"
        return responsible, stage_info

    def _hide_id_column(self) -> None:
        try:
            self.view.setColumnHidden(self.model.headers.index("ردیف"), True)
        except ValueError:
            pass

    def _on_header_clicked(self, li: int) -> None:
        if li == 0:
            return
        cn = self.model.headers[li]
        dc = HEADER_TO_DB_COL.get(cn)
        if not dc:
            return

        if dc == self.order_by:
            self.order_dir = "ASC" if self.order_dir == "DESC" else "DESC"
        else:
            self.order_by, self.order_dir = dc, "ASC"

        self.view.horizontalHeader().setSortIndicator(
            li,
            Qt.SortOrder.AscendingOrder if self.order_dir == "ASC"
            else Qt.SortOrder.DescendingOrder,
        )
        self.reload_page()

    def _change_page_size(self, value: str) -> None:
        try:
            self.page_size = max(1, int(value))
        except ValueError:
            return
        self.page = 0
        self._columns_initialized = False
        self.reload_page()

    def prev_page(self) -> None:
        if self.page > 0:
            self.page -= 1
            self.reload_page()

    def next_page(self) -> None:
        if (self.page + 1) * self.page_size < self.total:
            self.page += 1
            self.reload_page()

    def _selected_ids(self) -> List[int]:
        sel = self.view.selectionModel()
        if not sel:
            return []

        ids: List[int] = []
        for idx in sel.selectedRows():
            mid = self.model.get_row_id(idx.row())
            if mid is not None:
                ids.append(mid)
        return ids

    def copy_selected_number(self) -> None:
        ids = self._selected_ids()
        if not ids:
            return
        m = self.db.get_meeting(ids[0])
        if not m:
            return
        clipboard = QApplication.clipboard()
        if clipboard is None:
            return
        clipboard.setText(str(m.meeting_number or ""))
        self.statusBar().showMessage(
            f"شماره صورتجلسه «{m.meeting_number}» کپی شد.", 2500
        )

    def _show_table_context_menu(self, pos) -> None:
        ids = self._selected_ids()
        if not ids:
            return
        menu = QMenu(self)
        menu.addAction("ویرایش", self.edit_selected)
        menu.addAction("گردش کار", self.open_workflow)
        menu.addAction("پیگیری پرونده / پاسخ پیمانکار", self.open_tracking)
        menu.addSeparator()
        menu.addAction("باز کردن مدرک اسکن‌شده", self.open_scanned_document)
        menu.addAction("کپی شماره صورتجلسه", self.copy_selected_number)
        menu.addAction("باز کردن پوشه اسکن", self.open_scan_folder)
        menu.exec(self.view.viewport().mapToGlobal(pos))

    def _scan_file_matches(self, number: str) -> List[str]:
        root = self._scan_path()
        if not os.path.isdir(root):
            return []

        target = str(number or "").strip().casefold()
        matches: List[str] = []
        try:
            for current_root, _dirs, files in os.walk(root):
                for name in files:
                    stem, ext = os.path.splitext(name)
                    if stem.casefold() == target and (
                        not SCAN_FILE_EXTENSIONS or ext.casefold() in SCAN_FILE_EXTENSIONS
                    ):
                        matches.append(os.path.join(current_root, name))
        except OSError as exc:
            logger.warning("Scan directory could not be read: %s", exc)

        matches.sort(key=lambda p: (
            os.path.splitext(p)[1].casefold() != ".pdf",
            len(p),
            p.casefold(),
        ))
        return matches

    def _refresh_scan_status(self) -> None:
        if not hasattr(self, "lbl_scan"):
            return
        path = self._scan_path()
        if os.path.isdir(path):
            self.lbl_scan.setText("اسکن: متصل ✓")
            self.lbl_scan.setStyleSheet(
                "background:transparent;color:#16a34a;font-weight:bold;"
            )
            self.lbl_scan.setToolTip(f"مسیر اسکن در دسترس است:\n{path}")
        else:
            self.lbl_scan.setText("اسکن: قطع ✕")
            self.lbl_scan.setStyleSheet(
                "background:transparent;color:#dc2626;font-weight:bold;"
            )
            self.lbl_scan.setToolTip(f"مسیر اسکن در دسترس نیست:\n{path}")

    def _scan_path(self) -> str:
        path = str(
            self.settings.value("scan_path", DEFAULT_SCAN_PATH, type=str) or ""
        ).strip()
        return os.path.normpath(path) if path else DEFAULT_SCAN_PATH

    def configure_scan_path(self) -> None:
        current = self._scan_path()
        path = QFileDialog.getExistingDirectory(
            self,
            "انتخاب مسیر اسکن مدارک",
            current if os.path.isdir(current) else os.path.expanduser("~"),
            QFileDialog.Option.ShowDirsOnly,
        )
        if not path:
            return
        self.settings.setValue("scan_path", os.path.normpath(path))
        self._refresh_scan_status()
        QMessageBox.information(
            self, "تنظیمات اسکن",
            f"مسیر اسکن با موفقیت ذخیره شد:\n{os.path.normpath(path)}"
        )

    def open_scan_folder(self) -> None:
        path = self._scan_path()
        if not os.path.isdir(path):
            QMessageBox.warning(
                self, "مسیر اسکن در دسترس نیست",
                f"پوشه اسکن پیدا نشد:\n{path}\n\n"
                "از «تنظیمات → مسیر اسکن مدارک…» مسیر صحیح را انتخاب کنید."
            )
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def check_scan_path(self) -> None:
        path = self._scan_path()
        if os.path.isdir(path):
            QMessageBox.information(self, "مسیر اسکن", f"مسیر اسکن در دسترس است:\n{path}")
        else:
            QMessageBox.warning(self, "مسیر اسکن", f"مسیر اسکن در دسترس نیست:\n{path}")

    def open_scanned_document(self) -> None:
        ids = self._selected_ids()
        if not ids:
            QMessageBox.information(
                self, "انتخاب صورتجلسه", "ابتدا یک صورتجلسه را انتخاب کنید."
            )
            return

        meeting = self.db.get_meeting(ids[0])
        if not meeting:
            QMessageBox.warning(self, "خطا", "صورتجلسه انتخاب‌شده یافت نشد.")
            return

        number = str(meeting.meeting_number or "").strip()
        if not number:
            QMessageBox.warning(self, "شماره سند", "برای این صورتجلسه شماره سند ثبت نشده است.")
            return

        root = self._scan_path()
        if not os.path.isdir(root):
            QMessageBox.warning(
                self, "مسیر اسکن یافت نشد",
                f"پوشه اسکن در مسیر زیر پیدا نشد:\n{root}\n\n"
                "لطفاً مسیر اسکن را در تنظیمات اصلاح کنید."
            )
            return

        matches = self._scan_file_matches(number)

        if not matches:
            QMessageBox.information(
                self, "مدرک اسکن نشده",
                f"مدرک شماره «{number}» در مسیر اسکن پیدا نشد.\n\n"
                f"لطفاً مدرک را اسکن کرده و فایل را در این مسیر قرار دهید:\n{root}\n\n"
                f"نام فایل اسکن باید دقیقاً برابر شماره صورتجلسه باشد:\n{number}.pdf"
            )
            return

        if len(matches) > 1:
            self.statusBar().showMessage(
                f"{len(matches)} فایل برای شماره «{number}» پیدا شد؛ PDF اولویت دارد.", 4000
            )
        file_path = matches[0]
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(file_path)):
            QMessageBox.warning(self, "باز کردن مدرک", f"باز کردن فایل ممکن نشد:\n{file_path}")

    def _get_user_id(self) -> Optional[int]:
        return getattr(self.session, "user_id", None)

    def new_meeting(self) -> None:
        if not can(self.session, PERM_REPORT_WRITE):
            QMessageBox.warning(self, "دسترسی غیرمجاز", "اجازه ایجاد صورتجلسه ندارید.")
            return

        from ui.meeting_dialog import MeetingDialog
        dlg = MeetingDialog(self.db, self)
        if dlg.exec() == MeetingDialog.DialogCode.Accepted:
            try:
                m = self.db.create_meeting(dlg.get_data())
                self.db.assign_meeting_to_user(
                    m.id, self.session.username, self.session.username
                )
                self.db.audit(
                    self._get_user_id(),
                    self.session.username,
                    "MEETING_CREATED",
                    f"number={m.meeting_number}",
                    meeting_id=m.id,
                )
                self._apply_live_status(m.id)
                self.reload_meta()
                self.reload_page()
            except Exception as exc:
                logger.exception("Create meeting failed")
                QMessageBox.critical(self, "خطا", str(exc))

    def edit_selected(self) -> None:
        if not can(self.session, PERM_REPORT_WRITE):
            QMessageBox.warning(self, "دسترسی غیرمجاز", "اجازه ویرایش ندارید.")
            return

        ids = self._selected_ids()
        if not ids:
            QMessageBox.information(self, "اطلاع", "یک رکورد انتخاب کنید.")
            return

        m = self.db.get_meeting(ids[0])
        if not m:
            QMessageBox.warning(self, "خطا", "رکورد یافت نشد.")
            return

        from ui.meeting_dialog import MeetingDialog
        dlg = MeetingDialog(self.db, self, meeting=m)
        if dlg.exec() == MeetingDialog.DialogCode.Accepted:
            try:
                self.db.update_meeting(m.id, dlg.get_data())
                self.db.audit(
                    self._get_user_id(),
                    self.session.username,
                    "MEETING_UPDATED",
                    f"number={m.meeting_number}",
                    meeting_id=m.id,
                )
                self._apply_live_status(m.id)
                self.reload_meta()
                self.reload_page()
            except Exception as exc:
                logger.exception("Update meeting failed")
                QMessageBox.critical(self, "خطا", str(exc))

    def delete_selected(self) -> None:
        if not can(self.session, PERM_MEETING_DELETE):
            QMessageBox.warning(self, "دسترسی غیرمجاز", "اجازه حذف صورتجلسه ندارید.")
            return

        ids = self._selected_ids()
        if not ids:
            QMessageBox.information(self, "اطلاع", "رکوردی انتخاب نشده.")
            return

        reply = QMessageBox.question(
            self, "تأیید حذف", f"حذف {len(ids)} رکورد؟",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        errs: List[str] = []
        for mid in ids:
            try:
                self.db.delete_meeting(mid, deleted_by=self.session.username)
            except Exception as exc:
                logger.exception("Delete meeting %s failed", mid)
                errs.append(str(exc))

        if errs:
            QMessageBox.warning(self, "خطا", "\n".join(errs[:5]))
        self.reload_meta()
        self.reload_page()

    def open_workflow(self) -> None:
        ids = self._selected_ids()
        if not ids:
            QMessageBox.information(self, "اطلاع", "یک صورتجلسه انتخاب کنید.")
            return

        m = self.db.get_meeting(ids[0])
        if not m:
            QMessageBox.warning(self, "خطا", "یافت نشد.")
            return

        try:
            if not self.db.get_workflow_steps(m.id):
                self.db.initialize_workflow(m.id)
        except Exception as exc:
            logger.exception("Init workflow failed")
            QMessageBox.critical(self, "خطا", str(exc))
            return

        from ui.workflow_dialog import WorkflowDialog
        WorkflowDialog(self.db, m, self).exec()
        self._apply_live_status(m.id)
        self.reload_page()

    def open_workflow_reports(self) -> None:
        if not can(self.session, PERM_REPORT_READ):
            QMessageBox.warning(self, "دسترسی غیرمجاز", "اجازه مشاهده گزارش‌ها را ندارید.")
            return
        from ui.workflow_reports_dialog import WorkflowReportsDialog
        WorkflowReportsDialog(self.db, self.session, self).exec()

    def open_tracking(self) -> None:
        ids = self._selected_ids()
        if not ids:
            QMessageBox.information(
                self, "انتخاب صورتجلسه", "ابتدا یک صورتجلسه را انتخاب کنید."
            )
            return

        m = self.db.get_meeting(ids[0])
        if not m:
            QMessageBox.warning(self, "خطا", "صورتجلسه یافت نشد.")
            return

        from ui.tracking_dialog import TrackingDialog
        TrackingDialog(self.db, m, self.session.username, self).exec()
        self._apply_live_status(m.id)
        self.reload_meta()
        self.reload_page()

    def open_operational_dashboard(self) -> None:
        from ui.operations_dashboard import OperationsDashboard
        OperationsDashboard(self.db, self).exec()
        self.reload_meta()
        self.reload_page()

    def change_database(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "انتخاب دیتابیس", "", "SQLite DB (*.db);;All (*)"
        )
        if not path:
            return

        try:
            new_db = DatabaseManager(path)
        except Exception as exc:
            logger.exception("Open DB failed")
            QMessageBox.critical(self, "خطا", str(exc))
            return

        from ui.login_dialog import LoginDialog
        login = LoginDialog(new_db, self)
        if login.exec() != LoginDialog.DialogCode.Accepted or not login.session:
            return

        self.db, self.session = new_db, login.session
        self.settings.setValue("db_path", path)
        self._columns_initialized = False
        self.page = 0

        _cached_to_shamsi.cache_clear()
        _cached_days_until.cache_clear()

        self._apply_access()
        self._refresh_db_label()
        self.reload_meta()
        self.reload_page()
        self._update_title()

    def backup_db(self) -> None:
        default_name = f"backup_{date.today():%Y%m%d}.db"
        p, _ = QFileDialog.getSaveFileName(
            self, "پشتیبان‌گیری",
            os.path.join(os.path.expanduser("~"), default_name),
            "SQLite DB (*.db)",
        )
        if not p:
            return
        try:
            self.db.backup_database(p)
            QMessageBox.information(self, "انجام شد", f"پشتیبان امن ایجاد شد:\n{p}")
        except Exception as exc:
            logger.exception("Backup failed")
            QMessageBox.critical(self, "خطا", str(exc))

    def publish_db(self) -> None:
        if not can(self.session, PERM_DB_PUBLISH):
            QMessageBox.warning(self, "دسترسی غیرمجاز", "اجازه ندارید.")
            return

        p, _ = QFileDialog.getSaveFileName(
            self, "انتشار", "meetings_shared.db", "SQLite DB (*.db)"
        )
        if not p:
            return

        try:
            self.db.backup_database(p)
        except Exception as exc:
            logger.exception("Publish failed")
            QMessageBox.critical(self, "خطا", str(exc))
            return

        try:
            os.chmod(p, 0o444)
        except OSError:
            try:
                os.system(f'attrib +R "{p}"')
            except Exception:
                logger.debug("Set readonly failed", exc_info=True)

        QMessageBox.information(self, "انتشار شد", f"ذخیره شد:\n{p}")

    def import_data(self) -> None:
        if not can(self.session, PERM_REPORT_WRITE):
            QMessageBox.warning(self, "دسترسی غیرمجاز", "اجازه ندارید.")
            return

        path, _ = QFileDialog.getOpenFileName(
            self, "واردات", "", "Excel/CSV (*.xlsx *.xls *.csv)"
        )
        if not path:
            return

        self._import_progress = QProgressDialog("واردات…", "لغو", 0, 100, self)
        self._import_progress.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._import_progress.setWindowModality(Qt.WindowModality.WindowModal)
        self._import_progress.setMinimumDuration(200)
        self._import_progress.setValue(0)

        from services.import_export import ImportWorker
        worker = ImportWorker(self.db, path)
        worker.signals.progress.connect(self._import_progress.setValue)
        worker.signals.error.connect(lambda m: QMessageBox.critical(self, "خطا", m))
        worker.signals.finished.connect(self._on_import_finished)
        self._import_progress.canceled.connect(worker.cancel)
        self.thread_pool.start(worker)
        self._import_progress.exec()

    def _on_import_finished(self, result: Dict[str, Any]) -> None:
        if self._import_progress:
            try:
                self._import_progress.setValue(100)
                self._import_progress.close()
            except Exception:
                logger.debug("Close import progress failed", exc_info=True)
            self._import_progress = None

        _cached_to_shamsi.cache_clear()
        _cached_days_until.cache_clear()

        self.reload_meta()
        self.reload_page()

        added = int(result.get("added", 0) or 0)
        skipped = result.get("skipped", []) or []
        msg = f"افزوده: {added}\nرد شده: {len(skipped)}"
        if result.get("cancelled"):
            msg += "\n\nلغو شد."
        if skipped:
            msg += "\n\nنمونه:\n" + "\n".join(str(s) for s in skipped[:8])
        QMessageBox.information(self, "نتیجه", msg)

    def export_excel(self) -> None:
        if not can(self.session, PERM_REPORT_EXPORT):
            QMessageBox.warning(self, "دسترسی غیرمجاز", "اجازه ندارید.")
            return

        if not self.model.rows:
            QMessageBox.information(self, "اطلاع", "داده‌ای نیست.")
            return

        default_name = f"meetings_{date.today():%Y%m%d}.xlsx"
        path, sf = QFileDialog.getSaveFileName(
            self, "ذخیره", default_name, "Excel (*.xlsx);;CSV (*.csv)"
        )
        if not path:
            return

        try:
            if "CSV" in sf or path.lower().endswith(".csv"):
                if not path.lower().endswith(".csv"):
                    path += ".csv"
                self._export_csv(path)
            else:
                if not path.lower().endswith(".xlsx"):
                    path += ".xlsx"
                self._export_xlsx(path)
            QMessageBox.information(self, "انجام شد", f"ذخیره شد:\n{path}")
        except Exception as exc:
            logger.exception("Export failed")
            QMessageBox.critical(self, "خطا", str(exc))

    def _export_xlsx(self, path: str) -> None:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment
        from openpyxl.utils import get_column_letter

        wb = Workbook()
        ws = wb.active
        ws.title = "Meetings"
        try:
            ws.sheet_view.rightToLeft = True
        except Exception:
            logger.debug("rightToLeft not supported", exc_info=True)

        headers = self.model.headers
        hf = Font(bold=True, color="FFFFFF")
        hfi = PatternFill("solid", fgColor="00BFFF")
        ha = Alignment(horizontal="center", vertical="center")
        ca = Alignment(horizontal="right", vertical="center")

        for ci, h in enumerate(headers, 1):
            c = ws.cell(row=1, column=ci, value=h)
            c.font, c.fill, c.alignment = hf, hfi, ha

        for ri, row in enumerate(self.model.rows, 2):
            ws.cell(row=ri, column=1, value=ri - 1).alignment = ha
            for ci, val in enumerate(row, 2):
                ws.cell(
                    row=ri, column=ci, value="" if val is None else str(val)
                ).alignment = ca

        for ci in range(1, len(headers) + 1):
            ws.column_dimensions[get_column_letter(ci)].width = 16

        ws.freeze_panes = "A2"
        wb.save(path)

    def _export_csv(self, path: str) -> None:
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(self.model.headers)
            for i, row in enumerate(self.model.rows, 1):
                w.writerow([str(i)] + ["" if v is None else str(v) for v in row])

    def download_import_template(self) -> None:
        if not can(self.session, PERM_REPORT_WRITE):
            QMessageBox.warning(self, "دسترسی غیرمجاز", "اجازه ندارید.")
            return

        path, sf = QFileDialog.getSaveFileName(
            self, "قالب", "import_template.xlsx", "Excel (*.xlsx);;CSV (*.csv)"
        )
        if not path:
            return

        try:
            if "CSV" in sf or path.lower().endswith(".csv"):
                if not path.lower().endswith(".csv"):
                    path += ".csv"
                with open(path, "w", newline="", encoding="utf-8-sig") as f:
                    csv.writer(f).writerow(Meeting.headers())
            else:
                if not path.lower().endswith(".xlsx"):
                    path += ".xlsx"
                self._template_xlsx(path)
            QMessageBox.information(self, "انجام شد", f"قالب:\n{path}")
        except Exception as exc:
            logger.exception("Template creation failed")
            QMessageBox.critical(self, "خطا", str(exc))

    def _template_xlsx(self, path: str) -> None:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment
        from openpyxl.utils import get_column_letter

        wb = Workbook()
        ws = wb.active
        ws.title = "Template"
        try:
            ws.sheet_view.rightToLeft = True
        except Exception:
            logger.debug("rightToLeft not supported", exc_info=True)

        headers = Meeting.headers()
        for ci, h in enumerate(headers, 1):
            c = ws.cell(row=1, column=ci, value=h)
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = PatternFill("solid", fgColor="0099CC")
            c.alignment = Alignment(horizontal="center")
            ws.column_dimensions[get_column_letter(ci)].width = 16

        samples = {
            "شماره صورتجلسه": "1404-001",
            "موضوع": "نمونه",
            "تاریخ صورتجلسه": today_shamsi(),
            "مهلت رسیدگی": today_shamsi(),
            "وضعیت": STATUS_PENDING,
            "اولویت": PRIORITY_MEDIUM,
            "دیسیپلین": DISCIPLINES[0] if DISCIPLINES else "",
        }
        for ci, h in enumerate(headers, 1):
            ws.cell(row=2, column=ci, value=samples.get(h, ""))

        wb.save(path)

    def open_user_admin(self) -> None:
        if not can(self.session, PERM_USER_ADMIN):
            QMessageBox.warning(self, "دسترسی غیرمجاز", "اجازه ندارید.")
            return
        from ui.user_admin_dialog import UserAdminDialog
        UserAdminDialog(self.db, self).exec()

    def open_dashboard(self) -> None:
        if not _has_matplotlib():
            QMessageBox.critical(self, "خطا", "matplotlib نصب نیست.")
            return
        from ui.chart_dialog import ChartDialog
        ChartDialog(
            self.db.status_priority_counts(self._get_filters(), self.search.text().strip()),
            "وضعیت و اولویت",
            parent=self,
        ).exec()

    def _open_user_guide(self) -> None:
        g = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "user_guide.html",
        )
        if os.path.isfile(g):
            QDesktopServices.openUrl(QUrl.fromLocalFile(g))
        else:
            QMessageBox.warning(self, "یافت نشد", f"راهنما:\n{g}")

    def _show_about(self) -> None:
        QMessageBox.about(
            self, "درباره",
            "Document & MOM Tracking System\nنسخه ۳.۱\n\n"
            "• صورتجلسات • گردش کار • فیلتر • اکسل • تاریخ شمسی\n"
            "• رصد خودکار وضعیت زنده از گردش کار\n"
            "• قانون طلایی: ارسال به پیمانکار = اتمام کار"
        )

    def _apply_access(self) -> None:
        wr = can(self.session, PERM_REPORT_WRITE)
        ex = can(self.session, PERM_REPORT_EXPORT)
        dl = can(self.session, PERM_MEETING_DELETE)

        for w in (self.btn_new, self.btn_edit, self.btn_workflow,
                  self.btn_tracking, self.btn_template, self.act_import):
            w.setEnabled(wr)

        self.btn_del.setEnabled(dl)

        if isinstance(self.btn_workflow, MeteorButton):
            if wr:
                self.btn_workflow.start_meteor()
            else:
                self.btn_workflow.stop_meteor()

        self.btn_workflow_report.setEnabled(can(self.session, PERM_REPORT_READ))
        self.btn_refresh.setEnabled(True)
        self.btn_dashboard.setEnabled(True)
        self.btn_scan.setEnabled(True)

        for w in (self.btn_export, self.act_export_excel):
            w.setEnabled(ex)

        self.act_publish.setEnabled(can(self.session, PERM_DB_PUBLISH))
        self.act_users.setEnabled(can(self.session, PERM_USER_ADMIN))
