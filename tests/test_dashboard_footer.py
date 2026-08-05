"""Unit tests for the dashboard storage-overview footer logic."""

from webduck.pages.dashboard import _storage_footer_lines


def _t(key: str) -> str:
    return {
        "total": "Total",
        "databases": "DBs",
        "trash": "Trash",
        "objects": "Obj",
    }.get(key, key)


def test_footer_total_line_only_with_rows():
    lines = _storage_footer_lines(True, 2, 1500, 0, 0, _t)
    assert len(lines) == 1
    assert "2" in lines[0]
    assert "1.5 KB" in lines[0]


def test_footer_trash_line_only_when_trash_present():
    lines = _storage_footer_lines(False, 0, 0, 3, 5000, _t)
    assert len(lines) == 1
    assert "3" in lines[0]
    assert "5.0 KB" in lines[0]


def test_footer_both_lines_when_rows_and_trash():
    lines = _storage_footer_lines(True, 1, 1000, 2, 2000, _t)
    assert len(lines) == 2
    assert all(key in lines[0] for key in ("Total", "1.0 KB"))
    assert all(key in lines[1] for key in ("Trash", "2.0 KB"))


def test_footer_empty_when_no_rows_and_no_trash():
    assert _storage_footer_lines(False, 0, 0, 0, 0, _t) == []
