# Document & MOM Tracking System 3.0.1

## Security & Stability Patch

### Fixed
- **Password hashing**: Replaced weak SHA-256 with PBKDF2-HMAC-SHA256 (210k iterations). Existing SHA-256 hashes are still accepted and transparently upgraded on next successful login.
- **Roles consistency**: Aligned role definitions across `config.py`, `db/models.py` and `security/permissions.py` (admin / manager / editor / user / viewer).
- **Scan path**: `DEFAULT_SCAN_PATH` is now overridable via environment variable `MOM_SCAN_PATH` or QSettings key `scan_path` (helper `get_scan_path()` added).

### Notes
- Default admin remains `admin / admin` on first database creation; password is forced to change.
- No breaking schema changes; existing databases continue to work.
