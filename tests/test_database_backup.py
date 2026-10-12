# -*- coding: utf-8 -*-
"""آزمون یکپارچگی و ایمنی بکاپ SQLite."""
from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from db.manager import DatabaseManager


def test_backup_is_consistent_and_contains_workflow(tmp_path):
    source = tmp_path / "source.db"
    backup = tmp_path / "backups" / "nested" / "snapshot.db"
    db = DatabaseManager(str(source))
    try:
        meeting = db.create_meeting({
            "meeting_number": "BK-100",
            "subject": "پرونده آزمایشی بکاپ",
            "meeting_date": date.today(),
            "due_date": date.today(),
        })
        db.backup_database(str(backup))

        assert backup.is_file()
        with sqlite3.connect(str(backup)) as conn:
            assert conn.execute("PRAGMA quick_check").fetchone()[0] == "ok"
            assert conn.execute(
                "SELECT meeting_number FROM meetings WHERE id = ?",
                (meeting.id,),
            ).fetchone()[0] == "BK-100"
            assert conn.execute(
                "SELECT COUNT(*) FROM workflow_steps WHERE meeting_id = ?",
                (meeting.id,),
            ).fetchone()[0] == 6
    finally:
        db.close()


def test_backup_refuses_to_overwrite_live_database(tmp_path):
    source = tmp_path / "source.db"
    db = DatabaseManager(str(source))
    try:
        with pytest.raises(ValueError, match="نباید با فایل دیتابیس اصلی"):
            db.backup_database(str(source))
        assert source.is_file()
        with sqlite3.connect(str(source)) as conn:
            assert conn.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    finally:
        db.close()


def test_failed_backup_does_not_leave_temporary_file(tmp_path, monkeypatch):
    source = tmp_path / "source.db"
    destination = tmp_path / "backup.db"
    db = DatabaseManager(str(source))
    try:
        original_connect = sqlite3.connect

        def fail_for_temporary(path, *args, **kwargs):
            if str(path).endswith(".tmp"):
                raise sqlite3.OperationalError("simulated backup failure")
            return original_connect(path, *args, **kwargs)

        monkeypatch.setattr("db.manager.sqlite3.connect", fail_for_temporary)
        with pytest.raises(RuntimeError, match="تهیه بکاپ دیتابیس ناموفق بود"):
            db.backup_database(str(destination))
        assert not destination.exists()
        assert not (tmp_path / "backup.db.tmp").exists()
    finally:
        db.close()
