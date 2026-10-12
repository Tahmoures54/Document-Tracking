# -*- coding: utf-8 -*-
"""
ui.styles
استایل‌های سراسری، مدرن و ریسپانسیو سامانه Document & MOM Tracking System
شامل پالت رنگی فیروزه‌ای آسمانی (Sky Blue)، تم روشن ارگونومیک و تم تاریک حرفه‌ای
"""
from __future__ import annotations

from typing import Union
from PyQt6.QtWidgets import QApplication, QWidget

# ─────────────────────────────────────────────
# پالت رنگ‌های اصلی سیستم (Brand Palette)
# ─────────────────────────────────────────────
COLOR_SKY_BLUE      = "#00BFFF"       # رنگ اصلی برند
COLOR_SKY_DARK      = "#0099CC"       # رنگ Hover دکمه‌ها
COLOR_SKY_DARKER    = "#007799"       # رنگ Pressed دکمه‌ها
COLOR_SKY_LIGHT     = "#e0f2fe"       # پس‌زمینه لایت فیروزه‌ای
COLOR_SKY_BORDER    = "#7dd3fc"       # حاشیه المان‌های فعال

# رنگ‌های وضعیت (Status Colors)
COLOR_SUCCESS       = "#16a34a"
COLOR_WARNING       = "#f59e0b"
COLOR_DANGER        = "#e53935"
COLOR_DANGER_DARK   = "#c62828"
COLOR_INFO          = "#0284c7"

# رنگ‌های عمومی تم روشن (Light Theme Palette)
COLOR_LIGHT_BG_MAIN     = "#f8fafc"
COLOR_LIGHT_BG_PANEL    = "#ffffff"
COLOR_LIGHT_BG_ALT      = "#f1f5f9"
COLOR_LIGHT_TEXT_MAIN   = "#0f172a"
COLOR_LIGHT_TEXT_MUTED  = "#64748b"
COLOR_LIGHT_BORDER      = "#cbd5e1"
COLOR_LIGHT_GRID        = "#e2e8f0"

# رنگ‌های عمومی تم تاریک (Dark Theme Palette)
COLOR_DARK_BG_MAIN      = "#0b1220"
COLOR_DARK_BG_PANEL     = "#1e293b"
COLOR_DARK_BG_ALT       = "#0f172a"
COLOR_DARK_TEXT_MAIN    = "#f8fafc"
COLOR_DARK_TEXT_MUTED   = "#94a3b8"
COLOR_DARK_BORDER       = "#334155"
COLOR_DARK_GRID         = "#1e293b"

# فونت پیش‌فرض سراسری با پشتیبانی کامل از زبان فارسی
GLOBAL_FONT_FAMILY = "'Vazirmatn', 'Segoe UI', Tahoma, Arial, sans-serif"


# ─────────────────────────────────────────────
# ۱. استایل حالت روشن (Light Theme)
# ─────────────────────────────────────────────
LIGHT_STYLE = f"""
/* ========== تنظیمات پایه پنجره‌ها ========== */
QMainWindow, QDialog, QWidget {{
    background-color: {COLOR_LIGHT_BG_MAIN};
    color: {COLOR_LIGHT_TEXT_MAIN};
    font-family: {GLOBAL_FONT_FAMILY};
    font-size: 12.5px;
}}

/* ========== پنل‌ها و فریم‌ها ========== */
QFrame#content_frame, QFrame#card, QFrame#metric_card {{
    background-color: {COLOR_LIGHT_BG_PANEL};
    border: 1px solid {COLOR_LIGHT_BORDER};
    border-radius: 10px;
}}

QGroupBox {{
    background-color: {COLOR_LIGHT_BG_PANEL};
    border: 1px solid {COLOR_LIGHT_BORDER};
    border-radius: 8px;
    margin-top: 24px;
    padding-top: 14px;
    font-weight: bold;
    color: {COLOR_LIGHT_TEXT_MAIN};
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top right;
    right: 14px;
    padding: 0 6px;
    color: {COLOR_INFO};
}}

/* ========== جدول‌ها (QTableView & QTableWidget) ========== */
QTableView, QTableWidget {{
    background-color: {COLOR_LIGHT_BG_PANEL};
    alternate-background-color: {COLOR_LIGHT_BG_ALT};
    border: 1px solid {COLOR_LIGHT_BORDER};
    border-radius: 8px;
    gridline-color: {COLOR_LIGHT_GRID};
    color: {COLOR_LIGHT_TEXT_MAIN};
    selection-background-color: #b2ebf2;
    selection-color: #000000;
    outline: none;
    font-size: 12px;
}}

QTableView::item, QTableWidget::item {{
    padding: 6px 8px;
    border: none;
}}

QTableView::item:hover, QTableWidget::item:hover {{
    background-color: #e0f7fa;
}}

QTableView::item:selected, QTableWidget::item:selected {{
    background-color: #b2ebf2;
    color: #000000;
}}

/* سربرگ جدول‌ها */
QHeaderView::section {{
    background-color: #e8ecf1;
    color: {COLOR_LIGHT_TEXT_MAIN};
    padding: 6px 8px;
    border: none;
    border-right: 1px solid {COLOR_LIGHT_BORDER};
    border-bottom: 2px solid {COLOR_LIGHT_BORDER};
    font-weight: bold;
    font-size: 12px;
}}

QHeaderView::section:hover {{
    background-color: #dde4ea;
}}

QTableCornerButton::section {{
    background-color: #e8ecf1;
    border: none;
    border-bottom: 2px solid {COLOR_LIGHT_BORDER};
}}

/* ========== لیست‌ها (QListWidget) ========== */
QListWidget, QListView {{
    background-color: {COLOR_LIGHT_BG_PANEL};
    border: 1px solid {COLOR_LIGHT_BORDER};
    border-radius: 8px;
    padding: 4px;
    color: {COLOR_LIGHT_TEXT_MAIN};
}}

QListWidget::item, QListView::item {{
    padding: 8px 10px;
    border-radius: 6px;
    margin-bottom: 2px;
}}

QListWidget::item:hover, QListView::item:hover {{
    background-color: {COLOR_LIGHT_BG_ALT};
}}

QListWidget::item:selected, QListView::item:selected {{
    background-color: {COLOR_SKY_BLUE};
    color: #ffffff;
}}

/* ========== دکمه‌ها (Buttons) ========== */
QPushButton {{
    background-color: {COLOR_SKY_BLUE};
    color: #ffffff;
    border: none;
    border-radius: 6px;
    padding: 5px 16px;
    font-weight: bold;
    font-size: 12px;
    min-height: 22px;
}}

QPushButton:hover {{
    background-color: {COLOR_SKY_DARK};
}}

QPushButton:pressed {{
    background-color: {COLOR_SKY_DARKER};
}}

QPushButton:disabled {{
    background-color: #cbd5e1;
    color: #888888;
}}

/* دکمه‌های ثانویه / سفید */
QPushButton#btn_secondary, QPushButton[secondary="true"] {{
    background-color: {COLOR_LIGHT_BG_PANEL};
    color: {COLOR_LIGHT_TEXT_MAIN};
    border: 1px solid {COLOR_LIGHT_BORDER};
}}

QPushButton#btn_secondary:hover, QPushButton[secondary="true"]:hover {{
    background-color: {COLOR_LIGHT_BG_ALT};
    border-color: #94a3b8;
}}

/* دکمه‌های خطر (حذف) */
QPushButton#btn_danger, QPushButton[danger="true"] {{
    background-color: {COLOR_DANGER};
    color: #ffffff;
    border: none;
}}

QPushButton#btn_danger:hover, QPushButton[danger="true"]:hover {{
    background-color: {COLOR_DANGER_DARK};
}}

/* دکمه‌های لینک و متنی */
QPushButton#link_button {{
    background: transparent;
    border: none;
    color: {COLOR_INFO};
    text-decoration: underline;
    font-weight: normal;
    min-width: 0;
    padding: 0;
}}

QPushButton#link_button:hover {{
    color: #0369a1;
}}

/* ========== فیلدهای ورودی ========== */
QLineEdit, QComboBox, QDateEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox {{
    border: 1px solid {COLOR_LIGHT_BORDER};
    border-radius: 6px;
    padding: 4px 10px;
    background-color: {COLOR_LIGHT_BG_PANEL};
    color: {COLOR_LIGHT_TEXT_MAIN};
    font-size: 12px;
    min-height: 22px;
    selection-background-color: {COLOR_SKY_BLUE};
    selection-color: #ffffff;
}}

QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QSpinBox:focus {{
    border: 1.5px solid {COLOR_SKY_BLUE};
    background-color: #ffffff;
}}

QLineEdit:read-only, QTextEdit:read-only {{
    background-color: {COLOR_LIGHT_BG_ALT};
    color: {COLOR_LIGHT_TEXT_MUTED};
}}

QLineEdit:disabled, QComboBox:disabled, QDateEdit:disabled {{
    background-color: #f1f5f9;
    color: #94a3b8;
}}

QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top left;
    width: 24px;
    border-left: 1px solid {COLOR_LIGHT_BORDER};
}}

/* ========== چک‌باکس و رادیوباتن ========== */
QCheckBox, QRadioButton {{
    color: {COLOR_LIGHT_TEXT_MAIN};
    spacing: 8px;
    font-size: 12px;
}}

QCheckBox::indicator, QRadioButton::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {COLOR_LIGHT_BORDER};
    border-radius: 4px;
    background-color: {COLOR_LIGHT_BG_PANEL};
}}

QRadioButton::indicator {{
    border-radius: 9px;
}}

QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
    border-color: {COLOR_SKY_BLUE};
}}

QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background-color: {COLOR_SKY_BLUE};
    border-color: {COLOR_SKY_DARK};
}}

/* ========== منوها و منوبار ========== */
QMenuBar {{
    background-color: {COLOR_LIGHT_BG_PANEL};
    color: {COLOR_LIGHT_TEXT_MAIN};
    border-bottom: 1px solid {COLOR_LIGHT_BORDER};
    padding: 2px 4px;
    font-weight: bold;
}}

QMenuBar::item {{
    background: transparent;
    padding: 6px 12px;
    border-radius: 4px;
}}

QMenuBar::item:selected {{
    background-color: {COLOR_LIGHT_BG_ALT};
    color: {COLOR_INFO};
}}

QMenu {{
    background-color: {COLOR_LIGHT_BG_PANEL};
    border: 1px solid {COLOR_LIGHT_BORDER};
    border-radius: 6px;
    padding: 4px;
}}

QMenu::item {{
    padding: 6px 28px 6px 20px;
    border-radius: 4px;
    color: {COLOR_LIGHT_TEXT_MAIN};
}}

QMenu::item:selected {{
    background-color: {COLOR_SKY_BLUE};
    color: #ffffff;
}}

QMenu::separator {{
    height: 1px;
    background-color: {COLOR_LIGHT_GRID};
    margin: 4px 8px;
}}

/* ========== نوار ابزار (QToolBar) ========== */
QToolBar {{
    background-color: {COLOR_LIGHT_BG_PANEL};
    border-bottom: 1px solid {COLOR_LIGHT_BORDER};
    spacing: 6px;
    padding: 4px;
}}

QToolButton {{
    background-color: {COLOR_LIGHT_BG_ALT};
    border: 1px solid {COLOR_LIGHT_BORDER};
    border-radius: 5px;
    padding: 4px 10px;
    color: {COLOR_LIGHT_TEXT_MAIN};
}}

QToolButton:hover {{
    background-color: #e2e8f0;
    border-color: #94a3b8;
}}

QToolButton:pressed {{
    background-color: #cbd5e1;
}}

/* ========== نوار وضعیت (QStatusBar) ========== */
QStatusBar {{
    background-color: #f1f5f9;
    color: {COLOR_LIGHT_TEXT_MUTED};
    border-top: 1px solid {COLOR_LIGHT_BORDER};
}}

QStatusBar QLabel {{
    background: transparent;
    color: {COLOR_LIGHT_TEXT_MAIN};
}}

#lbl_stats, #lbl_date, #lbl_page {{
    color: #0369a1;
    font-weight: bold;
}}

/* ========== اسکرول‌بارهای باریک و مدرن ========== */
QScrollBar:vertical {{
    background-color: {COLOR_LIGHT_BG_MAIN};
    width: 8px;
    margin: 0;
    border-radius: 4px;
}}

QScrollBar::handle:vertical {{
    background-color: #cbd5e1;
    min-height: 24px;
    border-radius: 4px;
}}

QScrollBar::handle:vertical:hover {{
    background-color: #94a3b8;
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

QScrollBar:horizontal {{
    background-color: {COLOR_LIGHT_BG_MAIN};
    height: 8px;
    margin: 0;
    border-radius: 4px;
}}

QScrollBar::handle:horizontal {{
    background-color: #cbd5e1;
    min-width: 24px;
    border-radius: 4px;
}}

QScrollBar::handle:horizontal:hover {{
    background-color: #94a3b8;
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}

/* ========== تب‌ها (QTabWidget & QTabBar) ========== */
QTabWidget::pane {{
    border: 1px solid {COLOR_LIGHT_BORDER};
    background-color: {COLOR_LIGHT_BG_PANEL};
    border-radius: 6px;
}}

QTabBar::tab {{
    background-color: {COLOR_LIGHT_BG_ALT};
    color: {COLOR_LIGHT_TEXT_MUTED};
    padding: 8px 18px;
    border: 1px solid {COLOR_LIGHT_BORDER};
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    font-weight: bold;
}}

QTabBar::tab:selected {{
    background-color: {COLOR_LIGHT_BG_PANEL};
    color: {COLOR_SKY_DARKER};
    border-bottom: 2px solid {COLOR_SKY_BLUE};
}}

QTabBar::tab:hover:!selected {{
    background-color: #e2e8f0;
}}

/* ========== نوار پیشرفت (QProgressBar) ========== */
QProgressBar {{
    border: 1px solid {COLOR_LIGHT_BORDER};
    border-radius: 6px;
    text-align: center;
    background-color: {COLOR_LIGHT_BG_ALT};
    color: {COLOR_LIGHT_TEXT_MAIN};
    font-weight: bold;
    min-height: 14px;
}}

QProgressBar::chunk {{
    background-color: {COLOR_SKY_BLUE};
    border-radius: 5px;
}}

/* ========== تول‌تیپ (QToolTip) ========== */
QToolTip {{
    background-color: #0f172a;
    color: #ffffff;
    border: 1px solid #334155;
    border-radius: 5px;
    padding: 5px 8px;
    font-size: 11px;
}}

/* ========== جداکننده (QSplitter) ========== */
QSplitter::handle {{
    background-color: {COLOR_LIGHT_GRID};
}}

QSplitter::handle:hover {{
    background-color: {COLOR_SKY_BLUE};
}}
"""


# ─────────────────────────────────────────────
# ۲. استایل حالت تاریک (Dark Theme)
# ─────────────────────────────────────────────
DARK_STYLE = f"""
/* ========== تنظیمات پایه پنجره‌ها ========== */
QMainWindow, QDialog, QWidget {{
    background-color: {COLOR_DARK_BG_MAIN};
    color: {COLOR_DARK_TEXT_MAIN};
    font-family: {GLOBAL_FONT_FAMILY};
    font-size: 12.5px;
}}

/* ========== پنل‌ها و فریم‌ها ========== */
QFrame#content_frame, QFrame#card, QFrame#metric_card {{
    background-color: {COLOR_DARK_BG_PANEL};
    border: 1px solid {COLOR_DARK_BORDER};
    border-radius: 10px;
}}

QGroupBox {{
    background-color: {COLOR_DARK_BG_PANEL};
    border: 1px solid {COLOR_DARK_BORDER};
    border-radius: 8px;
    margin-top: 24px;
    padding-top: 14px;
    font-weight: bold;
    color: {COLOR_DARK_TEXT_MAIN};
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top right;
    right: 14px;
    padding: 0 6px;
    color: {COLOR_SKY_BLUE};
}}

/* ========== جدول‌ها (QTableView & QTableWidget) ========== */
QTableView, QTableWidget {{
    background-color: {COLOR_DARK_BG_PANEL};
    alternate-background-color: #243048;
    border: 1px solid {COLOR_DARK_BORDER};
    border-radius: 8px;
    gridline-color: {COLOR_DARK_GRID};
    color: {COLOR_DARK_TEXT_MAIN};
    selection-background-color: #006080;
    selection-color: #ffffff;
    outline: none;
    font-size: 12px;
}}

QTableView::item, QTableWidget::item {{
    padding: 6px 8px;
    border: none;
}}

QTableView::item:hover, QTableWidget::item:hover {{
    background-color: #2a3b5c;
}}

QTableView::item:selected, QTableWidget::item:selected {{
    background-color: #006080;
    color: #ffffff;
}}

/* سربرگ جدول‌ها */
QHeaderView::section {{
    background-color: #1e293b;
    color: {COLOR_DARK_TEXT_MAIN};
    padding: 6px 8px;
    border: none;
    border-right: 1px solid {COLOR_DARK_BORDER};
    border-bottom: 2px solid {COLOR_DARK_BORDER};
    font-weight: bold;
    font-size: 12px;
}}

QHeaderView::section:hover {{
    background-color: #2d3d5a;
}}

QTableCornerButton::section {{
    background-color: #1e293b;
    border: none;
    border-bottom: 2px solid {COLOR_DARK_BORDER};
}}

/* ========== لیست‌ها (QListWidget) ========== */
QListWidget, QListView {{
    background-color: {COLOR_DARK_BG_PANEL};
    border: 1px solid {COLOR_DARK_BORDER};
    border-radius: 8px;
    padding: 4px;
    color: {COLOR_DARK_TEXT_MAIN};
}}

QListWidget::item, QListView::item {{
    padding: 8px 10px;
    border-radius: 6px;
    margin-bottom: 2px;
}}

QListWidget::item:hover, QListView::item:hover {{
    background-color: #2a374d;
}}

QListWidget::item:selected, QListView::item:selected {{
    background-color: {COLOR_SKY_BLUE};
    color: #ffffff;
}}

/* ========== دکمه‌ها (Buttons) ========== */
QPushButton {{
    background-color: {COLOR_SKY_BLUE};
    color: #ffffff;
    border: none;
    border-radius: 6px;
    padding: 5px 16px;
    font-weight: bold;
    font-size: 12px;
    min-height: 22px;
}}

QPushButton:hover {{
    background-color: {COLOR_SKY_DARK};
}}

QPushButton:pressed {{
    background-color: {COLOR_SKY_DARKER};
}}

QPushButton:disabled {{
    background-color: #334155;
    color: #64748b;
}}

/* دکمه‌های ثانویه در دارک مود */
QPushButton#btn_secondary, QPushButton[secondary="true"] {{
    background-color: {COLOR_DARK_BG_PANEL};
    color: {COLOR_DARK_TEXT_MAIN};
    border: 1px solid {COLOR_DARK_BORDER};
}}

QPushButton#btn_secondary:hover, QPushButton[secondary="true"]:hover {{
    background-color: #2a374d;
    border-color: #475569;
}}

/* دکمه‌های خطر */
QPushButton#btn_danger, QPushButton[danger="true"] {{
    background-color: {COLOR_DANGER};
    color: #ffffff;
}}

QPushButton#btn_danger:hover, QPushButton[danger="true"]:hover {{
    background-color: {COLOR_DANGER_DARK};
}}

/* دکمه‌های لینک */
QPushButton#link_button {{
    background: transparent;
    border: none;
    color: {COLOR_SKY_BLUE};
    text-decoration: underline;
    font-weight: normal;
    min-width: 0;
    padding: 0;
}}

QPushButton#link_button:hover {{
    color: #7dd3fc;
}}

/* ========== فیلدهای ورودی ========== */
QLineEdit, QComboBox, QDateEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox {{
    border: 1px solid {COLOR_DARK_BORDER};
    border-radius: 6px;
    padding: 4px 10px;
    background-color: #162032;
    color: {COLOR_DARK_TEXT_MAIN};
    font-size: 12px;
    min-height: 22px;
    selection-background-color: {COLOR_SKY_BLUE};
    selection-color: #ffffff;
}}

QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QSpinBox:focus {{
    border: 1.5px solid {COLOR_SKY_BLUE};
    background-color: #1a263c;
}}

QLineEdit:read-only, QTextEdit:read-only {{
    background-color: #0f172a;
    color: {COLOR_DARK_TEXT_MUTED};
}}

QLineEdit:disabled, QComboBox:disabled, QDateEdit:disabled {{
    background-color: #0b1220;
    color: #475569;
}}

QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top left;
    width: 24px;
    border-left: 1px solid {COLOR_DARK_BORDER};
}}

/* ========== چک‌باکس و رادیوباتن ========== */
QCheckBox, QRadioButton {{
    color: {COLOR_DARK_TEXT_MAIN};
    spacing: 8px;
    font-size: 12px;
}}

QCheckBox::indicator, QRadioButton::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {COLOR_DARK_BORDER};
    border-radius: 4px;
    background-color: #162032;
}}

QRadioButton::indicator {{
    border-radius: 9px;
}}

QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
    border-color: {COLOR_SKY_BLUE};
}}

QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background-color: {COLOR_SKY_BLUE};
    border-color: {COLOR_SKY_DARK};
}}

/* ========== منوها و منوبار ========== */
QMenuBar {{
    background-color: #0b1220;
    color: {COLOR_DARK_TEXT_MAIN};
    border-bottom: 1px solid {COLOR_DARK_BORDER};
    padding: 2px 4px;
    font-weight: bold;
}}

QMenuBar::item {{
    background: transparent;
    padding: 6px 12px;
    border-radius: 4px;
}}

QMenuBar::item:selected {{
    background-color: #1e293b;
    color: {COLOR_SKY_BLUE};
}}

QMenu {{
    background-color: {COLOR_DARK_BG_PANEL};
    border: 1px solid {COLOR_DARK_BORDER};
    border-radius: 6px;
    padding: 4px;
}}

QMenu::item {{
    padding: 6px 28px 6px 20px;
    border-radius: 4px;
    color: {COLOR_DARK_TEXT_MAIN};
}}

QMenu::item:selected {{
    background-color: {COLOR_SKY_BLUE};
    color: #ffffff;
}}

QMenu::separator {{
    height: 1px;
    background-color: {COLOR_DARK_BORDER};
    margin: 4px 8px;
}}

/* ========== نوار ابزار (QToolBar) ========== */
QToolBar {{
    background-color: #0b1220;
    border-bottom: 1px solid {COLOR_DARK_BORDER};
    spacing: 6px;
    padding: 4px;
}}

QToolButton {{
    background-color: #1e293b;
    border: 1px solid {COLOR_DARK_BORDER};
    border-radius: 5px;
    padding: 4px 10px;
    color: {COLOR_DARK_TEXT_MAIN};
}}

QToolButton:hover {{
    background-color: #2d3d5a;
    border-color: #475569;
}}

QToolButton:pressed {{
    background-color: #0f172a;
}}

/* ========== نوار وضعیت (QStatusBar) ========== */
QStatusBar {{
    background-color: #080d18;
    color: {COLOR_DARK_TEXT_MUTED};
    border-top: 1px solid {COLOR_DARK_BORDER};
}}

QStatusBar QLabel {{
    background: transparent;
    color: {COLOR_DARK_TEXT_MAIN};
}}

#lbl_stats, #lbl_date, #lbl_page {{
    color: {COLOR_SKY_BLUE};
    font-weight: bold;
}}

/* ========== اسکرول‌بارهای باریک ========== */
QScrollBar:vertical {{
    background-color: {COLOR_DARK_BG_MAIN};
    width: 8px;
    margin: 0;
    border-radius: 4px;
}}

QScrollBar::handle:vertical {{
    background-color: #334155;
    min-height: 24px;
    border-radius: 4px;
}}

QScrollBar::handle:vertical:hover {{
    background-color: #475569;
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

QScrollBar:horizontal {{
    background-color: {COLOR_DARK_BG_MAIN};
    height: 8px;
    margin: 0;
    border-radius: 4px;
}}

QScrollBar::handle:horizontal {{
    background-color: #334155;
    min-width: 24px;
    border-radius: 4px;
}}

QScrollBar::handle:horizontal:hover {{
    background-color: #475569;
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}

/* ========== تب‌ها (QTabWidget & QTabBar) ========== */
QTabWidget::pane {{
    border: 1px solid {COLOR_DARK_BORDER};
    background-color: {COLOR_DARK_BG_PANEL};
    border-radius: 6px;
}}

QTabBar::tab {{
    background-color: #121b2b;
    color: {COLOR_DARK_TEXT_MUTED};
    padding: 8px 18px;
    border: 1px solid {COLOR_DARK_BORDER};
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    font-weight: bold;
}}

QTabBar::tab:selected {{
    background-color: {COLOR_DARK_BG_PANEL};
    color: {COLOR_SKY_BLUE};
    border-bottom: 2px solid {COLOR_SKY_BLUE};
}}

QTabBar::tab:hover:!selected {{
    background-color: #1a263c;
}}

/* ========== نوار پیشرفت (QProgressBar) ========== */
QProgressBar {{
    border: 1px solid {COLOR_DARK_BORDER};
    border-radius: 6px;
    text-align: center;
    background-color: #121b2b;
    color: {COLOR_DARK_TEXT_MAIN};
    font-weight: bold;
    min-height: 14px;
}}

QProgressBar::chunk {{
    background-color: {COLOR_SKY_BLUE};
    border-radius: 5px;
}}

/* ========== تول‌تیپ (QToolTip) ========== */
QToolTip {{
    background-color: #020617;
    color: #ffffff;
    border: 1px solid #1e293b;
    border-radius: 5px;
    padding: 5px 8px;
    font-size: 11px;
}}

/* ========== جداکننده (QSplitter) ========== */
QSplitter::handle {{
    background-color: {COLOR_DARK_BORDER};
}}

QSplitter::handle:hover {{
    background-color: {COLOR_SKY_BLUE};
}}
"""


# ─────────────────────────────────────────────
# توابع کمکی دسترسی و اعمال تم
# ─────────────────────────────────────────────

def get_stylesheet(dark_mode: bool = False) -> str:
    """
    برگرداندن رشته استایل کامل بر اساس وضعیت تم روشن یا تاریک.

    Args:
        dark_mode: در صورت True استایل تاریک، در غیر این صورت روشن بازگردانده می‌شود.
    """
    return DARK_STYLE if dark_mode else LIGHT_STYLE


def apply_theme(target: Union[QApplication, QWidget], dark_mode: bool = False) -> None:
    """
    اعمال مستقیم و آنی تم به نمونه برنامه (QApplication) یا یک ویجت خاص.

    Args:
        target: نمونه QApplication یا شیء QWidget/QMainWindow
        dark_mode: وضعیت حالت شب/روز
    """
    if target is not None:
        target.setStyleSheet(get_stylesheet(dark_mode=dark_mode))


# ثابت جهت حفظ سازگاری کامل با کدهای پیشین
STYLE_SHEET = LIGHT_STYLE