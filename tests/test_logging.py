"""Tests for webduck.logging."""

import logging

from webduck.logging import get_logger, log_query, setup_logging


def test_logging_disabled_by_default(tmp_path):
    logger = setup_logging(tmp_path, enabled=False)
    assert logger.isEnabledFor(logging.WARNING)
    assert not logger.isEnabledFor(logging.DEBUG)
    assert not (tmp_path / "webduck.log").exists()


def test_logging_enabled_creates_file(tmp_path):
    logger = setup_logging(tmp_path, enabled=True, max_size_mb=1, max_files=2,
                           log_dir=str(tmp_path))
    assert (tmp_path / "webduck.log").exists()
    logger.info("test message")
    content = (tmp_path / "webduck.log").read_text()
    assert "test message" in content


def test_log_query_does_nothing_when_disabled(tmp_path):
    setup_logging(tmp_path, enabled=False)
    # Should not raise
    log_query("p", "db", "SELECT 1", True, row_count=1)


def test_log_query_writes_to_file(tmp_path):
    setup_logging(tmp_path, enabled=True, query_log=True, log_dir=str(tmp_path))
    log_query("myproj", "db1", "SELECT * FROM users", True, row_count=5)
    content = (tmp_path / "webduck.log").read_text()
    assert "myproj/db1" in content
    assert "OK" in content
    assert "rows=5" in content


def test_log_query_error(tmp_path):
    setup_logging(tmp_path, enabled=True, query_log=True, log_dir=str(tmp_path))
    log_query("p", "db", "BAD SQL", False, error="syntax error")
    content = (tmp_path / "webduck.log").read_text()
    assert "FAIL" in content
    assert "syntax error" in content


def test_rotation_config(tmp_path):
    # 1 KB = very small, triggers rotation quickly
    logger = setup_logging(tmp_path, enabled=True, max_size_mb=0.001, max_files=3,
                           log_dir=str(tmp_path))
    # Write enough to trigger rotation
    for i in range(200):
        logger.info(f"line {i} {'x' * 100}")
    log_files = list(tmp_path.glob("webduck.log*"))
    assert len(log_files) > 1


def test_get_logger_returns_consistent_instance():
    logger1 = get_logger()
    logger2 = get_logger()
    assert logger1 is logger2
