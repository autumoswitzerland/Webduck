# ------------------------------------------------------------------------------
# Copyright (c) 2026 autumo GmbH. All rights reserved.
#
# Licensed under the MIT License. See LICENSE file in the project root for
# full license information.
#
# NOTICE: This file is part of WebDuck. The above copyright notice and this
# permission notice shall be included in all copies or substantial portions
# of this software.
# ------------------------------------------------------------------------------

# =============================================================================
#  WebDuck — Logging
#  ---------------------------------------------------------------------------
#  Optional rotated file logging with per-query database logging.
#
#  Provides setup_logging() to configure rotating file handlers and a
#  log_query() function to record individual SQL queries to a log file.
#
#  Project:   WebDuck
#  Author:    autumo GmbH
#  Version:   0.1.0
#  Date:      2026-07-20
# =============================================================================

"""WebDuck logging module — optional, rotated, per-database query logging."""

import logging
import logging.handlers
from pathlib import Path

_logger: logging.Logger | None = None


def setup_logging(data_dir: Path, enabled: bool = False, max_size_mb: int = 10,
                  max_files: int = 5, query_log: bool = False) -> logging.Logger:
    """Configure and return the WebDuck logger.

    Parameters
    ----------
    data_dir : Path
        Directory where ``webduck.log`` is written.
    enabled : bool
        If ``False`` only WARNING+ messages are emitted (no file handler).
    max_size_mb : int
        Maximum size of a single log file before rotation.
    max_files : int
        Number of rotated files to keep.
    query_log : bool
        If ``True``, every SQL query is logged at INFO level.
    """
    global _logger

    logger = logging.getLogger("webduck")

    # Remove existing handlers (safe for repeated calls)
    logger.handlers.clear()

    if not enabled:
        # Minimal console handler for warnings/errors only
        logger.setLevel(logging.WARNING)
        console = logging.StreamHandler()
        console.setLevel(logging.WARNING)
        console.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        logger.addHandler(console)
        _logger = logger
        return logger

    logger.setLevel(logging.DEBUG)
    data_dir.mkdir(parents=True, exist_ok=True)
    log_path = data_dir / "webduck.log"

    file_handler = logging.handlers.RotatingFileHandler(
        log_path,
        maxBytes=max_size_mb * 1024 * 1024,
        backupCount=max_files,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    logger.addHandler(file_handler)

    # Console handler at INFO
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    )
    logger.addHandler(console)

    _logger = logger
    logger.info("Logging enabled → %s", log_path)
    return logger


def get_logger() -> logging.Logger:
    """Return the current WebDuck logger (or a no-op placeholder)."""
    global _logger
    if _logger is None:
        _logger = logging.getLogger("webduck")
    return _logger


def log_query(project: str, database: str, sql: str, success: bool,
              row_count: int = 0, error: str = "") -> None:
    """Log a SQL query execution at INFO level (only if query_log is enabled)."""
    logger = get_logger()
    if not logger.isEnabledFor(logging.INFO):
        return
    status = "OK" if success else "FAIL"
    msg = f"[{project}/{database}] {status} rows={row_count}"
    if error:
        msg += f" err={error}"
    logger.info(msg)
    logger.debug("SQL: %s", sql[:500])
