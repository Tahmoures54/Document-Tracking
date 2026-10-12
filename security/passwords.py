# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import hmac
import base64
import secrets
import logging
from typing import Tuple, Optional

logger = logging.getLogger(__name__)

# تنظیمات پیش‌فرض امنیتی
PBKDF2_ITERATIONS = 210_000   # تعداد تکرار PBKDF2
SALT_LENGTH = 16              # طول نمک (بایت)
HASH_ALGORITHM = "sha256"    # الگوریتم هش
HASH_SCHEME = "pbkdf2_sha256" # شناسه طرح هش


def hash_password(password: str) -> str:
    """
    تولید هش امن برای رمز عبور با استفاده از PBKDF2-HMAC-SHA256.

    Args:
        password: رمز عبور به‌صورت متن ساده

    Returns:
        رشته هش شامل الگوریتم، تعداد تکرار، نمک و هش نهایی

    Raises:
        ValueError: اگر رمز عبور خالی یا None باشد
    """
    if not isinstance(password, str) or not password:
        raise ValueError("Password must be a non-empty string")

    # تولید نمک تصادفی امن
    salt = secrets.token_bytes(SALT_LENGTH)
    # تولید کلید مشتق‌شده
    dk = hashlib.pbkdf2_hmac(
        HASH_ALGORITHM,
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS
    )
    # کدگذاری base64 برای ذخیره‌سازی
    salt_b64 = base64.b64encode(salt).decode("ascii")
    hash_b64 = base64.b64encode(dk).decode("ascii")

    return f"{HASH_SCHEME}${PBKDF2_ITERATIONS}${salt_b64}${hash_b64}"


def verify_password(password: str, stored: str) -> bool:
    """
    بررسی صحت رمز عبور در برابر هش ذخیره‌شده.

    Args:
        password: رمز عبور واردشده توسط کاربر
        stored: هش ذخیره‌شده در دیتابیس

    Returns:
        True اگر رمز صحیح باشد، در غیر این صورت False
    """
    if not isinstance(password, str) or not stored or "$" not in stored:
        return False

    try:
        scheme, iterations_str, salt_b64, hash_b64 = stored.split("$", 3)
        if scheme != HASH_SCHEME:
            logger.warning("Unsupported hash scheme: %s", scheme)
            return False

        iterations = int(iterations_str)
        if iterations < 1:
            return False

        salt = base64.b64decode(salt_b64)
        expected_hash = base64.b64decode(hash_b64)

        # مشتق‌سازی مجدد با پارامترهای ذخیره‌شده
        dk = hashlib.pbkdf2_hmac(
            HASH_ALGORITHM,
            password.encode("utf-8"),
            salt,
            iterations
        )
        # مقایسه امن با hmac.compare_digest برای جلوگیری از timing attack
        return hmac.compare_digest(dk, expected_hash)

    except (ValueError, TypeError, base64.binascii.Error):
        logger.warning("Malformed password hash encountered")
        return False


def needs_rehash(stored: str) -> bool:
    """
    بررسی اینکه آیا هش ذخیره‌شده با تنظیمات فعلی (تعداد تکرار) به‌روز است یا خیر.

    Args:
        stored: هش ذخیره‌شده

    Returns:
        True اگر نیاز به هش مجدد دارد، در غیر این صورت False
    """
    try:
        scheme, iterations_str, _, _ = stored.split("$", 3)
        if scheme != HASH_SCHEME:
            return True
        return int(iterations_str) < PBKDF2_ITERATIONS
    except (ValueError, TypeError):
        return True


def validate_password_strength(password: str, min_length: int = 8) -> Tuple[bool, str]:
    """
    بررسی استحکام رمز عبور (اختیاری برای استفاده در رابط کاربری).

    Args:
        password: رمز عبور
        min_length: حداقل طول مجاز

    Returns:
        (is_valid, message) شامل وضعیت و پیام خطا
    """
    if not password or len(password) < min_length:
        return False, f"رمز عبور باید حداقل {min_length} کاراکتر باشد."
    if not any(c.isupper() for c in password):
        return False, "رمز عبور باید شامل حداقل یک حرف بزرگ باشد."
    if not any(c.islower() for c in password):
        return False, "رمز عبور باید شامل حداقل یک حرف کوچک باشد."
    if not any(c.isdigit() for c in password):
        return False, "رمز عبور باید شامل حداقل یک عدد باشد."
    return True, "رمز عبور قوی است."