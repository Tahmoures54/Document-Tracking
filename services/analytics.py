# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date
from typing import Dict, List, Tuple

from sqlalchemy import func

from db.manager import DatabaseManager
from db.models import (
    Meeting,
    STATUS_PENDING,
    STATUS_AWAITING,
    STATUS_COMPLETED,
    STATUS_CANCELLED,
)

# ستون‌های مجاز برای گروه‌بندی (هماهنگ با فیلدهای مدل Meeting)
SAFE_GROUP_COLUMNS = {
    "status",
    "priority",
    "employer",
    "consultant",
    "contractor",
    "drawing_number",
    "contract_number",
    "discipline",  # ← هماهنگ‌شده با ستون جدید
}


def _first_day_of_month(d: date) -> date:
    return date(d.year, d.month, 1)


def _add_months(d: date, months: int) -> date:
    """
    افزودن/کاستن ماه بدون وابستگی خارجی (months می‌تواند منفی باشد).
    خروجی همیشه روز 1 ماه مقصد است (برای فیلتر ماهانه مناسب).
    """
    y = d.year
    m = d.month + months
    while m > 12:
        m -= 12
        y += 1
    while m < 1:
        m += 12
        y -= 1
    return date(y, m, 1)


def summary_counts(db: DatabaseManager) -> Dict[str, int]:
    """
    آمار کلی صورتجلسات: کل، بر اساس وضعیت، تاخیردار.

    خروجی:
        {
          total, pending, awaiting, completed, cancelled, delayed
        }
    """
    with db.session() as sess:
        total = sess.query(func.count(Meeting.id)).scalar() or 0

        status_counts = dict(
            sess.query(Meeting.status, func.count(Meeting.id)).filter(Meeting.is_deleted.is_(False))
            .filter(Meeting.status.isnot(None))
            .group_by(Meeting.status)
            .all()
        )

        today = date.today()
        delayed = (
            sess.query(func.count(Meeting.id))
            .filter(
                Meeting.due_date < today,
                Meeting.status.in_([STATUS_PENDING, STATUS_AWAITING]),
            )
            .scalar()
            or 0
        )

    return {
        "total": int(total),
        "pending": int(status_counts.get(STATUS_PENDING, 0)),
        "awaiting": int(status_counts.get(STATUS_AWAITING, 0)),
        "completed": int(status_counts.get(STATUS_COMPLETED, 0)),
        "cancelled": int(status_counts.get(STATUS_CANCELLED, 0)),
        "delayed": int(delayed),
    }


def summary_by_priority(db: DatabaseManager) -> Dict[str, int]:
    """شمارش بر اساس اولویت."""
    with db.session() as sess:
        rows = (
            sess.query(Meeting.priority, func.count(Meeting.id)).filter(Meeting.is_deleted.is_(False))
            .group_by(Meeting.priority)
            .all()
        )
    return {str(k or "نامشخص"): int(v) for k, v in rows}


def group_by(db: DatabaseManager, col: str, limit: int = 100) -> List[Tuple[str, int]]:
    """
    گروه‌بندی صورتجلسات بر اساس یک ستون امن.

    Args:
        col: نام ستون (مثلاً employer / discipline)
        limit: حداکثر تعداد نتایج

    Returns:
        لیست (مقدار, تعداد) به ترتیب نزولی تعداد
    """
    if col not in SAFE_GROUP_COLUMNS:
        raise ValueError(f"Unsafe column: {col}")

    column_attr = getattr(Meeting, col, None)
    if column_attr is None:
        raise ValueError(f"Column not found on Meeting model: {col}")

    key_expr = func.coalesce(func.nullif(func.trim(column_attr), ""), "خالی").label("key")

    with db.session() as sess:
        rows = (
            sess.query(key_expr, func.count(Meeting.id).label("cnt"))
            .group_by(key_expr)
            .order_by(func.count(Meeting.id).desc())
            .limit(limit)
            .all()
        )

    return [(str(k), int(c)) for k, c in rows if k is not None]


def overdue_by_employer(db: DatabaseManager) -> List[Tuple[str, int]]:
    """
    تاخیرها بر اساس کارفرما (برای گزارش‌های مدیریتی).
    """
    today = date.today()
    with db.session() as sess:
        rows = (
            sess.query(Meeting.employer, func.count(Meeting.id)).filter(Meeting.is_deleted.is_(False))
            .filter(
                Meeting.due_date < today,
                Meeting.status.in_([STATUS_PENDING, STATUS_AWAITING]),
                Meeting.employer.isnot(None),
                func.trim(Meeting.employer) != "",
            )
            .group_by(Meeting.employer)
            .order_by(func.count(Meeting.id).desc())
            .all()
        )
    return [(str(e), int(c)) for e, c in rows if e]


def monthly_created_counts(db: DatabaseManager, months: int = 6) -> Dict[str, int]:
    """
    تعداد صورتجلسات ثبت‌شده در ماه‌های اخیر بر اساس entry_date.
    خروجی: {'YYYY-MM': count, ...}

    months:
        تعداد ماه‌های اخیر (شامل ماه جاری). اگر months<=0 باشد، کل داده‌ها را می‌دهد.
    """
    cutoff: date | None = None
    if months and months > 0:
        start = _first_day_of_month(date.today())
        cutoff = _add_months(start, -(months - 1))

    with db.session() as sess:
        q = (
            sess.query(
                func.strftime("%Y-%m", Meeting.entry_date).label("month"),
                func.count(Meeting.id),
            )
            .filter(Meeting.entry_date.isnot(None))
        )
        if cutoff:
            q = q.filter(Meeting.entry_date >= cutoff)

        rows = (
            q.group_by("month")
             .order_by("month")
             .all()
        )

    return {str(month): int(cnt) for month, cnt in rows if month is not None}


def get_status_priority_matrix(db: DatabaseManager) -> Dict[str, Dict[str, int]]:
    """
    ماتریس وضعیت × اولویت برای گزارش‌های تحلیلی.
    """
    with db.session() as sess:
        rows = (
            sess.query(Meeting.status, Meeting.priority, func.count(Meeting.id)).filter(Meeting.is_deleted.is_(False))
            .group_by(Meeting.status, Meeting.priority)
            .all()
        )

    matrix: Dict[str, Dict[str, int]] = {}
    for st, pr, cnt in rows:
        st = (st or "").strip() or "نامشخص"
        pr = (pr or "").strip() or "نامشخص"
        matrix.setdefault(st, {})
        matrix[st][pr] = int(cnt or 0)
    return matrix