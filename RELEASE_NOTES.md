# Document & MOM Tracking System 3.0.0

## MOM Tracking Edition

This release delivers the Document & MOM Tracking System as an operational Document & MOM tracking platform.

### Workflow
- Entry registration
- Automatic assignment to the current logged-in user at the engineering-review stage
- Full workflow with responsible person and current stage
- Due-date monitoring
- Overdue and near-due alerts
- Contractor handover stage
- Contractor response tracking
- Complete meeting-linked audit history
- Operational dashboard
- Scan document availability tracking

### Scan archive
Default path:
`\\192.168.200.6\technical office\_MOM\_Scan`

The scanner lookup is recursive and expects the scanned filename stem to exactly match the meeting number.

### UX
- Stable LTR rendering for document numbers
- Persian/Arabic digit normalization
- Right-click workflow/tracking actions
- Current responsible person and current workflow stage shown in the main table
- Quick scanned-document access
- Status bar connection indicators

### Data compatibility
The application performs lightweight SQLite migrations for older databases and preserves existing records.
