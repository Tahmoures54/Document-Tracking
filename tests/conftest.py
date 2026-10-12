# -*- coding: utf-8 -*-
"""fixtures مشترک تست‌ها"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# ریشه پروژه را به path اضافه کن
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture()
def tmp_db(tmp_path):
    """دیتابیس موقت برای تست‌های یکپارچگی."""
    from db.manager import DatabaseManager

    db_file = tmp_path / "test_meetings.db"
    db = DatabaseManager(str(db_file))
    yield db
