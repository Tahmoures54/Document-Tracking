# -*- coding: utf-8 -*-
"""
db.manager
مدیریت ارتباط با پایگاه داده SQLite با استفاده از SQLAlchemy ORM
شامل فرآیندهای خودکار مهاجرت داده (Migration)، ممیزی (Audit)، مدیریت تراکنش‌ها و بکاپ ایمن
نسخه نهایی: هماهنگ‌سازی کامل با منطق «ارسال به پیمانکار = اتمام کار» و حذف فیلدهای منسوخ پاسخ پیمانکار
"""
from __future__ import annotations

import hashlib
import logging
import os
import shutil
import sqlite3
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import asc, and_, case, create_engine, desc, func, or_, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload, sessionmaker

from config import Roles
from db.models import (
    Base,
    Meeting,
    User,
    AuditLog,
    WorkflowStep,
)

# بارگذاری وضعیت‌های استاندارد از مدل با لایه پشتیبان ایمن
try:
    from db.models import STATUS_COMPLETED, STATUS_PENDING, STATUS_AWAITING, STATUS_CANCELLED, STATUS_RETURNED
except ImportError:
    STATUS_PENDING = "در دست بررسی"
    STATUS_AWAITING = "در انتظار تأیید"
    STATUS_COMPLETED = "تکمیل شده"
    STATUS_CANCELLED = "لغو شده"
    STATUS_RETURNED = "بازگشت داده شده"

logger = logging.getLogger(__name__)

# مقدار نگهبان برای تشخیص عدم ارسال پارامترها و امکان تنظیم فیلدها به مقدار NULL واقعی
_UNSET = object()

# وضعیت‌های باز و نیازمند پیگیری (شامل بازگشت داده شده)
OPEN_STATUSES = [STATUS_PENDING, STATUS_AWAITING, STATUS_RETURNED]


# ─────────────────────────────────────────────────────────────
# توابع کمکی امنیت و احراز هویت
# ─────────────────────────────────────────────────────────────
def hash_password(password: str) -> str:
    """هش کردن رمز عبور با استفاده از SHA-256"""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """بررسی صحت رمز عبور وارد شده با هش ذخیره شده در دیتابیس"""
    return hash_password(plain_password) == hashed_password


class DatabaseManager:
    """مدیر پایگاه داده سیستم پیگیری اسناد و گردش کار صورتجلسات."""

    def __init__(self, db_path: str):
        self.db_path = os.path.abspath(db_path)

        # تبدیل مسیر دیتابیس به فرمت استاندارد URL برای SQLAlchemy
        normalized_path = self.db_path.replace(os.sep, "/")
        sqlite_url = f"sqlite:///{normalized_path}"
        
        # پیکربندی اتصال به گونه‌ای که تراکنش‌های ترد‌های موازی قفل نشوند
        self.engine = create_engine(
            sqlite_url,
            future=True,
            echo=False,
            connect_args={
                "timeout": 20,
                "check_same_thread": False,  # مجاز بودن دسترسی از ترد‌های کمکی مانند Workerها
            },
        )

        self.SessionLocal = sessionmaker(
            bind=self.engine,
            autoflush=False,
            expire_on_commit=False,
            future=True,
        )

        self._init_db()

    def __enter__(self) -> DatabaseManager:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def session(self) -> Session:
        """ارائه یک نمونه سشن جدید برای تراکنش‌های دیتابیس."""
        return self.SessionLocal()

    # ─────────────────────────────────────────────────────────────
    # تنظیمات کارایی، ایندکس‌ها و لایه‌های مهاجرت (Migrations)
    # ─────────────────────────────────────────────────────────────
    def _init_db(self) -> None:
        """فعال‌سازی WAL Mode، ساخت جداول، اجرای مهاجرت‌ها و ایندکس‌گذاری صریح."""
        try:
            with self.engine.begin() as conn:
                # اعمال تنظیمات سرعت و کارایی فوق‌العاده بالا برای SQLite
                conn.execute(text("PRAGMA foreign_keys=ON;"))
                conn.execute(text("PRAGMA journal_mode=WAL;"))  # عدم قفل شدن خواندن در حین نوشتن
                conn.execute(text("PRAGMA synchronous=NORMAL;"))
                conn.execute(text("PRAGMA temp_store=MEMORY;"))
                conn.execute(text("PRAGMA busy_timeout=8000;"))
                conn.execute(text("PRAGMA cache_size=-20000;"))  # تخصیص ۲۰ مگابایت حافظه کش رم
        except Exception as exc:
            logger.warning("PRAGMA performance configuration failed: %s", exc)

        # ساخت جداول در صورت عدم وجود
        Base.metadata.create_all(self.engine)

        # اجرای زنجیره‌ای مهاجرت‌های ایمن برای دیتابیس‌های قدیمی مشتریان
        self._migrate_add_discipline()
        self._migrate_add_soft_delete()
        self._migrate_add_tracking_fields()

        # بهینه‌سازی سرعت جستجوها
        self._ensure_indexes()
        self._ensure_default_admin()

    def _migrate_add_discipline(self) -> None:
        """افزودن ستون دیسیپلین به جدول meetings در دیتابیس‌های قدیمی."""
        try:
            with self.engine.begin() as conn:
                result = conn.execute(text("PRAGMA table_info(meetings);"))
                columns = [row[1] for row in result.fetchall()]
                if "discipline" not in columns:
                    conn.execute(text("ALTER TABLE meetings ADD COLUMN discipline VARCHAR;"))
                    logger.info("Migration Applied: Column 'discipline' added successfully.")
        except SQLAlchemyError as exc:
            logger.warning("Migration '_migrate_add_discipline' failed: %s", exc)

    def _migrate_add_soft_delete(self) -> None:
        """افزودن قابلیت حذف نرم (Soft Delete) به جداول قدیمی بدون از دست رفتن داده‌ها."""
        try:
            with self.engine.begin() as conn:
                result = conn.execute(text("PRAGMA table_info(meetings);"))
                columns = [row[1] for row in result.fetchall()]
                if "is_deleted" not in columns:
                    conn.execute(text("ALTER TABLE meetings ADD COLUMN is_deleted BOOLEAN NOT NULL DEFAULT 0;"))
                if "deleted_at" not in columns:
                    conn.execute(text("ALTER TABLE meetings ADD COLUMN deleted_at DATETIME;"))
                if "deleted_by" not in columns:
                    conn.execute(text("ALTER TABLE meetings ADD COLUMN deleted_by VARCHAR;"))
        except SQLAlchemyError as exc:
            logger.warning("Migration '_migrate_add_soft_delete' failed: %s", exc)

    def _migrate_add_tracking_fields(self) -> None:
        """
        افزودن ستون تاریخ پاسخ پیمانکار (فقط این فیلد حفظ شده است)
        و عطف ممیزی سوابق (audit_logs.meeting_id).
        فیلدهای contractor_response_status و contractor_response_note حذف شده‌اند.
        """
        try:
            with self.engine.begin() as conn:
                cols = [row[1] for row in conn.execute(text("PRAGMA table_info(meetings);")).fetchall()]
                if "contractor_response_date" not in cols:
                    conn.execute(text("ALTER TABLE meetings ADD COLUMN contractor_response_date DATE;"))

                acols = [row[1] for row in conn.execute(text("PRAGMA table_info(audit_logs);")).fetchall()]
                if "meeting_id" not in acols:
                    conn.execute(text("ALTER TABLE audit_logs ADD COLUMN meeting_id INTEGER;"))
        except Exception as exc:
            logger.warning("Tracking fields migration failed: %s", exc)

    def _ensure_indexes(self) -> None:
        """ایجاد ایندکس‌های تخصصی و مرکب جهت افزایش سرعت لود جداول پر حجم."""
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_meetings_number     ON meetings(meeting_number);",
            "CREATE INDEX IF NOT EXISTS idx_meetings_status     ON meetings(status);",
            "CREATE INDEX IF NOT EXISTS idx_meetings_due        ON meetings(due_date);",
            "CREATE INDEX IF NOT EXISTS idx_meetings_employer   ON meetings(employer);",
            "CREATE INDEX IF NOT EXISTS idx_meetings_contractor ON meetings(contractor);",
            "CREATE INDEX IF NOT EXISTS idx_meetings_subject    ON meetings(subject);",
            "CREATE INDEX IF NOT EXISTS idx_meetings_drawing    ON meetings(drawing_number);",
            "CREATE INDEX IF NOT EXISTS idx_meetings_discipline ON meetings(discipline);",
            "CREATE INDEX IF NOT EXISTS idx_meetings_deleted    ON meetings(is_deleted);",
            "CREATE INDEX IF NOT EXISTS idx_meetings_sent       ON meetings(sent_to_contractor_date);",
            "CREATE INDEX IF NOT EXISTS idx_audit_ts            ON audit_logs(ts);",
            "CREATE INDEX IF NOT EXISTS idx_audit_user          ON audit_logs(user_id);",
            "CREATE INDEX IF NOT EXISTS idx_audit_meeting       ON audit_logs(meeting_id);",
            "CREATE INDEX IF NOT EXISTS idx_workflow_meeting    ON workflow_steps(meeting_id);",
            "CREATE INDEX IF NOT EXISTS idx_workflow_order      ON workflow_steps(step_order);",
            "CREATE INDEX IF NOT EXISTS idx_workflow_resp       ON workflow_steps(responsible_person);",
            "CREATE INDEX IF NOT EXISTS idx_workflow_status     ON workflow_steps(status);",
        ]
        try:
            with self.engine.begin() as conn:
                for stmt in indexes:
                    try:
                        conn.execute(text(stmt))
                    except SQLAlchemyError:
                        pass
        except SQLAlchemyError as exc:
            logger.warning("Index optimization failed: %s", exc)

    def _ensure_default_admin(self) -> None:
        """تضمین وجود حداقل یک کاربر مدیر (admin) در دیتابیس برای جلوگیری از بن‌بست سیستم."""
        with self.session() as sess:
            any_user = sess.query(User.id).first()
            if any_user:
                return
            u = User(
                username="admin",
                password_hash=hash_password("admin"),
                role=Roles.ADMIN.value,
                is_active=True,
                must_change_password=True,
            )
            sess.add(u)
            sess.commit()

            sess.add(
                AuditLog(
                    user_id=u.id,
                    username=u.username,
                    action="SEED_ADMIN",
                    details="Default system admin seeded successfully",
                )
            )
            sess.commit()
            logger.info("Bootstrap: Default administrator account established.")

    def close(self) -> None:
        self.engine.dispose()
        logger.info("Database connection pool disposed.")

    # ─────────────────────────────────────────────────────────────
    # ممیزی و مانیتورینگ سوابق تغییرات (Audit Trail)
    # ─────────────────────────────────────────────────────────────
    def audit(
        self,
        user_id: Optional[int],
        username: str,
        action: str,
        details: str,
        meeting_id: Optional[int] = None,
    ) -> None:
        """ثبت سابقه عملیاتی کارشناس در لاگ‌های ممیزی سیستم."""
        try:
            with self.session() as sess:
                sess.add(
                    AuditLog(
                        user_id=user_id,
                        username=username,
                        action=action,
                        details=details,
                        meeting_id=meeting_id,
                    )
                )
                sess.commit()
        except Exception as exc:
            logger.error("Audit logging failed: %s", exc)

    # ─────────────────────────────────────────────────────────────
    # مدیریت حساب‌های کاربری و احراز هویت
    # ─────────────────────────────────────────────────────────────
    def authenticate(self, username: str, password: str) -> Optional[User]:
        with self.session() as sess:
            u = sess.query(User).filter(User.username == username).one_or_none()
            if not u or not u.is_active:
                self.audit(None, username, "LOGIN_FAIL", "Account inactive or does not exist")
                return None
            if not verify_password(password, u.password_hash):
                self.audit(u.id, u.username, "LOGIN_FAIL", "Invalid credential attempt")
                return None
            self.audit(u.id, u.username, "LOGIN_OK", "Success login")
            return u

    def change_password(self, user_id: int, new_password: str) -> None:
        with self.session() as sess:
            u = sess.get(User, user_id)
            if not u:
                raise ValueError("کاربر یافت نشد.")
            u.password_hash = hash_password(new_password)
            u.must_change_password = False
            sess.commit()

    def get_user(self, user_id: int) -> Optional[User]:
        with self.session() as sess:
            return sess.get(User, user_id)

    def get_user_by_username(self, username: str) -> Optional[User]:
        with self.session() as sess:
            return sess.query(User).filter(User.username == username).one_or_none()

    def get_all_users(self) -> List[User]:
        with self.session() as sess:
            return sess.query(User).order_by(User.id.asc()).all()

    def active_usernames(self) -> List[str]:
        """فهرست نام کاربری افراد فعال جهت نمایش در تخصیص مسئول گردش کار."""
        with self.session() as sess:
            rows = (
                sess.query(User.username)
                .filter(User.is_active.is_(True))
                .order_by(User.username.asc())
                .all()
            )
        return [r[0] for r in rows if r and r[0]]

    @staticmethod
    def _convert_role(role: Any) -> str:
        if isinstance(role, Roles):
            return role.value
        return str(role)

    def create_user(
        self,
        username: str,
        password: str,
        role: Any,
        is_active: bool = True,
        must_change_password: bool = True,
    ) -> User:
        role_str = self._convert_role(role)
        with self.session() as sess:
            exists = sess.query(User.id).filter(User.username == username).first()
            if exists:
                raise ValueError("نام کاربری پیش از این ثبت شده است.")
            u = User(
                username=username,
                password_hash=hash_password(password),
                role=role_str,
                is_active=is_active,
                must_change_password=must_change_password,
            )
            sess.add(u)
            sess.commit()
            self.audit(u.id, "system", "USER_CREATE", f"username={username}, role={role_str}")
            return u

    def update_user(self, user_id: int, **kwargs) -> Optional[User]:
        allowed = {"username", "role", "is_active", "must_change_password", "password_hash"}
        for k in kwargs:
            if k not in allowed:
                raise ValueError(f"فیلد غیرمجاز جهت ویرایش مستقیم: {k}")

        if "role" in kwargs:
            kwargs["role"] = self._convert_role(kwargs["role"])

        with self.session() as sess:
            u = sess.get(User, user_id)
            if not u:
                return None
            for k, v in kwargs.items():
                setattr(u, k, v)
            sess.commit()
            return u

    def delete_user(self, user_id: int) -> bool:
        with self.session() as sess:
            u = sess.get(User, user_id)
            if not u:
                return False
            sess.delete(u)
            sess.commit()
            self.audit(user_id, "system", "USER_DELETE", f"user_id={user_id}")
            return True

    # ─────────────────────────────────────────────────────────────
    # فرآیندهای اصلی و عملیاتی صورتجلسات (MOM CRUD)
    # ─────────────────────────────────────────────────────────────
    def create_meeting(self, data: Dict[str, Any]) -> Meeting:
        with self.session() as sess:
            m = Meeting(**data)
            sess.add(m)
            sess.commit()
            self.initialize_workflow(m.id)
            return m

    def get_meeting(self, meeting_id: int) -> Optional[Meeting]:
        with self.session() as sess:
            m = sess.get(Meeting, meeting_id)
            return m if m and not m.is_deleted else None

    def get_meeting_by_number(self, number: str) -> Optional[Meeting]:
        with self.session() as sess:
            return (
                sess.query(Meeting)
                .filter(Meeting.meeting_number == number, Meeting.is_deleted.is_(False))
                .one_or_none()
            )

    def update_meeting(self, meeting_id: int, data: Dict[str, Any]) -> Optional[Meeting]:
        with self.session() as sess:
            m = sess.get(Meeting, meeting_id)
            if not m or m.is_deleted:
                return None
            for k, v in data.items():
                setattr(m, k, v)
            sess.commit()
            return m

    def delete_meeting(self, meeting_id: int, deleted_by: str = "system") -> bool:
        """حذف منطقی (Soft Delete) پرونده جهت حفظ تبارنامه ممیزی و امنیت اطلاعات."""
        with self.session() as sess:
            m = sess.get(Meeting, meeting_id)
            if not m or m.is_deleted:
                return False
            m.is_deleted = True
            m.deleted_at = datetime.now(timezone.utc)
            m.deleted_by = deleted_by
            sess.commit()
            self.audit(
                None, deleted_by, "MEETING_SOFT_DELETE",
                f"meeting_id={meeting_id}; number={m.meeting_number}"
            )
            return True

    def bulk_delete_meetings(self, ids: List[int], deleted_by: str = "system") -> int:
        if not ids:
            return 0
        count = 0
        for mid in ids:
            if self.delete_meeting(mid, deleted_by=deleted_by):
                count += 1
        return count

    def is_duplicate_meeting_number(self, number: str, exclude_id: Optional[int] = None) -> bool:
        with self.session() as sess:
            q = sess.query(Meeting.id).filter(Meeting.meeting_number == number, Meeting.is_deleted.is_(False))
            if exclude_id is not None:
                q = q.filter(Meeting.id != exclude_id)
            return q.first() is not None

    def get_previous_meeting(self, exclude_id: Optional[int] = None) -> Optional[Meeting]:
        with self.session() as sess:
            q = sess.query(Meeting).filter(Meeting.is_deleted.is_(False)).order_by(Meeting.id.desc())
            if exclude_id is not None:
                q = q.filter(Meeting.id != exclude_id)
            return q.first()

    # ─────────────────────────────────────────────────────────────
    # موتور فیلترینگ و کوئری‌های پیشرفته تحت وب و کلاینت
    # ─────────────────────────────────────────────────────────────
    def query_meetings_page(
        self,
        filters: Dict[str, str],
        search: str,
        order_by: str,
        order_dir: str,
        limit: int,
        offset: int,
    ) -> Tuple[List[Meeting], int]:
        safe_cols = {
            "id":                      "id",
            "meeting_number":          "meeting_number",
            "meeting_date":            "meeting_date",
            "due_date":                "due_date",
            "status":                  "status",
            "priority":                "priority",
            "employer":                "employer",
            "contractor":              "contractor",
            "subject":                 "subject",
            "discipline":              "discipline",
            "entry_date":              "entry_date",
            "closing_date":            "closing_date",
            "sent_to_contractor_date": "sent_to_contractor_date",
            "contract_date":           "contract_date",
        }
        col_name = safe_cols.get(order_by, "id")
        column = getattr(Meeting, col_name, Meeting.id)
        direction = desc if order_dir.upper() == "DESC" else asc

        conditions = []

        for k in ("status", "priority", "employer", "contractor", "discipline"):
            v = (filters.get(k) or "").strip()
            if v and v != "همه":
                conditions.append(getattr(Meeting, k) == v)

        s = (search or "").strip()
        if s:
            like = f"%{s}%"
            conditions.append(
                or_(
                    Meeting.subject.like(like),
                    Meeting.meeting_number.like(like),
                    Meeting.drawing_number.like(like),
                    Meeting.employer.like(like),
                    Meeting.contractor.like(like),
                    Meeting.consultant.like(like),
                    Meeting.discipline.like(like),
                )
            )

        with self.session() as sess:
            # بارگذاری ایگرگر (Eager Load) به منظور ممانعت از ایجاد کوئری‌های N+1 سنگین
            q = (
                sess.query(Meeting)
                .options(selectinload(Meeting.workflow_steps))
                .filter(Meeting.is_deleted.is_(False))
            )
            if conditions:
                q = q.filter(and_(*conditions))

            total = q.count()
            rows = (
                q.order_by(direction(column))
                 .limit(limit)
                 .offset(offset)
                 .all()
            )
            return rows, int(total)

    def distinct_values(self, column: str, limit: int = 5000) -> List[str]:
        safe = {
            "status",
            "priority",
            "employer",
            "consultant",
            "contractor",
            "drawing_number",
            "contract_number",
            "discipline",
        }
        if column not in safe:
            raise ValueError(f"Unsafe column: {column}")

        with self.session() as sess:
            col = getattr(Meeting, column)
            rows = (
                sess.query(col)
                .filter(Meeting.is_deleted.is_(False), col.isnot(None), func.trim(col) != "")
                .distinct()
                .order_by(col)
                .limit(limit)
                .all()
            )
        return [str(r[0]) for r in rows if r and r[0] is not None]

    def status_priority_counts(self, filters: Dict[str, str], search: str) -> Dict[str, int]:
        conditions = []
        for k in ("status", "priority", "employer", "contractor", "discipline"):
            v = (filters.get(k) or "").strip()
            if v and v != "همه":
                conditions.append(getattr(Meeting, k) == v)

        s = (search or "").strip()
        if s:
            like = f"%{s}%"
            conditions.append(
                or_(
                    Meeting.subject.like(like),
                    Meeting.meeting_number.like(like),
                    Meeting.drawing_number.like(like),
                    Meeting.employer.like(like),
                    Meeting.contractor.like(like),
                    Meeting.discipline.like(like),
                )
            )

        with self.session() as sess:
            q = sess.query(Meeting.status, Meeting.priority, func.count(Meeting.id)).filter(Meeting.is_deleted.is_(False))
            if conditions:
                q = q.filter(and_(*conditions))
            rows = (
                q.group_by(Meeting.status, Meeting.priority)
                 .order_by(func.count(Meeting.id).desc())
                 .all()
            )

        out: Dict[str, int] = {}
        for st, pr, c in rows:
            st = (st or "").strip() or "نامشخص"
            pr = (pr or "").strip() or "نامشخص"
            key = f"{st} | {pr}" if pr != "نامشخص" else st
            out[key] = int(c or 0)
        return out

    def get_dashboard_stats(self) -> Dict[str, int]:
        today = date.today()
        with self.session() as sess:
            total = sess.query(func.count(Meeting.id)).filter(Meeting.is_deleted.is_(False)).scalar()
            pending = sess.query(func.count(Meeting.id)).filter(Meeting.is_deleted.is_(False), Meeting.status == STATUS_PENDING).scalar()
            delayed = sess.query(func.count(Meeting.id)).filter(
                Meeting.is_deleted.is_(False),
                Meeting.due_date < today,
                Meeting.status.in_(OPEN_STATUSES),
            ).scalar()
            completed = sess.query(func.count(Meeting.id)).filter(Meeting.is_deleted.is_(False), Meeting.status == STATUS_COMPLETED).scalar()

        return {
            "total": int(total or 0),
            "pending": int(pending or 0),
            "delayed": int(delayed or 0),
            "completed": int(completed or 0),
        }

    def assign_meeting_to_user(self, meeting_id: int, username: str, actor: str = "system") -> bool:
        steps = self.get_workflow_steps(meeting_id)
        if not steps:
            self.initialize_workflow(meeting_id)
            steps = self.get_workflow_steps(meeting_id)
        target = next((x for x in steps if x.step_order == 3), None)
        if not target:
            return False
        self.update_workflow_step(target.id, responsible_person=username, status="pending")
        self.audit(None, actor, "MEETING_ASSIGNED", f"assigned_to={username}", meeting_id=meeting_id)
        return True

    def set_contractor_response(
        self,
        meeting_id: int,
        response_date=None,
        actor: str = "system"
    ) -> bool:
        """
        ثبت تاریخ پاسخ پیمانکار (نسخه ساده‌سازی شده).
        بر اساس منطق طلایی، تاریخ ارسال به پیمانکار = تاریخ پاسخ = تاریخ بسته شدن پرونده.
        """
        with self.session() as sess:
            m = sess.get(Meeting, meeting_id)
            if not m or m.is_deleted:
                return False
            if response_date is not None:
                m.contractor_response_date = response_date
                # هم‌زمان تاریخ ارسال و بسته شدن هم مقداردهی می‌شوند
                if not m.sent_to_contractor_date:
                    m.sent_to_contractor_date = response_date
                if not m.closing_date:
                    m.closing_date = response_date
            sess.commit()
        self.audit(
            None, actor, "CONTRACTOR_RESPONSE",
            f"response_date={response_date}",
            meeting_id=meeting_id
        )
        return True

    def get_meeting_history(self, meeting_id: int, limit: int = 100) -> List[AuditLog]:
        with self.session() as sess:
            return sess.query(AuditLog).filter(AuditLog.meeting_id == meeting_id).order_by(AuditLog.ts.desc()).limit(limit).all()

    def operational_metrics(self) -> Dict[str, int]:
        """
        محاسبه معیارهای عملیاتی و آمارهای کلیدی سیستم پیگیری صورتجلسات
        هماهنگ با منطق طلایی «ارسال به پیمانکار = اتمام کار»
        (حذف کامل وابستگی به فیلدهای منسوخ contractor_response_status)
        """
        from datetime import timedelta
        today = date.today()
        three_days_later = today + timedelta(days=3)

        try:
            with self.session() as sess:
                # پایه اصلی کوئری: صورتجلسات حذف نشده
                base = sess.query(Meeting).filter(Meeting.is_deleted.is_(False))

                total = base.count()

                # صورتجلسات باز (پرونده هنوز ابلاغ نشده و لغو نشده)
                open_count = base.filter(
                    Meeting.sent_to_contractor_date.is_(None),
                    Meeting.status != STATUS_CANCELLED
                ).count()

                # صورتجلسات تأخیردار (مهلت گذشته و هنوز ابلاغ نشده)
                overdue = base.filter(
                    Meeting.due_date < today,
                    Meeting.sent_to_contractor_date.is_(None),
                    Meeting.status != STATUS_CANCELLED
                ).count()

                # صورتجلسات در آستانه سررسید (۳ روز آینده)
                due_3 = base.filter(
                    Meeting.due_date >= today,
                    Meeting.due_date <= three_days_later,
                    Meeting.sent_to_contractor_date.is_(None),
                    Meeting.status != STATUS_CANCELLED
                ).count()

                # در انتظار ابلاغ به پیمانکار (پرونده‌های باز)
                waiting_contractor = base.filter(
                    Meeting.sent_to_contractor_date.is_(None),
                    Meeting.status != STATUS_CANCELLED
                ).count()

                # پرونده‌های ابلاغ شده (پاسخ داده شده)
                answered = base.filter(
                    Meeting.sent_to_contractor_date.is_not(None)
                ).count()

                # پرونده‌های کاملاً تکمیل و بایگانی شده
                completed = base.filter(
                    Meeting.sent_to_contractor_date.is_not(None)
                ).count()

                return {
                    "total": total,
                    "open": open_count,
                    "overdue": overdue,
                    "due_3": due_3,
                    "waiting_contractor": waiting_contractor,
                    "answered": answered,
                    "completed": completed,
                }
        except Exception:
            logger.exception("Failed to calculate operational metrics")
            return {
                "total": 0,
                "open": 0,
                "overdue": 0,
                "due_3": 0,
                "waiting_contractor": 0,
                "answered": 0,
                "completed": 0,
            }

    # ─────────────────────────────────────────────────────────────
    # موتور گردش کار صورتجلسات (MOM Workflow Engine)
    # ─────────────────────────────────────────────────────────────
    def initialize_workflow(self, meeting_id: int) -> None:
        """ثبت سوابق و مراحل گردش کار شش‌گانه سازمانی به صورت پیش‌فرض."""
        steps = [
            ("ورود به دفتر کارفرما",              1),
            ("ورود به دفتر رئیس دفتر فنی",       2),
            ("ورود به دفتر کارشناس",              3),
            ("ورود مجدد به دفتر رئیس دفتر فنی",  4),
            ("خروج از دفتر مدیر سایت",            5),
            ("تحویل به پیمانکار",                 6),
        ]
        with self.session() as sess:
            exists = sess.query(WorkflowStep.id).filter(WorkflowStep.meeting_id == meeting_id).first()
            if exists:
                return

            for name, order in steps:
                sess.add(
                    WorkflowStep(
                        meeting_id=meeting_id,
                        step_name=name,
                        step_order=order,
                        status="pending",
                    )
                )
            sess.commit()

    def get_workflow_steps(self, meeting_id: int) -> List[WorkflowStep]:
        with self.session() as sess:
            return (
                sess.query(WorkflowStep)
                .filter(WorkflowStep.meeting_id == meeting_id)
                .order_by(WorkflowStep.step_order)
                .all()
            )

    def update_workflow_step(
        self,
        step_id: int,
        entry_date: Any = _UNSET,
        exit_date: Any = _UNSET,
        responsible_person: Any = _UNSET,
        signature: Any = _UNSET,
        status: Any = _UNSET,
        notes: Any = _UNSET,
    ) -> Optional[WorkflowStep]:
        with self.session() as sess:
            step = sess.get(WorkflowStep, step_id)
            if not step:
                return None

            if entry_date is not _UNSET:
                step.entry_date = entry_date
            if exit_date is not _UNSET:
                step.exit_date = exit_date
            if responsible_person is not _UNSET:
                step.responsible_person = responsible_person
            if signature is not _UNSET:
                step.signature = signature
            if status is not _UNSET:
                step.status = status
            if notes is not _UNSET:
                step.notes = notes

            sess.commit()
            return step

    def get_current_workflow_status(self, meeting_id: int) -> Dict[str, Any]:
        steps = self.get_workflow_steps(meeting_id)
        current_step = None
        for step in steps:
            if step.status in ["pending", "in_progress"]:
                current_step = step
                break
        if not current_step and steps:
            current_step = steps[-1]

        def step_to_dict(s: WorkflowStep) -> Dict[str, Any]:
            return {
                "id": s.id,
                "meeting_id": s.meeting_id,
                "step_name": s.step_name,
                "step_order": s.step_order,
                "status": s.status,
                "entry_date": s.entry_date.isoformat() if s.entry_date else None,
                "exit_date": s.exit_date.isoformat() if s.exit_date else None,
                "responsible_person": s.responsible_person,
                "signature": s.signature,
                "notes": s.notes,
            }

        return {
            "current_step": step_to_dict(current_step) if current_step else None,
            "all_steps": [step_to_dict(s) for s in steps],
            "is_completed": bool(steps) and all(s.status == "completed" for s in steps),
        }

    def workflow_performance_by_user(
        self,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> List[Dict[str, Any]]:
        """گزارش راندمان زمانی تاییدات کارشناسان فنی سامانه."""
        with self.session() as sess:
            q = (
                sess.query(
                    WorkflowStep.responsible_person.label("user"),
                    func.count(WorkflowStep.id).label("total"),
                    func.sum(case((WorkflowStep.status == "completed", 1), else_=0)).label("completed"),
                    func.sum(case((WorkflowStep.status == "in_progress", 1), else_=0)).label("in_progress"),
                    func.sum(case((WorkflowStep.status == "pending", 1), else_=0)).label("pending"),
                    func.sum(case((WorkflowStep.status == "rejected", 1), else_=0)).label("rejected"),
                    func.avg(
                        case(
                            (
                                and_(
                                    WorkflowStep.status == "completed",
                                    WorkflowStep.entry_date.isnot(None),
                                    WorkflowStep.exit_date.isnot(None),
                                ),
                                func.julianday(WorkflowStep.exit_date) - func.julianday(WorkflowStep.entry_date),
                            ),
                            else_=None,
                        )
                    ).label("avg_days"),
                )
                .filter(
                    WorkflowStep.responsible_person.isnot(None),
                    func.trim(WorkflowStep.responsible_person) != "",
                )
            )

            if from_date:
                q = q.filter(WorkflowStep.entry_date >= from_date)
            if to_date:
                q = q.filter(WorkflowStep.entry_date <= to_date)

            rows = (
                q.group_by(WorkflowStep.responsible_person)
                 .order_by(func.count(WorkflowStep.id).desc())
                 .all()
            )

        out: List[Dict[str, Any]] = []
        for user, total, completed, in_progress, pending, rejected, avg_days in rows:
            out.append(
                {
                    "user": str(user),
                    "total": int(total or 0),
                    "completed": int(completed or 0),
                    "in_progress": int(in_progress or 0),
                    "pending": int(pending or 0),
                    "rejected": int(rejected or 0),
                    "avg_days": float(avg_days) if avg_days is not None else None,
                }
            )
        return out

    # ─────────────────────────────────────────────────────────────
    # متدهای نگهداری پایگاه داده و بکاپ WAL-Safe
    # ─────────────────────────────────────────────────────────────
    def vacuum(self) -> None:
        """فشرده‌سازی فیزیکی و بهینه‌سازی جداول دیتابیس SQLite."""
        with self.engine.begin() as conn:
            conn.execute(text("VACUUM;"))

    def backup_database(self, destination: str) -> None:
        """بکاپ ایمن و زنده (Hot Backup) بدون قفل کردن فرآیندهای خواندن/نوشتن فعال WAL."""
        destination = os.path.abspath(destination)
        dest_dir = os.path.dirname(destination)
        if dest_dir and not os.path.isdir(dest_dir):
            os.makedirs(dest_dir, exist_ok=True)

        try:
            # استفاده از API رسمی برای کپی تراکنشی صفحات دیتابیس
            src = sqlite3.connect(self.db_path)
            try:
                dst = sqlite3.connect(destination)
                try:
                    src.backup(dst)
                    dst.commit()
                finally:
                    dst.close()
            finally:
                src.close()

            logger.info("Hot-backup written successfully: %s", destination)

        except Exception as exc:
            logger.exception("Transactional backup failed, entering fallback copy engine: %s", exc)
            try:
                shutil.copy2(self.db_path, destination)
                logger.info("Fallback copy-backup generated: %s", destination)
            except Exception as copy_exc:
                logger.exception("Fallback backup engine crashed: %s", copy_exc)
                raise copy_exc