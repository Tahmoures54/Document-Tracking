# -*- coding: utf-8 -*-
"""Tests for password hashing and transparent legacy-hash migration."""
from __future__ import annotations

import hashlib

from db.manager import DatabaseManager
from db.models import User
from security.passwords import verify_password as verify_pbkdf2


def test_new_password_hashes_are_salted_pbkdf2():
    from db.manager import hash_password

    first = hash_password("CorrectHorse9")
    second = hash_password("CorrectHorse9")

    assert first.startswith("pbkdf2_sha256$210000$")
    assert first != second
    assert verify_pbkdf2("CorrectHorse9", first)
    assert not verify_pbkdf2("wrong-password", first)


def test_legacy_sha256_hash_is_upgraded_after_successful_login(tmp_path):
    db = DatabaseManager(str(tmp_path / "password-migration.db"))
    try:
        with db.session() as session:
            user = session.query(User).filter_by(username="admin").one()
            user.password_hash = hashlib.sha256("legacy-pass".encode("utf-8")).hexdigest()
            user.must_change_password = False
            session.commit()
            user_id = user.id

        authenticated = db.authenticate("admin", "legacy-pass")
        assert authenticated is not None

        with db.session() as session:
            user = session.get(User, user_id)
            assert user is not None
            assert user.password_hash.startswith("pbkdf2_sha256$")
            assert verify_pbkdf2("legacy-pass", user.password_hash)
    finally:
        db.close()


def test_wrong_password_does_not_upgrade_legacy_hash(tmp_path):
    db = DatabaseManager(str(tmp_path / "password-failure.db"))
    try:
        legacy_hash = hashlib.sha256("legacy-pass".encode("utf-8")).hexdigest()
        with db.session() as session:
            user = session.query(User).filter_by(username="admin").one()
            user.password_hash = legacy_hash
            user.must_change_password = False
            session.commit()

        assert db.authenticate("admin", "incorrect") is None
        with db.session() as session:
            user = session.query(User).filter_by(username="admin").one()
            assert user.password_hash == legacy_hash
    finally:
        db.close()
