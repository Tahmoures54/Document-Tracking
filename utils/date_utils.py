# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Optional, Union

import jdatetime

logger = logging.getLogger(__name__)


def to_gregorian(shamsi_str: str) -> Optional[str]:
    """
    تبدیل تاریخ شمسی (رشته) به تاریخ میلادی (رشته ISO).

    Args:
        shamsi_str: تاریخ شمسی به فرمت 'YYYY-MM-DD'

    Returns:
        رشته تاریخ میلادی (YYYY-MM-DD) یا None در صورت نامعتبر بودن
    """
    if not shamsi_str:
        return None

    shamsi_str = str(shamsi_str).strip()
    if not shamsi_str:
        return None

    try:
        y, m, d = map(int, shamsi_str.split('-'))
        return jdatetime.date(y, m, d).togregorian().isoformat()
    except (ValueError, TypeError):
        logger.debug("Invalid Shamsi date string: %s", shamsi_str)
        return None


def to_gregorian_date(shamsi_str: str) -> Optional[date]:
    """
    تبدیل تاریخ شمسی (رشته) به شیء date میلادی.

    Args:
        shamsi_str: تاریخ شمسی به فرمت 'YYYY-MM-DD'

    Returns:
        شیء date میلادی یا None
    """
    greg_str = to_gregorian(shamsi_str)
    if not greg_str:
        return None
    return datetime.strptime(greg_str, '%Y-%m-%d').date()


def to_shamsi(gregorian_input: Union[str, date, datetime]) -> str:
    """
    تبدیل تاریخ میلادی (رشته، date، datetime) به تاریخ شمسی (رشته).

    Args:
        gregorian_input: تاریخ میلادی به صورت 'YYYY-MM-DD' یا شیء date/datetime

    Returns:
        رشته تاریخ شمسی (YYYY-MM-DD) یا "" در صورت نامعتبر بودن
    """
    if not gregorian_input:
        return ""

    try:
        if isinstance(gregorian_input, datetime):
            dt = gregorian_input.date()
        elif isinstance(gregorian_input, date):
            dt = gregorian_input
        else:
            dt = datetime.strptime(str(gregorian_input).strip(), '%Y-%m-%d').date()

        return jdatetime.date.fromgregorian(date=dt).strftime('%Y-%m-%d')
    except (ValueError, TypeError):
        logger.debug("Invalid Gregorian date: %s", gregorian_input)
        return ""


def to_shamsi_date(gregorian_input: Union[str, date, datetime]) -> Optional[jdatetime.date]:
    """
    تبدیل تاریخ میلادی به شیء jdatetime.date (شمسی).

    Args:
        gregorian_input: تاریخ میلادی

    Returns:
        شیء jdatetime.date یا None
    """
    if not gregorian_input:
        return None

    try:
        if isinstance(gregorian_input, datetime):
            dt = gregorian_input.date()
        elif isinstance(gregorian_input, date):
            dt = gregorian_input
        else:
            dt = datetime.strptime(str(gregorian_input).strip(), '%Y-%m-%d').date()
        return jdatetime.date.fromgregorian(date=dt)
    except (ValueError, TypeError):
        return None


def today_shamsi() -> str:
    """برگرداندن تاریخ امروز شمسی به صورت رشته (YYYY-MM-DD)."""
    return jdatetime.date.today().strftime('%Y-%m-%d')


def today_shamsi_date() -> jdatetime.date:
    """برگرداندن شیء jdatetime.date امروز."""
    return jdatetime.date.today()


def is_valid_shamsi(date_str: str) -> bool:
    """
    بررسی صحت تاریخ شمسی.

    Args:
        date_str: تاریخ شمسی (YYYY-MM-DD)

    Returns:
        True اگر تاریخ معتبر باشد
    """
    try:
        if not date_str:
            return False
        y, m, d = map(int, str(date_str).strip().split('-'))
        # بررسی محدوده ماه و روز
        return 1 <= m <= 12 and 1 <= d <= jdatetime.date(y, m, 1).togregorian().monthrange
    except Exception:
        return False


def now_shamsi() -> str:
    """برگرداندن تاریخ و زمان شمسی جاری به صورت رشته (YYYY-MM-DD HH:MM:SS)."""
    return jdatetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def now_shamsi_datetime() -> jdatetime.datetime:
    """برگرداندن شیء jdatetime.datetime جاری."""
    return jdatetime.datetime.now()


# توابع کمکی برای تبدیل معکوس (میلادی به شمسی و بالعکس)
def gregorian_to_shamsi(gregorian_input: Union[str, date, datetime]) -> str:
    """Alias برای to_shamsi."""
    return to_shamsi(gregorian_input)


def shamsi_to_gregorian(shamsi_str: str) -> Optional[str]:
    """Alias برای to_gregorian."""
    return to_gregorian(shamsi_str)