# -*- coding: utf-8 -*-
"""گزارش‌های HTML زمان رسیدگی و گردش کار صورتجلسات؛ بدون وابستگی به اینترنت."""
from __future__ import annotations

import os
from datetime import date, datetime
from html import escape
from typing import Iterable, Mapping, Sequence

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QFileDialog, QMessageBox

from utils.date_utils import to_shamsi, today_shamsi


STATUS_LABELS = {
    "pending": "در انتظار",
    "in_progress": "در حال انجام",
    "completed": "تکمیل شده",
    "rejected": "عودت برای اصلاح",
    "skipped": "رد شده",
}


def _as_date(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _date_text(value):
    parsed = _as_date(value)
    if not parsed:
        return "—"
    try:
        return to_shamsi(parsed.isoformat()) or parsed.isoformat()
    except Exception:
        return parsed.isoformat()


def _duration(start, end=None):
    """مدت سپری‌شده به روز؛ تاریخ‌های ناقص هرگز به‌عنوان صفر روز گزارش نمی‌شوند."""
    start_date = _as_date(start)
    end_date = _as_date(end) if end is not None else date.today()
    if not start_date or not end_date:
        return None
    return max(0, (end_date - start_date).days)


def _duration_text(days, ongoing=False):
    if days is None:
        return "ثبت نشده"
    if days == 0:
        label = "کمتر از یک روز"
    elif days == 1:
        label = "۱ روز"
    else:
        label = f"{days:,} روز"
    return f"{label} · در جریان" if ongoing else label


def _meeting_start(meeting, steps):
    started = [s.entry_date for s in steps if s.entry_date]
    if started:
        return min(started)
    return getattr(meeting, "entry_date", None) or getattr(meeting, "created_at", None)


def _meeting_end(meeting, steps):
    dispatched = getattr(meeting, "sent_to_contractor_date", None)
    if dispatched:
        return dispatched
    closing = getattr(meeting, "closing_date", None)
    if closing:
        return closing
    if steps and all(s.status in ("completed", "skipped") for s in steps):
        return next((s.exit_date for s in reversed(steps) if s.exit_date), None)
    return None


def _duration_cell(step):
    start = getattr(step, "entry_date", None)
    end = getattr(step, "exit_date", None)
    if not start:
        return "شروع ثبت نشده"
    days = _duration(start, end)
    return _duration_text(days, ongoing=not bool(end))


class WorkflowReportGenerator:
    """تولید گزارش رسمی یک صورتجلسه با مدت کل و زمان هر مرحله."""

    def __init__(self, meeting, steps, parent_widget=None):
        self.meeting = meeting
        self.steps = sorted(list(steps or []), key=lambda s: getattr(s, "step_order", 0))
        self.parent_widget = parent_widget

    def _generate_html(self) -> str:
        m = self.meeting
        steps = self.steps
        start = _meeting_start(m, steps)
        end = _meeting_end(m, steps)
        ongoing = not bool(end) and bool(start)
        total_days = _duration(start, end)
        status = getattr(m, "status", "نامشخص") or "نامشخص"
        stage_rows = []
        for idx, step in enumerate(steps, 1):
            entry = _date_text(step.entry_date)
            exit_date = _date_text(step.exit_date)
            duration = _duration(step.entry_date, step.exit_date)
            stage_ongoing = bool(step.entry_date and not step.exit_date)
            state = STATUS_LABELS.get(step.status, step.status or "نامشخص")
            row_class = "even" if idx % 2 == 0 else "odd"
            stage_rows.append(
                f'<tr class="{row_class}"><td>{idx}</td>'
                f'<td class="stage">{escape(step.step_name or "—")}</td>'
                f'<td><span class="badge {escape(step.status or "")}">{escape(state)}</span></td>'
                f'<td>{escape(entry)}</td><td>{escape(exit_date)}</td>'
                f'<td class="duration">{escape(_duration_text(duration, stage_ongoing))}</td>'
                f'<td>{escape(step.responsible_person or "—")}</td>'
                f'<td class="notes">{escape(step.notes or "—")}</td></tr>'
            )
        if not stage_rows:
            stage_rows.append('<tr><td colspan="8">برای این صورتجلسه مرحله‌ای ثبت نشده است.</td></tr>')

        return f"""<!doctype html>
<html lang="fa" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>گزارش زمان رسیدگی - {escape(str(m.meeting_number or ""))}</title>
<style>
@page{{size:A4 landscape;margin:12mm}}*{{box-sizing:border-box}}
body{{font-family:Tahoma,Arial,sans-serif;color:#172033;margin:0;background:#f3f6fb;font-size:13px;line-height:1.8}}
main{{max-width:1400px;margin:24px auto;background:white;padding:26px;border-radius:16px;box-shadow:0 8px 28px #1e293b12;border-top:6px solid #0f9ca8}}
header{{display:flex;justify-content:space-between;align-items:center;gap:20px;border-bottom:1px solid #e2e8f0;padding-bottom:16px}}
h1{{font-size:23px;margin:0;color:#12354a}}.sub{{color:#64748b;font-size:12px}}
.cards{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:18px 0}}
.card{{background:#f8fafc;border:1px solid #e2e8f0;border-radius:12px;padding:12px 15px;min-width:0}}
.card .label{{display:block;color:#64748b;font-size:11px}}.card strong{{display:block;color:#12354a;font-size:17px;overflow-wrap:anywhere}}
.card.accent{{background:#ecfeff;border-color:#a5f3fc}}.card.warn{{background:#fff7ed;border-color:#fed7aa}}
table{{width:100%;border-collapse:collapse;margin-top:14px}}th{{background:#17384d;color:white;font-weight:700}}
th,td{{border:1px solid #dce5ee;padding:9px 8px;text-align:center;vertical-align:middle}}
tr.even{{background:#f8fafc}}td.stage,td.notes{{text-align:right}}td.stage{{font-weight:bold;min-width:190px}}
td.duration{{font-weight:bold;white-space:nowrap;color:#075985}}
.badge{{display:inline-block;padding:2px 9px;border-radius:99px;font-size:11px;white-space:nowrap}}
.badge.completed{{background:#dcfce7;color:#166534}}.badge.in_progress{{background:#dbeafe;color:#1d4ed8}}
.badge.pending{{background:#fef3c7;color:#92400e}}.badge.rejected{{background:#fee2e2;color:#991b1b}}
.footer{{display:flex;justify-content:space-between;border-top:1px solid #e2e8f0;margin-top:18px;padding-top:10px;color:#64748b;font-size:11px}}
.actions{{text-align:left}}button{{border:0;border-radius:8px;background:#0f766e;color:white;padding:9px 14px;cursor:pointer;font:inherit}}
@media print{{body{{background:white}}main{{margin:0;max-width:none;padding:0;border:0;box-shadow:none}}.actions{{display:none}}.cards{{break-inside:avoid}}tr{{break-inside:avoid}}}}
@media(max-width:800px){{main{{margin:8px;padding:12px}}.cards{{grid-template-columns:repeat(2,minmax(0,1fr))}}header{{align-items:flex-start;flex-direction:column}}table{{font-size:11px}}th,td{{padding:5px}}}}
</style></head><body><main>
<header><div><h1>گزارش زمان رسیدگی صورتجلسه</h1>
<div class="sub">گزارش مسیر رسیدگی از آغاز تا پایان هر مرحله</div></div>
<div class="actions"><button onclick="window.print()">چاپ / ذخیره PDF</button></div></header>
<section class="cards">
<div class="card accent"><span class="label">شماره صورتجلسه</span><strong>{escape(str(m.meeting_number or "—"))}</strong></div>
<div class="card"><span class="label">موضوع</span><strong>{escape(str(m.subject or "—"))}</strong></div>
<div class="card"><span class="label">شروع رسیدگی</span><strong>{escape(_date_text(start))}</strong></div>
<div class="card {'warn' if ongoing else 'accent'}"><span class="label">پایان رسیدگی / وضعیت زمان</span><strong>{escape(_date_text(end) if end else ("در جریان" if ongoing else "ثبت نشده"))}</strong></div>
<div class="card accent"><span class="label">مدت کل سپری‌شده</span><strong>{escape(_duration_text(total_days, ongoing))}</strong></div>
<div class="card"><span class="label">وضعیت پرونده</span><strong>{escape(str(status))}</strong></div>
<div class="card"><span class="label">کارفرما</span><strong>{escape(str(m.employer or "—"))}</strong></div>
<div class="card"><span class="label">پیمانکار</span><strong>{escape(str(m.contractor or "—"))}</strong></div>
</section>
<p>مدت هر مرحله از اختلاف تاریخ شروع و پایان محاسبه شده است. برای مرحله باز، زمان تا امروز محاسبه و با عبارت «در جریان» مشخص می‌شود. اطلاعات تاریخِ ثبت‌نشده به‌عنوان صفر روز فرض نشده است.</p>
<table><thead><tr><th>ردیف</th><th>مرحله رسیدگی</th><th>وضعیت</th><th>تاریخ شروع</th><th>تاریخ پایان</th><th>مدت مرحله</th><th>مسئول</th><th>یادداشت / علت عودت</th></tr></thead>
<tbody>{''.join(stage_rows)}</tbody></table>
<div class="footer"><span>سامانه مدیریت و پیگیری صورتجلسات</span><span>تاریخ تهیه گزارش: {escape(today_shamsi())}</span></div>
</main></body></html>"""

    def generate_and_open(self):
        """ذخیره و بازکردن گزارش؛ در صورت خطا مسیر جایگزین پیشنهاد می‌شود."""
        report_dir = os.path.join(os.getcwd(), "reports")
        try:
            os.makedirs(report_dir, exist_ok=True)
            safe_num = "".join(c for c in str(self.meeting.meeting_number or "") if c.isalnum() or c in "-_.")
            path = os.path.abspath(os.path.join(report_dir, f"Workflow_{safe_num or 'report'}.html"))
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(self._generate_html())
        except OSError as exc:
            if not self.parent_widget:
                raise
            path, _ = QFileDialog.getSaveFileName(
                self.parent_widget, "ذخیره گزارش HTML", "Workflow_Report.html", "HTML (*.html)"
            )
            if not path:
                return None
            try:
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write(self._generate_html())
            except OSError as save_exc:
                QMessageBox.critical(self.parent_widget, "خطای ذخیره گزارش", str(save_exc))
                return None
        opened = QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        if not opened and self.parent_widget:
            QMessageBox.information(self.parent_widget, "گزارش ذخیره شد", f"فایل ذخیره شد اما مرورگر باز نشد:\n{path}")
        return path


class WorkflowOverviewReportGenerator:
    """گزارش تجمیعی HTML برای مقایسه مدت رسیدگی صورتجلسات."""

    def __init__(self, meetings: Sequence, steps_by_meeting: Mapping[int, Sequence], parent_widget=None):
        self.meetings = list(meetings)
        self.steps_by_meeting = steps_by_meeting
        self.parent_widget = parent_widget

    def _generate_html(self) -> str:
        stage_names = []
        for meeting in self.meetings:
            for step in self.steps_by_meeting.get(meeting.id, []):
                if step.step_name not in stage_names:
                    stage_names.append(step.step_name)
        stage_names.sort(key=lambda name: next(
            (getattr(s, "step_order", 999) for mid in self.steps_by_meeting
             for s in self.steps_by_meeting[mid] if s.step_name == name), 999
        ))
        rows = []
        complete_count = 0
        active_durations = []
        for idx, meeting in enumerate(self.meetings, 1):
            steps = sorted(self.steps_by_meeting.get(meeting.id, []), key=lambda s: s.step_order)
            start, end = _meeting_start(meeting, steps), _meeting_end(meeting, steps)
            ongoing = not bool(end) and bool(start)
            total_days = _duration(start, end)
            if end:
                complete_count += 1
            if total_days is not None:
                active_durations.append(total_days)
            cells = [
                f"<td>{idx}</td>",
                f"<td>{escape(str(meeting.meeting_number or '—'))}</td>",
                f"<td class='subject'>{escape(str(meeting.subject or '—'))}</td>",
                f"<td>{escape(_date_text(start))}</td>",
                f"<td>{escape(_date_text(end) if end else ('در جریان' if ongoing else 'ثبت نشده'))}</td>",
                f"<td class='duration'>{escape(_duration_text(total_days, ongoing))}</td>",
                f"<td>{escape(str(meeting.status or '—'))}</td>",
            ]
            for name in stage_names:
                step = next((s for s in steps if s.step_name == name), None)
                cells.append(f"<td>{escape(_duration_cell(step) if step else '—')}</td>")
            rows.append("<tr>" + "".join(cells) + "</tr>")
        average = round(sum(active_durations) / len(active_durations), 1) if active_durations else None
        stage_headers = "".join(f"<th>{escape(name)}</th>" for name in stage_names)
        return f"""<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>گزارش تجمیعی زمان رسیدگی</title>
<style>
@page{{size:A3 landscape;margin:10mm}}*{{box-sizing:border-box}}body{{font-family:Tahoma,Arial,sans-serif;color:#172033;background:#f1f5f9;margin:0;font-size:12px;line-height:1.7}}
main{{margin:20px auto;max-width:1800px;background:#fff;padding:24px;border-radius:14px;border-top:6px solid #0f9ca8}}
header{{display:flex;justify-content:space-between;align-items:center;gap:16px}}h1{{margin:0;color:#12354a;font-size:22px}}.muted{{color:#64748b}}
.cards{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:18px 0}}.card{{padding:12px;border:1px solid #dbe5ef;background:#f8fafc;border-radius:10px}}
.card span{{display:block;color:#64748b;font-size:11px}}.card strong{{font-size:18px;color:#12354a}}
button{{background:#0f766e;color:white;border:0;border-radius:8px;padding:9px 14px;cursor:pointer;font:inherit}}
.table-wrap{{overflow-x:auto}}table{{width:100%;border-collapse:collapse;margin-top:12px}}th,td{{border:1px solid #dbe4ee;padding:7px;text-align:center;vertical-align:middle;white-space:nowrap}}th{{background:#17384d;color:white}}tbody tr:nth-child(even){{background:#f8fafc}}td.subject{{text-align:right;white-space:normal;min-width:200px}}td.duration{{font-weight:bold;color:#075985}}.footer{{border-top:1px solid #e2e8f0;margin-top:16px;padding-top:8px;color:#64748b;font-size:11px}}
@media print{{body{{background:white}}main{{margin:0;max-width:none;padding:0;border:0}}button{{display:none}}}}
</style></head><body><main>
<header><div><h1>گزارش تجمیعی زمان رسیدگی صورتجلسات</h1><div class="muted">مدت کل و زمان صرف‌شده در هر مرحله · گزارش تهیه‌شده در {escape(today_shamsi())}</div></div><button onclick="window.print()">چاپ / ذخیره PDF</button></header>
<section class="cards"><div class="card"><span>تعداد صورتجلسات</span><strong>{len(self.meetings):,}</strong></div>
<div class="card"><span>پایان‌یافته‌ها بر اساس تاریخ پایان موجود</span><strong>{complete_count:,}</strong></div>
<div class="card"><span>میانگین مدت سپری‌شده (روز)</span><strong>{escape(str(average) if average is not None else 'داده کافی نیست')}</strong></div></section>
<p class="muted">مدت مراحل بر اساس تاریخ‌های ثبت‌شده محاسبه می‌شود. برای مراحل آغازشده و پایان‌نیافته، مدت تا امروز و نشان «در جریان» نمایش داده می‌شود. خانه خالی به معنای نبود تاریخ شروع است، نه صفر روز.</p>
<div class="table-wrap"><table><thead><tr><th>ردیف</th><th>شماره</th><th>موضوع</th><th>شروع رسیدگی</th><th>پایان رسیدگی</th><th>مدت کل</th><th>وضعیت پرونده</th>{stage_headers}</tr></thead><tbody>{''.join(rows) or '<tr><td colspan="7">صورتجلسه‌ای یافت نشد.</td></tr>'}</tbody></table></div>
<div class="footer">سامانه مدیریت و پیگیری صورتجلسات — تاریخ تهیه گزارش: {escape(today_shamsi())}</div>
</main></body></html>"""

    def generate_and_open(self):
        report_dir = os.path.join(os.getcwd(), "reports")
        os.makedirs(report_dir, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.abspath(os.path.join(report_dir, f"Workflow_Time_Overview_{stamp}.html"))
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(self._generate_html())
        opened = QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        if not opened and self.parent_widget:
            QMessageBox.information(self.parent_widget, "گزارش ذخیره شد", f"فایل ذخیره شد اما مرورگر باز نشد:\n{path}")
        return path
