# -*- coding: utf-8 -*-
"""
ui.main_window
پنجره اصلی برنامه Document & MOM Tracking System
نسخه نهایی هوشمند: رصد خودکار وضعیت از گردش کار، رفع تمام باگ‌های RTL،
دکمه‌های مدرن SaaS و همگام‌سازی کامل با قانون جدید (ارسال به پیمانکار = اتمام کار)
(اصلاح نمایش نام کارشناس واقعی دپارتمان در اسناد ابلاغ شده)
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
    QStyle,
    QStyleOptionViewItem,
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
    PERM_REPORT_WRITE,
    PERM_USER_ADMIN,
    can,
)
from security.session import UserSession
from utils.date_utils import to_gregorian, to_shamsi, today_shamsi
from services.meeting_number_report import MeetingNumberReportGenerator

logger = logging.getLogger(__name__)

def _has_matplotlib() -> bool:
    try:
        from ui.chart_dialog import HAS_MATPLOTLIB
        return bool(HAS_MATPLOTLIB)
    except Exception:
        return False


# ─────────────────────────────────────────────
# ثابت‌های UI
# ─────────────────────────────────────────────
COLOR_SKY_BLUE = "#00BFFF"
COLOR_SKY_DARK = "#0099CC"
COLOR_SELECTION_BG = "#E0F7FA"
COLOR_SELECTION_FG = "#004D40"
COLOR_TEXT_MAIN = "#1E293B"

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
    "تاریخ صورتجلسه", "تاریخ قرارداد",
    "تاریخ ارسال به پیمانکار", "مهلت انجام", "تاریخ بسته شدن", "تاریخ پاسخ پیمانکار",
])

HEADER_TO_DB_COL: Dict[str, str] = {
    "ردیف": "id",
    "ارسال به نظارت": "sent_to_supervision_date",
    "ورود به نظارت": "supervision_entry_date",
    "ورود به کارفرما": "entry_date",
    "تاریخ صورتجلسه": "meeting_date",
    "شماره صورتجلسه": "meeting_number",
    "کارفرما": "employer", "مشاور": "consultant", "پیمانکار": "contractor",
    "شماره قرارداد": "contract_number", "تاریخ قرارداد": "contract_date",
    "موضوع": "subject", "دیسیپلین": "discipline", "محل کار": "location",
    "وضعیت": "status", "اولویت": "priority", "مهلت انجام": "due_date",
    "تاریخ بسته شدن": "closing_date",
    "تاریخ ارسال به پیمانکار": "sent_to_contractor_date",
    "تاریخ پاسخ پیمانکار": "contractor_response_date",
}


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

    _BG: Dict[str, QColor] = {
        STATUS_COMPLETED: QColor("#DCFCE7"),
        STATUS_PENDING:   QColor("#FEF3C7"),
        STATUS_AWAITING:  QColor("#E0F2FE"),
        STATUS_CANCELLED: QColor("#FEE2E2"),
        STATUS_RETURNED:  QColor("#FFEDD5"),
    }
    _FG: Dict[str, QColor] = {
        STATUS_COMPLETED: QColor("#166534"),
        STATUS_PENDING:   QColor("#92400E"),
        STATUS_AWAITING:  QColor("#1E40AF"),
        STATUS_CANCELLED: QColor("#991B1B"),
        STATUS_RETURNED:  QColor("#9A3412"),
    }

    _OVERDUE_BG = QColor("#FEE2E2")
    _OVERDUE_FG = QColor("#991B1B")
    _WARNING_BG = QColor("#FEF3C7")
    _WARNING_FG = QColor("#92400E")
    _WARNING_DAYS = 3
    _DEFAULT_FG = QColor("#1E293B")

    def __init__(self) -> None:
        super().__init__()
        self._orig_headers: List[str] = Meeting.headers()
        self.headers: List[str] = ["#"] + self._orig_headers + ["کارشناس رسیدگی‌کننده", "مرحله جاری"]
        self.rows: List[List[Any]] = []
        # وضعیت واقعی گردش‌کار، جدا از وضعیت عمومی پرونده نگهداری می‌شود.
        # کلیدها شناسه پرونده‌اند تا هیچ ستون داخلی به جدول نمایشی اضافه نشود.
        self.workflow_states: Dict[int, str] = {}

        self._col_status = self._find("وضعیت")
        self._col_due = self._find("مهلت انجام")
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

        # رنگ ردیف از وضعیت واقعی گام‌ها می‌آید؛ تاریخ ابلاغ به‌تنهایی سبز نمی‌شود.
        meeting_id = self.get_row_id(row)
        workflow_state = self.workflow_states.get(meeting_id) if meeting_id is not None else None
        workflow_colors = {
            "completed": (QColor("#DCFCE7"), QColor("#166534")),
            "in_progress": (QColor("#DBEAFE"), QColor("#1D4ED8")),
            "pending": (QColor("#FEF3C7"), QColor("#92400E")),
            "returned": (QColor("#FEE2E2"), QColor("#991B1B")),
            "cancelled": (QColor("#F3F4F6"), QColor("#4B5563")),
            "unknown": (QColor("#F3F4F6"), QColor("#374151")),
        }
        colors = workflow_colors.get(workflow_state or "")
        if colors:
            return QBrush(colors[0] if is_bg else self._DEFAULT_FG)

        if self._col_status >= 0:
            v = self._cell(row, self._col_status)
            status = str(v).strip() if v else None
            if status:
                # وضعیت، پس‌زمینه را رنگی می‌کند؛ متن خنثی می‌ماند تا خوانا باشد.
                color = self._BG.get(status) if is_bg else self._DEFAULT_FG
                if color:
                    return QBrush(color)

        if self._col_due >= 0:
            v = self._cell(row, self._col_due)
            due_str = str(v).strip() if v else None
            if due_str:
                days = _cached_days_until(due_str)
                if days is not None:
                    if days < 0:
                        return QBrush(self._OVERDUE_BG if is_bg else self._OVERDUE_FG)
                    if days <= self._WARNING_DAYS:
                        return QBrush(self._WARNING_BG if is_bg else self._WARNING_FG)

        if not is_bg:
            return QBrush(self._DEFAULT_FG)
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
        painter.fillRect(opt.rect, QColor("#BAE6FD") if selected else bg_color)
        painter.restore()

        # جلوگیری از نقاشی دوباره پس‌زمینه توسط QStyle؛ متن و آیکون‌ها
        # همچنان با موتور استاندارد Qt و تنظیمات مدل رسم می‌شوند.
        opt.backgroundBrush = QBrush()
        opt.state &= ~QStyle.StateFlag.State_Selected
        opt.palette.setColor(
            QPalette.ColorRole.Text,
            QColor("#0C4A6E") if selected else (
                index.data(Qt.ItemDataRole.ForegroundRole).color()
                if isinstance(index.data(Qt.ItemDataRole.ForegroundRole), QBrush)
                else QColor("#1E293B")
            ),
        )
        opt.palette.setColor(QPalette.ColorRole.Highlight, QColor("#BAE6FD"))
        opt.palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#0C4A6E"))
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
            logger.exception("Cannot open DB folder")

    def _show_operational_alerts(self) -> None:
        try:
            m = self.db.operational_metrics()
            if m.get("overdue", 0) > 0:
                QMessageBox.warning(
                    self, "⚠️ هشدار پیگیری",
                    f"{m['overdue']} صورتجلسه از مهلت انجام عبور کرده است.\n\n"
                    "از «داشبورد عملیاتی MOM» برای پیگیری استفاده کنید."
                )
            elif m.get("due_3", 0) > 0:
                self.statusBar().showMessage(
                    f"⏳ هشدار: {m['due_3']} صورتجلسه در ۳ روز آینده سررسید می‌شود.", 10000
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
        body_layout.setContentsMargins(10, 10, 10, 10)
        body_layout.setSpacing(8)

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
        banner.setFixedHeight(40)

        layout = QHBoxLayout(banner)
        layout.setContentsMargins(15, 0, 15, 0)
        layout.setSpacing(10)

        title_label = QLabel("✨ سامانه جامع مدیریت، پیگیری هوشمند و گردش‌کار صورتجلسات")
        title_label.setStyleSheet("""
            color: #ffffff;
            font-size: 13.5px;
            font-weight: bold;
            font-family: 'B Yekan', 'Vazir', 'Segoe UI', Tahoma;
            background: transparent;
        """)

        info_label = QLabel("پایش مداوم اسناد کارگاهی | نسخه ۳.۰")
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
        bar.setSpacing(6)

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
        bar.setSpacing(8)

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
        bar.setSpacing(6)

        self.search = QLineEdit()
        self.search.setPlaceholderText("🔎 جستجو بر اساس شماره صورتجلسه، موضوع، ارکان پروژه، دیسیپلین فنی...")
        self.search.setClearButtonEnabled(True)
        self.search.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.search.setAlignment(Qt.AlignmentFlag.AlignRight)

        self.meeting_no_filter = QComboBox()
        self.meeting_no_filter.setEditable(True)  # تایپ برای جستجو داخل لیست
        self.meeting_no_filter.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.meeting_no_filter.setFixedWidth(200)
        self.meeting_no_filter.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.meeting_no_filter.setToolTip(
            "یک شماره صورتجلسه را از لیست انتخاب کنید؛ سپس گزارش همان پرونده نمایش داده می‌شود."
        )
        self.meeting_no_filter.setMaxVisibleItems(20)
        # فقط انتخاب از لیست (نه متن آزاد خارج از لیست)
        le = self.meeting_no_filter.lineEdit()
        if le:
            le.setPlaceholderText("انتخاب شماره صورتجلسه…")
            le.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self.btn_meeting_no_report = QPushButton("📄 گزارش شماره")
        self.btn_meeting_no_report.setObjectName("btn_primary")
        self.btn_meeting_no_report.setToolTip(
            "گزارش HTML برای صورتجلسه انتخاب‌شده (محل کار | روز مانده | موضوع | پیمانکار)"
        )

        bar.addWidget(QLabel("شماره صورتجلسه:"))
        bar.addWidget(self.meeting_no_filter)
        bar.addWidget(self.btn_meeting_no_report)
        bar.addSpacing(12)
        bar.addWidget(QLabel("جستجوی سریع:"))
        bar.addWidget(self.search, stretch=1)
        return bar

    def _build_status_legend(self) -> QWidget:
        """راهنمای دائمی رنگ‌ها؛ رنگ تنها نشانه وضعیت نباشد."""
        legend = QWidget()
        legend.setObjectName("status_legend")
        layout = QHBoxLayout(legend)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(8)

        title = QLabel("راهنمای وضعیت:")
        title.setObjectName("legend_title")
        layout.addWidget(title)

        items = [
            ("در حال انجام", "#DBEAFE", "#1D4ED8"),
            ("در انتظار", "#FEF3C7", "#92400E"),
            ("برگشت برای اصلاح", "#FFE4E6", "#9F1239"),
            ("تکمیل و ابلاغ‌شده", "#D1FAE5", "#166534"),
            ("لغوشده / نامشخص", "#F3F4F6", "#4B5563"),
        ]
        for label, bg, fg in items:
            chip = QLabel(f"●  {label}")
            chip.setObjectName("status_legend_item")
            chip.setStyleSheet(
                f"QLabel#status_legend_item {{ background:{bg}; color:{fg}; "
                "border:1px solid rgba(100,116,139,0.28); border-radius:9px; "
                "padding:4px 9px; font-weight:600; }}"
            )
            layout.addWidget(chip)
        layout.addStretch(1)
        return legend

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

        # اسکرول افقی نرم و قابل‌اعتماد (بدون کش آمدن اجباری آخرین ستون)
        self.view.setHorizontalScrollMode(QTableView.ScrollMode.ScrollPerPixel)
        self.view.setVerticalScrollMode(QTableView.ScrollMode.ScrollPerPixel)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        hdr = self.view.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        hdr.setStretchLastSection(False)  # اسکرول افقی واقعی به‌جای فشردن ستون‌ها
        hdr.setMinimumSectionSize(56)
        hdr.setDefaultSectionSize(110)
        hdr.setSortIndicatorShown(True)
        hdr.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        hdr.sectionClicked.connect(self._on_header_clicked)

        self.view.verticalHeader().setDefaultSectionSize(34)
        self.view.verticalHeader().setVisible(False)

        self.model = MeetingsPageModel()
        self.view.setModel(self.model)
        self.view.setItemDelegate(StatusRowDelegate(self.view))
        self.view.doubleClicked.connect(self.edit_selected)
        return self.view

    def _connect_signals(self) -> None:
        self.search.textChanged.connect(self.search_timer.start)
        self.btn_meeting_no_report.clicked.connect(self._report_by_meeting_number)
        # Enter در خط‌ویرایش کمبو
        if self.meeting_no_filter.lineEdit():
            self.meeting_no_filter.lineEdit().returnPressed.connect(self._report_by_meeting_number)
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
    # اعمال استایل هماهنگ منوها، دکمه‌ها و بدنه
    # ─────────────────────────────────────────
    def _apply_style(self) -> None:
        if self.dark_mode:
            bg_m, bg_t, bg_a = "#0F172A", "#1E293B", "#334155"
            bg_h, fg_m, fg_h = "#1E293B", "#E2E8F0", "#F1F5F9"
            brd, inp, sbb = "#475569", "#1E293B", "#1E293B"
            bd, sf = "#64748B", COLOR_SKY_BLUE
            tf, sb, sfg = "#E2E8F0", "#0369A1", "#FFFFFF"
            
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
            tf, sb, sfg = "#1E293B", COLOR_SELECTION_BG, COLOR_SELECTION_FG
            
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
                selection-background-color:#BAE6FD;
                selection-color:#0C4A6E;
                gridline-color:transparent;
                font-size:12.5px;
                outline:0;
            }}
            QTableView#meetings_table::item {{
                padding:7px 9px;
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
                padding:9px 7px;
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
                border:1px solid {brd}; border-radius:5px;
                padding:4px 10px; background:{inp};
                color:{fg_m}; font-size:12.5px; min-height:26px;
            }}
            QLineEdit:focus, QComboBox:focus {{
                border-color: #00ADB5;
                background: #F0FDFA;
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
                background-color: #FFFFFF;
                border: 1px solid {brd};
                color: #334155;
            }}
            QPushButton#btn_secondary:hover {{
                background-color: #F1F5F9;
                border-color: #94A3B8;
                color: #0F172A;
            }}
            QPushButton#btn_secondary:pressed {{
                background-color: #E2E8F0;
            }}
            QPushButton#btn_danger {{
                background-color: #FEE2E2;
                border: 1px solid #FCA5A5;
                color: #991B1B;
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
                background-color: #FFFFFF;
                border: 1px solid {brd};
                color: #334155;
                min-width: 60px;
            }}
            QPushButton#btn_pager:hover {{
                background-color: #F1F5F9;
                color: #0F172A;
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
        محاسبه خودکار وضعیت کلی صورتجلسه بر اساس گام‌های گردش کار و پاسخ پیمانکار.
        """
        try:
            with self.db.session() as sess:
                meeting = sess.get(Meeting, meeting_id)
                if not meeting:
                    return STATUS_PENDING

                if meeting.status == STATUS_CANCELLED:
                    return STATUS_CANCELLED

                steps = sess.query(WorkflowStep).filter(
                    WorkflowStep.meeting_id == meeting_id
                ).order_by(WorkflowStep.step_order.asc()).all()

                return self._compute_live_status_from_steps(meeting, steps)

        except Exception as exc:
            logger.warning("Live status computation failed for meeting %s: %s", meeting_id, exc)
            return STATUS_PENDING

    def _compute_live_status_from_steps(self, meeting: Meeting, steps: List[WorkflowStep]) -> str:
        """محاسبه وضعیت از روی لیست لود شده گام‌ها (فوق‌سریع و بدون کوئری دیتابیس مجدد)"""
        if meeting.status == STATUS_CANCELLED:
            return STATUS_CANCELLED

        # 👑 قانون طلایی ارسال: به محض اینکه فیلد تاریخ ارسال پر شود -> کل کار تکمیل شده است!
        if meeting.sent_to_contractor_date is not None:
            return STATUS_COMPLETED

        if not steps:
            return STATUS_PENDING

        # ۱. اگر گام ریجکت شده (برگشت داده شده) وجود داشته باشد -> «بازگشت داده شده»
        rejected_step = next(
            (s for s in reversed(steps) if s.status == "rejected"), None
        )
        if rejected_step:
            return STATUS_RETURNED

        # ۲. اگر همه مراحل تکمیل شده باشند -> «تکمیل شده»
        if all(s.status in ("completed", "skipped") for s in steps):
            return STATUS_COMPLETED

        # ۳. اگر گام در حال جریانی وجود دارد -> «در انتظار تأیید»
        in_progress = any(s.status == "in_progress" for s in steps)
        if in_progress:
            return STATUS_AWAITING

        # ۴. پیش‌فرض -> «در دست بررسی»
        return STATUS_PENDING

    def _apply_live_status(self, meeting_id: int) -> None:
        """اعمال وضعیت زنده محاسبه شده بر روی رکورد پایگاه داده به همراه بسته شدن هوشمند گام‌ها."""
        new_status = self._compute_live_status(meeting_id)
        try:
            with self.db.session() as sess:
                meeting = sess.get(Meeting, meeting_id)
                if meeting:
                    # الف) اگر وضعیت تکمیل شده باشد و تاریخ ارسال پر باشد، تمام مراحل گردش‌کار تکمیل و بسته می‌شوند
                    if new_status == STATUS_COMPLETED and meeting.sent_to_contractor_date is not None:
                        # 🎯 همگام‌سازی: تاریخ بسته شدن و تاریخ پاسخ پیمانکار هم زمان با تاریخ ارسال مقداردهی می‌شوند
                        meeting.closing_date = meeting.sent_to_contractor_date
                        meeting.contractor_response_date = meeting.sent_to_contractor_date

                        steps = sess.query(WorkflowStep).filter(
                            WorkflowStep.meeting_id == meeting_id,
                            WorkflowStep.status != "completed"
                        ).all()
                        for s in steps:
                            s.status = "completed"
                            s.exit_date = meeting.sent_to_contractor_date

                    if meeting.status != new_status:
                        old_status = meeting.status
                        meeting.status = new_status
                        sess.commit()
                        logger.info(
                            "Live status updated for meeting %s: %s → %s",
                            meeting_id, old_status, new_status
                        )
        except Exception:
            logger.exception("Failed to persist live status for meeting %s", meeting_id)

    def sync_all_statuses(self) -> None:
        """همگام‌سازی سراسری تمام رکوردهای قدیمی با منطق جدید گردش کار."""
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
            with self.db.session() as sess:
                meetings = sess.query(Meeting).filter(
                    Meeting.is_deleted.is_(False)
                ).all()
                meeting_ids = [m.id for m in meetings]

            for mid in meeting_ids:
                # محاسبه و ثبت خودکار وضعیت تکمیل شده بر اساس قانون طلایی
                self._apply_live_status(mid)
                updated += 1

            QMessageBox.information(
                self, "همگام‌سازی انجام شد",
                f"وضعیت {updated} صورتجلسه به‌روزرسانی شد."
            )
            self.reload_page()
        except Exception as exc:
            logger.exception("Bulk status sync failed")
            QMessageBox.critical(self, "خطا", f"همگام‌سازی با خطا مواجه شد:\n{exc}")

    # ─────────────────────────────────────────
    # سایر متدها و کنترل‌های برنامه
    # ─────────────────────────────────────────
    def _reset_column_sizes(self) -> None:
        h = self.view.horizontalHeader()
        for i in range(self.model.columnCount()):
            h.resizeSection(i, 110)
        h.setStretchLastSection(True)
        self._columns_initialized = False

    def _auto_size_columns(self) -> None:
        if self._columns_initialized:
            return
        h = self.view.horizontalHeader()
        for c in range(self.model.columnCount()):
            ht = self.model.headerData(c, Qt.Orientation.Horizontal) or ""
            width = max(len(str(ht)) * 10, 56)
            for r in range(min(self.model.rowCount(), 40)):
                t = self.model.data(self.model.index(r, c), Qt.ItemDataRole.DisplayRole) or ""
                width = max(width, min(len(str(t)) * 8, 280))
            # سقف معقول تا اسکرول افقی ممکن بماند
            h.resizeSection(c, min(width + 20, 260))
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
            if v and v != "همه":
                f[key] = v
        return f

    def _on_filters_changed(self) -> None:
        self.page = 0
        self.reload_page()

    def _report_by_meeting_number(self) -> None:
        """گزارش HTML برای یک صورتجلسه انتخاب‌شده از کمبوباکس."""
        q = (self.meeting_no_filter.currentText() or "").strip()
        if not q or q == "— انتخاب —":
            QMessageBox.information(
                self,
                "انتخاب صورتجلسه",
                "لطفاً یک شماره صورتجلسه را از لیست انتخاب کنید.",
            )
            self.meeting_no_filter.setFocus()
            return
        try:
            meeting = self.db.get_meeting_by_number(q)
        except Exception as exc:
            logger.exception("meeting number lookup failed")
            QMessageBox.critical(self, "خطا", f"جستجو ناموفق بود:\n{exc}")
            return
        if not meeting:
            QMessageBox.information(
                self,
                "یافت نشد",
                f"صورتجلسه‌ای با شماره «{q}» در سیستم ثبت نشده است.\n"
                "فقط موارد داخل لیست معتبر هستند.",
            )
            return
        try:
            gen = MeetingNumberReportGenerator([meeting], q, parent=self)
            gen.generate_and_open()
        except Exception as e:
            logger.exception("meeting number report failed")
            QMessageBox.critical(self, "خطا", f"تولید گزارش ناموفق بود:\n{e}")


    def reload_meta(self) -> None:
        def _fill(cb: QComboBox, vals: List[str]) -> None:
            cur = cb.currentText()
            cb.blockSignals(True)
            cb.clear()
            cb.addItem("همه")
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
        # لیست شماره‌های صورتجلسه برای گزارش تک‌پرونده
        self._reload_meeting_number_combo()
        self._update_stats()

    def _reload_meeting_number_combo(self) -> None:
        """پر کردن کمبوباکس شماره صورتجلسه (فقط انتخاب از لیست)."""
        cb = getattr(self, "meeting_no_filter", None)
        if cb is None:
            return
        cur = cb.currentText().strip()
        cb.blockSignals(True)
        cb.clear()
        cb.addItem("— انتخاب —")
        try:
            nums = self.db.distinct_values("meeting_number", limit=10000)
        except Exception as exc:
            logger.warning("load meeting numbers failed: %s", exc)
            nums = []
        # مرتب‌سازی طبیعی‌تر: همان ترتیب distinct (معمولاً الفبایی)
        cb.addItems(nums)
        # Completer برای جستجوی سریع داخل لیست
        from PyQt6.QtCore import Qt as _Qt
        from PyQt6.QtWidgets import QCompleter
        completer = QCompleter(nums, cb)
        completer.setCaseSensitivity(_Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(_Qt.MatchFlag.MatchContains)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        cb.setCompleter(completer)
        i = cb.findText(cur)
        cb.setCurrentIndex(i if i >= 0 else 0)
        cb.blockSignals(False)

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

        # ⚡ لود دسته‌ای و بسیار بهینه گردش‌کار تمام سطرها تنها با ۱ کوئری در کل صفحه (سرعت فوق‌العاده بالا)
        meeting_ids = [m.id for m in meetings]
        workflow_map: Dict[int, List[WorkflowStep]] = {}
        try:
            with self.db.session() as sess:
                steps = sess.query(WorkflowStep).filter(
                    WorkflowStep.meeting_id.in_(meeting_ids)
                ).order_by(WorkflowStep.meeting_id, WorkflowStep.step_order.asc()).all()
                for s in steps:
                    workflow_map.setdefault(s.meeting_id, []).append(s)
        except Exception as exc:
            logger.warning("Failed to bulk fetch workflow steps: %s", exc)

        for m in meetings:
            row = m.to_row(hdrs)

            for i in date_indices:
                if row[i]:
                    row[i] = _cached_to_shamsi(str(row[i]))

            # واکشی گام‌های این سطر مشخص از حافظه موقت
            m_steps = workflow_map.get(m.id, [])

            # وضعیت رنگ ردیف را از زنجیره واقعی گام‌ها محاسبه می‌کنیم.
            # سبز فقط وقتی مجاز است که همه گام‌ها تکمیل و ابلاغ ثبت شده باشد.
            if m.status == STATUS_CANCELLED:
                workflow_states[m.id] = "cancelled"
            elif not m_steps:
                workflow_states[m.id] = "pending"
            elif any(s.status == "rejected" for s in m_steps):
                workflow_states[m.id] = "returned"
            elif any(s.status == "in_progress" for s in m_steps):
                workflow_states[m.id] = "in_progress"
            elif any(s.status == "pending" for s in m_steps):
                workflow_states[m.id] = "pending"
            elif all(s.status == "completed" for s in m_steps):
                workflow_states[m.id] = (
                    "completed" if m.sent_to_contractor_date is not None else "pending"
                )
            else:
                # وجود گام skipped یا وضعیت ناشناخته هرگز به‌اشتباه سبز نمی‌شود.
                workflow_states[m.id] = "unknown"

            # نمایش وضعیت زنده (محاسبه شده از گام‌های واکشی شده)
            if status_index >= 0:
                live_status = self._compute_live_status_from_steps(m, m_steps)
                row[status_index] = live_status

            # نمایش کارشناس زنده و مرحله گردش‌کار جاری
            responsible, stage = self._resolve_workflow_step_from_list(m, m_steps)
            row.append(responsible or "—")
            row.append(stage or "—")
            result.append(row)

        self.model.set_workflow_states(workflow_states)
        return result

    def _resolve_workflow_step_from_list(self, meeting: Meeting, steps: List[WorkflowStep]) -> Tuple[str, str]:
        """محاسبه سریع مرحله و کارشناس رسیدگی‌کننده فعال از روی لیست لود شده با رعایت قانون طلایی ارسال."""
        # 🎯 اصلاح هوشمند: کارشناس رسیدگی‌کننده اصلی پروژه همیشه کارشناس تخصیص‌یافته در گام ۳ (ورود به دفتر کارشناس) است
        # این کارشناس حتی پس از ابلاغ به پیمانکار نیز باید در صفحه اصلی نمایش داده شود
        specialist_step = next((s for s in steps if s.step_order == 3), None) if steps else None
        specialist_name = specialist_step.responsible_person if specialist_step else None

        # حالت ۱: پرونده به پیمانکار ابلاغ شده است
        if meeting.sent_to_contractor_date is not None:
            responsible_display = specialist_name or "—"
            return responsible_display, "گردش کار به اتمام رسیده (ابلاغ شده به پیمانکار)"

        # حالت ۲: هیچ گامی هنوز ایجاد نشده است
        if not steps:
            return specialist_name or "—", "—"

        # پیدا کردن گام فعال فعلی (pending یا in_progress) برای نمایش در ستون مرحله جاری
        step = next(
            (s for s in steps if s.status in ("pending", "in_progress")),
            None
        )
        if not step:
            step = steps[-1]

        status_map = {
            "pending": "در انتظار انجام",
            "in_progress": "در حال انجام",
            "completed": "تکمیل شده",
            "skipped": "عبور شده",
            "rejected": "برگشت داده شده"
        }
        status_fa = status_map.get(step.status, step.status)

        # نمایش مسئول فعلی گام جاری در پرانتز برای وضوح بیشتر فرآیند
        current_resp = f" [{step.responsible_person}]" if step.responsible_person else ""
        stage_info = f"{step.step_name} ({status_fa}){current_resp}"

        # اولویت نمایش کارشناس: کارشناس گام ۳ (اصلی) > مسئول گام فعال
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
        from ui.meeting_dialog import MeetingDialog
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
                # اعمال وضعیت پیش‌فرض زنده
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
        from ui.meeting_dialog import MeetingDialog
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
        from ui.login_dialog import LoginDialog
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
                logger.exception("Set readonly failed")

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
                pass
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
            pass

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
            pass

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
            "مهلت انجام": today_shamsi(),
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
            "Document & MOM Tracking System\nنسخه ۳.۰\n\n"
            "• صورتجلسات • گردش کار • فیلتر • اکسل • تاریخ شمسی\n"
            "• رصد خودکار وضعیت زنده از گردش کار"
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

        self.btn_refresh.setEnabled(True)
        self.btn_dashboard.setEnabled(True)
        self.btn_scan.setEnabled(True)

        for w in (self.btn_export, self.act_export_excel):
            w.setEnabled(ex)

        self.act_publish.setEnabled(can(self.session, PERM_DB_PUBLISH))
        self.act_users.setEnabled(can(self.session, PERM_USER_ADMIN))
