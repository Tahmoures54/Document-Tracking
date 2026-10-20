# -*- coding: utf-8 -*-
"""Regression tests for scan-file discovery."""
from __future__ import annotations

from ui.main_window import _build_scan_index


def test_build_scan_index_finds_supported_files_case_insensitively(tmp_path):
    (tmp_path / "1404-025.pdf").write_bytes(b"%PDF")
    (tmp_path / "1404-026.PNG").write_bytes(b"image")
    (tmp_path / "ignore.txt").write_text("not a scan", encoding="utf-8")

    index, available = _build_scan_index(str(tmp_path))

    assert available is True
    assert "1404-025" in index
    assert "1404-026" in index
    assert "ignore" not in index
    assert index["1404-025"][0].endswith("1404-025.pdf")


def test_build_scan_index_marks_missing_folder_unavailable(tmp_path):
    index, available = _build_scan_index(str(tmp_path / "does-not-exist"))
    assert index == {}
    assert available is False
