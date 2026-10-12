# Document & MOM Tracking System 3.0.0

Professional Operational desktop system for technical-office teams, focused on meeting minutes (MOM), document tracking and operational follow-up.

## Core flow
`Entry → Auto Assignment → Workflow → Due Date → Contractor Handover → Contractor Response → Close`

The system surfaces overdue items, near-due items, waiting contractor responses, current responsible person, current workflow stage and document-scan availability.

## Scan archive
Default network path:
`\\192.168.200.6\technical office\_MOM\_Scan`

Scans are searched recursively by exact filename stem. Example: meeting `1404-025` should be stored as `1404-025.pdf` (or another supported scan extension).

## Build
1. Install Python 3.11+ and requirements.
2. Run `pip install -r requirements.txt`.
3. Run `python app.py`.
4. For Windows packaging run `build_release.bat`.

## Default account
`admin / admin` on first database creation. Change the password when prompted.
