# -*- coding: utf-8 -*-
"""
ui.user_admin_dialog
دیالوگ مدیریت کاربران، سطوح دسترسی، بازنشانی رمز و تنظیمات سربرگ گزارشات

نسخه ۲.۱ بهسازی‌شده:
    - رفع باگ import تکراری (ui.style → ui.styles)
    - احترام به حالت شب کاربر از QSettings
    - fail-safe واقعی در حفاظت از آخرین مدیر
    - تأییدیه رمز + اعتبارسنجی نام کاربری + نمایش قدرت رمز
    - تأیید تغییر نقش قبل از اعمال
    - استفاده از UserRole برای شناسه (مقاوم در برابر مرتب‌سازی)
    - ذخیره/بازیابی هندسه و عرض ستون‌ها
    - فیلتر بر اساس شناسه + debounce روی جستجو
    - ثابت‌های ستون به‌جای اعداد جادویی
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any, List, Optional, Tuple

from PyQt6.QtCore import QPoint, QSettings, Qt, QTimer
from PyQt6.QtGui import QAction, QCloseEvent, QColor, QFont, QKeySequence
from PyQt6.QtWidgets import (
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from config import APP_NAME, ORG_NAME
from db.manager import DatabaseManager
from db.models import User
from security.passwords import hash_password

# نقش‌ها با مقادیر پشتیبان
try:
    from config import Roles
    ROLE_CHOICES: List[str] = [r.value for r in Roles]
except Exception:
    ROLE_CHOICES = ["admin", "editor", "viewer"]

# ✅ FIXED: import یک‌بار و از مسیر صحیح
try:
    from ui.styles import get_stylesheet  # noqa: F401
except ImportError:
    def get_stylesheet(dark_mode: bool = False) -> str:  # type: ignore[no-redef]
        return ""

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════
# ثابت‌های ماژول — منبع واحد حقیقت
# ══════════════════════════════════════════════════

COL_ID = 0
COL_USERNAME = 1
COL_ROLE = 2
COL_ACTIVE = 3
COL_MUST_CHANGE = 4
COLUMN_COUNT = 5

COLUMN_HEADERS: List[str] = [
    "شناسه",
    "نام کاربری",
    "سطح دسترسی (نقش)",
    "وضعیت حساب",
    "تغییر رمز در ورود بعدی",
]

# الگوی نام کاربری امن (حروف لاتین، فارسی، ارقام، نقطه، خط تیره، زیرخط، ۳ تا ۳۲)
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_\u0600-\u06FF.\-]{3,32}$")

# رنگ‌بندی بج‌های نقش کاربری
ROLE_COLORS = {
    "admin":  {"bg": "#fee2e2", "fg": "#b91c1c", "label": "مدیر سیستم"},
    "editor": {"bg": "#e0f2fe", "fg": "#0369a1", "label": "ویرایشگر / کارشناس"},
    "viewer": {"bg": "#f1f5f9", "fg": "#475569", "label": "مشاهده‌گر"},
}

SEARCH_DEBOUNCE_MS = 150


# ══════════════════════════════════════════════════
# توابع کمکی
# ══════════════════════════════════════════════════

def _password_strength_hint(password: str) -> str:
    """ارزیابی سریع قدرت رمز — فقط برای راهنمایی بصری."""
    if not password:
        return ""
    has_lower = any(c.islower() for c in password)
    has_upper = any(c.isupper() for c in password)
    has_digit = any(c.isdigit() for c in password)
    has_symbol = any(not c.isalnum() for c in password)
    score = sum([has_lower, has_upper, has_digit, has_symbol])

    if len(password) < 8 or score <= 1:
        return "ضعیف"
    if len(password) < 12 or score == 2:
        return "متوسط"
    return "قوی"


# ══════════════════════════════════════════════════
# دیالوگ اصلی
# ══════════════════════════════════════════════════

class UserAdminDialog(QDialog):
    """دیالوگ مدیریت جامع کاربران و تنظیمات سربرگ گزارش‌های سازمانی."""

    MIN_PASSWORD_LENGTH = 8

    def __init__(
        self,
        db: DatabaseManager,
        parent: Optional[QWidget] = None,
        session: Optional[Any] = None,
    ) -> None:
        super().__init__(parent)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        self.db = db
        self.settings = QSettings(ORG_NAME, APP_NAME)

        self.current_session = session or getattr(parent, "session", None)
        self.current_username = getattr(self.current_session, "username", "admin")
        self.current_user_id = getattr(self.current_session, "user_id", None)

        self.setWindowTitle("مدیریت کاربران و تنظیمات سربرگ سازمانی")
        self.resize(920, 620)
        self.setMinimumSize(740, 500)
        self.setModal(True)

        self._total_count: int = 0

        # Debounce برای فیلتر
        self._filter_timer = QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.setInterval(SEARCH_DEBOUNCE_MS)
        self._filter_timer.timeout.connect(self._apply_filter)

        self._build_ui()
        self._restore_geometry()
        self._restore_header_state()
        self.load_branding()
        self.load_users()
        self._apply_style()
        self._setup_shortcuts()

    # ─────────────────────────────────────────────────────────────
    # ساخت رابط کاربری
    # ─────────────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 16)
        root.setSpacing(14)

        root.addWidget(self._build_branding_section())
        root.addLayout(self._build_table_toolbar())
        root.addWidget(self._build_users_table(), stretch=1)
        root.addLayout(self._build_action_buttons())

    def _build_branding_section(self) -> QGroupBox:
        box = QGroupBox("تنظیمات سربرگ گزارشات (نام شرکت / پروژه)")
        form = QFormLayout(box)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setVerticalSpacing(8)
        form.setHorizontalSpacing(12)

        self.lbl_scope = QLabel("")
        self.lbl_scope.setStyleSheet(
            "color: #0284c7; font-weight: bold; font-size: 11px;"
        )

        self.ed_company = QLineEdit()
        self.ed_company.setPlaceholderText("مثال: مهندسین مشاور سازه‌پرداز")

        self.ed_project = QLineEdit()
        self.ed_project.setPlaceholderText("مثال: پروژه خطوط انتقال و ایستگاه پمپاژ")

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self.btn_reload_header = QPushButton("بازخوانی")
        self.btn_reload_header.setObjectName("btn_secondary")
        self.btn_reload_header.clicked.connect(self.load_branding)

        # ✅ btn_save در styles.py نیست → استفاده از btn_primary
        self.btn_save_header = QPushButton("💾 ذخیره سربرگ")
        self.btn_save_header.setObjectName("btn_primary")
        self.btn_save_header.clicked.connect(self.save_branding)

        btn_row.addWidget(self.btn_reload_header)
        btn_row.addWidget(self.btn_save_header)

        form.addRow("پایگاه داده متصل:", self.lbl_scope)
        form.addRow("نام شرکت / کارفرما:", self.ed_company)
        form.addRow("عنوان پروژه:", self.ed_project)
        form.addRow("", btn_row)

        return box

    def _build_table_toolbar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        bar.setSpacing(8)

        lbl_search = QLabel("🔍 جستجوی کاربر:")
        self.ed_search = QLineEdit()
        self.ed_search.setPlaceholderText("جستجو بر اساس نام کاربری، نقش یا شناسه…")
        self.ed_search.setClearButtonEnabled(True)
        self.ed_search.textChanged.connect(lambda: self._filter_timer.start())

        self.lbl_count = QLabel("کاربران: ۰")
        self.lbl_count.setStyleSheet(
            "color: #64748b; font-size: 11px; font-weight: bold;"
        )

        bar.addWidget(lbl_search)
        bar.addWidget(self.ed_search, stretch=1)
        bar.addWidget(self.lbl_count)
        return bar

    def _build_users_table(self) -> QTableWidget:
        table = QTableWidget(0, COLUMN_COUNT)
        table.setHorizontalHeaderLabels(COLUMN_HEADERS)
        table.verticalHeader().setVisible(False)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        table.customContextMenuRequested.connect(self._show_context_menu)
        table.itemDoubleClicked.connect(lambda _: self.change_role())

        hdr = table.horizontalHeader()
        hdr.setSectionResizeMode(COL_ID, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(COL_USERNAME, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(COL_ROLE, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(COL_ACTIVE, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(COL_MUST_CHANGE, QHeaderView.ResizeMode.ResizeToContents)

        table.verticalHeader().setDefaultSectionSize(36)
        table.setShowGrid(False)

        self.table = table
        return table

    def _build_action_buttons(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        bar.setSpacing(8)

        self.btn_add = QPushButton("➕ کاربر جدید")
        self.btn_add.setToolTip("تعریف کاربر جدید با دسترسی مشخص (Ctrl+N)")
        self.btn_add.clicked.connect(self.add_user)

        self.btn_role = QPushButton("👤 تغییر نقش")
        self.btn_role.setObjectName("btn_secondary")
        self.btn_role.clicked.connect(self.change_role)

        self.btn_toggle = QPushButton("🔄 فعال/غیرفعال")
        self.btn_toggle.setObjectName("btn_secondary")
        self.btn_toggle.clicked.connect(self.toggle_active)

        self.btn_reset = QPushButton("🔑 بازنشانی رمز")
        self.btn_reset.setObjectName("btn_secondary")
        self.btn_reset.setToolTip("تنظیم مجدد رمز عبور موقت (Ctrl+R)")
        self.btn_reset.clicked.connect(self.reset_password)

        self.btn_delete = QPushButton("🗑️ حذف")
        self.btn_delete.setObjectName("btn_danger")
        self.btn_delete.setToolTip("حذف دائمی کاربر از سیستم (Delete)")
        self.btn_delete.clicked.connect(self.delete_user)

        btn_close = QPushButton("بستن")
        btn_close.setObjectName("btn_close")
        btn_close.clicked.connect(self.accept)

        bar.addWidget(self.btn_add)
        bar.addWidget(self.btn_role)
        bar.addWidget(self.btn_toggle)
        bar.addWidget(self.btn_reset)
        bar.addWidget(self.btn_delete)
        bar.addStretch()
        bar.addWidget(btn_close)

        return bar

    # ─────────────────────────────────────────────────────────────
    # میانبرها، استایل، geometry
    # ─────────────────────────────────────────────────────────────
    def _setup_shortcuts(self) -> None:
        shortcuts = [
            ("Ctrl+N", self.add_user),
            ("Ctrl+R", self.reset_password),
            ("Delete", self.delete_user),
            ("F5", self.load_users),
            ("Ctrl+F", lambda: self.ed_search.setFocus()),
        ]
        for key, slot in shortcuts:
            action = QAction(self)
            action.setShortcut(QKeySequence(key))
            action.triggered.connect(slot)
            self.addAction(action)

    def _apply_style(self) -> None:
        # ✅ احترام به حالت شب کاربر (ذخیره‌شده در QSettings توسط MainWindow)
        dark_mode = self.settings.value("dark_mode", False, type=bool)
        self.setStyleSheet(get_stylesheet(dark_mode=dark_mode))

    def _restore_geometry(self) -> None:
        geometry = self.settings.value("user_admin_geometry")
        if geometry:
            self.restoreGeometry(geometry)

    def _save_geometry(self) -> None:
        self.settings.setValue("user_admin_geometry", self.saveGeometry())

    def _restore_header_state(self) -> None:
        state = self.settings.value("user_admin_header_state")
        if state:
            self.table.horizontalHeader().restoreState(state)

    def _save_header_state(self) -> None:
        self.settings.setValue(
            "user_admin_header_state",
            self.table.horizontalHeader().saveState(),
        )

    def closeEvent(self, event: QCloseEvent) -> None:
        self._save_geometry()
        self._save_header_state()
        super().closeEvent(event)

    def reject(self) -> None:
        self._save_geometry()
        self._save_header_state()
        super().reject()

    # ─────────────────────────────────────────────────────────────
    # مدیریت سربرگ گزارشات
    # ─────────────────────────────────────────────────────────────
    def _branding_keys(self) -> Tuple[str, str, str]:
        db_path = str(getattr(self.db, "db_path", "") or "")
        db_id = os.path.basename(db_path) if db_path else "default.db"
        return (
            f"branding/{db_id}/company_name",
            f"branding/{db_id}/project_name",
            db_id,
        )

    def load_branding(self) -> None:
        company_key, project_key, scope_text = self._branding_keys()
        self.lbl_scope.setText(f"فایل دیتابیس فعال: {scope_text}")

        company = str(self.settings.value(company_key, "") or "").strip()
        project = str(self.settings.value(project_key, "") or "").strip()

        self.ed_company.setText(company)
        self.ed_project.setText(project)

    def save_branding(self) -> None:
        company_key, project_key, _ = self._branding_keys()
        company = self.ed_company.text().strip()
        project = self.ed_project.text().strip()

        self.settings.setValue(company_key, company)
        self.settings.setValue(project_key, project)

        QMessageBox.information(
            self, "✅ ذخیره شد",
            "تنظیمات سربرگ گزارشات با موفقیت ذخیره شد.",
        )

    # ─────────────────────────────────────────────────────────────
    # بارگذاری و فیلتر کاربران
    # ─────────────────────────────────────────────────────────────
    def load_users(self) -> None:
        """بارگذاری کاربران از پایگاه داده در جدول."""
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)

        try:
            with self.db.session() as sess:
                users = sess.query(User).order_by(User.id.asc()).all()
                user_list = [
                    (u.id, u.username, u.role, u.is_active, u.must_change_password)
                    for u in users
                ]
        except Exception as exc:
            logger.exception("Failed to query users list")
            QMessageBox.critical(
                self, "خطای دیتابیس",
                f"بارگذاری کاربران با خطا مواجه شد:\n{exc}",
            )
            return

        self.table.setRowCount(len(user_list))

        for r, (uid, username, role, is_active, must_change) in enumerate(user_list):
            # شناسه — با UserRole (مقاوم در برابر مرتب‌سازی)
            id_item = QTableWidgetItem()
            id_item.setData(Qt.ItemDataRole.DisplayRole, uid)
            id_item.setData(Qt.ItemDataRole.UserRole, uid)
            id_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            # نام کاربری
            name_item = QTableWidgetItem(username)
            name_item.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))

            # نقش با برچسب خوانا
            role_meta = ROLE_COLORS.get(role, {"label": role, "fg": "#334155"})
            role_item = QTableWidgetItem(role_meta.get("label", role))
            role_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            role_item.setForeground(QColor(role_meta.get("fg", "#334155")))

            # وضعیت فعال/غیرفعال
            active_str = "فعال ✓" if is_active else "غیرفعال ✕"
            active_item = QTableWidgetItem(active_str)
            active_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            active_item.setForeground(
                QColor("#16a34a" if is_active else "#dc2626")
            )

            # تغییر رمز
            change_str = "الزامی" if must_change else "—"
            must_change_item = QTableWidgetItem(change_str)
            must_change_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if must_change:
                must_change_item.setForeground(QColor("#d97706"))

            self.table.setItem(r, COL_ID, id_item)
            self.table.setItem(r, COL_USERNAME, name_item)
            self.table.setItem(r, COL_ROLE, role_item)
            self.table.setItem(r, COL_ACTIVE, active_item)
            self.table.setItem(r, COL_MUST_CHANGE, must_change_item)

        self.table.setSortingEnabled(True)
        self._total_count = len(user_list)
        self._apply_filter()

    def _apply_filter(self) -> None:
        """اعمال فیلتر بر اساس متن جستجو (نام کاربری، نقش یا شناسه)."""
        target = self.ed_search.text().strip().lower()
        visible_count = 0

        for r in range(self.table.rowCount()):
            id_item = self.table.item(r, COL_ID)
            u_item = self.table.item(r, COL_USERNAME)
            r_item = self.table.item(r, COL_ROLE)

            id_text = id_item.text() if id_item else ""
            u_text = u_item.text().lower() if u_item else ""
            r_text = r_item.text().lower() if r_item else ""

            match = (
                not target
                or target in u_text
                or target in r_text
                or target == id_text
            )
            self.table.setRowHidden(r, not match)
            if match:
                visible_count += 1

        total = getattr(self, "_total_count", self.table.rowCount())
        if target:
            self.lbl_count.setText(f"نمایش: {visible_count} از {total}")
        else:
            self.lbl_count.setText(f"تعداد کل کاربران: {total}")

    # ─────────────────────────────────────────────────────────────
    # کمکی‌های انتخاب
    # ─────────────────────────────────────────────────────────────
    def _selected_user_id(self) -> Optional[int]:
        """دریافت شناسه کاربر انتخاب‌شده با استفاده از UserRole (مقاوم)."""
        selected = self.table.selectionModel().selectedRows()
        if not selected:
            return None
        row = selected[0].row()
        item = self.table.item(row, COL_ID)
        if item is None:
            return None
        uid = item.data(Qt.ItemDataRole.UserRole)
        try:
            return int(uid) if uid is not None else None
        except (TypeError, ValueError):
            return None

    def _show_context_menu(self, pos: QPoint) -> None:
        item = self.table.itemAt(pos)
        if item:
            self.table.selectRow(item.row())

        if self._selected_user_id() is None:
            return

        menu = QMenu(self)
        menu.addAction("👤 تغییر نقش کاربر", self.change_role)
        menu.addAction("🔄 فعال / غیرفعال‌سازی", self.toggle_active)
        menu.addAction("🔑 بازنشانی رمز عبور", self.reset_password)
        menu.addSeparator()
        act_del = menu.addAction("🗑️ حذف کاربر", self.delete_user)
        act_del.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_TrashIcon))

        menu.exec(self.table.viewport().mapToGlobal(pos))

    # ─────────────────────────────────────────────────────────────
    # عملیات کاربران
    # ─────────────────────────────────────────────────────────────
    def add_user(self) -> None:
        # ── نام کاربری با اعتبارسنجی
        username, ok = QInputDialog.getText(
            self, "افزودن کاربر جدید", "نام کاربری:"
        )
        if not ok:
            return
        username = username.strip()
        if not username:
            QMessageBox.warning(self, "خطا", "نام کاربری نمی‌تواند خالی باشد.")
            return
        if not USERNAME_PATTERN.match(username):
            QMessageBox.warning(
                self, "نام کاربری نامعتبر",
                "نام کاربری باید ۳ تا ۳۲ کاراکتر و شامل حروف، ارقام، "
                "نقطه، خط تیره یا زیرخط باشد.",
            )
            return

        # ── رمز عبور
        password, ok = QInputDialog.getText(
            self, "افزودن کاربر جدید",
            f"رمز عبور موقت (حداقل {self.MIN_PASSWORD_LENGTH} کاراکتر):",
            QLineEdit.EchoMode.Password,
        )
        if not ok or not password:
            return
        password = password.strip()
        if len(password) < self.MIN_PASSWORD_LENGTH:
            QMessageBox.warning(
                self, "رمز عبور ضعیف",
                f"رمز عبور باید حداقل {self.MIN_PASSWORD_LENGTH} کاراکتر باشد.",
            )
            return

        # ── تأییدیه رمز
        confirm, ok = QInputDialog.getText(
            self, "تأیید رمز عبور",
            "لطفاً رمز عبور را مجدداً وارد کنید:",
            QLineEdit.EchoMode.Password,
        )
        if not ok or not confirm:
            return
        if password != confirm.strip():
            QMessageBox.warning(
                self, "عدم تطابق", "رمز عبور و تأییدیه آن یکسان نیستند."
            )
            return

        # راهنمای قدرت رمز (غیرمسدودکننده)
        strength = _password_strength_hint(password)
        if strength == "ضعیف":
            reply = QMessageBox.question(
                self, "رمز ضعیف",
                "قدرت رمز وارد‌شده «ضعیف» ارزیابی می‌شود.\n"
                "استفاده از ترکیب حروف بزرگ و کوچک، ارقام و نمادها توصیه می‌شود.\n\n"
                "ادامه می‌دهید؟",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        # ── انتخاب نقش
        default_idx = 1 if len(ROLE_CHOICES) > 1 else 0
        role, ok = QInputDialog.getItem(
            self, "انتخاب سطح دسترسی", "نقش کاربر در سامانه:",
            ROLE_CHOICES, default_idx, False,
        )
        if not ok:
            return

        try:
            with self.db.session() as sess:
                exists = (
                    sess.query(User.id)
                    .filter(User.username == username)
                    .first()
                )
                if exists:
                    QMessageBox.warning(
                        self, "نام کاربری تکراری",
                        f"کاربر «{username}» قبلاً ثبت شده است.",
                    )
                    return

                new_user = User(
                    username=username,
                    password_hash=hash_password(password),
                    role=role,
                    is_active=True,
                    must_change_password=True,
                )
                sess.add(new_user)
                sess.commit()

            self.db.audit(
                self.current_user_id, self.current_username,
                "USER_CREATE",
                f"created_username={username}, role={role}",
            )
            self.load_users()
            QMessageBox.information(
                self, "✅ کاربر ایجاد شد",
                f"کاربر «{username}» با موفقیت تعریف شد.",
            )
        except Exception as exc:
            logger.exception("Failed to add user")
            QMessageBox.critical(self, "خطا", f"ایجاد کاربر با شکست مواجه شد:\n{exc}")

    def change_role(self) -> None:
        uid = self._selected_user_id()
        if uid is None:
            QMessageBox.information(
                self, "انتخاب کاربر", "لطفاً ابتدا یک کاربر را انتخاب کنید."
            )
            return

        try:
            with self.db.session() as sess:
                u = sess.get(User, uid)
                if not u:
                    QMessageBox.warning(self, "خطا", "کاربر در پایگاه داده یافت نشد.")
                    return
                current_role = u.role
                current_username = u.username

            current_idx = (
                ROLE_CHOICES.index(current_role)
                if current_role in ROLE_CHOICES else 0
            )
            new_role, ok = QInputDialog.getItem(
                self, "تغییر سطح دسترسی",
                f"نقش جدید برای کاربر «{current_username}»:",
                ROLE_CHOICES, current_idx, False,
            )
            if not ok or new_role == current_role:
                return

            # ✅ تأیید قبل از اعمال
            reply = QMessageBox.question(
                self, "تأیید تغییر نقش",
                f"تغییر نقش «{current_username}» از «{current_role}» "
                f"به «{new_role}». ادامه می‌دهید؟",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

            # حفاظت از آخرین مدیر
            if current_role == "admin" and new_role != "admin":
                if not self._has_other_active_admins(exclude_id=uid):
                    QMessageBox.warning(
                        self, "عملیات غیرمجاز",
                        "امکان تنزل رتبه این کاربر وجود ندارد؛ "
                        "حداقل یک مدیر فعال باید در سیستم باقی بماند.",
                    )
                    return

            with self.db.session() as sess:
                user_obj = sess.get(User, uid)
                if user_obj:
                    user_obj.role = new_role
                    sess.commit()

            self.db.audit(
                self.current_user_id, self.current_username,
                "USER_ROLE_CHANGE",
                f"target_user={current_username}, "
                f"old_role={current_role}, new_role={new_role}",
            )
            self.load_users()
            QMessageBox.information(
                self, "✅ تغییر نقش انجام شد",
                "نقش کاربر به‌روزرسانی شد.",
            )

        except Exception as exc:
            logger.exception("Failed to change user role")
            QMessageBox.critical(self, "خطا", f"تغییر نقش با شکست مواجه شد:\n{exc}")

    def toggle_active(self) -> None:
        uid = self._selected_user_id()
        if uid is None:
            QMessageBox.information(
                self, "انتخاب کاربر", "لطفاً یک کاربر را انتخاب کنید."
            )
            return

        if self.current_user_id and self.current_user_id == uid:
            QMessageBox.warning(
                self, "عملیات غیرمجاز",
                "شما نمی‌توانید حساب کاربری جاری خود را غیرفعال کنید.",
            )
            return

        try:
            with self.db.session() as sess:
                u = sess.get(User, uid)
                if not u:
                    return
                target_username = u.username
                is_currently_active = u.is_active
                is_admin = (u.role == "admin")

            if is_currently_active and is_admin:
                if not self._has_other_active_admins(exclude_id=uid):
                    QMessageBox.warning(
                        self, "غیرمجاز",
                        "امکان غیرفعال‌سازی این کاربر وجود ندارد؛ "
                        "حداقل یک مدیر فعال باید در سیستم بماند.",
                    )
                    return

            action_title = "غیرفعال" if is_currently_active else "فعال"
            reply = QMessageBox.question(
                self, "تأیید تغییر وضعیت",
                f"آیا از {action_title} کردن کاربر «{target_username}» اطمینان دارید؟",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

            with self.db.session() as sess:
                user_obj = sess.get(User, uid)
                if user_obj:
                    user_obj.is_active = not is_currently_active
                    sess.commit()

            self.db.audit(
                self.current_user_id, self.current_username,
                "USER_TOGGLE_ACTIVE",
                f"target_user={target_username}, "
                f"active={not is_currently_active}",
            )
            self.load_users()
            QMessageBox.information(
                self, "موفق",
                f"حساب کاربر «{target_username}» با موفقیت {action_title} شد.",
            )

        except Exception as exc:
            logger.exception("Failed to toggle user active state")
            QMessageBox.critical(self, "خطا", f"تغییر وضعیت حساب با خطا مواجه شد:\n{exc}")

    def reset_password(self) -> None:
        uid = self._selected_user_id()
        if uid is None:
            QMessageBox.information(
                self, "انتخاب کاربر", "لطفاً یک کاربر را انتخاب کنید."
            )
            return

        try:
            with self.db.session() as sess:
                u = sess.get(User, uid)
                if not u:
                    return
                target_username = u.username

            new_pw, ok = QInputDialog.getText(
                self, "بازنشانی رمز عبور",
                f"رمز عبور موقت جدید برای «{target_username}» "
                f"(حداقل {self.MIN_PASSWORD_LENGTH} کاراکتر):",
                QLineEdit.EchoMode.Password,
            )
            if not ok or not new_pw:
                return

            new_pw = new_pw.strip()
            if len(new_pw) < self.MIN_PASSWORD_LENGTH:
                QMessageBox.warning(
                    self, "رمز ضعیف",
                    f"رمز عبور باید حداقل {self.MIN_PASSWORD_LENGTH} کاراکتر باشد.",
                )
                return

            # ✅ تأییدیه رمز
            confirm, ok = QInputDialog.getText(
                self, "تأیید رمز عبور",
                "لطفاً رمز عبور جدید را مجدداً وارد کنید:",
                QLineEdit.EchoMode.Password,
            )
            if not ok or not confirm:
                return
            if new_pw != confirm.strip():
                QMessageBox.warning(
                    self, "عدم تطابق",
                    "رمز عبور و تأییدیه آن یکسان نیستند.",
                )
                return

            with self.db.session() as sess:
                user_obj = sess.get(User, uid)
                if user_obj:
                    user_obj.password_hash = hash_password(new_pw)
                    user_obj.must_change_password = True
                    sess.commit()

            self.db.audit(
                self.current_user_id, self.current_username,
                "USER_RESET_PASSWORD",
                f"target_user={target_username}",
            )
            QMessageBox.information(
                self, "✅ رمز بازنشانی شد",
                f"رمز عبور کاربر «{target_username}» تغییر یافت.\n"
                "کاربر در ورود بعدی ملزم به تعیین رمز عبور اختصاصی خود خواهد بود.",
            )
            self.load_users()

        except Exception as exc:
            logger.exception("Failed to reset password")
            QMessageBox.critical(self, "خطا", f"بازنشانی رمز با خطا مواجه شد:\n{exc}")

    def delete_user(self) -> None:
        uid = self._selected_user_id()
        if uid is None:
            QMessageBox.information(
                self, "انتخاب کاربر", "لطفاً یک کاربر را انتخاب کنید."
            )
            return

        if self.current_user_id and self.current_user_id == uid:
            QMessageBox.warning(
                self, "عملیات غیرمجاز",
                "شما نمی‌توانید حساب کاربری جاری خود را حذف کنید.",
            )
            return

        try:
            with self.db.session() as sess:
                u = sess.get(User, uid)
                if not u:
                    return
                target_username = u.username
                is_admin = (u.role == "admin")

            if is_admin and not self._has_other_active_admins(exclude_id=uid):
                QMessageBox.warning(
                    self, "غیرمجاز",
                    "امکان حذف این کاربر وجود ندارد؛ "
                    "سیستم باید حداقل دارای یک مدیر فعال باشد.",
                )
                return

            reply = QMessageBox.question(
                self, "تأیید حذف دائمی",
                f"آیا از حذف دائمی کاربر «{target_username}» اطمینان دارید؟\n"
                "این عملیات غیرقابل بازگشت است.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

            with self.db.session() as sess:
                user_obj = sess.get(User, uid)
                if user_obj:
                    sess.delete(user_obj)
                    sess.commit()

            self.db.audit(
                self.current_user_id, self.current_username,
                "USER_DELETE",
                f"deleted_username={target_username}",
            )
            self.load_users()
            QMessageBox.information(
                self, "✅ کاربر حذف شد",
                f"کاربر «{target_username}» با موفقیت از سیستم حذف شد.",
            )

        except Exception as exc:
            logger.exception("Failed to delete user")
            QMessageBox.critical(self, "خطا", f"حذف کاربر با شکست مواجه شد:\n{exc}")

    def _has_other_active_admins(self, exclude_id: int) -> bool:
        """
        بررسی وجود حداقل یک مدیر فعال دیگر در سیستم.

        در صورت خطای دیتابیس، مقدار False بازگردانده می‌شود تا عملیات
        خطرناک (حذف/غیرفعال‌سازی/تنزل) به‌صورت fail-safe مسدود شود.
        """
        try:
            with self.db.session() as sess:
                count = (
                    sess.query(User.id)
                    .filter(
                        User.role == "admin",
                        User.is_active.is_(True),
                        User.id != exclude_id,
                    )
                    .count()
                )
                return count > 0
        except Exception:
            logger.exception(
                "Failed to verify other active admins; "
                "operation will be blocked (fail-safe)."
            )
            return False
