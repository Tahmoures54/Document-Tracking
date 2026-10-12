# -*- coding: utf-8 -*-
"""
services.meeting_number_report
گزارش HTML بر اساس فیلتر شماره صورتجلسه (جستجوی حاوی رشته)
"""
from __future__ import annotations

import os
from datetime import date
from html import escape as esc
from typing import List, Optional

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QFileDialog, QMessageBox, QWidget

from db.models import Meeting
from utils.date_utils import to_shamsi, today_shamsi


def _days_until(due: Optional[date]) -> Optional[int]:
    if not due:
        return None
    return (due - date.today()).days


def _days_label(days: Optional[int]) -> str:
    if days is None:
        return "—"
    if days < 0:
        return f"{abs(days)} روز گذشته (تأخیر)"
    if days == 0:
        return "امروز سررسید"
    return f"{days} روز مانده"


def _days_class(days: Optional[int]) -> str:
    if days is None:
        return "neutral"
    if days < 0:
        return "overdue"
    if days <= 3:
        return "warn"
    return "ok"


class MeetingNumberReportGenerator:
    """گزارش HTML برای نتیجه فیلتر شماره صورتجلسه."""

    def __init__(self, meetings: List[Meeting], query: str, parent: Optional[QWidget] = None):
        self.meetings = meetings
        self.query = (query or "").strip()
        self.parent = parent

    def _generate_html(self) -> str:
        now = today_shamsi()
        rows_html = []
        for i, m in enumerate(self.meetings, start=1):
            days = _days_until(m.due_date)
            due_s = to_shamsi(m.due_date.isoformat()) if m.due_date else "—"
            meet_s = to_shamsi(m.meeting_date.isoformat()) if m.meeting_date else "—"
            loc = (m.location or "—").strip() or "—"
            rows_html.append(f"""
            <tr class="{'even' if i % 2 == 0 else 'odd'}">
                <td class="c">{i}</td>
                <td class="mono c">{esc(m.meeting_number or '')}</td>
                <td>{esc(loc)}</td>
                <td>{esc(m.subject or '—')}</td>
                <td>{esc(m.contractor or '—')}</td>
                <td class="c">{esc(meet_s)}</td>
                <td class="c">{esc(due_s)}</td>
                <td class="c days {_days_class(days)}">{esc(_days_label(days))}</td>
                <td class="c">{esc(m.status or '—')}</td>
                <td class="c">{esc(m.priority or '—')}</td>
            </tr>""")

        body_rows = "\n".join(rows_html) if rows_html else """
            <tr><td colspan="10" class="c empty">موردی یافت نشد.</td></tr>"""

        # خلاصه بر اساس محل کار
        by_loc: dict = {}
        for m in self.meetings:
            key = (m.location or "نامشخص").strip() or "نامشخص"
            by_loc.setdefault(key, []).append(m)

        summary_rows = []
        for j, (loc, items) in enumerate(sorted(by_loc.items(), key=lambda x: -len(x[1])), start=1):
            overdue = sum(1 for m in items if m.due_date and m.due_date < date.today() and m.status not in ("تکمیل شده", "لغو شده"))
            summary_rows.append(f"""
            <tr class="{'even' if j % 2 == 0 else 'odd'}">
                <td class="c">{j}</td>
                <td>{esc(loc)}</td>
                <td class="c bold">{len(items)}</td>
                <td class="c {'overdue' if overdue else 'ok'}">{overdue}</td>
            </tr>""")
        summary_html = "\n".join(summary_rows) if summary_rows else ""

        return f"""<!doctype html>
<html dir="rtl" lang="fa">
<head>
<meta charset="utf-8">
<title>گزارش فیلتر شماره صورتجلسه — {esc(self.query)}</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Vazirmatn:wght@400;600;700&display=swap');
  * {{ box-sizing: border-box; }}
  body {{
    font-family: Vazirmatn, Tahoma, sans-serif;
    background: #f1f5f9;
    color: #0f172a;
    margin: 0;
    padding: 24px;
    font-size: 13px;
  }}
  .wrap {{
    max-width: 1100px;
    margin: 0 auto;
    background: #fff;
    border-radius: 12px;
    box-shadow: 0 4px 24px rgba(15,23,42,.08);
    overflow: hidden;
  }}
  .head {{
    background: linear-gradient(90deg, #0f172a, #0369a1);
    color: #fff;
    padding: 20px 24px;
  }}
  .head h1 {{ margin: 0 0 6px; font-size: 18px; }}
  .head .meta {{ opacity: .9; font-size: 12px; }}
  .section {{ padding: 18px 24px; }}
  .section h2 {{
    margin: 0 0 12px;
    font-size: 14px;
    color: #0369a1;
    border-bottom: 2px solid #e2e8f0;
    padding-bottom: 6px;
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 12px;
  }}
  th {{
    background: #1e293b;
    color: #fff;
    padding: 8px 6px;
    text-align: center;
  }}
  td {{
    border: 1px solid #e2e8f0;
    padding: 7px 6px;
    vertical-align: top;
  }}
  tr.even {{ background: #f8fafc; }}
  .c {{ text-align: center; }}
  .mono {{ font-family: Consolas, monospace; direction: ltr; }}
  .bold {{ font-weight: 700; }}
  .days.ok {{ background: #dcfce7; color: #166534; font-weight: 600; }}
  .days.warn {{ background: #fef3c7; color: #92400e; font-weight: 600; }}
  .days.overdue {{ background: #fee2e2; color: #991b1b; font-weight: 700; }}
  td.overdue {{ color: #991b1b; font-weight: 700; }}
  td.ok {{ color: #166534; }}
  .empty {{ color: #64748b; padding: 24px; }}
  .foot {{
    padding: 12px 24px 20px;
    font-size: 11px;
    color: #64748b;
    display: flex;
    justify-content: space-between;
  }}
  .badge {{
    display: inline-block;
    background: #e0f2fe;
    color: #0369a1;
    padding: 2px 10px;
    border-radius: 20px;
    font-weight: 600;
    font-size: 12px;
  }}
</style>
</head>
<body>
<div class="wrap">
  <div class="head">
    <h1>گزارش فیلتر شماره صورتجلسه</h1>
    <div class="meta">
      عبارت جستجو: <span class="badge">{esc(self.query) or '—'}</span>
      &nbsp;|&nbsp; تعداد نتیجه: <strong>{len(self.meetings)}</strong>
      &nbsp;|&nbsp; تاریخ گزارش: {now}
    </div>
  </div>

  <div class="section">
    <h2>خلاصه بر اساس محل کار</h2>
    <table>
      <thead>
        <tr>
          <th style="width:50px">ردیف</th>
          <th>محل کار</th>
          <th style="width:100px">تعداد صورتجلسه</th>
          <th style="width:100px">تعداد تأخیری</th>
        </tr>
      </thead>
      <tbody>
        {summary_html or '<tr><td colspan="4" class="c empty">—</td></tr>'}
      </tbody>
    </table>
  </div>

  <div class="section">
    <h2>جزئیات صورتجلسات</h2>
    <table>
      <thead>
        <tr>
          <th style="width:40px">#</th>
          <th style="width:120px">شماره صورتجلسه</th>
          <th style="width:110px">محل کار</th>
          <th>موضوع</th>
          <th style="width:120px">پیمانکار</th>
          <th style="width:90px">تاریخ جلسه</th>
          <th style="width:90px">مهلت انجام</th>
          <th style="width:120px">روز مانده</th>
          <th style="width:90px">وضعیت</th>
          <th style="width:70px">اولویت</th>
        </tr>
      </thead>
      <tbody>
        {body_rows}
      </tbody>
    </table>
  </div>

  <div class="foot">
    <span>Document &amp; MOM Tracking System</span>
    <span>جستجو در شماره: حاوی «{esc(self.query)}»</span>
  </div>
</div>
</body>
</html>"""

    def generate_and_open(self) -> None:
        report_dir = os.path.join(os.getcwd(), "reports")
        try:
            os.makedirs(report_dir, exist_ok=True)
        except OSError as exc:
            if self.parent:
                QMessageBox.critical(self.parent, "خطا", f"ساخت پوشه reports ممکن نیست:\n{exc}")
            return

        safe_q = "".join(c for c in self.query if c.isalnum() or c in "-_")[:40] or "all"
        default_path = os.path.abspath(
            os.path.join(report_dir, f"MeetingNo_{safe_q}_{today_shamsi().replace('-', '')}.html")
        )
        html = self._generate_html()

        try:
            with open(default_path, "w", encoding="utf-8") as fh:
                fh.write(html)
            QDesktopServices.openUrl(QUrl.fromLocalFile(default_path))
        except Exception:
            if not self.parent:
                return
            path, _ = QFileDialog.getSaveFileName(
                self.parent, "ذخیره گزارش", default_path, "HTML (*.html)"
            )
            if path:
                try:
                    with open(path, "w", encoding="utf-8") as fh:
                        fh.write(html)
                    QDesktopServices.openUrl(QUrl.fromLocalFile(path))
                except Exception as e:
                    QMessageBox.critical(self.parent, "خطا", str(e))
