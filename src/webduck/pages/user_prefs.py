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

"""User preferences — server-side JSON storage per view."""

import json
from pathlib import Path

from nicegui import app as nicegui_app


def _prefs_path() -> Path:
    from webduck.pages.context import storage
    return Path(storage.data_dir) / ".user_preferences.json"


def _load_prefs() -> dict:
    p = _prefs_path()
    if p.exists():
        try:
            return json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_prefs(data: dict) -> None:
    _prefs_path().parent.mkdir(parents=True, exist_ok=True)
    _prefs_path().write_text(json.dumps(data, indent=2))


def get_user_pref(view: str, field: str) -> str | None:
    username = nicegui_app.storage.user.get("username", "")
    if not username:
        return None
    return _load_prefs().get(username, {}).get(f"{view}_{field}")


def set_user_pref(view: str, field: str, value: str) -> None:
    username = nicegui_app.storage.user.get("username", "")
    if not username:
        return
    prefs = _load_prefs()
    prefs.setdefault(username, {})[f"{view}_{field}"] = value
    _save_prefs(prefs)
