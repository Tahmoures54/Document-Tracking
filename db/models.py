# -*- coding: utf-8 -*-
"""
db.models
طراحی مدل‌های پایگاه داده رابطه‌ای با SQLAlchemy ORM
نسخه نهایی و کاملاً هماهنگ:
• حذف فیلدهای منسوخ وضعیت پاسخ پیمانکار (بر اساس منطق «ارسال = اتمام کار»)
• حذف ستون‌های «لینک فایل»، «تاریخ بسته شدن» و «تاریخ پاسخ پیمانکار» از نمایش جدول اصلی
• قانون طلایی: تاریخ ارسال به پیمانکار = بسته شدن پرونده = تاریخ پاسخ پیمانکار
• هماهنگی کامل با وضعیت «بازگشت داده شده»
• ایندکس‌های ترکیبی برای بهبود سرعت کوئری‌ها
• پروپرتی‌های محاسباتی پیشرفته و متد کمکی ابلاغ
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

# ──────────────────────────────────────────────
# ثابت‌های وضعیت و اولویت (MOM Workflow Constants)
# ──────────────────────────────────────────────
STATUS_PENDING   = "در دست بررسی"
STATUS_AWAITING  = "در انتظار تأیید"
STATUS_COMPLETED = "تکمیل شده"
STATUS_CANCELLED = "لغو شده"
STATUS_RETURNED  = "بازگشت داده شده"

STATUSES: List[str] = [
    STATUS_PENDING,
    STATUS_AWAITING,
    STATUS_COMPLETED,
    STATUS_CANCELLED,
    STATUS_RETURNED,
]

OPEN_STATUSES: List[str] = [STATUS_PENDING, STATUS_AWAITING, STATUS_RETURNED]
CLOSED_STATUSES: List[str] = [STATUS_COMPLETED, STATUS_CANCELLED]

PRIORITY_HIGH   = "بالا"
PRIORITY_MEDIUM = "متوسط"
PRIORITY_LOW    = "پایین"
PRIORITIES: List[str] = [PRIORITY_HIGH, PRIORITY_MEDIUM, PRIORITY_LOW]

# ──────────────────────────────────────────────
# تخصص‌ها و دیسیپلین‌های مهندسی پروژه
# ──────────────────────────────────────────────
DISCIPLINE_CIVIL            = "عمران"
DISCIPLINE_MECHANICAL       = "مکانیک"
DISCIPLINE_ELECTRICAL       = "برق"
DISCIPLINE_INSTRUMENTATION  = "ابزار دقیق"
DISCIPLINE_ARCHITECTURE     = "معماری"
DISCIPLINE_PROCESS          = "فرآیند"
DISCIPLINE_PIPING           = "خطوط لوله"
DISCIPLINE_HSE              = "HSE"
DISCIPLINE_OTHER            = "سایر"

DISCIPLINES: List[str] = [
    DISCIPLINE_CIVIL,
    DISCIPLINE_MECHANICAL,
    DISCIPLINE_ELECTRICAL,
    DISCIPLINE_INSTRUMENTATION,
    DISCIPLINE_ARCHITECTURE,
    DISCIPLINE_PROCESS,
    DISCIPLINE_PIPING,
    DISCIPLINE_HSE,
    DISCIPLINE_OTHER,
]

# ──────────────────────────────────────────────
# نقش‌های کاربری (هم‌تراز با config.Roles)
# ──────────────────────────────────────────────
ROLE_ADMIN   = "admin"
ROLE_MANAGER = "manager"
ROLE_EDITOR  = "editor"
ROLE_USER    = "user"
ROLE_VIEWER  = "viewer"

ROLES: List[str] = [ROLE_ADMIN, ROLE_MANAGER, ROLE_EDITOR, ROLE_USER, ROLE_VIEWER]


class Meeting(Base):
    """مدل اطلاعات شناسنامه‌ای و ممیزی صورتجلسه."""

    __tablename__ = "meetings"

    id = Column(Integer, primary_key=True)

    # تاریخ‌های کنترل زمانی پروژه
    entry_date = Column(Date, default=date.today, index=True)
    meeting_date = Column(Date, nullable=False, index=True)
    due_date = Column(Date, nullable=False, index=True)
    contract_date = Column(Date)
    
    # مسیر واقعی: پیمانکار → نظارت → کارفرما
    sent_to_supervision_date = Column(Date, index=True)   # ارسال پیمانکار به نظارت
    supervision_entry_date = Column(Date, index=True)     # ورود به دفتر نظارت (دستی)

    # 🎯 تاریخ کلیدی: ابلاغ به پیمانکار = بسته شدن پرونده = تاریخ پاسخ پیمانکار = اتمام کار
    sent_to_contractor_date = Column(Date, index=True)
    closing_date = Column(Date)

    # تاریخ پاسخ پیمانکار (برای حفظ سازگاری فیزیکی با دیتابیس قدیمی نگهداری می‌شود)
    contractor_response_date = Column(Date)

    # شناسه‌ها و اطلاعات مرجع اسناد فنی
    meeting_number = Column(String, nullable=False, unique=True, index=True)
    drawing_number = Column(String, index=True)
    contract_number = Column(String, index=True)

    # ارکان پروژه
    employer = Column(String, index=True)
    consultant = Column(String)
    contractor = Column(String, index=True)

    # اطلاعات محتوایی و ضمائم
    subject = Column(String, nullable=False, index=True)
    file_link = Column(String)
    attachment_count = Column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )

    # دیسیپلین فنی، محل کار و وضعیت‌های اجرایی
    discipline = Column(String, index=True)
    location = Column(String, index=True)  # محل کار
    status = Column(
        String,
        default=STATUS_PENDING,
        server_default=STATUS_PENDING,
        nullable=False,
        index=True,
    )
    priority = Column(
        String,
        default=PRIORITY_MEDIUM,
        server_default=PRIORITY_MEDIUM,
        nullable=False,
        index=True,
    )

    # مدیریت حذف منطقی (Soft Delete)
    is_deleted = Column(
        Boolean,
        default=False,
        server_default=text("false"),
        nullable=False,
        index=True,
    )
    deleted_at = Column(DateTime)
    deleted_by = Column(String)

    # فیلدهای زمان‌بندی سیستمی
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # رابطه با مراحل گردش کار
    workflow_steps = relationship(
        "WorkflowStep",
        back_populates="meeting",
        cascade="all, delete-orphan",
        order_by="WorkflowStep.step_order",
    )

    # ایندکس‌های ترکیبی برای کوئری‌های سریع‌تر
    __table_args__ = (
        Index("idx_meeting_status_priority", "status", "priority"),
        Index("idx_meeting_active_status", "is_deleted", "status"),
        Index("idx_meeting_due_active", "due_date", "is_deleted", "status"),
        Index("idx_meeting_employer_contractor", "employer", "contractor"),
        Index("idx_meeting_discipline_priority", "discipline", "priority"),
        Index("idx_meeting_location", "location"),
        Index("idx_meeting_supervision_dates", "sent_to_supervision_date", "supervision_entry_date"),
        Index("idx_meeting_dispatch_status", "sent_to_contractor_date", "status"),
    )

    # 🎯 نگاشت هدرهای فارسی به فیلدهای مدل جهت نمایش در گرید اصلی پنجره اصلی
    # حذف ستون‌های «لینک فایل»، «تاریخ پاسخ پیمانکار» و «تاریخ بسته شدن» از گرید اصلی به سلیقه مهندسی جدید
    HEADER_TO_ATTR: Dict[str, str] = {
        "ردیف":                     "id",
        "ارسال به نظارت":           "sent_to_supervision_date",
        "ورود به نظارت":            "supervision_entry_date",
        "ورود به کارفرما":          "entry_date",
        "تاریخ صورتجلسه":           "meeting_date",
        "شماره صورتجلسه":           "meeting_number",
        "تعداد پیوست":              "attachment_count",
        "شماره نقشه":               "drawing_number",
        "کارفرما":                  "employer",
        "مشاور":                    "consultant",
        "پیمانکار":                 "contractor",
        "شماره قرارداد":            "contract_number",
        "تاریخ قرارداد":            "contract_date",
        "موضوع":                    "subject",
        "دیسیپلین":                 "discipline",
        "محل کار":                  "location",
        "تاریخ ارسال به پیمانکار":  "sent_to_contractor_date",
        "وضعیت":                    "status",
        "اولویت":                   "priority",
        "مهلت انجام":               "due_date",
    }

    @classmethod
    def headers(cls) -> List[str]:
        """لیست هدرهای فارسی برای نمایش در جدول و خروجی اکسل."""
        return list(cls.HEADER_TO_ATTR.keys())

    def to_row(self, headers: Optional[List[str]] = None) -> List[Any]:
        """تبدیل داده‌های کلاس به فرمت لیست موازی هماهنگ با هدرها."""
        if headers is None:
            headers = self.headers()

        out: List[Any] = []
        for h in headers:
            attr = self.HEADER_TO_ATTR.get(h)
            val = getattr(self, attr, "") if attr else ""

            if isinstance(val, (date, datetime)) and val:
                val = val.isoformat()

            out.append(val if val is not None else "")
        return out

    def to_dict(self) -> Dict[str, Any]:
        """تبدیل جامع مدل به دیکشنری JSON-Safe."""
        return {
            "id":                          self.id,
            "sent_to_supervision_date":    self.sent_to_supervision_date.isoformat() if self.sent_to_supervision_date else None,
            "supervision_entry_date":      self.supervision_entry_date.isoformat() if self.supervision_entry_date else None,
            "entry_date":                  self.entry_date.isoformat() if self.entry_date else None,
            "meeting_date":                self.meeting_date.isoformat() if self.meeting_date else None,
            "meeting_number":              self.meeting_number,
            "attachment_count":            self.attachment_count,
            "drawing_number":              self.drawing_number,
            "employer":                    self.employer,
            "consultant":                  self.consultant,
            "contractor":                  self.contractor,
            "contract_number":             self.contract_number,
            "contract_date":               self.contract_date.isoformat() if self.contract_date else None,
            "subject":                     self.subject,
            "discipline":                  self.discipline,
            "location":                    self.location,
            "sent_to_contractor_date":     self.sent_to_contractor_date.isoformat() if self.sent_to_contractor_date else None,
            "file_link":                   self.file_link,
            "status":                      self.status,
            "priority":                    self.priority,
            "due_date":                    self.due_date.isoformat() if self.due_date else None,
            "closing_date":                self.closing_date.isoformat() if self.closing_date else None,
            "contractor_response_date":    self.contractor_response_date.isoformat() if self.contractor_response_date else None,
            "created_at":                  self.created_at.isoformat() if self.created_at else None,
            "updated_at":                  self.updated_at.isoformat() if self.updated_at else None,
            "is_deleted":                  self.is_deleted,
            "deleted_at":                  self.deleted_at.isoformat() if self.deleted_at else None,
            "deleted_by":                  self.deleted_by,
            "is_delayed":                  self.is_delayed,
            "is_open":                     self.is_open,
            "is_dispatched":               self.is_dispatched,
            "days_until_due":              self.days_until_due,
            "dispatch_days":               self.dispatch_days,
            "progress_percentage":         self.progress_percentage,
        }

    # ──────────────────────────────────────────
    # پروپرتی‌های محاسباتی پیشرفته
    # ──────────────────────────────────────────

    @property
    def is_delayed(self) -> bool:
        """تشخیص عبور از مهلت انجام برای پرونده‌های باز."""
        if not self.due_date:
            return False
        if self.status in CLOSED_STATUSES:
            return False
        if self.is_dispatched:  # اگر ابلاغ شده باشد، تأخیر معنا ندارد
            return False
        return self.due_date < date.today()

    @property
    def is_open(self) -> bool:
        """آیا پرونده در حال جریان و باز است؟"""
        return self.status in OPEN_STATUSES

    @property
    def is_closed(self) -> bool:
        """آیا پرونده بسته و پایان یافته است؟"""
        return self.status in CLOSED_STATUSES

    @property
    def is_dispatched(self) -> bool:
        """آیا پرونده به پیمانکار ابلاغ شده و کارش تمام است؟"""
        return self.sent_to_contractor_date is not None

    @property
    def days_until_due(self) -> Optional[int]:
        """تعداد روز باقی‌مانده تا مهلت (منفی = گذشته)."""
        if not self.due_date:
            return None
        return (self.due_date - date.today()).days

    @property
    def dispatch_days(self) -> Optional[int]:
        """تعداد روزهای طی شده از تاریخ صورتجلسه تا ابلاغ به پیمانکار."""
        if not self.meeting_date or not self.sent_to_contractor_date:
            return None
        return (self.sent_to_contractor_date - self.meeting_date).days

    @property
    def has_attachments(self) -> bool:
        """آیا این صورتجلسه دارای پیوست است؟"""
        return (self.attachment_count or 0) > 0

    @property
    def current_step(self) -> Optional["WorkflowStep"]:
        """پیدا کردن گام فعال جاری فرآیند."""
        if not self.workflow_steps:
            return None
        for step in self.workflow_steps:
            if step.status in ("pending", "in_progress"):
                return step
        return self.workflow_steps[-1]

    @property
    def progress_percentage(self) -> int:
        """محاسبه درصد پیشرفت گام‌های تاییدات به صورت داینامیک."""
        if not self.workflow_steps:
            return 0
        total = len(self.workflow_steps)
        completed = sum(1 for s in self.workflow_steps if s.status == "completed")
        return int((completed / total) * 100)

    @property
    def current_responsible(self) -> str:
        """نام کارشناس مسئول گام جاری."""
        step = self.current_step
        if step and step.responsible_person:
            return step.responsible_person.strip()
        return ""

    @property
    def current_stage_name(self) -> str:
        """نام گام جاری فرآیند."""
        step = self.current_step
        if step and step.step_name:
            return step.step_name.strip()
        return ""

    # ──────────────────────────────────────────
    # 🎯 متد کمکی هوشمند: منطق طلایی ابلاغ به پیمانکار
    # ──────────────────────────────────────────

    def set_dispatched_to_contractor(self, dispatch_date: Optional[date] = None) -> None:
        """
        ابلاغ پرونده به پیمانکار طبق منطق طلایی کارگاه:
        ارسال به پیمانکار = بسته شدن پرونده = تاریخ پاسخ پیمانکار = تکمیل شده
        """
        d = dispatch_date or date.today()
        self.sent_to_contractor_date = d
        self.closing_date = d
        self.contractor_response_date = d
        self.status = STATUS_COMPLETED

    # ──────────────────────────────────────────
    # اعتبارسنجی سطح مدل
    # ──────────────────────────────────────────

    def validate(self) -> Optional[str]:
        """اعتبارسنجی سطح مدل قبل از ذخیره در پایگاه داده."""
        if not self.meeting_number or not self.meeting_number.strip():
            return "شماره صورتجلسه الزامی است."
        if not self.subject or not self.subject.strip():
            return "موضوع صورتجلسه الزامی است."
        if not self.meeting_date:
            return "تاریخ صورتجلسه الزامی است."
        if not self.due_date:
            return "مهلت انجام الزامی است."
        if self.meeting_date and self.due_date and self.due_date < self.meeting_date:
            return "مهلت انجام نمی‌تواند قبل از تاریخ صورتجلسه باشد."
        if self.status and self.status not in STATUSES:
            return f"وضعیت «{self.status}» نامعتبر است."
        if self.priority and self.priority not in PRIORITIES:
            return f"اولویت «{self.priority}» نامعتبر است."
        if self.attachment_count is not None and self.attachment_count < 0:
            return "تعداد پیوست نمی‌تواند منفی باشد."
        if self.sent_to_contractor_date and self.meeting_date and self.sent_to_contractor_date < self.meeting_date:
            return "تاریخ ارسال به پیمانکار نمی‌تواند قبل از تاریخ صورتجلسه باشد."
        return None

    def __repr__(self) -> str:
        return (
            f"<Meeting(id={self.id}, number='{self.meeting_number}', "
            f"discipline='{self.discipline}', status='{self.status}')>"
        )


class WorkflowStep(Base):
    """مراحل پیشرفت کار و تبارنامه امضاهای گردش کار."""

    __tablename__ = "workflow_steps"

    STATUS_PENDING     = "pending"
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_COMPLETED   = "completed"
    STATUS_SKIPPED     = "skipped"
    STATUS_REJECTED    = "rejected"

    VALID_STATUSES = [
        STATUS_PENDING,
        STATUS_IN_PROGRESS,
        STATUS_COMPLETED,
        STATUS_SKIPPED,
        STATUS_REJECTED,
    ]

    id = Column(Integer, primary_key=True)
    meeting_id = Column(
        Integer,
        ForeignKey("meetings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    step_name = Column(String, nullable=False)
    step_order = Column(Integer, nullable=False, index=True)

    entry_date = Column(Date)
    exit_date = Column(Date)

    responsible_person = Column(String, index=True)
    signature = Column(String)

    status = Column(
        String,
        default=STATUS_PENDING,
        server_default=STATUS_PENDING,
        nullable=False,
        index=True,
    )
    notes = Column(Text)

    meeting = relationship("Meeting", back_populates="workflow_steps")

    __table_args__ = (
        UniqueConstraint("meeting_id", "step_order", name="uq_workflow_meeting_steporder"),
        Index("idx_workflow_meeting_order", "meeting_id", "step_order"),
        Index("idx_workflow_status_responsible", "status", "responsible_person"),
    )

    @property
    def is_active(self) -> bool:
        """آیا این گام در حال پیشرفت یا در انتظار انجام است؟"""
        return self.status in (self.STATUS_PENDING, self.STATUS_IN_PROGRESS)

    @property
    def is_rejected(self) -> bool:
        """آیا این گام توسط کارشناس عودت داده شده است؟"""
        return self.status == self.STATUS_REJECTED

    @property
    def duration_days(self) -> Optional[int]:
        """مدت زمان انجام این گام به روز (در صورت تکمیل)."""
        if self.entry_date and self.exit_date:
            return (self.exit_date - self.entry_date).days
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id":                  self.id,
            "meeting_id":          self.meeting_id,
            "step_name":           self.step_name,
            "step_order":          self.step_order,
            "entry_date":          self.entry_date.isoformat() if self.entry_date else None,
            "exit_date":           self.exit_date.isoformat() if self.exit_date else None,
            "responsible_person":  self.responsible_person,
            "signature":           self.signature,
            "status":              self.status,
            "notes":               self.notes,
            "is_active":           self.is_active,
            "is_rejected":         self.is_rejected,
            "duration_days":       self.duration_days,
        }

    def __repr__(self) -> str:
        return (
            f"<WorkflowStep(id={self.id}, name='{self.step_name}', "
            f"order={self.step_order}, status='{self.status}')>"
        )


class User(Base):
    """مدل حساب‌های کاربری."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False, index=True)

    is_active = Column(
        Boolean,
        default=True,
        server_default="1",
        nullable=False,
        index=True,
    )
    must_change_password = Column(
        Boolean,
        default=False,
        server_default="0",
        nullable=False,
    )

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_user_active_role", "is_active", "role"),
    )

    @property
    def is_admin(self) -> bool:
        """آیا این کاربر مدیر سیستم است؟"""
        return self.role == ROLE_ADMIN

    @property
    def is_manager(self) -> bool:
        """آیا این کاربر مدیر پروژه/واحد است؟"""
        return self.role in (ROLE_ADMIN, ROLE_MANAGER)

    @property
    def is_editor(self) -> bool:
        """آیا این کاربر دسترسی ویرایش دارد؟"""
        return self.role in (ROLE_ADMIN, ROLE_MANAGER, ROLE_EDITOR, ROLE_USER)

    @property
    def can_login(self) -> bool:
        """آیا این کاربر مجاز به ورود به سیستم است؟"""
        return bool(self.is_active) and bool(self.password_hash)

    @property
    def display_name(self) -> str:
        """نام قابل نمایش زیبا برای کاربر (خصوصاً ادمین سیستم)."""
        if self.username == "admin":
            return "مدیر سیستم (admin)"
        return self.username

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id":                   self.id,
            "username":             self.username,
            "display_name":         self.display_name,
            "role":                 self.role,
            "is_active":            self.is_active,
            "must_change_password": self.must_change_password,
            "created_at":           self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self) -> str:
        return f"<User(id={self.id}, username='{self.username}', role='{self.role}')>"


class AuditLog(Base):
    """مدل سوابق ممیزی عملیات کاربران (Audit Trail)."""

    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)
    ts = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    user_id = Column(Integer, index=True)
    username = Column(String, index=True)
    action = Column(String, nullable=False, index=True)
    details = Column(Text)
    meeting_id = Column(Integer, index=True)

    __table_args__ = (
        Index("idx_audit_user_action", "username", "action"),
        Index("idx_audit_ts_action", "ts", "action"),
        Index("idx_audit_meeting_ts", "meeting_id", "ts"),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id":         self.id,
            "ts":         self.ts.isoformat() if self.ts else None,
            "user_id":    self.user_id,
            "username":   self.username,
            "action":     self.action,
            "details":    self.details,
            "meeting_id": self.meeting_id,
        }

    def __repr__(self) -> str:
        return (
            f"<AuditLog(id={self.id}, action='{self.action}', "
            f"user='{self.username}', ts={self.ts})>"
        )
