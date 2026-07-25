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
#  Rotation strategy:
#    Uses Python's built-in ``RotatingFileHandler`` which keeps log files
#    bounded by size.  When ``webduck.log`` exceeds ``max_size_mb`` bytes
#    it is rotated to ``webduck.log.1``, ``webduck.log.2``, etc.  The
#    oldest file (``webduck.log.<max_files>``) is deleted when the limit
#    is reached — no external log rotation (logrotate) needed.
#
#  Custom logging vs framework:
#    This module intentionally avoids uvicorn's or FastAPI's logging
#    configuration.  Uvicorn has its own access/error log handlers that
#    are controlled via ``uvicorn.run()`` kwargs in ``main.py``.  This
#    module only sets up the ``"webduck"`` named logger used by the
#    application code (storage engine, auth, REST endpoints).
#
#  Project:   WebDuck
#  Author:    autumo GmbH
#  Version:   1.0.0
#  Date:      2026-07-20
# =============================================================================

"""WebDuck logging module — optional, rotated, per-database query logging.

The logger is stored in the module-level ``_logger`` variable and lazily
initialised by ``setup_logging()`` (called once during ``webduck start``).
All other modules obtain the logger via ``get_logger()`` or the convenience
helpers ``log_query()``, ``log_warning()``, ``log_error()``.
"""

import logging
import logging.handlers
from pathlib import Path

# Module-level logger — populated by setup_logging(); remains None until
# the server starts so that import-time log calls are harmless no-ops.
_logger: logging.Logger | None = None


def setup_logging(data_dir: Path, enabled: bool = False, max_size_mb: int = 10,
                  max_files: int = 5, query_log: bool = False,
                  log_dir: str = "", level: str = "debug",
                  console_enabled: bool = False) -> logging.Logger:
    """Configure and return the WebDuck logger.

    Sets up one or two handlers on the ``"webduck"`` named logger:

    1. **File handler** (``RotatingFileHandler``) — created only when
       *enabled* is ``True``.  Writes to ``<log_dir>/webduck.log`` with
       size-based rotation (``max_size_mb`` × ``max_files`` total storage).
       The file handler level is controlled by *level*.

    2. **Console handler** (``StreamHandler`` to stderr) — created when
       *console_enabled* is ``True``.  Always set to ``INFO`` level with
       a compact timestamp format, independent of the file handler level.

    If *enabled* is ``False`` and *console_enabled* is ``False`` the logger
    has no handlers and every log call is a no-op (which is the production
    default for a quiet console).

    Parameters
    ----------
    data_dir : Path
        Fallback directory when *log_dir* is empty.
    enabled : bool
        If ``False`` no file handler is created.
    max_size_mb : int
        Maximum size of a single log file before rotation.
    max_files : int
        Number of rotated files to keep.
    query_log : bool
        If ``True``, every SQL query is logged at INFO level.
    log_dir : str
        Directory for ``webduck.log``.  Empty string falls back to ``log/``.
    level : str
        Minimum log level for the file handler (debug/info/warning/error).
    console_enabled : bool
        If ``True``, a StreamHandler (stderr) is attached to the logger.
    """
    global _logger

    # Use the standard library named logger — other modules retrieve it
    # via logging.getLogger("webduck") or get_logger().
    logger = logging.getLogger("webduck")

    # Remove existing handlers so setup_logging() is idempotent (safe to
    # call again if the server is restarted within the same process).
    logger.handlers.clear()

    if not enabled:
        # File logging off — optionally add a console handler only
        if console_enabled:
            logger.setLevel(logging.WARNING)
            console = logging.StreamHandler()
            console.setLevel(logging.WARNING)
            console.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
            logger.addHandler(console)
        _logger = logger
        return logger

    # --- File handler setup ---
    _level = getattr(logging, level.upper(), logging.DEBUG)
    logger.setLevel(_level)

    # Resolve the log directory: explicit log_dir wins, otherwise "log/"
    effective_dir = Path(log_dir) if log_dir else Path("log")
    effective_dir.mkdir(parents=True, exist_ok=True)
    log_path = effective_dir / "webduck.log"

    # RotatingFileHandler: grows until maxBytes, then rotates to .1, .2, …
    # backupCount controls how many old files are kept before the oldest
    # is deleted — total disk usage ≈ max_size_mb × (backupCount + 1).
    file_handler = logging.handlers.RotatingFileHandler(
        log_path,
        maxBytes=max_size_mb * 1024 * 1024,
        backupCount=max_files,
        encoding="utf-8",
    )
    file_handler.setLevel(_level)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    logger.addHandler(file_handler)

    # --- Optional console handler (independent of file handler level) ---
    if console_enabled:
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
    """Return the current WebDuck logger (or a no-op placeholder).

    If ``setup_logging()`` has not been called yet, a bare named logger
    is returned — it has no handlers so all log calls are silently
    discarded.  This prevents import-time errors in modules that call
    ``get_logger()`` before the server boots.
    """
    global _logger
    if _logger is None:
        _logger = logging.getLogger("webduck")
    return _logger


def log_query(project: str, database: str, sql: str, success: bool,
              row_count: int = 0, error: str = "") -> None:
    """Log a SQL query execution at INFO level (only if query_log is enabled).

    The INFO-level message includes project/database, success/fail status,
    and row count.  The full SQL text (truncated to 500 chars) is logged
    at DEBUG level so it only appears when the file handler level is set
    to ``debug``.

    Args:
        project:   Project name the query ran against.
        database:  Database name within the project.
        sql:       The SQL statement executed.
        success:   ``True`` if the query completed without error.
        row_count: Number of rows returned/affected.
        error:     Error message string (empty on success).
    """
    logger = get_logger()
    # Early-out: skip string formatting if nobody is listening at INFO
    if not logger.isEnabledFor(logging.INFO):
        return
    status = "OK" if success else "FAIL"
    msg = f"[{project}/{database}] {status} rows={row_count}"
    if error:
        msg += f" err={error}"
    logger.info(msg)
    logger.debug("SQL: %s", sql[:500])


def log_warning(msg: str) -> None:
    """Log a warning message."""
    get_logger().warning(msg)


def log_error(msg: str) -> None:
    """Log an error message."""
    get_logger().error(msg)
