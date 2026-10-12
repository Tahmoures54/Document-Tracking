# -*- coding: utf-8 -*-
"""
ماژول گزارش نموداری وضعیت صورتجلسات
ChartDialog — نمایش نمودار، جدول آماری و خروجی HTML/Excel/CSV

نسخه بهبودیافته ۲:
- رفع بهم‌ریختگی حروف فارسی در نمودار: تمامی برچسب‌ها به انگلیسی (پایدار)
- سایر بخش‌ها (کارت‌ها، جداول، خروجی‌ها) کاملاً فارسی
- کش هوشمند برای بهینه‌سازی سرعت
- Exception handling دقیق‌تر
- حذف متن تکراری، پارامتری‌سازی عنوان، تاریخ شمسی در گزارش
- تبدیل صحیح رنگ hex به RGB روشن برای Excel (بدون alpha نادیده‌گرفته‌شده)
- یکسان‌سازی واحد درصد در همه خروجی‌ها
- هماهنگ‌سازی رفتار چاپ و HTML (نمودار پیش‌فرض شامل)
- جداسازی CSS به ثابت ماژول برای نگهداری بهتر
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

from PyQt6.QtCore import Qt, QMarginsF, QSizeF, QUrl
from PyQt6.QtGui import QColor, QDesktopServices, QFont, QKeyEvent
from PyQt6.QtPrintSupport import QPrinter, QPrintDialog
from PyQt6.QtWidgets import (
    QDialog, QFileDialog, QFrame, QHBoxLayout,
    QHeaderView, QLabel, QMessageBox, QPushButton,
    QSplitter, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from utils.date_utils import today_shamsi, to_shamsi

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

DEFAULT_REPORT_SUBJECT = "گزارش وضعیت صورتجلسات"
DEFAULT_REPORT_TYPE    = "وضعیت و اولویت"
DEFAULT_CHART_TITLE    = "Meetings Status Overview"
APP_NAME_FA            = "Document & MOM Tracking System"

# رنگ‌بندی وضعیت‌ها
STATUS_COLORS: Dict[str, str] = {
    "در دست بررسی":     "#f59e0b",
    "در انتظار تأیید":   "#3b82f6",
    "تکمیل شده":         "#22c55e",
    "لغو شده":           "#ef4444",
    "بازگشت داده شده":   "#fb923c",
}

DEFAULT_STATUS_COLOR = "#94a3b8"

# نگاشت وضعیت/اولویت به انگلیسی — فقط برای نمودار matplotlib
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

# ترتیب نمایش کارت‌ها (وضعیت‌های خارج از این لیست خودکار در انتها می‌آیند)
CARD_ORDER = ["در دست بررسی", "در انتظار تأیید", "تکمیل شده", "لغو شده", "بازگشت داده شده"]

# حداکثر ردیف در جدول اولویت‌های برتر
TOP_N = 15

# فونت پیش‌فرض گزارش
DEFAULT_FONT_FAMILY = "Vazirmatn"

# واحد درصد یکسان در همه خروجی‌ها (نسخه فارسی)
PERCENT_SUFFIX = "٪"

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
# توابع کمکی ماژول
# ══════════════════════════════════════════════════

def _safe_int(value: Any, default: int = 0) -> int:
    """تبدیل امن هر مقدار به int."""
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _lighten_hex(hex_color: str, factor: float = 0.85) -> str:
    """
    روشن‌سازی یک رنگ hex (بدون آلفا) برای استفاده در Excel.
    `factor=0.85` یعنی نتیجه ۸۵٪ به سفید نزدیک‌تر است.
    مثال: '#f59e0b' → 'FBE7B8'
    """
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return DEFAULT_STATUS_COLOR.lstrip("#").upper()
    try:
        r = int(h[0:2], 16)
        g = int(h[2:4], 16)
        b = int(h[4:6], 16)
    except ValueError:
        return DEFAULT_STATUS_COLOR.lstrip("#").upper()
    factor = max(0.0, min(1.0, factor))
    r = int(r + (255 - r) * factor)
    g = int(g + (255 - g) * factor)
    b = int(b + (255 - b) * factor)
    return f"{r:02X}{g:02X}{b:02X}"


def _format_shamsi_timestamp() -> str:
    """تولید مهر زمانی به شمسی برای استفاده در گزارش."""
    try:
        shamsi_date = today_shamsi() or ""
    except Exception:
        shamsi_date = ""
    time_str = datetime.now().strftime("%H:%M:%S")
    return f"{shamsi_date}  {time_str}".strip()


def _sanitize_filename(s: str) -> str:
    """پاک‌سازی رشته برای استفاده در نام فایل."""
    s = (s or "").strip()
    s = _INVALID_FILENAME_CHARS.sub("_", s)
    s = _WHITESPACE_PATTERN.sub("_", s).strip("_")
    return (s or "report")[:100]


def _parse_key(key: str) -> Tuple[str, str]:
    """تبدیل کلید ترکیبی 'وضعیت | اولویت' به تاپل."""
    raw = (key or "").strip()
    parts = _KEY_SEP_PATTERN.split(raw, maxsplit=1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return raw, "نامشخص"


def _esc(s: Any) -> str:
    """HTML escape ایمن."""
    return html.escape(str(s) if s is not None else "")


# ══════════════════════════════════════════════════
# CSS گزارش HTML — به‌صورت یک ثابت ماژول
# ══════════════════════════════════════════════════

_REPORT_CSS_TEMPLATE = """
    @page {{ size:A4 landscape; margin:9mm 9mm 18mm 9mm; }}
    :root {{ --text:#111827; --muted:#4b5563; --border:#d1d5db; }}

    html {{ font-size:{font_size_px}; -webkit-text-size-adjust:100%; }}
    body {{
      margin:0; padding:0;
      font-family:'{font_family}','Segoe UI',Tahoma,Arial,sans-serif;
      color:var(--text);
      {body_bg}
    }}

    .wrap {{ padding:{body_padding}; box-sizing:border-box; }}
    .page {{ background:#fff; {page_shadow} overflow:hidden; }}

    /* ── هدر ── */
    .header {{ padding:{header_pad}; {header_bg} }}
    .hdr-row {{
      display:flex; align-items:center;
      justify-content:space-between; gap:12px; flex-wrap:wrap;
    }}
    .hdr-left  {{ display:flex; align-items:center; gap:10px; min-width:240px; }}
    .mark {{
      width:36px; height:36px; border-radius:9px; flex-shrink:0;
      background:linear-gradient(135deg,rgba(0,191,255,.95),rgba(16,185,129,.95));
      display:flex; align-items:center; justify-content:center;
      color:#fff; font-weight:900; font-size:12px;
    }}
    .hdr-pills {{ display:flex; gap:8px; flex-wrap:wrap; align-items:center; }}
    .pill {{
      display:inline-block; padding:5px 10px; border-radius:999px;
      font-weight:850; font-size:12px;
      border:{pill_border}; background:{pill_bg};
      color:{pill_color}; white-space:nowrap;
    }}
    .hdr-brand {{
      margin-top:8px; font-size:14px; font-weight:bold;
      color:{brand_color};
    }}
    .hdr-title {{
      margin-top:10px; font-size:22px; font-weight:900;
      color:{pill_color};
    }}
    .hdr-meta {{ margin-top:6px; font-size:13px; color:{meta_color}; }}

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


# ══════════════════════════════════════════════════
# کلاس اصلی
# ══════════════════════════════════════════════════

class ChartDialog(QDialog):
    """
    دیالوگ گزارش نموداری وضعیت و اولویت صورتجلسات.

    قابلیت‌ها:
    - نمودار میله‌ای وضعیت‌ها (matplotlib با برچسب انگلیسی)
    - جدول تفکیکی وضعیت × اولویت (فارسی)
    - خروجی HTML شکیل (قابل چاپ)
    - خروجی Excel (openpyxl) و CSV
    - چاپ مستقیم روی A4 افقی

    پارامترها:
        data_counts: دیکشنری {'وضعیت | اولویت': تعداد}
        context_title: عنوان کانتکست گزارش (مثلاً فیلتر فعلی)
        company: نام شرکت (اختیاری)
        project: نام پروژه (اختیاری)
        report_subject: عنوان موضوع گزارش (پیش‌فرض: 'گزارش وضعیت صورتجلسات')
        chart_title: عنوان بالای نمودار matplotlib (پیش‌فرض انگلیسی)
        parent: ویجت والد
    """

    def __init__(
        self,
        data_counts: Dict[str, int],
        context_title: str,
        company: str = "",
        project: str = "",
        report_subject: str = DEFAULT_REPORT_SUBJECT,
        chart_title: str = DEFAULT_CHART_TITLE,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)

        if not HAS_MATPLOTLIB:
            raise RuntimeError(
                "کتابخانه matplotlib نصب نیست.\n"
                "دستور نصب: pip install matplotlib"
            )

        # پاک‌سازی و نرمال‌سازی ورودی
        self.data_counts: Dict[str, int] = {
            str(k): _safe_int(v, 0)
            for k, v in (data_counts or {}).items()
        }
        self.context_title: str = (context_title or "").strip()
        self.company: str = (company or "").strip()
        self.project: str = (project or "").strip()
        self.report_subject: str = (report_subject or DEFAULT_REPORT_SUBJECT).strip()
        self.chart_title: str = (chart_title or DEFAULT_CHART_TITLE).strip()

        self.setWindowTitle(f"{DEFAULT_REPORT_TYPE}  —  {self.context_title}")
        self.resize(1300, 760)
        self.setMinimumSize(1024, 600)

        # کش محاسبه‌شده
        self._cached_rows: Optional[List[_Row]] = None
        self._cached_status_totals: Optional[Dict[str, int]] = None
        self._cached_priority_totals: Optional[Dict[str, int]] = None
        self._cached_grand_total: Optional[int] = None
        self._cached_top_n: Optional[List[_TopItem]] = None
        self._cached_top_n_size: int = -1

        self._apply_style()
        self._build_ui()
        self._plot_chart()
        self._fill_table()

    # ══════════════════════════════════════════════
    # متدهای کمکی داده
    # ══════════════════════════════════════════════

    @staticmethod
    def _to_english_status(status_fa: str) -> str:
        return STATUS_EN.get(status_fa.strip(), status_fa.strip())

    @staticmethod
    def _to_english_priority(priority_fa: str) -> str:
        return PRIORITY_EN.get(priority_fa.strip(), priority_fa.strip())

    def _grand_total(self) -> int:
        """مجموع کل رکوردها (کش‌شده)."""
        if self._cached_grand_total is None:
            self._cached_grand_total = sum(self.data_counts.values())
        return self._cached_grand_total

    def _rows(self) -> List[_Row]:
        """لیست ردیف‌های جدول جزئیات (کش‌شده)."""
        if self._cached_rows is not None:
            return self._cached_rows

        grand = self._grand_total() or 1
        items = sorted(
            self.data_counts.items(),
            key=lambda x: x[1],
            reverse=True,
        )
        self._cached_rows = [
            _Row(
                status=st,
                priority=pr,
                count=c,
                pct=(c / grand) * 100.0,
            )
            for key, c in items
            for st, pr in [_parse_key(str(key))]
        ]
        return self._cached_rows

    def _status_totals(self) -> Dict[str, int]:
        """مجموع تعداد به تفکیک وضعیت (کش‌شده)."""
        if self._cached_status_totals is not None:
            return self._cached_status_totals

        totals: Dict[str, int] = {}
        for key, c in self.data_counts.items():
            st, _ = _parse_key(str(key))
            totals[st] = totals.get(st, 0) + c
        self._cached_status_totals = totals
        return totals

    def _priority_totals(self) -> Dict[str, int]:
        """مجموع تعداد به تفکیک اولویت (کش‌شده)."""
        if self._cached_priority_totals is not None:
            return self._cached_priority_totals

        totals: Dict[str, int] = {}
        for key, c in self.data_counts.items():
            _, pr = _parse_key(str(key))
            totals[pr] = totals.get(pr, 0) + c
        self._cached_priority_totals = totals
        return self._cached_priority_totals

    def _top_priority(self, n: int = TOP_N) -> List[_TopItem]:
        """n ردیف برتر بر اساس تعداد (کش‌شده)."""
        if self._cached_top_n is not None and self._cached_top_n_size == n:
            return self._cached_top_n

        agg: Dict[Tuple[str, str], int] = {}
        for key, c in self.data_counts.items():
            pair = _parse_key(str(key))
            agg[pair] = agg.get(pair, 0) + c

        grand = sum(agg.values()) or 1
        top_n_items = sorted(
            agg.items(), key=lambda kv: kv[1], reverse=True
        )[:max(0, n)]

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
        self.data_counts = {
            str(k): _safe_int(v, 0)
            for k, v in (data_counts or {}).items()
        }
        self._invalidate_cache()
        self._plot_chart()
        self._fill_table()

    # ══════════════════════════════════════════════
    # نمودار matplotlib (تمامی متون به انگلیسی)
    # ══════════════════════════════════════════════

    def _draw_on_figure(self, fig: "Figure") -> None:
        """
        ترسیم نمودار میله‌ای روی Figure داده‌شده.
        تمامی برچسب‌ها به انگلیسی نگاشت می‌شوند (پایداری فونت matplotlib).
        """
        # تمیزکاری محافظتی — اجازه می‌دهد این متد چند بار روی یک fig صدا زده شود
        fig.clear()

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
        colors = [STATUS_COLORS.get(lbl, DEFAULT_STATUS_COLOR) for lbl in labels_fa]

        ax = fig.add_subplot(111)
        ax.bar(
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

        ax.set_title(
            self.chart_title,
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

        self.table_widget.setRowCount(len(rows) + 1)

        for r, row in enumerate(rows):
            self._set_table_row(r, row.status, row.priority, row.count, row.pct)

        # ردیف مجموع
        total_count = sum(r.count for r in rows)
        sum_row = len(rows)

        items = {
            0: self._make_item("مجموع", bold=True),
            1: self._make_item("", bold=False),
            2: self._make_item(str(total_count), bold=True, align=Qt.AlignmentFlag.AlignCenter),
            3: self._make_item(f"۱۰۰{PERCENT_SUFFIX}", bold=True, align=Qt.AlignmentFlag.AlignCenter),
        }
        for col, item in items.items():
            self.table_widget.setItem(sum_row, col, item)

        self.table_widget.setSpan(sum_row, 0, 1, 2)

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
            self._make_item(f"{pct:.1f}{PERCENT_SUFFIX}", align=Qt.AlignmentFlag.AlignCenter)
        )

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
        ts_str = _format_shamsi_timestamp()

        return "\n".join([
            "<!doctype html>",
            '<html dir="rtl">',
            self._html_head(theme),
            "<body>",
            self._html_body(theme, ts_str, include_chart),
            "</body>",
            "</html>",
        ])

    def _html_head(self, theme: _ReportTheme) -> str:
        """تولید بخش <head> HTML."""
        title = _esc(self.context_title)
        css = self._build_css(theme)
        return f"""<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{_esc(DEFAULT_REPORT_TYPE)} — {title}</title>
  <style>{css}</style>
</head>"""

    def _html_body(
        self,
        theme: _ReportTheme,
        ts: str,
        include_chart: bool,
    ) -> str:
        """تولید بخش <body> HTML."""
        brand     = _esc(self._brand_line())
        title     = _esc(self.context_title)
        subject   = _esc(self.report_subject)
        rtype     = _esc(DEFAULT_REPORT_TYPE)
        app_name  = _esc(APP_NAME_FA)

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

        actual_top = len(top_items)
        top_label = f"{actual_top} مورد" if actual_top > 0 else "بدون داده"

        # فوتر فقط نام برنامه — بدون تکرار timestamp
        footer_html = (
            f'<span><strong>{app_name}</strong> — سامانه Document & MOM Tracking System</span>'
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
            v = status_totals.get(k, 0)
            pct = (v / grand) * 100.0
            color = STATUS_COLORS.get(k, "#64748b")
            cards.append(f"""
<div class="card" style="border-top:3px solid {color};">
  <div class="card-title">{_esc(k)}</div>
  <div class="card-value" style="color:{color};">{v:,}</div>
  <div class="card-sub">{pct:.1f}{PERCENT_SUFFIX}</div>
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
  <td>{_esc(t.status)}</td>
  <td>{_esc(t.priority)}</td>
  <td class="num">{t.total:,}</td>
  <td class="num">{t.pct:.1f}{PERCENT_SUFFIX}</td>
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
                f"<td class='col-st'>{_esc(r.status)}</td>"
                f"<td class='col-pr'>{_esc(r.priority)}</td>"
                f"<td class='num col-cnt'>{r.count:,}</td>"
                f"<td class='num col-pct'>{r.pct:.1f}{PERCENT_SUFFIX}</td>"
                f"</tr>"
            )

        total = sum(r.count for r in rows)
        html_rows.append(
            "<tr style='font-weight:bold;background:#f0f9ff;'>"
            "<td class='col-st'>مجموع</td>"
            "<td class='col-pr'></td>"
            f"<td class='num col-cnt'>{total:,}</td>"
            f"<td class='num col-pct'>۱۰۰{PERCENT_SUFFIX}</td>"
            "</tr>"
        )
        return "\n".join(html_rows)

    def _build_css(self, theme: _ReportTheme) -> str:
        """تولید CSS گزارش بر اساس theme."""
        return _REPORT_CSS_TEMPLATE.format(
            font_size_px=theme.font_size_px,
            font_family=DEFAULT_FONT_FAMILY,
            body_bg=theme.body_bg,
            body_padding=theme.body_padding,
            page_shadow=theme.page_shadow,
            header_pad=theme.header_pad,
            header_bg=theme.header_bg,
            pill_border=theme.pill_border,
            pill_bg=theme.pill_bg,
            pill_color=theme.pill_color,
            brand_color=theme.brand_color,
            meta_color=theme.meta_color,
        )

    # ══════════════════════════════════════════════
    # خروجی‌ها
    # ══════════════════════════════════════════════

    def save_report_html(self) -> None:
        """ذخیره گزارش HTML و پیشنهاد باز کردن در مرورگر."""
        base = _sanitize_filename(self.context_title)
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

        base = _sanitize_filename(f"status_priority_{self.context_title}")
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
                # ✅ استفاده از رنگ روشن‌شده به‌جای ARGB با آلفا (که openpyxl نادیده می‌گیرد)
                light_hex = _lighten_hex(color_hex, factor=0.82)
                row_fill = PatternFill("solid", fgColor=light_hex)
                for ci in range(1, 5):
                    ws.cell(row=ri, column=ci).fill = row_fill

        # ── ردیف مجموع ──
        total_count = sum(r.count for r in rows)
        if total_count > 0:
            sum_row  = len(rows) + 2
            sum_font = Font(bold=True, size=11)
            sum_fill = PatternFill("solid", fgColor="EFF6FF")

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

        base = _sanitize_filename(f"status_priority_{self.context_title}")
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
                writer.writerow(["تاریخ تولید", _format_shamsi_timestamp()])
                writer.writerow([])
                writer.writerow(["وضعیت", "اولویت", "تعداد", f"درصد ({PERCENT_SUFFIX})"])
                for r in rows:
                    writer.writerow([
                        r.status, r.priority, r.count,
                        f"{r.pct:.1f}{PERCENT_SUFFIX}",
                    ])
                total = sum(r.count for r in rows)
                if total:
                    writer.writerow(["مجموع", "", total, f"100{PERCENT_SUFFIX}"])

            QMessageBox.information(self, "✅ انجام شد", f"خروجی CSV ذخیره شد:\n{path}")
            logger.info("CSV exported to %s", path)
        except OSError as exc:
            logger.exception("CSV export failed.")
            QMessageBox.critical(self, "خطا در خروجی CSV", str(exc))
        except Exception as exc:
            logger.exception("Unexpected error in CSV export.")
            QMessageBox.critical(self, "خطا", f"خطای غیرمنتظره:\n{exc}")

    def print_report(self, include_chart: bool = True) -> None:
        """
        چاپ گزارش HTML روی پرینتر (A4 افقی).
        `include_chart` پیش‌فرض True برای هماهنگی با خروجی HTML.
        """
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
