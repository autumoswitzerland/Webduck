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

"""User preferences — server-side JSON storage per view.

Strategy: a single ``.user_preferences.json`` file in the data directory
holds all preferences.  Each user has their own namespace (keyed by
username), and within that namespace preferences are stored as
``{view}_{field}`` composite keys — e.g. ``query_project`` or
``browse_database``.

This avoids per-user files while keeping preferences isolated per user
and per view.  The file is read/written atomically via simple read/write
calls (no locking needed since NiceGUI runs in a single process).
"""

import json
import time
from collections.abc import Callable
from pathlib import Path

from nicegui import app as nicegui_app


def _prefs_path() -> Path:
    """Return the path to the shared preferences JSON file.

    Located at ``<data_dir>/.user_preferences.json`` so it sits
    alongside the DuckDB databases but is hidden from normal browsing.
    """
    from webduck.pages.context import storage
    return Path(storage.data_dir) / ".user_preferences.json"


def _load_prefs() -> dict:
    """Load and parse the preferences file.

    Returns an empty dict if the file doesn't exist or is corrupted
    (e.g. truncated write).  This makes the system resilient to
    partially-written files.
    """
    p = _prefs_path()
    if p.exists():
        try:
            return json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_prefs(data: dict) -> None:
    """Persist the full preferences dict to disk.

    Ensures the parent directory exists (first run scenario) and
    writes pretty-printed JSON for manual inspection/debugging.
    """
    _prefs_path().parent.mkdir(parents=True, exist_ok=True)
    _prefs_path().write_text(json.dumps(data, indent=2))


def get_user_pref(view: str, field: str) -> str | None:
    """Retrieve a single preference value for the current user.

    Args:
        view:  The page/view name (e.g. "query", "browse").
        field: The setting name (e.g. "project", "database").

    Returns:
        The stored string value, or ``None`` if not set or no user
        is logged in.
    """
    _maybe_prune()
    username = nicegui_app.storage.user.get("username", "")
    if not username:
        return None
    return _load_prefs().get(username, {}).get(f"{view}_{field}")


def set_user_pref(view: str, field: str, value: str) -> None:
    """Persist a preference value for the current user.

    Uses ``setdefault`` to lazily create the user's namespace on
    first write.  The composite key ``{view}_{field}`` prevents
    collisions between different views that use the same field name
    (e.g. both "query" and "browse" store a "database" preference).
    """
    _maybe_prune()
    username = nicegui_app.storage.user.get("username", "")
    if not username:
        return
    prefs = _load_prefs()
    prefs.setdefault(username, {})[f"{view}_{field}"] = value
    _save_prefs(prefs)


# ---------------------------------------------------------------------------
# Query history — stored in a separate file so long SQL strings never bloat
# the shared preferences file.  Same per-user namespace strategy.
# ---------------------------------------------------------------------------

def _history_path() -> Path:
    """Return the path to the per-instance query history JSON file.

    Sits alongside the preferences file but is dedicated to SQL
    history so that long queries don't inflate ``.user_preferences.json``.
    """
    from webduck.pages.context import storage
    return Path(storage.data_dir) / ".query_history.json"


def _load_history() -> dict:
    """Load and parse the query history file (empty dict if missing/broken)."""
    p = _history_path()
    if p.exists():
        try:
            return json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_history(data: dict) -> None:
    """Persist the query history dict to disk."""
    _history_path().parent.mkdir(parents=True, exist_ok=True)
    _history_path().write_text(json.dumps(data, indent=2))


def get_query_history(project: str, database: str) -> list[str]:
    """Return the saved SQL queries for the current user, project and database.

    Keyed per project and per database so that databases with the same
    name in different projects never share entries.  Most recent query
    first, oldest last.  Returns an empty list when nothing was saved yet
    or no user is logged in.
    """
    _maybe_prune()
    username = nicegui_app.storage.user.get("username", "")
    if not username:
        return []
    return (
        _load_history()
        .get(username, {})
        .get(project, {})
        .get(database, [])
    )


def add_query_history(project: str, database: str, sql: str) -> None:
    """Record a successfully executed SQL query for the current user.

    The query is stored under ``project`` + ``database`` and inserted at
    the front of the list; the oldest entry is dropped once the
    per-database maximum is exceeded.  If the query is already present it
    is     moved to the front instead of being duplicated.
    """
    from webduck.main import QUERY_HISTORY_MAX

    _maybe_prune()
    username = nicegui_app.storage.user.get("username", "")
    if not username:
        return
    data = _load_history()
    per_user = data.setdefault(username, {})
    per_project = per_user.setdefault(project, {})
    entries = per_project.setdefault(database, [])
    _push_history_entry(entries, sql, QUERY_HISTORY_MAX)
    _save_history(data)


def _push_history_entry(entries: list, sql: str, max_entries: int) -> None:
    """Insert ``sql`` at the front of ``entries``, trimming to ``max_entries``.

    Pure list logic kept separate so it can be unit-tested without a
    NiceGUI session context.  Existing occurrences of ``sql`` are removed
    first so re-running a query moves it to the front instead of
    duplicating it.
    """
    if sql in entries:
        entries.remove(sql)

    entries.insert(0, sql)
    del entries[max_entries:]


# ---------------------------------------------------------------------------
# Stale-data cleanup — drop preferences and query-history entries that
# reference projects/databases which no longer exist on disk.
# ---------------------------------------------------------------------------

# Minimum time between two automatic cleanups while the server runs.
# A full cleanup needs filesystem scans, so it runs at most this often
# instead of on every accessor call.
_PRUNE_INTERVAL_SECONDS = 3600

_last_prune: float = 0.0


def _prune_prefs_data(
    prefs: dict,
    existing_projects: set,
    dbs_for: Callable[[str], set],
) -> dict:
    """Drop stale project/database references from ``prefs``.

    For every user and every known view (query, browse, import):

    * ``{view}_project`` no longer exists → both the project and the
      database preference are removed.
    * ``{view}_project`` exists but ``{view}_database`` is not listed in
      that project → only the database preference is removed.

    Unknown keys are left untouched so future preferences survive.
    Users left without any preferences are dropped.  Pure dict logic kept
    separate so it can be unit-tested without storage or a session.
    """
    views = ("query", "browse", "import")
    cleaned: dict = {}
    for username, user_prefs in prefs.items():
        if not isinstance(user_prefs, dict):
            continue
        out = dict(user_prefs)
        for view in views:
            project = out.get(f"{view}_project")
            if project is None:
                continue
            if project not in existing_projects:
                out.pop(f"{view}_project", None)
                out.pop(f"{view}_database", None)
            else:
                database = out.get(f"{view}_database")
                if (
                    database is not None
                    and database not in dbs_for(project)
                ):
                    out.pop(f"{view}_database", None)
        if out:
            cleaned[username] = out
    return cleaned


def _prune_history_data(
    data: dict,
    existing_projects: set,
    dbs_for: Callable[[str], set],
) -> dict:
    """Drop query-history entries whose project or database is gone.

    Structure: ``{username: {project: {database: [sql, ...]}}}``.  Any
    malformed value (e.g. the old flat format) is dropped as well, which
    lets the cleanup migrate away legacy data.  Users left with nothing
    are dropped.  Pure dict logic kept separate so it can be unit-tested
    without storage or a session.
    """
    cleaned: dict = {}
    for username, per_project in data.items():
        if not isinstance(per_project, dict):
            continue
        kept_projects: dict = {}
        for project, per_db in per_project.items():
            if (
                project not in existing_projects
                or not isinstance(per_db, dict)
            ):
                continue
            kept_dbs = {
                db: entries
                for db, entries in per_db.items()
                if isinstance(entries, list)
                and db in dbs_for(project)
            }
            if kept_dbs:
                kept_projects[project] = kept_dbs
        if kept_projects:
            cleaned[username] = kept_projects
    return cleaned


def prune_user_data() -> None:
    """Remove preferences and history entries pointing at missing data.

    Scans the filesystem once, prunes both JSON files, and only writes a
    file back when something actually changed.  Called at server startup
    and, via :func:`_maybe_prune`, at most once per interval while the
    server keeps running.
    """
    global _last_prune
    _last_prune = time.monotonic()
    from webduck.pages.context import storage
    if storage is None:
        return
    projects = storage.list_projects()
    existing_projects = set(projects)
    db_lists = {p: storage.list_databases(p) for p in projects}

    def dbs_for(project: str) -> set:
        return set(db_lists.get(project, []))

    prefs = _load_prefs()
    cleaned_prefs = _prune_prefs_data(
        prefs, existing_projects, dbs_for
    )
    if cleaned_prefs != prefs:
        _save_prefs(cleaned_prefs)

    history = _load_history()
    cleaned_history = _prune_history_data(
        history, existing_projects, dbs_for
    )
    if cleaned_history != history:
        _save_history(cleaned_history)


def _maybe_prune() -> None:
    """Run the stale-data cleanup at most once per interval.

    Called from every accessor function; the time guard keeps the
    filesystem scan from running on every single call.  The first call
    after server start also performs the initial cleanup.
    """
    global _last_prune
    now = time.monotonic()
    if now - _last_prune < _PRUNE_INTERVAL_SECONDS:
        return
    _last_prune = now
    prune_user_data()
