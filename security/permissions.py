# -*- coding: utf-8 -*-
"""
مدیریت سطوح دسترسی و نقش‌ها
"""
from __future__ import annotations

import logging
from typing import Optional, FrozenSet, List, Iterable

from config import Roles
from security.session import UserSession

logger = logging.getLogger(__name__)

# ========== ثابت‌های دسترسی ==========
PERM_REPORT_READ = "report.read"
PERM_REPORT_WRITE = "report.write"
PERM_USER_ADMIN = "user.admin"
PERM_DB_PUBLISH = "db.publish"
PERM_MEETING_DELETE = "meeting.delete"
PERM_REPORT_EXPORT = "report.export"

ALL_PERMISSIONS: FrozenSet[str] = frozenset({
    PERM_REPORT_READ,
    PERM_REPORT_WRITE,
    PERM_USER_ADMIN,
    PERM_DB_PUBLISH,
    PERM_MEETING_DELETE,
    PERM_REPORT_EXPORT,
})

# ========== دسترسی‌های هر نقش ==========
# 🔥 کلیدها به‌صورت رشته ذخیره می‌شوند (value مربوط به Enum)
ROLE_PERMS: dict[str, FrozenSet[str]] = {
    Roles.ADMIN.value: frozenset({
        PERM_REPORT_READ,
        PERM_REPORT_WRITE,
        PERM_USER_ADMIN,
        PERM_DB_PUBLISH,
        PERM_MEETING_DELETE,
        PERM_REPORT_EXPORT,
    }),
    Roles.EDITOR.value: frozenset({
        PERM_REPORT_READ,
        PERM_REPORT_WRITE,
        PERM_MEETING_DELETE,
        PERM_REPORT_EXPORT,
    }),
    Roles.VIEWER.value: frozenset({
        PERM_REPORT_READ,
        PERM_REPORT_EXPORT,
    }),
    # اگر نقش‌های دیگری مانند MANAGER، USER نیاز به دسترسی خاص دارند، اینجا اضافه کنید
    Roles.MANAGER.value: frozenset({
        PERM_REPORT_READ,
        PERM_REPORT_WRITE,
        PERM_REPORT_EXPORT,
    }),
    Roles.USER.value: frozenset({
        PERM_REPORT_READ,
        PERM_REPORT_WRITE,
        PERM_MEETING_DELETE,
    }),
}


def _normalize_role(role: Optional[str]) -> str:
    """نرمال‌سازی نام نقش برای مقایسه امن."""
    if role is None:
        return ""
    return str(role).strip().lower()


def get_permissions(role: Optional[str]) -> FrozenSet[str]:
    """
    دریافت مجموعه دسترسی‌های یک نقش.

    Args:
        role: نام نقش (رشته یا عضو Enum)

    Returns:
        مجموعه دسترسی‌ها (frozenset). برای نقش ناشناخته، مجموعه خالی برمی‌گرداند.
    """
    normalized = _normalize_role(role)
    return ROLE_PERMS.get(normalized, frozenset())


def can(session: Optional[UserSession], perm: str) -> bool:
    """بررسی دسترسی یک نشست."""
    if session is None:
        return False

    role = getattr(session, "role", None)
    if not role:
        return False

    permissions = get_permissions(role)
    if perm not in ALL_PERMISSIONS:
        logger.warning("Unknown permission requested: %s (role=%s)", perm, role)
        return False

    return perm in permissions


def has_all(session: Optional[UserSession], perms: Iterable[str]) -> bool:
    if session is None:
        return False
    return all(can(session, p) for p in perms)


def has_any(session: Optional[UserSession], perms: Iterable[str]) -> bool:
    if session is None:
        return False
    return any(can(session, p) for p in perms)


def ensure_can(session: Optional[UserSession], perm: str, message: str = "دسترسی غیرمجاز") -> None:
    if not can(session, perm):
        raise PermissionError(message)