# -*- coding: utf-8 -*-
"""
ui.styles
استایل‌های سراسری، مدرن و ریسپانسیو سامانه Document & MOM Tracking System
شامل پالت رنگی فیروزه‌ای آسمانی (Sky Blue)، تم روشن ارگونومیک و تم تاریک حرفه‌ای

نسخه ۲.۰ بهسازی‌شده:
    - حذف تکرار ساختاری بین تم روشن و تاریک با یک قالب CSS واحد (Template)
    - پالت رنگ کامل با تمام رنگ‌های Hover/Border/Scrollbar/Tooltip
    - افزودن استایل QSlider، QCalendarWidget، QTreeView، QTreeWidget
    - رفع جهت مرز ComboBox در چیدمان RTL
    - افزودن حالت focus-visible برای دسترس‌پذیری
    - حذف ثابت منسوخ STYLE_SHEET (سازگاری با alias حفظ شده)
    - پوشش کامل polish فرم‌ها در همان قالب
"""
from __future__ import annotations

from string import Template
from typing import Dict, Union

from PyQt6.QtWidgets import QApplication, QWidget


# ══════════════════════════════════════════════════
# پالت رنگ‌های پایه (Brand Palette)
# ══════════════════════════════════════════════════
COLOR_SKY_BLUE      = "#00BFFF"
COLOR_SKY_DARK      = "#0099CC"
COLOR_SKY_DARKER    = "#007799"
COLOR_SKY_LIGHT     = "#e0f2fe"
COLOR_SKY_BORDER    = "#7dd3fc"

COLOR_SUCCESS       = "#16a34a"
COLOR_WARNING       = "#f59e0b"
COLOR_DANGER        = "#e53935"
COLOR_DANGER_DARK   = "#c62828"
COLOR_INFO          = "#0284c7"

COLOR_LIGHT_BG_MAIN     = "#f8fafc"
COLOR_LIGHT_BG_PANEL    = "#ffffff"
COLOR_LIGHT_BG_ALT      = "#f1f5f9"
COLOR_LIGHT_TEXT_MAIN   = "#0f172a"
COLOR_LIGHT_TEXT_MUTED  = "#64748b"
COLOR_LIGHT_BORDER      = "#cbd5e1"
COLOR_LIGHT_GRID        = "#e2e8f0"

COLOR_DARK_BG_MAIN      = "#0b1220"
COLOR_DARK_BG_PANEL     = "#1e293b"
COLOR_DARK_BG_ALT       = "#0f172a"
COLOR_DARK_TEXT_MAIN    = "#f8fafc"
COLOR_DARK_TEXT_MUTED   = "#94a3b8"
COLOR_DARK_BORDER       = "#334155"
COLOR_DARK_GRID         = "#1e293b"

GLOBAL_FONT_FAMILY = "'Vazirmatn', 'Segoe UI', Tahoma, Arial, sans-serif"


# ══════════════════════════════════════════════════
# قالب CSS واحد — تنها منبع ساختار استایل
# (تمام رنگ‌ها از پالت تزریق می‌شوند)
# ══════════════════════════════════════════════════
_THEME_TEMPLATE = Template(r"""
/* ════════════════════════════════════════════
   پایه
   ════════════════════════════════════════════ */
QMainWindow, QDialog, QWidget {
    background-color: $bg_main;
    color: $text_main;
    font-family: $font_family;
    font-size: 12.5px;
}

QLabel {
    color: $text_main;
    padding-top: 1px;
    padding-bottom: 1px;
}

/* ════════════════════════════════════════════
   پنل‌ها و فریم‌ها
   ════════════════════════════════════════════ */
QFrame#content_frame, QFrame#card, QFrame#metric_card, QFrame#form_card {
    background-color: $bg_panel;
    border: 1px solid $border;
    border-radius: 12px;
}

QGroupBox {
    background-color: $bg_panel;
    border: 1px solid $border;
    border-radius: 10px;
    margin-top: 24px;
    padding: 18px 12px 12px 12px;
    font-weight: bold;
    color: $text_main;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top right;
    right: 14px;
    padding: 0 8px;
    color: $brand_title_fg;
}

/* ════════════════════════════════════════════
   جدول‌ها
   ════════════════════════════════════════════ */
QTableView, QTableWidget {
    background-color: $bg_panel;
    alternate-background-color: $row_alt;
    border: 1px solid $border;
    border-radius: 8px;
    gridline-color: $grid;
    color: $text_main;
    selection-background-color: $selection_bg;
    selection-color: $selection_fg;
    outline: none;
    font-size: 12px;
}

QTableView::item, QTableWidget::item {
    padding: 6px 8px;
    border: none;
}

QTableView::item:hover, QTableWidget::item:hover {
    background-color: $row_hover;
}

QTableView::item:selected, QTableWidget::item:selected {
    background-color: $selection_bg;
    color: $selection_fg;
}

QHeaderView::section {
    background-color: $header_bg;
    color: $text_main;
    padding: 6px 8px;
    border: none;
    border-right: 1px solid $border;
    border-bottom: 2px solid $border;
    font-weight: bold;
    font-size: 12px;
}

QHeaderView::section:hover {
    background-color: $header_hover;
}

QTableCornerButton::section {
    background-color: $header_bg;
    border: none;
    border-bottom: 2px solid $border;
}

/* ════════════════════════════════════════════
   لیست‌ها و درخت‌ها
   ════════════════════════════════════════════ */
QListWidget, QListView, QTreeView, QTreeWidget {
    background-color: $bg_panel;
    border: 1px solid $border;
    border-radius: 8px;
    padding: 4px;
    color: $text_main;
    outline: none;
}

QListWidget::item, QListView::item,
QTreeView::item, QTreeWidget::item {
    padding: 8px 10px;
    border-radius: 6px;
    margin-bottom: 2px;
}

QListWidget::item:hover, QListView::item:hover,
QTreeView::item:hover, QTreeWidget::item:hover {
    background-color: $list_hover;
}

QListWidget::item:selected, QListView::item:selected,
QTreeView::item:selected, QTreeWidget::item:selected {
    background-color: $brand;
    color: $brand_text;
}

QTreeView::branch {
    background: transparent;
}

/* ════════════════════════════════════════════
   دکمه‌ها
   ════════════════════════════════════════════ */
QPushButton {
    background-color: $brand;
    color: $brand_text;
    border: none;
    border-radius: 8px;
    padding: 7px 17px;
    font-weight: bold;
    font-size: 12px;
    min-height: 30px;
}

QPushButton:hover {
    background-color: $brand_hover;
}

QPushButton:pressed {
    background-color: $brand_pressed;
}

QPushButton:focus {
    outline: none;
    border: 2px solid $focus_ring;
}

QPushButton:disabled {
    background-color: $btn_disabled_bg;
    color: $btn_disabled_fg;
}

QPushButton#btn_secondary, QPushButton[secondary="true"] {
    background-color: $bg_panel;
    color: $text_main;
    border: 1px solid $border;
}

QPushButton#btn_secondary:hover, QPushButton[secondary="true"]:hover {
    background-color: $bg_alt;
    border-color: $border_hover;
}

QPushButton#btn_danger, QPushButton[danger="true"] {
    background-color: $danger;
    color: #ffffff;
    border: none;
}

QPushButton#btn_danger:hover, QPushButton[danger="true"]:hover {
    background-color: $danger_hover;
}

QPushButton#link_button {
    background: transparent;
    border: none;
    color: $link_fg;
    text-decoration: underline;
    font-weight: normal;
    min-width: 0;
    padding: 0;
    min-height: 0;
}

QPushButton#link_button:hover {
    color: $link_hover_fg;
}

/* ════════════════════════════════════════════
   فیلدهای ورودی
   ════════════════════════════════════════════ */
QLineEdit, QComboBox, QDateEdit, QDateTimeEdit, QTimeEdit,
QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox {
    border: 1px solid $border;
    border-radius: 8px;
    padding: 6px 11px;
    background-color: $bg_input;
    color: $text_main;
    font-size: 12px;
    min-height: 30px;
    selection-background-color: $brand;
    selection-color: $brand_text;
}

QLineEdit:hover, QComboBox:hover, QDateEdit:hover, QDateTimeEdit:hover,
QTimeEdit:hover, QTextEdit:hover, QPlainTextEdit:hover,
QSpinBox:hover, QDoubleSpinBox:hover {
    border-color: $border_hover;
}

QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QDateTimeEdit:focus,
QTimeEdit:focus, QTextEdit:focus, QPlainTextEdit:focus,
QSpinBox:focus, QDoubleSpinBox:focus {
    border: 2px solid $border_focus;
    background-color: $bg_input_focus;
}

QLineEdit:read-only, QTextEdit:read-only, QPlainTextEdit:read-only {
    background-color: $bg_input_readonly;
    color: $text_muted;
}

QLineEdit:disabled, QComboBox:disabled, QDateEdit:disabled,
QDateTimeEdit:disabled, QTimeEdit:disabled, QTextEdit:disabled,
QPlainTextEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {
    background-color: $bg_input_disabled;
    color: $text_disabled;
}

/* ── ComboBox Drop-Down (RTL: فلش در سمت چپ، مرز در سمت راست کادر) ── */
QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top left;
    width: 24px;
    border-right: 1px solid $border;
    background: transparent;
}

QComboBox::down-arrow {
    image: none;
    width: 8px;
    height: 8px;
    border-left: 2px solid $text_muted;
    border-bottom: 2px solid $text_muted;
    transform: rotate(-45deg);
    margin-right: 6px;
}

QComboBox QAbstractItemView {
    border: 1px solid $border;
    background-color: $bg_panel;
    color: $text_main;
    selection-background-color: $brand;
    selection-color: $brand_text;
    outline: none;
}

/* ════════════════════════════════════════════
   چک‌باکس و رادیوباتن
   ════════════════════════════════════════════ */
QCheckBox, QRadioButton {
    color: $text_main;
    spacing: 8px;
    font-size: 12px;
}

QCheckBox::indicator, QRadioButton::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid $border;
    border-radius: 4px;
    background-color: $bg_input;
}

QRadioButton::indicator {
    border-radius: 9px;
}

QCheckBox::indicator:hover, QRadioButton::indicator:hover {
    border-color: $brand;
}

QCheckBox::indicator:checked, QRadioButton::indicator:checked {
    background-color: $brand;
    border-color: $brand_hover;
}

/* ════════════════════════════════════════════
   اسلایدر
   ════════════════════════════════════════════ */
QSlider::groove:horizontal {
    height: 4px;
    background: $bg_alt;
    border-radius: 2px;
}

QSlider::sub-page:horizontal {
    background: $brand;
    border-radius: 2px;
}

QSlider::handle:horizontal {
    background: $bg_panel;
    border: 2px solid $brand;
    width: 14px;
    height: 14px;
    margin: -6px 0;
    border-radius: 8px;
}

QSlider::handle:horizontal:hover {
    background: $brand;
}

/* ════════════════════════════════════════════
   منوها
   ════════════════════════════════════════════ */
QMenuBar {
    background-color: $menubar_bg;
    color: $text_main;
    border-bottom: 1px solid $border;
    padding: 2px 4px;
    font-weight: bold;
}

QMenuBar::item {
    background: transparent;
    padding: 6px 12px;
    border-radius: 4px;
}

QMenuBar::item:selected {
    background-color: $menubar_hover_bg;
    color: $menubar_hover_fg;
}

QMenu {
    background-color: $bg_panel;
    border: 1px solid $border;
    border-radius: 6px;
    padding: 4px;
}

QMenu::item {
    padding: 6px 28px 6px 20px;
    border-radius: 4px;
    color: $text_main;
}

QMenu::item:selected {
    background-color: $brand;
    color: $brand_text;
}

QMenu::separator {
    height: 1px;
    background-color: $grid;
    margin: 4px 8px;
}

/* ════════════════════════════════════════════
   نوار ابزار
   ════════════════════════════════════════════ */
QToolBar {
    background-color: $toolbar_bg;
    border-bottom: 1px solid $border;
    spacing: 6px;
    padding: 4px;
}

QToolButton {
    background-color: $toolbutton_bg;
    border: 1px solid $border;
    border-radius: 5px;
    padding: 4px 10px;
    color: $text_main;
}

QToolButton:hover {
    background-color: $toolbutton_hover;
    border-color: $border_hover;
}

QToolButton:pressed {
    background-color: $toolbutton_pressed;
}

/* ════════════════════════════════════════════
   نوار وضعیت
   ════════════════════════════════════════════ */
QStatusBar {
    background-color: $statusbar_bg;
    color: $text_muted;
    border-top: 1px solid $border;
}

QStatusBar QLabel {
    background: transparent;
    color: $text_main;
}

#lbl_stats, #lbl_date, #lbl_page {
    color: $statusbar_accent;
    font-weight: bold;
}

/* ════════════════════════════════════════════
   اسکرول‌بارها (عمودی و افقی یکسان‌سازی شده)
   ════════════════════════════════════════════ */
QScrollBar:vertical {
    background-color: $scrollbar_bg;
    width: 8px;
    margin: 0;
    border-radius: 4px;
}

QScrollBar::handle:vertical {
    background-color: $scrollbar_handle;
    min-height: 24px;
    border-radius: 4px;
}

QScrollBar::handle:vertical:hover {
    background-color: $scrollbar_handle_hover;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}

QScrollBar:horizontal {
    background-color: $scrollbar_bg;
    height: 8px;
    margin: 0;
    border-radius: 4px;
}

QScrollBar::handle:horizontal {
    background-color: $scrollbar_handle;
    min-width: 24px;
    border-radius: 4px;
}

QScrollBar::handle:horizontal:hover {
    background-color: $scrollbar_handle_hover;
}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
}

/* ════════════════════════════════════════════
   تب‌ها
   ════════════════════════════════════════════ */
QTabWidget::pane {
    border: 1px solid $border;
    background-color: $bg_panel;
    border-radius: 6px;
}

QTabBar::tab {
    background-color: $tab_bg;
    color: $text_muted;
    padding: 8px 18px;
    border: 1px solid $border;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    font-weight: bold;
}

QTabBar::tab:selected {
    background-color: $tab_selected_bg;
    color: $tab_selected_fg;
    border-bottom: 2px solid $brand;
}

QTabBar::tab:hover:!selected {
    background-color: $tab_hover_bg;
}

/* ════════════════════════════════════════════
   نوار پیشرفت
   ════════════════════════════════════════════ */
QProgressBar {
    border: 1px solid $border;
    border-radius: 6px;
    text-align: center;
    background-color: $progress_bg;
    color: $text_main;
    font-weight: bold;
    min-height: 14px;
}

QProgressBar::chunk {
    background-color: $brand;
    border-radius: 5px;
}

/* ════════════════════════════════════════════
   تقویم
   ════════════════════════════════════════════ */
QCalendarWidget QWidget {
    alternate-background-color: $bg_alt;
    color: $text_main;
}

QCalendarWidget QAbstractItemView {
    background-color: $bg_panel;
    color: $text_main;
    selection-background-color: $brand;
    selection-color: $brand_text;
    outline: none;
}

QCalendarWidget QToolButton {
    color: $text_main;
    background-color: transparent;
    border: none;
}

QCalendarWidget QMenu {
    background-color: $bg_panel;
    color: $text_main;
}

/* ════════════════════════════════════════════
   Tooltip و Splitter
   ════════════════════════════════════════════ */
QToolTip {
    background-color: $tooltip_bg;
    color: $tooltip_fg;
    border: 1px solid $tooltip_border;
    border-radius: 5px;
    padding: 7px 10px;
    font-size: 11px;
}

QSplitter::handle {
    background-color: $splitter_handle;
}

QSplitter::handle:hover {
    background-color: $brand;
}

QScrollArea {
    border: none;
    background: transparent;
}
""")


# ══════════════════════════════════════════════════
# پالت‌های تزریق (Light / Dark)
# ══════════════════════════════════════════════════
_LIGHT_PALETTE: Dict[str, str] = {
    "font_family": GLOBAL_FONT_FAMILY,

    # Base
    "bg_main":  COLOR_LIGHT_BG_MAIN,
    "bg_panel": COLOR_LIGHT_BG_PANEL,
    "bg_alt":   COLOR_LIGHT_BG_ALT,
    "text_main":  COLOR_LIGHT_TEXT_MAIN,
    "text_muted": COLOR_LIGHT_TEXT_MUTED,
    "text_disabled": "#94a3b8",

    # Borders / Grid
    "border":         COLOR_LIGHT_BORDER,
    "border_hover":   "#94a3b8",
    "border_focus":   "#00a8d8",
    "focus_ring":     "#60a5fa",
    "grid":           COLOR_LIGHT_GRID,

    # Brand
    "brand":         COLOR_SKY_BLUE,
    "brand_hover":   COLOR_SKY_DARK,
    "brand_pressed": COLOR_SKY_DARKER,
    "brand_text":    "#ffffff",
    "brand_title_fg": COLOR_INFO,

    # Semantic
    "danger":       COLOR_DANGER,
    "danger_hover": COLOR_DANGER_DARK,
    "success":      COLOR_SUCCESS,
    "info":         COLOR_INFO,

    # Selection
    "selection_bg": "#b2ebf2",
    "selection_fg": "#000000",

    # Header
    "header_bg":    "#e8ecf1",
    "header_hover": "#dde4ea",

    # Row
    "row_alt":   COLOR_LIGHT_BG_ALT,
    "row_hover": "#e0f7fa",

    # Input
    "bg_input":           "#ffffff",
    "bg_input_focus":     "#fafdff",
    "bg_input_readonly":  COLOR_LIGHT_BG_ALT,
    "bg_input_disabled":  "#f1f5f9",
    "btn_disabled_bg":    "#cbd5e1",
    "btn_disabled_fg":    "#888888",

    # Menu
    "menubar_bg":        COLOR_LIGHT_BG_PANEL,
    "menubar_hover_bg":  COLOR_LIGHT_BG_ALT,
    "menubar_hover_fg":  COLOR_INFO,

    # Toolbar
    "toolbar_bg":        COLOR_LIGHT_BG_PANEL,
    "toolbutton_bg":     COLOR_LIGHT_BG_ALT,
    "toolbutton_hover":  "#e2e8f0",
    "toolbutton_pressed": "#cbd5e1",

    # Statusbar
    "statusbar_bg":     "#f1f5f9",
    "statusbar_accent": "#0369a1",

    # Scrollbar
    "scrollbar_bg":           COLOR_LIGHT_BG_MAIN,
    "scrollbar_handle":       "#cbd5e1",
    "scrollbar_handle_hover": "#94a3b8",

    # Tabs
    "tab_bg":           COLOR_LIGHT_BG_ALT,
    "tab_selected_bg":  COLOR_LIGHT_BG_PANEL,
    "tab_selected_fg":  COLOR_SKY_DARKER,
    "tab_hover_bg":     "#e2e8f0",

    # Lists
    "list_hover": COLOR_LIGHT_BG_ALT,

    # Progress
    "progress_bg": COLOR_LIGHT_BG_ALT,

    # Tooltip
    "tooltip_bg":     "#0f172a",
    "tooltip_fg":     "#ffffff",
    "tooltip_border": "#334155",

    # Splitter
    "splitter_handle": COLOR_LIGHT_GRID,

    # Link
    "link_fg":       COLOR_INFO,
    "link_hover_fg": "#0369a1",
}


_DARK_PALETTE: Dict[str, str] = {
    "font_family": GLOBAL_FONT_FAMILY,

    # Base
    "bg_main":  COLOR_DARK_BG_MAIN,
    "bg_panel": COLOR_DARK_BG_PANEL,
    "bg_alt":   COLOR_DARK_BG_ALT,
    "text_main":  COLOR_DARK_TEXT_MAIN,
    "text_muted": COLOR_DARK_TEXT_MUTED,
    "text_disabled": "#475569",

    # Borders / Grid
    "border":         COLOR_DARK_BORDER,
    "border_hover":   "#64748b",
    "border_focus":   COLOR_SKY_BLUE,
    "focus_ring":     "#60a5fa",
    "grid":           COLOR_DARK_GRID,

    # Brand
    "brand":         COLOR_SKY_BLUE,
    "brand_hover":   COLOR_SKY_DARK,
    "brand_pressed": COLOR_SKY_DARKER,
    "brand_text":    "#ffffff",
    "brand_title_fg": COLOR_SKY_BLUE,

    # Semantic
    "danger":       COLOR_DANGER,
    "danger_hover": COLOR_DANGER_DARK,
    "success":      COLOR_SUCCESS,
    "info":         COLOR_INFO,

    # Selection
    "selection_bg": "#006080",
    "selection_fg": "#ffffff",

    # Header
    "header_bg":    "#1e293b",
    "header_hover": "#2d3d5a",

    # Row
    "row_alt":   "#243048",
    "row_hover": "#2a3b5c",

    # Input
    "bg_input":           "#162032",
    "bg_input_focus":     "#1a263c",
    "bg_input_readonly":  COLOR_DARK_BG_ALT,
    "bg_input_disabled":  COLOR_DARK_BG_MAIN,
    "btn_disabled_bg":    "#334155",
    "btn_disabled_fg":    "#64748b",

    # Menu
    "menubar_bg":        "#0b1220",
    "menubar_hover_bg":  "#1e293b",
    "menubar_hover_fg":  COLOR_SKY_BLUE,

    # Toolbar
    "toolbar_bg":        "#0b1220",
    "toolbutton_bg":     "#1e293b",
    "toolbutton_hover":  "#2d3d5a",
    "toolbutton_pressed": COLOR_DARK_BG_ALT,

    # Statusbar
    "statusbar_bg":     "#080d18",
    "statusbar_accent": COLOR_SKY_BLUE,

    # Scrollbar
    "scrollbar_bg":           COLOR_DARK_BG_MAIN,
    "scrollbar_handle":       "#334155",
    "scrollbar_handle_hover": "#475569",

    # Tabs
    "tab_bg":           "#121b2b",
    "tab_selected_bg":  COLOR_DARK_BG_PANEL,
    "tab_selected_fg":  COLOR_SKY_BLUE,
    "tab_hover_bg":     "#1a263c",

    # Lists
    "list_hover": "#2a374d",

    # Progress
    "progress_bg": "#121b2b",

    # Tooltip
    "tooltip_bg":     "#0f172a",
    "tooltip_fg":     "#ffffff",
    "tooltip_border": "#334155",

    # Splitter
    "splitter_handle": COLOR_DARK_BORDER,

    # Link
    "link_fg":       COLOR_SKY_BLUE,
    "link_hover_fg": "#7dd3fc",
}


# ══════════════════════════════════════════════════
# رندر نهایی استایل‌ها
# ══════════════════════════════════════════════════
LIGHT_STYLE: str = _THEME_TEMPLATE.substitute(_LIGHT_PALETTE)
DARK_STYLE:  str = _THEME_TEMPLATE.substitute(_DARK_PALETTE)


# ══════════════════════════════════════════════════
# ثابت سازگاری (compatibility)
# ══════════════════════════════════════════════════
STYLE_SHEET = LIGHT_STYLE


# ══════════════════════════════════════════════════
# توابع کمکی
# ══════════════════════════════════════════════════

def get_stylesheet(dark_mode: bool = False) -> str:
    """
    برگرداندن رشته استایل کامل بر اساس وضعیت تم روشن یا تاریک.

    Args:
        dark_mode: در صورت True استایل تاریک، در غیر این صورت روشن.

    Returns:
        رشته کامل استایل آماده اعمال روی QApplication/QWidget.
    """
    return DARK_STYLE if dark_mode else LIGHT_STYLE


def apply_theme(
    target: Union[QApplication, QWidget],
    dark_mode: bool = False,
) -> None:
    """
    اعمال مستقیم و آنی تم به نمونه برنامه (QApplication) یا یک ویجت خاص.

    Args:
        target: نمونه QApplication یا شیء QWidget/QMainWindow
        dark_mode: وضعیت حالت شب/روز
    """
    if target is None:
        return
    try:
        target.setStyleSheet(get_stylesheet(dark_mode=dark_mode))
    except Exception:
        # چاپ در لاگ در سطح بالاتر اگر تنظیم استایل ناموفق بود
        import logging
        logging.getLogger(__name__).exception(
            "Failed to apply theme (dark_mode=%s) to %r", dark_mode, target
        )


def get_palette(dark_mode: bool = False) -> Dict[str, str]:
    """
    دسترسی به دیکشنری پالت رنگ برای استفاده در محاسبات خارجی.
    (مثلاً تولید HTML یا QColor-based rendering).

    Args:
        dark_mode: در صورت True پالت تاریک، در غیر این صورت روشن.
    """
    return dict(_DARK_PALETTE if dark_mode else _LIGHT_PALETTE)


__all__ = [
    # توابع
    "get_stylesheet",
    "apply_theme",
    "get_palette",
    # استایل‌های رندرشده
    "LIGHT_STYLE",
    "DARK_STYLE",
    "STYLE_SHEET",
    # پالت رنگ
    "COLOR_SKY_BLUE",
    "COLOR_SKY_DARK",
    "COLOR_SKY_DARKER",
    "COLOR_SKY_LIGHT",
    "COLOR_SKY_BORDER",
    "COLOR_SUCCESS",
    "COLOR_WARNING",
    "COLOR_DANGER",
    "COLOR_DANGER_DARK",
    "COLOR_INFO",
    "COLOR_LIGHT_BG_MAIN",
    "COLOR_LIGHT_BG_PANEL",
    "COLOR_LIGHT_BG_ALT",
    "COLOR_LIGHT_TEXT_MAIN",
    "COLOR_LIGHT_TEXT_MUTED",
    "COLOR_LIGHT_BORDER",
    "COLOR_LIGHT_GRID",
    "COLOR_DARK_BG_MAIN",
    "COLOR_DARK_BG_PANEL",
    "COLOR_DARK_BG_ALT",
    "COLOR_DARK_TEXT_MAIN",
    "COLOR_DARK_TEXT_MUTED",
    "COLOR_DARK_BORDER",
    "COLOR_DARK_GRID",
    "GLOBAL_FONT_FAMILY",
]
