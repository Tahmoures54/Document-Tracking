# -*- coding: utf-8 -*-
"""تست‌های مستقل و سریع برای تعیین وضعیت رنگی گردش‌کار."""
from services.workflow_status import derive_workflow_state


def test_empty_workflow_is_pending():
    assert derive_workflow_state("در دست بررسی", [], False) == "pending"


def test_in_progress_takes_precedence_over_pending():
    assert derive_workflow_state(
        "در دست بررسی", ["completed", "pending", "in_progress"], False
    ) == "in_progress"


def test_rejected_step_marks_record_returned():
    assert derive_workflow_state(
        "در دست بررسی", ["completed", "rejected"], False
    ) == "returned"


def test_completed_requires_dispatch_date():
    assert derive_workflow_state(
        "تکمیل شده", ["completed", "completed"], False
    ) == "pending"
    assert derive_workflow_state(
        "تکمیل شده", ["completed", "completed"], True
    ) == "completed"


def test_cancelled_record_stays_cancelled():
    assert derive_workflow_state("لغو شده", [], False) == "cancelled"


def test_database_fetch_failure_is_unknown_not_pending():
    assert derive_workflow_state(
        "در دست بررسی", [], False, workflow_loaded=False
    ) == "unknown"


def test_skipped_or_unknown_step_never_marks_record_completed():
    assert derive_workflow_state(
        "تکمیل شده", ["completed", "skipped"], True
    ) == "unknown"
