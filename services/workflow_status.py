# -*- coding: utf-8 -*-
"""تعیین وضعیت نمایشی گردش کار بدون وابستگی به رابط گرافیکی."""
from __future__ import annotations

from typing import Iterable, Optional


def derive_workflow_state(
    meeting_status: Optional[str],
    step_statuses: Iterable[str],
    dispatched: bool,
    *,
    workflow_loaded: bool = True,
) -> str:
    """وضعیت رنگی پرونده را محافظه‌کارانه از گردش‌کار واقعی استخراج می‌کند.

    اگر واکشی گردش‌کار از دیتابیس شکست بخورد، وضعیت unknown است؛
    خطای دیتابیس نباید به‌اشتباه به شکل «در انتظار بررسی» نمایش داده شود.
    """
    if meeting_status == "لغو شده":
        return "cancelled"

    if not workflow_loaded:
        return "unknown"

    statuses = list(step_statuses)
    if not statuses:
        return "pending"
    if "rejected" in statuses:
        return "returned"
    if "in_progress" in statuses:
        return "in_progress"
    if "pending" in statuses:
        return "pending"
    if all(status == "completed" for status in statuses):
        return "completed" if dispatched else "pending"

    # وضعیت skipped یا هر مقدار ناشناخته هرگز به‌اشتباه سبز نمی‌شود.
    return "unknown"
