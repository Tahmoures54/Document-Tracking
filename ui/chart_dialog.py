# -*- coding: utf-8 -*-
"""
ماژول گزارش نموداری وضعیت صورتجلسات
ChartDialog - نمایش نمودار، جدول آماری و خروجی HTML/Excel/CSV

نسخه بهبودیافته:
- رفع بهم‌ریختگی حروف فارسی در نمودار: تمامی برچسب‌ها و متون نمودار به انگلیسی نمایش داده می‌شوند.
- سایر بخش‌ها (کارت‌ها، جداول، خروجی‌ها) کاملاً فارسی باقی مانده‌اند.
- کش هوشمند برای بهینه‌سازی سرعت
- Exception handling دقیق‌تر
"""
from __future__ import annotations

import base64
import csv
import html
import io
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

from PyQt6.QtCore import Qt, QMarginsF, QSizeF, QUrl
from PyQt6.QtGui import QColor, QDesktopServices, QFont, QKeyEvent
from PyQt6.QtPrintSupport import QPrinter, QPrintDialog
from PyQt6.QtWidgets import (
    QDialog, QFileDialog, QFrame, QHBoxLayout,
    QHeaderView, QLabel, QMessageBox, QPushButton,
    QSplitter, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════
# بارگذاری اختیاری کتابخانه‌ها
# ══════════════════════════════════════════════════

try:
    import matplotlib
    matplotlib.use("QtAgg")
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure
    HAS_MATPLOTLIB = True
except ImportError as _mpl_err:
    HAS_MATPLOTLIB = False
    logger.warning("matplotlib not available: %s", _mpl_err)
except Exception as _mpl_err:
    HAS_MATPLOTLIB = False
    logger.warning("matplotlib initialization failed: %s", _mpl_err)

try:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False
    logger.warning("openpyxl not available; Excel export disabled.")


# ══════════════════════════════════════════════════
# ثابت‌های ماژول
# ══════════════════════════════════════════════════

REPORT_SUBJECT  = "گزارش وضعیت صورتجلسات"
REPORT_TYPE     = "وضعیت و اولویت"
APP_NAME_FA     = "Document & MOM Tracking System"
APP_SEARCH_URL  = "https://www.google.com/search?q=" + quote("Document & MOM Tracking System")

# رنگ‌بندی وضعیت‌ها
STATUS_COLORS: Dict[str, str] = {
    "در دست بررسی":     "#f59e0b",
    "در انتظار تأیید":   "#3b82f6",
    "تکمیل شده":         "#22c55e",
    "لغو شده":           "#ef4444",
    "بازگشت داده شده":   "#fb923c",
}

# رنگ پیش‌فرض برای وضعیت‌های ناشناخته
DEFAULT_STATUS_COLOR = "#94a3b8"

# ⭐️ نگاشت وضعیت‌ها و اولویت‌های فارسی به انگلیسی جهت رفع مشکل نمایش
# فقط در نمودار Matplotlib کاربرد دارد
STATUS_EN: Dict[str, str] = {
    "در دست بررسی":     "In Review",
    "در انتظار تأیید":   "Awaiting Approval",
    "تکمیل شده":         "Completed",
    "لغو شده":           "Cancelled",
    "بازگشت داده شده":   "Returned",
    "نامشخص":            "Unknown",
    "بدون داده":         "No Data",
}

PRIORITY_EN: Dict[str, str] = {
    "بالا":     "High",
    "متوسط":    "Medium",
    "پایین":    "Low",
    "نامشخص":   "Unknown",
}

# ترتیب نمایش کارت‌ها
CARD_ORDER = ["در دست بررسی", "در انتظار تأیید", "تکمیل شده", "لغو شده", "بازگشت داده شده"]

# حداکثر ردیف در جدول اولویت‌های برتر
TOP_N = 15

# فونت پیش‌فرض
DEFAULT_FONT_FAMILY = "Vazirmatn"

# جداکننده کلید ترکیبی status|priority
_KEY_SEP_PATTERN = re.compile(r"\s*\|\s*")

# الگوی نامعتبر برای نام فایل
_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\n\r\t]+')
_WHITESPACE_PATTERN = re.compile(r"\s+")


# ══════════════════════════════════════════════════
# ساختارهای داده
# ══════════════════════════════════════════════════

@dataclass(frozen=True)
class _Row:
    """یک ردیف از جدول جزئیات (وضعیت + اولویت + تعداد + درصد)."""
    status:   str
    priority: str
    count:    int
    pct:      float


@dataclass(frozen=True)
class _TopItem:
    """یک ردیف از جدول اولویت‌های برتر."""
    status:   str
    priority: str
    total:    int
    pct:      float


@dataclass
class _ReportTheme:
    """پارامترهای بصری گزارش HTML بر اساس حالت چاپ یا نمایش."""
    body_bg:      str
    header_bg:    str
    page_shadow:  str
    pill_border:  str
    pill_bg:      str
    pill_color:   str
    meta_color:   str
    brand_color:  str
    font_size_px: str
    body_padding: str
    header_pad:   str

    @classmethod
    def screen(cls) -> "_ReportTheme":
        return cls(
            body_bg=(
                "background:"
                " radial-gradient(1200px 700px at 10% 5%, rgba(0,191,255,0.15), transparent 60%),"
                " radial-gradient(900px 600px at 95% 10%, rgba(16,185,129,0.12), transparent 55%),"
                " linear-gradient(160deg, #0b1220 0%, #0f172a 45%, #0b1220 100%);"
            ),
            header_bg="background:linear-gradient(135deg,#00BFFF 0%,#0099CC 45%,#007799 100%);color:#fff;",
            page_shadow="box-shadow:0 10px 30px rgba(15,23,42,0.14);border-radius:14px;",
            pill_border="1px solid #ffffff55",
            pill_bg="rgba(255,255,255,0.12)",
            pill_color="#fff",
            meta_color="#ffffffdd",
            brand_color="#ffffffee",
            font_size_px="17px",
            body_padding="18px",
            header_pad="16px 18px 14px 18px",
        )

    @classmethod
    def print_mode(cls) -> "_ReportTheme":
        return cls(
            body_bg="background:#fff;",
            header_bg="background:#fff;color:#000;border-bottom:1px solid #d1d5db;",
            page_shadow="box-shadow:none;border-radius:0;",
            pill_border="1px solid #d1d5db",
            pill_bg="#f3f4f6",
            pill_color="#111827",
            meta_color="#4b5563",
            brand_color="#111827",
            font_size_px="16px",
            body_padding="0",
            header_pad="10mm 10mm 6mm 10mm",
        )


# ══════════════════════════════════════════════════
# کلاس اصلی
# ══════════════════════════════════════════════════

class ChartDialog(QDialog):
    """
    دیالوگ گزارش نموداری وضعیت و اولویت صورتجلسات.

    قابلیت‌ها:
    - نمودار میله‌ای وضعیت‌ها (matplotlib با برچسب انگلیسی برای پایداری فونت)
    - جدول تفکیکی وضعیت × اولویت (فارسی)
    - خروجی HTML شکیل (قابل چاپ)
    - خروجی اکسل (openpyxl) و CSV
    - چاپ مستقیم
    """

    def __init__(
        self,
        data_counts: Dict[str, int],
        context_title: str,
        company:  str = "",
        project:  str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)

        if not HAS_MATPLOTLIB:
            raise RuntimeError(
                "کتابخانه matplotlib نصب نیست.\n"
                "دستور نصب: pip install matplotlib"
            )

        self.data_counts:   Dict[str, int] = dict(data_counts or {})
        self.context_title: str = (context_title or "").strip()
        self.company:       str = (company or "").strip()
        self.project:       str = (project or "").strip()

        self.setWindowTitle(f"{REPORT_TYPE}  —  {self.context_title}")
        self.resize(1300, 760)
        self.setMinimumSize(1024, 600)

        # کش محاسبه‌شده
        self._cached_rows:            Optional[List[_Row]]     = None
        self._cached_status_totals:   Optional[Dict[str, int]] = None
        self._cached_priority_totals: Optional[Dict[str, int]] = None
        self._cached_grand_total:     Optional[int]            = None
        self._cached_top_n:           Optional[List[_TopItem]] = None
        self._cached_top_n_size:      int                      = -1

        self._apply_style()
        self._build_ui()
        self._plot_chart()
        self._fill_table()

    # ══════════════════════════════════════════════
    # متدهای کمکی داده
    # ══════════════════════════════════════════════

    @staticmethod
    def _sanitize_filename(s: str) -> str:
        """پاک‌سازی رشته برای استفاده در نام فایل."""
        s = (s or "").strip()
        s = _INVALID_FILENAME_CHARS.sub("_", s)
        s = _WHITESPACE_PATTERN.sub("_", s).strip("_")
        return (s or "report")[:100]

    @staticmethod
    def _esc(s: Any) -> str:
        """HTML escape ایمن."""
        return html.escape(str(s) if s is not None else "")

    @staticmethod
    def _parse_key(key: str) -> Tuple[str, str]:
        """
        تبدیل کلید ترکیبی 'وضعیت | اولویت' به تاپل.
        """
        raw = (key or "").strip()
        parts = _KEY_SEP_PATTERN.split(raw, maxsplit=1)
        if len(parts) == 2:
            return parts[0].strip(), parts[1].strip()
        return raw, "نامشخص"

    @staticmethod
    def _hex_to_argb(hex_color: str, alpha: str = "22") -> str:
        """
        تبدیل رنگ hex به فرمت ARGB مورد نیاز openpyxl.
        """
        bg = hex_color.lstrip("#")
        if len(bg) == 6:
            return f"{alpha}{bg}"
        return f"FF{DEFAULT_STATUS_COLOR.lstrip('#')}"

    @staticmethod
    def _to_english_status(status_fa: str) -> str:
        """تبدیل وضعیت فارسی به معادل انگلیسی برای نمودار."""
        return STATUS_EN.get(status_fa.strip(), status_fa.strip())

    @staticmethod
    def _to_english_priority(priority_fa: str) -> str:
        """تبدیل اولویت فارسی به معادل انگلیسی برای نمودار."""
        return PRIORITY_EN.get(priority_fa.strip(), priority_fa.strip())

    def _grand_total(self) -> int:
        """مجموع کل رکوردها (کش‌شده)."""
        if self._cached_grand_total is None:
            self._cached_grand_total = sum(
                int(v or 0) for v in self.data_counts.values()
            )
        return self._cached_grand_total

    def _rows(self) -> List[_Row]:
        """لیست ردیف‌های جدول جزئیات (کش‌شده)."""
        if self._cached_rows is not None:
            return self._cached_rows

        grand = self._grand_total() or 1
        items = sorted(
            self.data_counts.items(),
            key=lambda x: int(x[1] or 0),
            reverse=True,
        )
        self._cached_rows = [
            _Row(
                status=st,
                priority=pr,
                count=int(c or 0),
                pct=(int(c or 0) / grand) * 100.0,
            )
            for key, c in items
            for st, pr in [self._parse_key(str(key))]
        ]
        return self._cached_rows

    def _status_totals(self) -> Dict[str, int]:
        """مجموع تعداد به تفکیک وضعیت (کش‌شده)."""
        if self._cached_status_totals is not None:
            return self._cached_status_totals

        totals: Dict[str, int] = {}
        for key, c in self.data_counts.items():
            st, _ = self._parse_key(str(key))
            totals[st] = totals.get(st, 0) + int(c or 0)
        self._cached_status_totals = totals
        return totals

    def _priority_totals(self) -> Dict[str, int]:
        """مجموع تعداد به تفکیک اولویت (کش‌شده)."""
        if self._cached_priority_totals is not None:
            return self._cached_priority_totals

        totals: Dict[str, int] = {}
        for key, c in self.data_counts.items():
            _, pr = self._parse_key(str(key))
            totals[pr] = totals.get(pr, 0) + int(c or 0)
        self._cached_priority_totals = totals
        return totals

    def _top_priority(self, n: int = TOP_N) -> List[_TopItem]:
        """n ردیف برتر بر اساس تعداد (کش‌شده)."""
        if self._cached_top_n is not None and self._cached_top_n_size == n:
            return self._cached_top_n

        agg: Dict[Tuple[str, str], int] = {}
        for key, c in self.data_counts.items():
            pair = self._parse_key(str(key))
            agg[pair] = agg.get(pair, 0) + int(c or 0)

        grand = sum(agg.values()) or 1
        top_n_items = sorted(agg.items(), key=lambda kv: kv[1], reverse=True)[:max(0, n)]

        result = [
            _TopItem(status=st, priority=pr, total=cnt, pct=(cnt / grand) * 100.0)
            for (st, pr), cnt in top_n_items
        ]
        self._cached_top_n = result
        self._cached_top_n_size = n
        return result

    def _brand_line(self) -> str:
        """ترکیب نام شرکت و پروژه."""
        return " — ".join(p for p in (self.company, self.project) if p)

    def _invalidate_cache(self) -> None:
        """پاک کردن تمام کش‌های محاسباتی."""
        self._cached_rows = None
        self._cached_status_totals = None
        self._cached_priority_totals = None
        self._cached_grand_total = None
        self._cached_top_n = None
        self._cached_top_n_size = -1

    def update_data(self, data_counts: Dict[str, int]) -> None:
        """به‌روزرسانی داده‌ها و رفرش UI."""
        self.data_counts = dict(data_counts or {})
        self._invalidate_cache()
        self._plot_chart()
        self._fill_table()

    # ══════════════════════════════════════════════
    # نمودار matplotlib (تمامی متون به انگلیسی)
    # ══════════════════════════════════════════════

    def _draw_on_figure(self, fig: "Figure") -> None:
        """
        ترسیم نمودار میله‌ای روی Figure داده‌شده.
        
        نکته: به‌دلیل عدم پشتیبانی پایدار matplotlib از حروف فارسی،
        تمامی برچسب‌ها و متون این نمودار به انگلیسی نمایش داده می‌شوند.
        """
        status_totals = self._status_totals()
        if status_totals:
            labels_fa = list(status_totals.keys())
            labels_en = [self._to_english_status(lbl) for lbl in labels_fa]
            values = list(status_totals.values())
        else:
            labels_fa = ["بدون داده"]
            labels_en = ["No Data"]
            values = [0]

        grand = sum(values) or 1
        # از رنگ‌های اصلی مبتنی بر نسخه فارسی وضعیت استفاده می‌شود
        colors = [STATUS_COLORS.get(lbl, DEFAULT_STATUS_COLOR) for lbl in labels_fa]

        ax = fig.add_subplot(111)
        bars = ax.bar(
            labels_en, values,
            color=colors,
            edgecolor="white",
            linewidth=1.2,
            zorder=3,
        )

        # تنظیم محور Y
        y_max = max(values) if values else 1
        ax.set_ylim(0, max(5, int(y_max * 1.25) + 1))

        # برچسب روی هر میله
        for i, val in enumerate(values):
            if val == 0:
                continue
            pct = (val / grand) * 100.0
            ax.text(
                i,
                val + max(grand * 0.008, 0.3),
                f"{val:,} ({pct:.1f}%)",
                ha="center",
                va="bottom",
                fontsize=9,
                color="#111827",
                fontweight="bold",
            )

        # عنوان بالای نمودار (برند)
        brand = self._brand_line()
        # چون ممکن است برند شامل حروف فارسی باشد، در نمودار نمایش داده نمی‌شود
        # اما بقیه اطلاعات به انگلیسی رندر می‌شوند

        ax.set_title(
            "Meetings Status Overview",
            fontsize=13,
            fontweight="bold",
            pad=12,
            color="#0f172a",
        )
        ax.set_ylabel("Count", fontsize=10, fontweight="bold")
        ax.set_xlabel("Status", fontsize=10, fontweight="bold")
        ax.grid(axis="y", alpha=0.25, zorder=0)
        ax.set_axisbelow(True)

        # چرخاندن برچسب‌های محور X در صورت طولانی بودن
        if any(len(lbl) > 8 for lbl in labels_en):
            for label in ax.get_xticklabels():
                label.set_rotation(15)
                label.set_horizontalalignment("right")

        for spine in ax.spines.values():
            spine.set_alpha(0.18)

        fig.tight_layout()

    def _plot_chart(self) -> None:
        """رسم نمودار روی canvas اصلی."""
        self.figure.clear()
        self._draw_on_figure(self.figure)
        self.canvas.draw()

    def _chart_png_base64(self) -> str:
        """رندر نمودار به PNG و برگرداندن رشته base64."""
        import matplotlib.pyplot as plt

        fig = Figure(figsize=(7.0, 4.0), dpi=130)
        fig.patch.set_facecolor("white")
        try:
            self._draw_on_figure(fig)
            buf = io.BytesIO()
            fig.savefig(
                buf,
                format="png",
                dpi=200,
                bbox_inches="tight",
                facecolor="white",
            )
            return base64.b64encode(buf.getvalue()).decode("ascii")
        finally:
            plt.close(fig)

    # ══════════════════════════════════════════════
    # ساخت رابط کاربری
    # ══════════════════════════════════════════════

    def _apply_style(self) -> None:
        """اعمال استایل CSS به دیالوگ."""
        self.setStyleSheet("""
            QDialog { background:#f0f2f5; }

            QPushButton {
                background:#ffffff; border:1px solid #c0c0d0;
                border-radius:6px; padding:6px 16px;
                font-weight:600; font-size:12px; color:#1e293b;
            }
            QPushButton:hover   { background:#e9ecf2; }
            QPushButton:pressed { background:#d0d4dc; }

            QPushButton#btn_close {
                background:#00BFFF; color:white; border:none;
                padding:8px 28px; font-weight:bold; font-size:13px;
            }
            QPushButton#btn_close:hover { background:#0099CC; }

            QFrame#content_frame {
                background:#ffffff;
                border:1px solid #d6d6d6;
                border-radius:10px;
            }

            QTableWidget {
                font-size:13px;
                gridline-color:#e2e8f0;
                alternate-background-color:#f8fafc;
            }
            QTableWidget::item          { padding:8px; }
            QTableWidget::item:selected { background:#00BFFF; color:white; }

            QHeaderView::section {
                background:#f8fafc; padding:8px;
                border:none; border-bottom:2px solid #e2e8f0;
                font-weight:bold; color:#334155; font-size:12px;
            }
        """)

    def _build_ui(self) -> None:
        """ساخت کامل رابط کاربری."""
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        # ── هدر برند ──
        brand = self._brand_line()
        if brand:
            lbl = QLabel(brand)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(
                "font-size:15px; font-weight:bold; color:#1e293b; padding:4px;"
            )
            root.addWidget(lbl)

        # ── نوار ابزار ──
        root.addLayout(self._build_toolbar())

        # ── محتوای اصلی ──
        self.content_frame = QFrame()
        self.content_frame.setObjectName("content_frame")
        frame_layout = QVBoxLayout(self.content_frame)
        frame_layout.setContentsMargins(10, 10, 10, 10)
        frame_layout.setSpacing(0)
        frame_layout.addWidget(self._build_splitter())
        root.addWidget(self.content_frame, stretch=1)

        # ── دکمه بستن ──
        close_row = QHBoxLayout()
        close_row.addStretch()
        self.btn_close = QPushButton("✕  بستن")
        self.btn_close.setObjectName("btn_close")
        self.btn_close.setMinimumSize(110, 36)
        self.btn_close.clicked.connect(self.accept)
        close_row.addWidget(self.btn_close)
        root.addLayout(close_row)

    def _build_toolbar(self) -> QHBoxLayout:
        """ساخت نوار ابزار دکمه‌های خروجی."""
        bar = QHBoxLayout()
        bar.setSpacing(8)

        self.btn_save_html    = QPushButton("💾 ذخیره HTML")
        self.btn_export_excel = QPushButton("📊 خروجی اکسل")
        self.btn_export_csv   = QPushButton("📄 خروجی CSV")
        self.btn_print        = QPushButton("🖨️ چاپ")

        self.btn_save_html.setToolTip("ذخیره گزارش کامل به فرمت HTML")
        self.btn_export_excel.setToolTip("خروجی جدول به فرمت Excel")
        self.btn_export_csv.setToolTip("خروجی جدول به فرمت CSV")
        self.btn_print.setToolTip("چاپ گزارش (A4 افقی)")

        # غیرفعال‌سازی دکمه اکسل در صورت نبود openpyxl
        if not HAS_OPENPYXL:
            self.btn_export_excel.setEnabled(False)
            self.btn_export_excel.setToolTip(
                "کتابخانه openpyxl نصب نیست.\nدستور نصب: pip install openpyxl"
            )

        for btn in (
            self.btn_save_html,
            self.btn_export_excel,
            self.btn_export_csv,
            self.btn_print,
        ):
            bar.addWidget(btn)

        bar.addStretch()

        # اتصال سیگنال‌ها
        self.btn_save_html.clicked.connect(self.save_report_html)
        self.btn_export_excel.clicked.connect(self.export_excel)
        self.btn_export_csv.clicked.connect(self.export_data_csv)
        self.btn_print.clicked.connect(self.print_report)

        return bar

    def _build_splitter(self) -> QSplitter:
        """ساخت splitter حاوی نمودار و جدول."""
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ── نمودار ──
        chart_widget = QWidget()
        chart_layout = QVBoxLayout(chart_widget)
        chart_layout.setContentsMargins(0, 0, 0, 0)

        self.figure = Figure(figsize=(6, 4), dpi=110)
        self.figure.patch.set_facecolor("white")
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setMinimumHeight(280)
        chart_layout.addWidget(self.canvas)

        # ── جدول ──
        self.table_widget = self._build_table_widget()

        splitter.addWidget(chart_widget)
        splitter.addWidget(self.table_widget)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([420, 600])

        return splitter

    def _build_table_widget(self) -> QTableWidget:
        """ساخت و پیکربندی QTableWidget."""
        table = QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["وضعیت", "اولویت", "تعداد", "درصد"])
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.verticalHeader().setVisible(False)

        hdr = table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)

        return table

    def _fill_table(self) -> None:
        """پر کردن جدول با داده‌های وضعیت × اولویت."""
        rows = self._rows()
        self.table_widget.clearContents()
        self.table_widget.clearSpans()

        if not rows:
            self.table_widget.setRowCount(1)
            msg = QTableWidgetItem("هیچ داده‌ای برای نمایش وجود ندارد")
            msg.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            msg.setForeground(QColor("#94a3b8"))
            self.table_widget.setItem(0, 0, msg)
            self.table_widget.setSpan(0, 0, 1, 4)
            return

        # ردیف‌های داده
        self.table_widget.setRowCount(len(rows) + 1)  # +1 برای مجموع

        for r, row in enumerate(rows):
            self._set_table_row(r, row.status, row.priority, row.count, row.pct)

        # ردیف مجموع
        total_count = sum(r.count for r in rows)
        sum_row = len(rows)

        items = {
            0: self._make_item("مجموع",         bold=True),
            1: self._make_item("",              bold=False),
            2: self._make_item(str(total_count), bold=True, align=Qt.AlignmentFlag.AlignCenter),
            3: self._make_item("۱۰۰٪",         bold=True, align=Qt.AlignmentFlag.AlignCenter),
        }
        for col, item in items.items():
            self.table_widget.setItem(sum_row, col, item)

        # ادغام دو ستون اول ردیف مجموع
        self.table_widget.setSpan(sum_row, 0, 1, 2)

        # رنگ پس‌زمینه ردیف مجموع
        for col in range(4):
            item = self.table_widget.item(sum_row, col)
            if item:
                item.setBackground(QColor("#f0f9ff"))

    def _set_table_row(
        self,
        row: int,
        status: str,
        priority: str,
        count: int,
        pct: float,
    ) -> None:
        """تنظیم یک ردیف جدول."""
        self.table_widget.setItem(row, 0, self._make_item(status))
        self.table_widget.setItem(row, 1, self._make_item(priority))
        self.table_widget.setItem(
            row, 2,
            self._make_item(str(count), align=Qt.AlignmentFlag.AlignCenter)
        )
        self.table_widget.setItem(
            row, 3,
            self._make_item(f"{pct:.1f}٪", align=Qt.AlignmentFlag.AlignCenter)
        )

        # رنگ‌بندی بر اساس وضعیت
        color_hex = STATUS_COLORS.get(status)
        if color_hex:
            bg = QColor(color_hex)
            bg.setAlphaF(0.12)
            for col in range(4):
                item = self.table_widget.item(row, col)
                if item:
                    item.setBackground(bg)

    @staticmethod
    def _make_item(
        text: str,
        bold: bool = False,
        align: Optional[Qt.AlignmentFlag] = None,
    ) -> QTableWidgetItem:
        """ساخت QTableWidgetItem با تنظیمات."""
        item = QTableWidgetItem(text)
        if bold:
            f = item.font()
            f.setBold(True)
            item.setFont(f)
        if align is not None:
            item.setTextAlignment(align)
        return item

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.accept()
        else:
            super().keyPressEvent(event)

    # ══════════════════════════════════════════════
    # تولید HTML گزارش
    # ══════════════════════════════════════════════

    def _generate_report_html(
        self,
        print_mode: bool = False,
        include_chart: bool = True,
    ) -> str:
        """تولید HTML گزارش کامل."""
        theme = _ReportTheme.print_mode() if print_mode else _ReportTheme.screen()
        ts_str = datetime.now().strftime("%Y-%m-%d  %H:%M:%S")

        return "\n".join([
            "<!doctype html>",
            '<html dir="rtl">',
            self._html_head(theme, ts_str),
            "<body>",
            self._html_body(theme, ts_str, include_chart),
            "</body>",
            "</html>",
        ])

    def _html_head(self, theme: _ReportTheme, ts: str) -> str:
        """تولید بخش <head> HTML."""
        title = self._esc(self.context_title)
        css = self._build_css(theme)
        return f"""<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{self._esc(REPORT_TYPE)} — {title}</title>
  <style>{css}</style>
</head>"""

    def _html_body(
        self,
        theme: _ReportTheme,
        ts: str,
        include_chart: bool,
    ) -> str:
        """تولید بخش <body> HTML."""
        brand     = self._esc(self._brand_line())
        title     = self._esc(self.context_title)
        subject   = self._esc(REPORT_SUBJECT)
        rtype     = self._esc(REPORT_TYPE)
        app_name  = self._esc(APP_NAME_FA)

        brand_block = f'<div class="hdr-brand">{brand}</div>' if brand else ""

        # ── کارت‌های وضعیت ──
        cards_html = self._build_cards_html()

        # ── پانل نمودار ──
        chart_panel = ""
        if include_chart:
            try:
                chart_b64 = self._chart_png_base64()
                chart_panel = f"""
<div class="panel">
  <div class="panel-title"><strong>نمودار</strong><span>خلاصه وضعیت‌ها</span></div>
  <div class="chart">
    <img alt="نمودار وضعیت" src="data:image/png;base64,{chart_b64}" />
  </div>
</div>"""
            except Exception as exc:
                logger.warning("Chart rendering for HTML failed: %s", exc)
                chart_panel = ""

        # ── جداول ──
        top_items = self._top_priority(TOP_N)
        top_rows_html    = self._build_top_rows_html(top_items)
        detail_rows_html = self._build_detail_rows_html()

        grid_cols = "1fr 1fr" if (include_chart and chart_panel) else "1fr"

        # تعداد واقعی Top
        actual_top = len(top_items)
        top_label = f"{actual_top} مورد" if actual_top > 0 else "بدون داده"

        footer_html = (
            f'<span><a href="{APP_SEARCH_URL}" style="color:inherit;">'
            f"<strong>{app_name}</strong></a> — سامانه Document & MOM Tracking System</span>"
            f"<span>تولید شده: {ts}</span>"
        )

        return f"""<div class="wrap">
  <div class="page">
    <div class="header">
      <div class="hdr-row">
        <div class="hdr-left">
          <div class="mark">م.ص</div>
          <div class="hdr-pills">
            <div class="pill">{subject}</div>
            <div class="pill">{rtype}</div>
          </div>
        </div>
      </div>
      {brand_block}
      <div class="hdr-title">{title}</div>
      <div class="hdr-meta">تولید شده: {ts}</div>
    </div>

    <div class="body">
      <div class="cards">{cards_html}</div>

      <div class="grid" style="grid-template-columns:{grid_cols};">
        {chart_panel}
        <div class="panel">
          <div class="panel-title">
            <strong>اولویت‌های برتر</strong>
            <span>{top_label}</span>
          </div>
          <div class="tablewrap" style="max-height:50vh;">
            <table>
              <thead>
                <tr>
                  <th style="width:50px;">#</th>
                  <th style="width:32%;">وضعیت</th>
                  <th>اولویت</th>
                  <th style="width:110px;">تعداد</th>
                  <th style="width:90px;">درصد</th>
                </tr>
              </thead>
              <tbody>{top_rows_html}</tbody>
            </table>
          </div>
        </div>
      </div>

      <div class="panel" style="margin-top:12px;">
        <div class="panel-title">
          <strong>جزئیات کامل</strong>
          <span>وضعیت / اولویت / تعداد / درصد</span>
        </div>
        <div class="tablewrap">
          <table>
            <thead>
              <tr>
                <th class="col-st">وضعیت</th>
                <th class="col-pr">اولویت</th>
                <th class="col-cnt">تعداد</th>
                <th class="col-pct">درصد</th>
              </tr>
            </thead>
            <tbody>{detail_rows_html}</tbody>
          </table>
        </div>
      </div>
    </div>

    <div class="footer">{footer_html}</div>
  </div>
</div>"""

    def _build_cards_html(self) -> str:
        """ساخت HTML کارت‌های وضعیت."""
        status_totals = self._status_totals()
        grand = sum(status_totals.values()) or 1
        cards: List[str] = []

        ordered = list(CARD_ORDER)
        extras = sorted(set(status_totals.keys()) - set(CARD_ORDER))

        for k in ordered + extras:
            v = int(status_totals.get(k, 0))
            pct = (v / grand) * 100.0
            color = STATUS_COLORS.get(k, "#64748b")
            cards.append(f"""
<div class="card" style="border-top:3px solid {color};">
  <div class="card-title">{self._esc(k)}</div>
  <div class="card-value" style="color:{color};">{v:,}</div>
  <div class="card-sub">{pct:.1f}٪</div>
</div>""")

        return "\n".join(cards)

    def _build_top_rows_html(self, items: List[_TopItem]) -> str:
        """ساخت HTML ردیف‌های جدول اولویت‌های برتر."""
        if not items:
            return '<tr><td colspan="5" style="text-align:center;color:#94a3b8;">بدون داده</td></tr>'

        rows: List[str] = []
        for i, t in enumerate(items, start=1):
            rows.append(f"""<tr>
  <td class="num">{i}</td>
  <td>{self._esc(t.status)}</td>
  <td>{self._esc(t.priority)}</td>
  <td class="num">{t.total:,}</td>
  <td class="num">{t.pct:.1f}٪</td>
</tr>""")
        return "\n".join(rows)

    def _build_detail_rows_html(self) -> str:
        """ساخت HTML ردیف‌های جدول جزئیات."""
        rows = self._rows()
        if not rows:
            return '<tr><td colspan="4" style="text-align:center;color:#94a3b8;">بدون داده</td></tr>'

        html_rows: List[str] = []
        for r in rows:
            html_rows.append(
                f"<tr>"
                f"<td class='col-st'>{self._esc(r.status)}</td>"
                f"<td class='col-pr'>{self._esc(r.priority)}</td>"
                f"<td class='num col-cnt'>{r.count:,}</td>"
                f"<td class='num col-pct'>{r.pct:.1f}٪</td>"
                f"</tr>"
            )

        total = sum(r.count for r in rows)
        html_rows.append(
            "<tr style='font-weight:bold;background:#f0f9ff;'>"
            "<td class='col-st'>مجموع</td>"
            "<td class='col-pr'></td>"
            f"<td class='num col-cnt'>{total:,}</td>"
            "<td class='num col-pct'>۱۰۰٪</td>"
            "</tr>"
        )
        return "\n".join(html_rows)

    def _build_css(self, theme: _ReportTheme) -> str:
        """تولید CSS گزارش بر اساس theme."""
        return f"""
    @page {{ size:A4 landscape; margin:9mm 9mm 18mm 9mm; }}
    :root {{ --text:#111827; --muted:#4b5563; --border:#d1d5db; }}

    html {{ font-size:{theme.font_size_px}; -webkit-text-size-adjust:100%; }}
    body {{
      margin:0; padding:0;
      font-family:'{DEFAULT_FONT_FAMILY}','Segoe UI',Tahoma,Arial,sans-serif;
      color:var(--text);
      {theme.body_bg}
    }}

    .wrap {{ padding:{theme.body_padding}; box-sizing:border-box; }}
    .page {{ background:#fff; {theme.page_shadow} overflow:hidden; }}

    /* ── هدر ── */
    .header {{ padding:{theme.header_pad}; {theme.header_bg} }}
    .hdr-row {{
      display:flex; align-items:center;
      justify-content:space-between; gap:12px; flex-wrap:wrap;
    }}
    .hdr-left  {{ display:flex; align-items:center; gap:10px; min-width:240px; }}
    .mark {{
      width:32px; height:32px; border-radius:8px; flex-shrink:0;
      background:linear-gradient(135deg,rgba(0,191,255,.95),rgba(16,185,129,.95));
      display:flex; align-items:center; justify-content:center;
      color:#fff; font-weight:900; font-size:10px;
    }}
    .hdr-pills {{ display:flex; gap:8px; flex-wrap:wrap; align-items:center; }}
    .pill {{
      display:inline-block; padding:5px 10px; border-radius:999px;
      font-weight:850; font-size:12px;
      border:{theme.pill_border}; background:{theme.pill_bg};
      color:{theme.pill_color}; white-space:nowrap;
    }}
    .hdr-brand {{
      margin-top:8px; font-size:14px; font-weight:bold;
      color:{theme.brand_color};
    }}
    .hdr-title {{
      margin-top:10px; font-size:22px; font-weight:900;
      color:{theme.pill_color};
    }}
    .hdr-meta {{ margin-top:6px; font-size:13px; color:{theme.meta_color}; }}

    /* ── کارت‌ها ── */
    .body {{ padding:14px 16px 12px 16px; }}
    .cards {{
      display:grid;
      grid-template-columns:repeat(auto-fit,minmax(140px,1fr));
      gap:10px; margin-bottom:12px;
    }}
    .card {{
      border:1px solid var(--border); border-radius:12px;
      padding:12px; background:#fff;
    }}
    .card-title {{ font-size:14px; color:var(--muted); font-weight:650; }}
    .card-value {{ margin-top:8px; font-size:32px; font-weight:900; font-variant-numeric:tabular-nums; }}
    .card-sub   {{ margin-top:4px; font-size:14px; color:var(--muted); }}

    /* ── گرید و پانل ── */
    .grid {{ display:grid; gap:12px; align-items:start; margin-top:4px; }}
    .panel {{ border:1px solid var(--border); border-radius:12px; background:#fff; overflow:hidden; }}
    .panel-title {{
      padding:10px 14px; background:#f8fafc; border-bottom:1px solid var(--border);
      font-size:14px; color:var(--muted);
      display:flex; justify-content:space-between; gap:8px; flex-wrap:wrap;
    }}
    .panel-title strong {{ color:#111827; font-weight:850; }}

    /* ── نمودار ── */
    .chart {{ padding:10px; text-align:center; }}
    .chart img {{
      max-width:90%; max-height:230px;
      border-radius:10px; border:1px solid var(--border);
    }}

    /* ── جدول ── */
    .tablewrap {{ overflow:auto; }}
    table {{ width:100%; border-collapse:collapse; table-layout:fixed; font-size:14px; }}
    thead th {{
      position:sticky; top:0; z-index:2; background:#f3f4f6;
      color:#111827; text-align:right;
      padding:10px 12px; border-bottom:1px solid var(--border);
      white-space:nowrap;
    }}
    tbody td {{
      padding:10px 12px; border-bottom:1px solid var(--border);
      vertical-align:top; word-break:break-word;
    }}
    td.num {{ text-align:center; white-space:nowrap; font-variant-numeric:tabular-nums; }}
    .col-st  {{ width:24%; }}
    .col-pr  {{ width:38%; }}
    .col-cnt {{ width:19%; }}
    .col-pct {{ width:19%; }}

    /* ── فوتر ── */
    .footer {{
      padding:10px 16px 12px 16px; border-top:1px solid var(--border);
      color:var(--muted); font-size:13px;
      display:flex; justify-content:space-between; gap:10px; flex-wrap:wrap;
      background:#fff;
    }}
    .footer a {{ color:inherit; text-decoration:underline; }}

    /* ── چاپ ── */
    @media print {{
      body {{ background:#fff; }}
      .wrap {{ padding:0; }}
      .page {{ box-shadow:none; border:none; border-radius:0; }}
      .tablewrap {{ max-height:none !important; overflow:visible; }}
      .grid {{ grid-template-columns:1fr !important; }}
      thead {{ display:table-header-group; }}
      .footer {{
        position:fixed; left:9mm; right:9mm; bottom:8mm;
        border-top:1px solid #ddd; background:#fff;
      }}
    }}
"""

    # ══════════════════════════════════════════════
    # خروجی‌ها
    # ══════════════════════════════════════════════

    def save_report_html(self) -> None:
        """ذخیره گزارش HTML و پیشنهاد باز کردن در مرورگر."""
        base = self._sanitize_filename(self.context_title)
        path, _ = QFileDialog.getSaveFileName(
            self, "ذخیره گزارش HTML",
            f"{base}.html",
            "HTML Files (*.html)"
        )
        if not path:
            return
        if not path.lower().endswith(".html"):
            path += ".html"

        try:
            content = self._generate_report_html(print_mode=False, include_chart=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(content)
            logger.info("HTML report saved to %s", path)
        except OSError as exc:
            logger.exception("Failed to save HTML report.")
            QMessageBox.critical(self, "خطا در ذخیره", str(exc))
            return
        except Exception as exc:
            logger.exception("Unexpected error while generating HTML report.")
            QMessageBox.critical(self, "خطا", f"خطای غیرمنتظره:\n{exc}")
            return

        msg = QMessageBox(self)
        msg.setWindowTitle("✅ ذخیره شد")
        msg.setText(f"گزارش در مسیر زیر ذخیره شد:\n{path}")
        btn_open = msg.addButton("🌐 باز کردن در مرورگر", QMessageBox.ButtonRole.AcceptRole)
        msg.addButton(QMessageBox.StandardButton.Ok)
        msg.exec()
        if msg.clickedButton() == btn_open:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def export_excel(self) -> None:
        """خروجی جدول به فرمت Excel با openpyxl."""
        if not HAS_OPENPYXL:
            QMessageBox.critical(
                self, "خطا",
                "کتابخانه openpyxl نصب نیست.\n"
                "دستور نصب: pip install openpyxl"
            )
            return

        if not self._rows():
            QMessageBox.information(self, "اطلاع", "داده‌ای برای خروجی وجود ندارد.")
            return

        base = self._sanitize_filename(f"status_priority_{self.context_title}")
        path, _ = QFileDialog.getSaveFileName(
            self, "خروجی اکسل",
            f"{base}.xlsx",
            "Excel Files (*.xlsx)"
        )
        if not path:
            return
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"

        try:
            self._write_excel(path)
            QMessageBox.information(self, "✅ انجام شد", f"خروجی اکسل ذخیره شد:\n{path}")
            logger.info("Excel exported to %s", path)
        except (OSError, ValueError, KeyError) as exc:
            logger.exception("Excel export failed.")
            QMessageBox.critical(self, "خطا در خروجی اکسل", str(exc))
        except Exception as exc:
            logger.exception("Unexpected error in Excel export.")
            QMessageBox.critical(self, "خطا", f"خطای غیرمنتظره:\n{exc}")

    def _write_excel(self, path: str) -> None:
        """نوشتن فایل اکسل."""
        wb = Workbook()
        ws = wb.active
        ws.title = "وضعیت و اولویت"
        ws.sheet_view.rightToLeft = True

        # ── هدر ──
        hdr_fill  = PatternFill("solid", fgColor="1E293B")
        hdr_font  = Font(bold=True, color="FFFFFF", size=11)
        hdr_align = Alignment(horizontal="center", vertical="center")

        col_names = ["وضعیت", "اولویت", "تعداد", "درصد (%)"]
        for ci, name in enumerate(col_names, start=1):
            cell = ws.cell(row=1, column=ci, value=name)
            cell.font      = hdr_font
            cell.fill      = hdr_fill
            cell.alignment = hdr_align

        ws.row_dimensions[1].height = 22

        # ── داده‌ها ──
        rows = self._rows()
        for ri, row in enumerate(rows, start=2):
            ws.cell(row=ri, column=1, value=row.status).alignment   = Alignment(horizontal="right")
            ws.cell(row=ri, column=2, value=row.priority).alignment = Alignment(horizontal="right")

            count_cell = ws.cell(row=ri, column=3, value=row.count)
            count_cell.alignment = Alignment(horizontal="center")

            pct_cell = ws.cell(row=ri, column=4, value=row.pct / 100.0)
            pct_cell.number_format = "0.0%"
            pct_cell.alignment     = Alignment(horizontal="center")

            color_hex = STATUS_COLORS.get(row.status)
            if color_hex:
                argb = self._hex_to_argb(color_hex, alpha="22")
                row_fill = PatternFill("solid", fgColor=argb)
                for ci in range(1, 5):
                    ws.cell(row=ri, column=ci).fill = row_fill

        # ── ردیف مجموع ──
        total_count = sum(r.count for r in rows)
        if total_count > 0:
            sum_row  = len(rows) + 2
            sum_font = Font(bold=True, size=11)
            sum_fill = PatternFill("solid", fgColor="FFEFF6FF")

            ws.cell(row=sum_row, column=1, value="مجموع").font = sum_font
            ws.cell(row=sum_row, column=3, value=total_count).font = sum_font

            pct_total = ws.cell(row=sum_row, column=4, value=1.0)
            pct_total.number_format = "0.0%"
            pct_total.font          = sum_font

            for ci in range(1, 5):
                c = ws.cell(row=sum_row, column=ci)
                c.fill      = sum_fill
                c.alignment = Alignment(horizontal="center")

            ws.cell(row=sum_row, column=1).alignment = Alignment(horizontal="right")

        # ── عرض ستون‌ها ──
        col_widths = [4] * len(col_names)
        for ri in range(1, ws.max_row + 1):
            for ci in range(1, len(col_names) + 1):
                val = ws.cell(row=ri, column=ci).value
                if val is not None:
                    col_widths[ci - 1] = max(col_widths[ci - 1], len(str(val)))

        for ci, w in enumerate(col_widths, start=1):
            ws.column_dimensions[get_column_letter(ci)].width = min(w + 5, 48)

        wb.save(path)

    def export_data_csv(self) -> None:
        """خروجی جدول به فرمت CSV."""
        if not self._rows():
            QMessageBox.information(self, "اطلاع", "داده‌ای برای خروجی وجود ندارد.")
            return

        base = self._sanitize_filename(f"status_priority_{self.context_title}")
        path, _ = QFileDialog.getSaveFileName(
            self, "خروجی CSV",
            f"{base}.csv",
            "CSV Files (*.csv)"
        )
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"

        try:
            rows = self._rows()
            with open(path, "w", newline="", encoding="utf-8-sig") as fh:
                writer = csv.writer(fh)
                writer.writerow(["عنوان گزارش", self.context_title])
                writer.writerow(["تاریخ تولید", datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
                writer.writerow([])
                writer.writerow(["وضعیت", "اولویت", "تعداد", "درصد"])
                for r in rows:
                    writer.writerow([r.status, r.priority, r.count, f"{r.pct:.1f}%"])
                total = sum(r.count for r in rows)
                if total:
                    writer.writerow(["مجموع", "", total, "100%"])

            QMessageBox.information(self, "✅ انجام شد", f"خروجی CSV ذخیره شد:\n{path}")
            logger.info("CSV exported to %s", path)
        except OSError as exc:
            logger.exception("CSV export failed.")
            QMessageBox.critical(self, "خطا در خروجی CSV", str(exc))
        except Exception as exc:
            logger.exception("Unexpected error in CSV export.")
            QMessageBox.critical(self, "خطا", f"خطای غیرمنتظره:\n{exc}")

    def print_report(self, include_chart: bool = False) -> None:
        """چاپ گزارش HTML روی پرینتر (A4 افقی)."""
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)

        try:
            from PyQt6.QtGui import QPageLayout, QPageSize
            page_layout = QPageLayout(
                QPageSize(QPageSize.PageSizeId.A4),
                QPageLayout.Orientation.Landscape,
                QMarginsF(9.0, 9.0, 18.0, 9.0),
                QPageLayout.Unit.Millimeter,
            )
            printer.setPageLayout(page_layout)
        except Exception as exc:
            logger.warning("Could not set page layout: %s", exc)

        dialog = QPrintDialog(printer, self)
        dialog.setWindowTitle("چاپ گزارش")
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            html_str = self._generate_report_html(
                print_mode=True,
                include_chart=include_chart,
            )
            from PyQt6.QtGui import QTextDocument
            doc = QTextDocument()
            doc.setDefaultFont(QFont(DEFAULT_FONT_FAMILY, 11))
            doc.setHtml(html_str)

            try:
                rect = printer.pageRect(QPrinter.Unit.Point)
                doc.setPageSize(QSizeF(rect.size()))
            except Exception as exc:
                logger.debug("Could not set page size on document: %s", exc)

            doc.print(printer)
            logger.info("Report printed successfully.")
        except Exception as exc:
            logger.exception("Print failed.")
            QMessageBox.critical(self, "خطا در چاپ", str(exc))