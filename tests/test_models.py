# -*- coding: utf-8 -*-
"""تست منطق مدل Meeting — بدون UI"""
from __future__ import annotations

from datetime import date, timedelta

from db.models import (
    Meeting,
    STATUS_PENDING,
    STATUS_COMPLETED,
    STATUS_CANCELLED,
)


def test_is_delayed_open_past_due():
    m = Meeting(
        meeting_number="T-1",
        subject="تست",
        meeting_date=date.today() - timedelta(days=10),
        due_date=date.today() - timedelta(days=1),
        status=STATUS_PENDING,
    )
    assert m.is_delayed is True


def test_is_delayed_false_when_completed():
    m = Meeting(
        meeting_number="T-2",
        subject="تست",
        meeting_date=date.today() - timedelta(days=10),
        due_date=date.today() - timedelta(days=1),
        status=STATUS_COMPLETED,
    )
    assert m.is_delayed is False


def test_is_delayed_false_when_dispatched():
    m = Meeting(
        meeting_number="T-3",
        subject="تست",
        meeting_date=date.today() - timedelta(days=10),
        due_date=date.today() - timedelta(days=1),
        status=STATUS_PENDING,
        sent_to_contractor_date=date.today(),
    )
    assert m.is_delayed is False


def test_set_dispatched_to_contractor():
    m = Meeting(
        meeting_number="T-4",
        subject="تست",
        meeting_date=date.today() - timedelta(days=5),
        due_date=date.today() + timedelta(days=5),
        status=STATUS_PENDING,
    )
    d = date.today()
    m.set_dispatched_to_contractor(d)
    assert m.sent_to_contractor_date == d
    assert m.closing_date == d
    assert m.contractor_response_date == d
    assert m.status == STATUS_COMPLETED
    assert m.is_dispatched is True


def test_validate_requires_meeting_number():
    m = Meeting(
        meeting_number="  ",
        subject="موضوع",
        meeting_date=date.today(),
        due_date=date.today() + timedelta(days=3),
    )
    err = m.validate()
    assert err is not None
    assert "شماره" in err


def test_validate_due_before_meeting():
    m = Meeting(
        meeting_number="T-5",
        subject="موضوع",
        meeting_date=date.today(),
        due_date=date.today() - timedelta(days=1),
    )
    err = m.validate()
    assert err is not None



def test_registration_date_column_uses_entry_date():
    entry_date = date(2026, 10, 20)
    m = Meeting(
        meeting_number="T-REG-DATE",
        subject="آزمون تاریخ ثبت",
        entry_date=entry_date,
        meeting_date=date(2026, 10, 19),
        due_date=date(2026, 10, 23),
    )
    headers = Meeting.headers()
    row = m.to_row(headers)

    registration_col = headers.index("تاریخ ثبت / ورود به کارفرما")
    due_col = headers.index("مهلت رسیدگی")
    assert row[registration_col] == "2026-10-20"
    assert row[due_col] == "2026-10-23"
