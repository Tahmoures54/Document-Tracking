# -*- coding: utf-8 -*-
"""
ماژول تولید گزارش HTML گردش کار
مسیر: services/workflow_report.py
"""
import os
from html import escape as esc
from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QMessageBox, QFileDialog

from utils.date_utils import to_shamsi, today_shamsi


class WorkflowReportGenerator:
    """کلاس سازنده خروجی چاپی و رسمی برای گردش کار صورتجلسه"""

    def __init__(self, meeting, steps, parent_widget=None):
        self.meeting = meeting
        self.steps = steps
        self.parent_widget = parent_widget

    def _generate_html(self) -> str:
        now_str = today_shamsi()
        m = self.meeting
        meeting_date_str = to_shamsi(m.meeting_date.isoformat()) if m.meeting_date else "—"

        # تولید ردیف‌های جدول
        steps_rows = ""
        for idx, step in enumerate(self.steps, start=1):
            entry = to_shamsi(step.entry_date.isoformat()) if step.entry_date else ""
            exit_ = to_shamsi(step.exit_date.isoformat()) if step.exit_date else ""

            status_map = {
                "pending": "در انتظار",
                "in_progress": "در حال انجام",
                "completed": "تکمیل شده",
                "rejected": "رد شده"
            }
            status_text = status_map.get(step.status, step.status)

            row_class = "row-even" if idx % 2 == 0 else "row-odd"

            steps_rows += f"""
            <tr class="{row_class}">
                <td class="center bold-num">{idx}</td>
                <td class="step-title">
                    {esc(step.step_name)}
                    <span class="status-badge status-{step.status}">{status_text}</span>
                </td>
                <td class="center">{esc(entry)}</td>
                <td class="center">{esc(exit_)}</td>
                <td class="center resp-name">{esc(step.responsible_person or '—')}</td>
                <td class="center signature-box">{esc(step.signature or '')}</td>
                <td class="notes">{esc(step.notes or '')}</td>
            </tr>
            """

        return f"""<!doctype html>
<html dir="rtl" lang="fa">
<head>
<meta charset="utf-8">
<title>فرم گردش کار - {esc(m.meeting_number)}</title>
<style>
    @import url('https://fonts.googleapis.com/css2?family=Vazirmatn:wght@400;500;700&display=swap');

    @page {{ size: A5 landscape; margin: 10mm; }}

    * {{ box-sizing: border-box; }}

    body {{
        font-family: 'Vazirmatn', Tahoma, Arial, sans-serif;
        font-size: 8.5pt;
        color: #1e293b;
        background: #fff;
        direction: rtl;
        margin: 0;
        padding: 0;
        line-height: 1.5;
        -webkit-print-color-adjust: exact;
        print-color-adjust: exact;
    }}

    .document-container {{
        width: 100%;
        max-width: 190mm;
        margin: 0 auto;
        border-top: 6px solid #0f172a;
        padding-top: 10px;
    }}

    /* سربرگ اصلی */
    .main-header {{
        text-align: center;
        margin-bottom: 10px;
    }}
    .main-header h1 {{
        font-size: 14pt;
        font-weight: 700;
        color: #0f172a;
        margin: 0 0 3px 0;
    }}
    .main-header .en-title {{
        font-family: 'Arial', sans-serif;
        direction: ltr;
        display: block;
        color: #64748b;
        font-size: 8.5pt;
        letter-spacing: 0.8px;
    }}

    /* نوار اطلاعات ادغام‌شده (فشرده) */
    .info-grid {{
        display: grid;
        grid-template-columns: repeat(6, 1fr);
        gap: 5px;
        margin-bottom: 10px;
        padding: 6px;
        background: #f8fafc;
        border: 1.5px solid #94a3b8;
        border-radius: 8px;
    }}
    .info-item {{
        display: flex;
        align-items: center;
        gap: 4px;
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 4px;
        padding: 2px 6px;
        font-size: 7.5pt;
        min-height: 20px;
    }}
    .info-item .lbl {{
        font-weight: 700;
        color: #334155;
        white-space: nowrap;
        flex-shrink: 0;
    }}
    .info-item .en-inline {{
        font-family: 'Arial', sans-serif;
        font-size: 6pt;
        color: #94a3b8;
        margin-right: 2px;
    }}
    .info-item .val {{
        font-family: 'Courier New', monospace;
        font-weight: bold;
        color: #0f172a;
        flex: 1;
        min-width: 0;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        direction: ltr;
        text-align: center;
    }}
    .info-item .val.subject {{
        direction: rtl;
        font-family: inherit;
        font-weight: 700;
        font-size: 8pt;
        white-space: normal;
        text-align: right;
    }}
    .info-item .val.employer {{
        direction: rtl;
        font-family: inherit;
        font-weight: normal;
        white-space: normal;
        text-align: right;
    }}
    .span-1 {{ grid-column: span 1; }}
    .span-2 {{ grid-column: span 2; }}
    .span-3 {{ grid-column: span 3; }}
    .span-4 {{ grid-column: span 4; }}

    /* جدول مراحل */
    .data-table {{
        width: 100%;
        border-collapse: collapse;
        table-layout: fixed;
        border: 1.5px solid #0f172a;
    }}
    .data-table th,
    .data-table td {{
        border: 1px solid #94a3b8;
        padding: 5px 4px;
        vertical-align: middle;
        word-wrap: break-word;
        font-size: 8pt;
    }}
    .data-table th {{
        background-color: #1e293b;
        color: #ffffff;
        text-align: center;
        padding: 7px 4px;
        font-size: 8pt;
    }}
    .data-table tr {{
        page-break-inside: avoid;
    }}
    .row-even {{ background-color: #f8fafc; }}
    .row-odd {{ background-color: #ffffff; }}

    .col-id {{ width: 4%; }}
    .col-title {{ width: 25%; }}
    .col-date {{ width: 11%; }}
    .col-resp {{ width: 14%; }}
    .col-sign {{ width: 12%; }}
    .col-notes {{ width: 23%; }}

    .center {{ text-align: center; }}
    .bold-num {{ font-weight: bold; font-size: 9pt; color: #0f172a; }}
    .step-title {{
        font-weight: 700;
        color: #1e293b;
        font-size: 8.5pt;
        line-height: 1.6;
    }}
    .resp-name {{ font-weight: bold; color: #0369a1; }}
    .signature-box {{ height: 30px; }}
    .notes {{
        font-size: 7.5pt;
        text-align: justify;
        color: #475569;
    }}

    /* نشان‌های وضعیت */
    .status-badge {{
        font-size: 6.5pt;
        padding: 2px 6px;
        border-radius: 10px;
        font-weight: 500;
        margin-right: 6px;
        display: inline-block;
    }}
    .status-pending {{ background: #fef3c7; color: #92400e; border: 1px solid #fcd34d; }}
    .status-in_progress {{ background: #e0f2fe; color: #1e40af; border: 1px solid #bae6fd; }}
    .status-completed {{ background: #dcfce7; color: #166534; border: 1px solid #86efac; }}
    .status-rejected {{ background: #fee2e2; color: #991b1b; border: 1px solid #fca5a5; }}

    /* فوتر */
    .footer {{
        margin-top: 12px;
        font-size: 7pt;
        color: #64748b;
        border-top: 1.5px solid #cbd5e1;
        padding-top: 6px;
        display: flex;
        justify-content: space-between;
        direction: rtl;
    }}
    .footer-right {{ text-align: right; }}
    .footer-left {{ text-align: left; direction: rtl; }}
</style>
</head>
<body>
<div class="document-container">

    <!-- سربرگ اصلی -->
    <div class="main-header">
        <h1>فرم پیگیری و گردش کار صورتجلسات</h1>
        <span class="en-title">Meeting Workflow &amp; Follow-up Form</span>
    </div>

    <!-- اطلاعات ادغام‌شده (شماره، تاریخ، پیوست، موضوع، تاریخ جلسه، کارفرما/پیمانکار) -->
    <div class="info-grid">
        <div class="info-item span-1">
            <span class="lbl">شماره <span class="en-inline">No.</span>:</span>
            <span class="val">{esc(m.meeting_number)}</span>
        </div>
        <div class="info-item span-1">
            <span class="lbl">تاریخ <span class="en-inline">Date</span>:</span>
            <span class="val">{now_str}</span>
        </div>
        <div class="info-item span-1">
            <span class="lbl">پیوست <span class="en-inline">Att.</span>:</span>
            <span class="val">ندارد</span>
        </div>
        <div class="info-item span-3">
            <span class="lbl">موضوع جلسه:</span>
            <span class="val subject">{esc(m.subject)}</span>
        </div>
        <div class="info-item span-2">
            <span class="lbl">تاریخ جلسه:</span>
            <span class="val">{esc(meeting_date_str)}</span>
        </div>
        <div class="info-item span-4">
            <span class="lbl">کارفرما / پیمانکار:</span>
            <span class="val employer">{esc(m.employer or '—')} <span style="color:#cbd5e1; margin:0 4px;">|</span> {esc(m.contractor or '—')}</span>
        </div>
    </div>

    <!-- جدول اصلی -->
    <table class="data-table">
        <thead>
            <tr>
                <th class="col-id">ردیف</th>
                <th class="col-title">عنوان مرحله</th>
                <th class="col-date">تاریخ ورود</th>
                <th class="col-date">تاریخ خروج</th>
                <th class="col-resp">مسئول پیگیری</th>
                <th class="col-sign">امضاء</th>
                <th class="col-notes">توضیحات و یادداشت‌ها</th>
            </tr>
        </thead>
        <tbody>
            {steps_rows}
        </tbody>
    </table>

    <!-- فوتر -->
    <div class="footer">
        <div class="footer-right">سیستم یکپارچه Document & MOM Tracking System</div>
        <div class="footer-left">تاریخ چاپ: {now_str}</div>
    </div>

</div>
</body>
</html>"""

    def generate_and_open(self):
        """تولید پوشه، ذخیره فایل HTML و باز کردن آن در مرورگر"""
        report_dir = os.path.join(os.getcwd(), "reports")
        try:
            os.makedirs(report_dir, exist_ok=True)
        except OSError as exc:
            if self.parent_widget:
                QMessageBox.critical(self.parent_widget, "خطا", f"امکان ساخت پوشه reports وجود ندارد:\n{exc}")
            return

        safe_num = "".join(c for c in self.meeting.meeting_number if c.isalnum() or c in "-_.")
        default_path = os.path.abspath(os.path.join(report_dir, f"Workflow_{safe_num or 'report'}.html"))
        html_content = self._generate_html()

        try:
            with open(default_path, "w", encoding="utf-8") as fh:
                fh.write(html_content)
            QDesktopServices.openUrl(QUrl.fromLocalFile(default_path))
        except Exception:
            if self.parent_widget:
                path, _ = QFileDialog.getSaveFileName(
                    self.parent_widget, "ذخیره گزارش", default_path, "HTML Files (*.html)"
                )
                if path:
                    try:
                        with open(path, "w", encoding="utf-8") as fh:
                            fh.write(html_content)
                        QDesktopServices.openUrl(QUrl.fromLocalFile(path))
                    except Exception as e:
                        QMessageBox.critical(self.parent_widget, "خطا", f"امکان ذخیره فایل نیست:\n{e}")