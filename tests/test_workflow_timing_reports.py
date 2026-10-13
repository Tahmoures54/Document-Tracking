from datetime import date, datetime
from types import SimpleNamespace

from services.workflow_report import (
    WorkflowOverviewReportGenerator,
    WorkflowReportGenerator,
)


def make_meeting():
    return SimpleNamespace(
        id=7,
        meeting_number="1405-007",
        subject="آزمایش زمان رسیدگی",
        meeting_date=date(2026, 1, 1),
        entry_date=date(2026, 1, 1),
        created_at=datetime(2026, 1, 1, 8, 0),
        due_date=date(2026, 1, 20),
        sent_to_contractor_date=date(2026, 1, 10),
        closing_date=date(2026, 1, 10),
        status="تکمیل شده",
        employer="کارفرما",
        contractor="پیمانکار",
    )


def make_steps():
    return [
        SimpleNamespace(
            id=1,
            meeting_id=7,
            step_name="مرحله اول",
            step_order=1,
            entry_date=date(2026, 1, 1),
            exit_date=date(2026, 1, 4),
            responsible_person="کارشناس",
            status="completed",
            notes="",
            signature="",
        ),
        SimpleNamespace(
            id=2,
            meeting_id=7,
            step_name="مرحله دوم",
            step_order=2,
            entry_date=date(2026, 1, 4),
            exit_date=None,
            responsible_person="مدیر",
            status="in_progress",
            notes="در انتظار بررسی",
            signature="",
        ),
    ]


def test_individual_report_includes_start_end_and_stage_duration():
    html = WorkflowReportGenerator(make_meeting(), make_steps())._generate_html()

    assert "گزارش زمان رسیدگی صورتجلسه" in html
    assert "1405-007" in html
    assert "مرحله اول" in html
    assert "مرحله دوم" in html
    assert "3 روز" in html
    assert "در جریان" in html
    assert "تاریخ شروع" in html
    assert "تاریخ پایان" in html


def test_overview_report_contains_per_meeting_and_stage_columns():
    meeting = make_meeting()
    steps = make_steps()
    html = WorkflowOverviewReportGenerator(
        [meeting], {meeting.id: steps}
    )._generate_html()

    assert "گزارش تجمیعی زمان رسیدگی صورتجلسات" in html
    assert "1405-007" in html
    assert "مرحله اول" in html
    assert "مرحله دوم" in html
    assert "مدت کل" in html
    assert "3 روز" in html
