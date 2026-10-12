# -*- coding: utf-8 -*-
"""
ui.login_dialog
دیالوگ ورود کاربران به سیستم Document & MOM Tracking System
نسخه بهبودیافته: رفع باگ‌های UI/UX، همگام‌سازی نمایش رمز، حذف کوئری‌های تکراری و بهینه‌سازی استایل
"""
from __future__ import annotations

import logging
import os
from typing import List, Optional, Tuple

from PyQt6.QtCore import Qt, QSettings, QTimer
from PyQt6.QtGui import (
    QAction,
    QCloseEvent,
    QColor,
    QFont,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QCompleter,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from config import APP_NAME, ORG_NAME
from db.manager import DatabaseManager
from db.models import User
from security.session import UserSession

logger = logging.getLogger(__name__)


class LoginDialog(QDialog):
    """دیالوگ ورود به سیستم با پشتیبانی کامل از RTL، اعتبارسنجی و رابط کاربری مدرن."""

    def __init__(self, db: DatabaseManager, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        self.db = db
        self.session: Optional[UserSession] = None
        self.settings = QSettings(ORG_NAME, APP_NAME)
        self._login_in_progress: bool = False
        self._last_username: str = str(
            self.settings.value("last_username", "", type=str) or ""
        ).strip()
        self._cached_users: List[Tuple[str, bool]] = []

        self.setWindowTitle(f"ورود – {APP_NAME}")
        self.setModal(True)
        self.resize(500, 350)
        self.setMinimumSize(460, 320)

        self._build_ui()
        self._restore_geometry()
        self._load_users()

        # اتصال کلید Enter
        self.ed_password.returnPressed.connect(self._on_login)
        if self.cb_username.lineEdit():
            self.cb_username.lineEdit().returnPressed.connect(self._on_login)

    # ─────────────────────────────────────────────────────────────
    # ساخت رابط کاربری
    # ─────────────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(15)
        root.setContentsMargins(26, 24, 26, 22)

        # ── Header ──
        header = QHBoxLayout()
        header.setSpacing(12)

        icon_label = QLabel()
        icon_path = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "app.ico")
        )
        if os.path.isfile(icon_path):
            pix = QPixmap(icon_path).scaled(
                48, 48,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            icon_label.setPixmap(pix)
        icon_label.setFixedWidth(52)
        header.addWidget(icon_label)

        title_block = QVBoxLayout()
        title = QLabel(APP_NAME)
        title.setObjectName("login_title")
        title.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))

        subtitle = QLabel("سامانه جامع مدیریت و پیگیری صورتجلسات و اسناد")
        subtitle.setObjectName("login_subtitle")
        subtitle.setFont(QFont("Segoe UI", 9))

        title_block.addWidget(title)
        title_block.addWidget(subtitle)
        header.addLayout(title_block)
        header.addStretch()

        root.addLayout(header)

        # ── Branding (Company / Project) ──
        company, project = self._get_branding()
        if company or project:
            branding_text = "  |  ".join([p for p in [company, project] if p])
            lbl_brand = QLabel(branding_text)
            lbl_brand.setObjectName("branding_label")
            lbl_brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_brand.setWordWrap(True)
            root.addWidget(lbl_brand)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        root.addWidget(line)

        # ── فرم ورود ──
        form_container = QWidget()
        form = QFormLayout(form_container)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        form.setVerticalSpacing(12)
        form.setHorizontalSpacing(12)
        form.setContentsMargins(4, 6, 4, 4)

        # کمبوباکس نام کاربری با فیلتر جستجوی خودکار
        self.cb_username = QComboBox()
        self.cb_username.setEditable(True)
        self.cb_username.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.cb_username.setMinimumHeight(32)
        self.cb_username.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        completer = QCompleter(self.cb_username.model(), self.cb_username)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.cb_username.setCompleter(completer)

        if self.cb_username.lineEdit():
            self.cb_username.lineEdit().setPlaceholderText("نام کاربری را وارد یا انتخاب کنید…")
            self.cb_username.lineEdit().setClearButtonEnabled(True)

        # فیلد رمز عبور
        self.ed_password = QLineEdit()
        self.ed_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.ed_password.setMinimumHeight(32)
        self.ed_password.setPlaceholderText("رمز عبور…")
        self.ed_password.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.ed_password.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._setup_password_toggle()

        self.chk_show = QCheckBox("نمایش رمز عبور")
        self.chk_show.toggled.connect(self._sync_password_visibility)

        form.addRow("نام کاربری:", self.cb_username)
        form.addRow("رمز عبور:", self.ed_password)
        form.addRow("", self.chk_show)

        root.addWidget(form_container)

        # ── دکمه‌ها ──
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        self.btn_forgot = QPushButton("فراموشی رمز عبور؟")
        self.btn_forgot.setObjectName("link_button")
        self.btn_forgot.setFlat(True)
        self.btn_forgot.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_forgot.clicked.connect(self._show_forgot_message)

        btn_layout.addWidget(self.btn_forgot)
        btn_layout.addStretch()

        self.btn_refresh = QPushButton("بروزرسانی")
        self.btn_login = QPushButton("ورود")
        self.btn_login.setObjectName("btn_login")
        self.btn_cancel = QPushButton("انصراف")

        self.btn_refresh.clicked.connect(self._load_users)
        self.btn_login.clicked.connect(self._on_login)
        self.btn_cancel.clicked.connect(self.reject)

        btn_layout.addWidget(self.btn_refresh)
        btn_layout.addWidget(self.btn_login)
        btn_layout.addWidget(self.btn_cancel)

        root.addLayout(btn_layout)

        # ── برچسب وضعیت و راهنما ──
        self.lbl_hint = QLabel("")
        self.lbl_hint.setObjectName("hint_label")
        self.lbl_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.lbl_hint)

        self._apply_style()

    # ─────────────────────────────────────────────────────────────
    # مدیریت نمایش/مخفی‌سازی رمز
    # ─────────────────────────────────────────────────────────────
    def _setup_password_toggle(self) -> None:
        """افزودن دکمه اکشن چشم به فیلد رمز عبور."""
        self.act_toggle_password = QAction(self)
        self.act_toggle_password.setIcon(self._draw_eye_icon(visible=False))
        self.act_toggle_password.setToolTip("نمایش/مخفی‌سازی رمز")
        self.act_toggle_password.triggered.connect(
            lambda: self.chk_show.setChecked(not self.chk_show.isChecked())
        )
        self.ed_password.addAction(
            self.act_toggle_password, QLineEdit.ActionPosition.TrailingPosition
        )

    def _sync_password_visibility(self, visible: bool) -> None:
        """همگام‌سازی کامل اکشن درون فیلد و چک‌باکس."""
        mode = QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password
        self.ed_password.setEchoMode(mode)
        self.act_toggle_password.setIcon(self._draw_eye_icon(visible=visible))

    @staticmethod
    def _draw_eye_icon(visible: bool) -> QIcon:
        """رسم برداری آیکون چشم مستقل از سیستم عامل برای سازگاری ۱۰۰٪."""
        pixmap = QPixmap(20, 20)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        pen = QPen(QColor("#475569" if not visible else "#0099CC"), 1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        # رسم فرم چشم
        path = QPainterPath()
        path.moveTo(2, 10)
        path.quadTo(10, 3, 18, 10)
        path.quadTo(10, 17, 2, 10)
        painter.drawPath(path)

        # رسم مردمک
        if visible:
            painter.setBrush(QColor("#0099CC"))
            painter.drawEllipse(7, 7, 6, 6)
        else:
            painter.drawEllipse(8, 8, 4, 4)
            # خط مورب روی چشم وقتی مخفی است
            painter.drawLine(3, 3, 17, 17)

        painter.end()
        return QIcon(pixmap)

    # ─────────────────────────────────────────────────────────────
    # استایل دیالوگ
    # ─────────────────────────────────────────────────────────────
    def _apply_style(self) -> None:
        self.setStyleSheet("""
            QDialog {
                background-color: #f4f7fb;
            }
            #login_title {
                color: #0f172a;
                font-size: 15px;
                font-weight: bold;
            }
            #login_subtitle {
                color: #64748b;
                font-size: 11px;
            }
            #branding_label {
                font-size: 11px;
                color: #0284c7;
                font-weight: bold;
                background: #e0f2fe;
                padding: 7px 12px;
                border-radius: 9px;
            }
            QComboBox, QLineEdit {
                border: 1px solid #cbd5e1;
                border-radius: 9px;
                padding: 7px 11px;
                min-height: 30px;
                background: #ffffff;
                font-size: 12px;
                color: #0f172a;
                selection-background-color: #0284c7;
                selection-color: #ffffff;
            }
            QComboBox:focus, QLineEdit:focus {
                border: 2px solid #0284c7;
                background: #ffffff;
            }
            QPushButton {
                background-color: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 9px;
                padding: 8px 16px;
                min-height: 28px;
                font-weight: bold;
                font-size: 12px;
                min-width: 68px;
                min-height: 20px;
                color: #334155;
            }
            QPushButton:hover {
                background-color: #f1f5f9;
                border-color: #94a3b8;
            }
            QPushButton:pressed {
                background-color: #e2e8f0;
            }
            QPushButton#btn_login {
                background-color: #00BFFF;
                color: #ffffff;
                border: none;
            }
            QPushButton#btn_login:hover {
                background-color: #0369a1;
            }
            QPushButton#btn_login:pressed {
                background-color: #075985;
            }
            QPushButton:disabled {
                background-color: #e2e8f0;
                color: #94a3b8;
            }
            #link_button {
                background: transparent;
                border: none;
                color: #0284c7;
                text-decoration: underline;
                font-weight: normal;
                font-size: 11px;
                min-width: 0;
                padding: 0;
            }
            #link_button:hover {
                color: #0369a1;
            }
            #hint_label {
                color: #64748b;
                font-size: 11px;
            }
            QCheckBox {
                font-size: 11px;
                color: #475569;
            }
        """)

    # ─────────────────────────────────────────────────────────────
    # تنظیمات و برندینگ
    # ─────────────────────────────────────────────────────────────
    def _restore_geometry(self) -> None:
        geometry = self.settings.value("login_geometry")
        if geometry:
            self.restoreGeometry(geometry)

    def _save_geometry(self) -> None:
        self.settings.setValue("login_geometry", self.saveGeometry())

    def _branding_keys(self) -> Tuple[str, str]:
        db_id = os.path.basename(getattr(self.db, "db_path", "") or "default.db")
        return (
            f"branding/{db_id}/company_name",
            f"branding/{db_id}/project_name",
        )

    def _get_branding(self) -> Tuple[str, str]:
        k_company, k_project = self._branding_keys()
        company = str(self.settings.value(k_company, "") or "").strip()
        project = str(self.settings.value(k_project, "") or "").strip()
        return company, project

    # ─────────────────────────────────────────────────────────────
    # بارگذاری کاربران و تنظیم فوکوس
    # ─────────────────────────────────────────────────────────────
    def _fetch_users(self) -> List[Tuple[str, bool]]:
        """واکشی لیست نام کاربران و وضعیت فعال بودن از پایگاه داده."""
        with self.db.session() as sess:
            rows = (
                sess.query(User.username, User.is_active)
                .order_by(User.username.asc())
                .all()
            )
        result: List[Tuple[str, bool]] = []
        for username, is_active in rows:
            if username:
                u = str(username).strip()
                if u:
                    result.append((u, bool(is_active)))
        return result

    def _load_users(self) -> None:
        """بارگذاری کاربران در کمبوباکس بدون کوئری‌های تکراری."""
        cur_text = (self.cb_username.currentText() or "").strip()

        self.cb_username.blockSignals(True)
        self.cb_username.clear()

        try:
            self._cached_users = self._fetch_users()
        except Exception as exc:
            logger.exception("Failed to load users from DB")
            self.lbl_hint.setText("بارگذاری کاربران ناموفق بود.")
            self.cb_username.blockSignals(False)
            QMessageBox.critical(self, "خطا در اتصال", f"خطا در دریافت کاربران:\n{exc}")
            return

        active_count = 0
        for username, is_active in self._cached_users:
            if is_active:
                active_count += 1
                display = username
            else:
                display = f"{username} (غیرفعال)"
            self.cb_username.addItem(display, username)

        self.lbl_hint.setText(f"تعداد کاربران: {len(self._cached_users)}  |  فعال: {active_count}")

        # بازیابی انتخاب قبلی
        target_username = cur_text or self._last_username
        if target_username:
            idx = self._find_username_index(target_username)
            if idx >= 0:
                self.cb_username.setCurrentIndex(idx)

        self.cb_username.blockSignals(False)

        # به‌روزرسانی مدل تکمیل‌کننده
        comp = self.cb_username.completer()
        if comp is not None:
            comp.setModel(self.cb_username.model())

        # تنظیم بهینه فوکوس
        QTimer.singleShot(50, self._set_initial_focus)

    def _set_initial_focus(self) -> None:
        """تنظیم فوکوس با استفاده از کش کاربران به جای کوئری مجدد."""
        active_users = [u for u, active in self._cached_users if active]

        if len(active_users) == 1:
            idx = self._find_username_index(active_users[0])
            if idx >= 0:
                self.cb_username.setCurrentIndex(idx)
            self.ed_password.setFocus()
        elif self._last_username:
            idx = self._find_username_index(self._last_username)
            if idx >= 0:
                self.cb_username.setCurrentIndex(idx)
            self.ed_password.setFocus()
        else:
            if self.cb_username.lineEdit():
                self.cb_username.lineEdit().setFocus()
            else:
                self.cb_username.setFocus()

    def _find_username_index(self, username_or_display: str) -> int:
        target = (username_or_display or "").strip().lower()
        if not target:
            return -1

        for i in range(self.cb_username.count()):
            data = self.cb_username.itemData(i)
            if data is not None and str(data).strip().lower() == target:
                return i
            txt = self.cb_username.itemText(i)
            if txt and str(txt).strip().lower() == target:
                return i
        return -1

    def _selected_username(self) -> str:
        idx = self.cb_username.currentIndex()
        if idx >= 0:
            data = self.cb_username.itemData(idx)
            if data is not None:
                return str(data).strip()
        return (self.cb_username.currentText() or "").strip()

    # ─────────────────────────────────────────────────────────────
    # فرآیند احراز هویت
    # ─────────────────────────────────────────────────────────────
    def _show_forgot_message(self) -> None:
        QMessageBox.information(
            self,
            "بازیابی رمز عبور",
            "برای بازیابی یا تنظیم مجدد رمز عبور با مدیر سیستم تماس بگیرید.\n\n"
            "مدیر سیستم می‌تواند از بخش «مدیریت → مدیریت کاربران» رمز عبور شما را بازنشانی کند.",
        )

    def _on_login(self) -> None:
        """بررسی اعتبار کاربر و انجام ورود."""
        if self._login_in_progress:
            return

        self._login_in_progress = True
        self.btn_login.setEnabled(False)

        username = self._selected_username()
        password = self.ed_password.text()

        if not username:
            QMessageBox.warning(self, "ورود", "لطفاً نام کاربری را انتخاب یا وارد کنید.")
            self._reset_login_state(focus_password=False)
            return

        if not password:
            QMessageBox.warning(self, "ورود", "لطفاً رمز عبور را وارد کنید.")
            self._reset_login_state(focus_password=True)
            return

        try:
            user = self.db.authenticate(username, password)
        except Exception as exc:
            logger.exception("Authentication exception for user: %s", username)
            QMessageBox.critical(self, "خطای دیتابیس", f"خطا در بررسی مشخصات:\n{exc}")
            self._reset_login_state()
            return

        if not user:
            logger.warning("Failed login attempt for user: %s", username)
            QMessageBox.warning(
                self,
                "ورود ناموفق",
                "نام کاربری یا رمز عبور اشتباه است، یا حساب کاربری غیرفعال می‌باشد.",
            )
            self._reset_login_state(focus_password=True, select_all=True)
            return

        # بررسی الزام تغییر رمز در اولین ورود
        if getattr(user, "must_change_password", False):
            if not self._handle_force_password_change(user):
                self._reset_login_state()
                return

        # ذخیره نام کاربری معتبر
        self.settings.setValue("last_username", user.username)

        # مقداردهی نشست کاربر
        try:
            self.session = UserSession(
                user_id=user.id, username=user.username, role=user.role
            )
        except TypeError:
            self.session = UserSession(user.id, user.username, user.role)

        logger.info("User logged in successfully: %s (Role: %s)", user.username, user.role)
        self._login_in_progress = False
        self.btn_login.setEnabled(True)
        self.accept()

    def _handle_force_password_change(self, user: User) -> bool:
        """دیالوگ اجباری تغییر رمز عبور اولیه."""
        QMessageBox.information(
            self,
            "تغییر رمز عبور",
            "رمز عبور شما موقت است. لطفاً یک رمز عبور جدید تعیین کنید.",
        )

        new_password, ok = QInputDialog.getText(
            self,
            "تغییر رمز عبور",
            "رمز عبور جدید را وارد کنید (حداقل ۸ کاراکتر):",
            QLineEdit.EchoMode.Password,
        )
        if not ok or not new_password:
            return False

        new_password = new_password.strip()
        if len(new_password) < 8:
            QMessageBox.warning(self, "رمز عبور ضعیف", "رمز عبور جدید باید حداقل ۸ کاراکتر باشد.")
            return False

        confirm_password, ok = QInputDialog.getText(
            self,
            "تأیید رمز عبور",
            "تکرار رمز عبور جدید را وارد کنید:",
            QLineEdit.EchoMode.Password,
        )
        if not ok:
            return False

        if confirm_password != new_password:
            QMessageBox.warning(self, "عدم تطابق", "تکرار رمز عبور با رمز جدید مطابقت ندارد.")
            return False

        try:
            self.db.change_password(user.id, new_password)
            QMessageBox.information(self, "موفق", "رمز عبور با موفقیت تغییر یافت.")
            return True
        except Exception as exc:
            logger.exception("Failed to force change password for user %s", user.id)
            QMessageBox.critical(self, "خطا", f"تغییر رمز عبور انجام نشد:\n{exc}")
            return False

    def _reset_login_state(
        self, focus_password: bool = True, select_all: bool = False
    ) -> None:
        """بازنشانی کنترل‌های ورود پس از خطا."""
        self._login_in_progress = False
        self.btn_login.setEnabled(True)
        if focus_password:
            self.ed_password.setFocus()
            if select_all:
                self.ed_password.selectAll()
        else:
            if self.cb_username.lineEdit():
                self.cb_username.lineEdit().setFocus()

    # ─────────────────────────────────────────────────────────────
    # مدیریت پنجره
    # ─────────────────────────────────────────────────────────────
    def closeEvent(self, event: QCloseEvent) -> None:
        self._save_geometry()
        super().closeEvent(event)

    def reject(self) -> None:
        self._save_geometry()
        super().reject()