# -*- coding: utf-8 -*-
"""Smoke tests for database initialization and local SQLite compatibility."""
from __future__ import annotations

from db.manager import DatabaseManager
from db.models import User


def test_database_manager_initializes_local_sqlite(tmp_path):
    database_file = tmp_path / "meetings.db"
    db = DatabaseManager(str(database_file))
    try:
        assert db.engine.dialect.name == "sqlite"
        with db.engine.connect() as connection:
            assert connection.exec_driver_sql("PRAGMA journal_mode").scalar().lower() == "delete"
            assert connection.exec_driver_sql("PRAGMA busy_timeout").scalar() == 30000
        with db.session() as session:
            admin = session.query(User).filter_by(username="admin").one()
            assert admin.is_active is True
            assert admin.must_change_password is True
        assert database_file.exists()
    finally:
        db.close()


def test_database_manager_accepts_sqlite_url(tmp_path):
    database_file = (tmp_path / "url-db.db").as_posix()
    db = DatabaseManager(f"sqlite:///{database_file}")
    try:
        assert db.engine.dialect.name == "sqlite"
    finally:
        db.close()
