# -*- coding: utf-8 -*-
"""
db.models
طراحی مدل‌های پایگاه داده رابطه‌ای با SQLAlchemy ORM
نسخه نهایی و کاملاً هماهنگ:
• حذف فیلدهای منسوخ وضعیت پاسخ پیمانکار (بر اساس منطق «ارسال = اتمام کار»)
• حذف ستون‌های «لینک فایل»، «تاریخ بسته شدن» و «تاریخ پاسخ پیمانکار» از نمایش جدول اصلی
• قانون طلایی: تاریخ ارسال به پیمانکار = بسته شدن پرونده = تاریخ پاسخ پیمانکار
• هماهنگی کامل با وضعیت «بازگشت داده شده»
• ایندکس‌های ترکیبی برای بهبود سرعت کوئری‌ها
• پروپرتی‌های محاسباتی پیشرفته و متد کمکی ابلاغ
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

# ──────────────────────────────────────────────
# ثابت‌های وضعیت و اولویت (MOM Workflow Constants)
# ──────────────────────────────────────────────
STATUS_PENDING   = "در دست بررسی"
STATUS_AWAITING  = "در انتظار تأیید"
STATUS_COMPLETED = "تکمیل شده"
STATUS_CANCELLED = "لغو شده"
STATUS_RETURNED  = "بازگشت داده شده"

STATUSES: List[str] = [
    STATUS_PENDING,
    STATUS_AWAITING,
    STATUS_COMPLETED,
    STATUS_CANCELLED,
    STATUS_RETURNED,
]

OPEN_STATUSES: List[str] = [STATUS_PENDING, STATUS_AWAITING, STATUS_RETURNED]
CLOSED_STATUSES: List[str] = [STATUS_COMPLETED, STATUS_CANCELLED]

PRIORITY_HIGH   = "بالا"
PRIORITY_MEDIUM = "متوسط"
PRIORITY_LOW    = "پایین"
PRIORITIES: List[str] = [PRIORITY_HIGH, PRIORITY_MEDIUM, PRIORITY_LOW]

# ──────────────────────────────────────────────
# تخصص‌ها و دیسیپلین‌های مهندسی پروژه
# ──────────────────────────────────────────────
DISCIPLINE_CIVIL            = "عمران"
DISCIPLINE_MECHANICAL       = "مکانیک"
DISCIPLINE_ELECTRICAL       = "برق"
DISCIPLINE_INSTRUMENTATION  = "ابزار دقیق"
DISCIPLINE_ARCHITECTURE     = "معماری"
DISCIPLINE_PROCESS          = "فرآیند"
DISCIPLINE_PIPING           = "خطوط لوله"
DISCIPLINE_HSE              = "HSE"
DISCIPLINE_OTHER            = "سایر"

DISCIPLINES: List[str] = [
    DISCIPLINE_CIVIL,
    DISCIPLINE_MECHANICAL,
    DISCIPLINE_ELECTRICAL,
    DISCIPLINE_INSTRUMENTATION,
    DISCIPLINE_ARCHITECTURE,
    DISCIPLINE_PROCESS,
    DISCIPLINE_PIPING,
    DISCIPLINE_HSE,
    DISCIPLINE_OTHER,
]

# ──────────────────────────────────────────────
# نقش‌های کاربری (هم‌تراز با config.Roles)
# ──────────────────────────────────────────────
ROLE_ADMIN   = "admin"
ROLE_MANAGER = "manager"
ROLE_EDITOR  = "editor"
ROLE_USER    = "user"
ROLE_VIEWER  = "viewer"

ROLES: List[str] = [ROLE_ADMIN, ROLE_MANAGER, ROLE_EDITOR, ROLE_USER, ROLE_VIEWER]
