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
    username = nicegui_app.storage.user.get("username", "")
    if not username:
        return
    prefs = _load_prefs()
    prefs.setdefault(username, {})[f"{view}_{field}"] = value
    _save_prefs(prefs)
