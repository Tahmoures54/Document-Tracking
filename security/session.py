# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Any, Optional


@dataclass(frozen=True)
class UserSession:
    """
    نشست کاربر جاری در سیستم.

    Attributes:
        user_id: شناسه یکتای کاربر
        username: نام کاربری
        role: نقش کاربر (admin، editor، viewer)
    """

    user_id: int
    username: str
    role: str

    def __post_init__(self) -> None:
        """اعتبارسنجی مقادیر اولیه."""
        if not isinstance(self.user_id, int) or self.user_id <= 0:
            raise ValueError("user_id must be a positive integer")
        if not self.username or not self.username.strip():
            raise ValueError("username cannot be empty")
        if not self.role or not self.role.strip():
            raise ValueError("role cannot be empty")

        # نرمال‌سازی نام کاربری و نقش (حذف فاصله‌های اضافی)
        object.__setattr__(self, "username", self.username.strip())
        object.__setattr__(self, "role", self.role.strip().lower())

    @property
    def is_admin(self) -> bool:
        """آیا نقش کاربر مدیر است؟"""
        return self.role == "admin"

    @property
    def is_editor(self) -> bool:
        """آیا نقش کاربر ویرایشگر است؟"""
        return self.role == "editor"

    @property
    def is_viewer(self) -> bool:
        """آیا نقش کاربر فقط مشاهده‌گر است؟"""
        return self.role == "viewer"

    def to_dict(self) -> Dict[str, Any]:
        """تبدیل به دیکشنری برای ذخیره‌سازی یا ارسال."""
        return {
            "user_id": self.user_id,
            "username": self.username,
            "role": self.role,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UserSession":
        """ساخت نمونه از دیکشنری."""
        return cls(
            user_id=int(data.get("user_id", 0)),
            username=str(data.get("username", "")),
            role=str(data.get("role", "")),
        )

    def __str__(self) -> str:
        return f"{self.username} ({self.role})"

    def __repr__(self) -> str:
        return f"UserSession(user_id={self.user_id}, username='{self.username}', role='{self.role}')"