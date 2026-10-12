# -*- coding: utf-8 -*-
"""تست جستجوی شماره صورتجلسه و شباهت"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from db.models import Meeting, STATUS_PENDING


def _add(db, **kwargs):
    data = {
        "meeting_number": kwargs.pop("meeting_number"),
        "subject": kwargs.pop("subject", "موضوع تست"),
        "meeting_date": kwargs.pop("meeting_date", date.today()),
        "due_date": kwargs.pop("due_date", date.today() + timedelta(days=7)),
        "status": kwargs.pop("status", STATUS_PENDING),
        "priority": kwargs.pop("priority", "متوسط"),
        "entry_date": kwargs.pop("entry_date", date.today()),
        "attachment_count": 0,
        "is_deleted": False,
    }
    data.update(kwargs)
    return db.create_meeting(data)


def test_search_contains_10(tmp_db):
    _add(tmp_db, meeting_number="MOM-10")
    _add(tmp_db, meeting_number="MOM-100")
    _add(tmp_db, meeting_number="A-10-B")
    _add(tmp_db, meeting_number="MOM-20")

    found = tmp_db.search_by_meeting_number_contains("10")
    nums = {m.meeting_number for m in found}
    assert "MOM-10" in nums
    assert "MOM-100" in nums
    assert "A-10-B" in nums
    assert "MOM-20" not in nums


def test_search_empty_returns_empty(tmp_db):
    assert tmp_db.search_by_meeting_number_contains("") == []
    assert tmp_db.search_by_meeting_number_contains("   ") == []


def test_find_similar_same_contractor_location(tmp_db):
    _add(
        tmp_db,
        meeting_number="S-1",
        contractor="پیمانکار الف",
        location="سایت فاز ۲",
        drawing_number="DWG-01",
    )
    _add(
        tmp_db,
        meeting_number="S-2",
        contractor="پیمانکار الف",
        location="سایت فاز ۲",
        drawing_number="DWG-99",
    )
    _add(
        tmp_db,
        meeting_number="S-3",
        contractor="پیمانکار ب",
        location="سایت فاز ۲",
    )

    similar = tmp_db.find_similar_meetings(
        contractor="پیمانکار الف",
        location="سایت فاز ۲",
        days_window=90,
    )
    nums = {m.meeting_number for m in similar}
    assert "S-1" in nums
    assert "S-2" in nums
    assert "S-3" not in nums


def test_find_similar_requires_contractor(tmp_db):
    _add(tmp_db, meeting_number="X-1", location="محل ۱")
    assert tmp_db.find_similar_meetings(location="محل ۱") == []


def test_workflow_initialized_on_create(tmp_db):
    m = _add(tmp_db, meeting_number="W-1")
    steps = tmp_db.get_workflow_steps(m.id)
    assert len(steps) == 6
    names = [s.step_name for s in steps]
    assert "دریافت در دفتر کارفرما" in names or "ورود به دفتر کارفرما" in names
    assert steps[0].step_order == 1
