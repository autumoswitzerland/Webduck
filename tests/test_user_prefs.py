"""Tests for the query-history list logic in webduck.pages.user_prefs.

Only the pure list/dict helpers are exercised here — the file I/O and
accessor functions need a running NiceGUI session context.
"""

from webduck.pages.user_prefs import (
    _prune_history_data,
    _prune_prefs_data,
    _push_history_entry,
)


class TestPushHistoryEntry:
    def test_inserts_newest_first(self):
        entries = []
        _push_history_entry(entries, "SELECT 1", 20)
        _push_history_entry(entries, "SELECT 2", 20)
        assert entries == ["SELECT 2", "SELECT 1"]

    def test_skips_consecutive_duplicate(self):
        entries = ["SELECT 1"]
        _push_history_entry(entries, "SELECT 1", 20)
        assert entries == ["SELECT 1"]

    def test_keeps_only_max_entries(self):
        entries = []
        for i in range(25):
            _push_history_entry(entries, f"SELECT {i}", 20)
        assert len(entries) == 20
        assert entries[0] == "SELECT 24"
        assert entries[-1] == "SELECT 5"

    def test_dedup_still_trims(self):
        entries = []
        for i in range(25):
            _push_history_entry(entries, f"SELECT {i}", 20)
        # Re-adding the current head must not exceed the max.
        _push_history_entry(entries, "SELECT 24", 20)
        assert len(entries) == 20


class TestPrunePrefsData:
    def test_drops_project_and_database_when_project_deleted(self):
        prefs = {
            "mike": {"query_project": "gone", "query_database": "db"}
        }
        cleaned = _prune_prefs_data(prefs, {"alive"}, lambda p: {"db"})
        assert cleaned == {}

    def test_drops_database_when_db_deleted_but_project_kept(self):
        prefs = {
            "mike": {"query_project": "alive", "query_database": "gone"}
        }
        cleaned = _prune_prefs_data(prefs, {"alive"}, lambda p: {"other"})
        assert cleaned == {"mike": {"query_project": "alive"}}

    def test_keeps_valid_references(self):
        prefs = {
            "mike": {"query_project": "alive", "query_database": "db"}
        }
        cleaned = _prune_prefs_data(prefs, {"alive"}, lambda p: {"db"})
        assert cleaned == prefs

    def test_keeps_unknown_keys(self):
        prefs = {"mike": {"query_project": "gone", "custom_thing": "x"}}
        cleaned = _prune_prefs_data(prefs, set(), lambda p: set())
        assert cleaned == {"mike": {"custom_thing": "x"}}

    def test_same_db_name_dropped_when_not_in_target_project(self):
        # "sales" exists in another project, but the pref targets "alive".
        prefs = {
            "mike": {"query_project": "alive", "query_database": "sales"}
        }
        cleaned = _prune_prefs_data(
            prefs, {"alive"}, lambda p: {"otherdb"}
        )
        assert cleaned == {"mike": {"query_project": "alive"}}

    def test_all_views_pruned(self):
        prefs = {
            "mike": {
                "query_project": "gone", "query_database": "db",
                "browse_project": "alive", "browse_database": "gone",
                "import_project": "alive", "import_database": "db",
            }
        }
        cleaned = _prune_prefs_data(prefs, {"alive"}, lambda p: {"db"})
        assert cleaned == {
            "mike": {
                "browse_project": "alive",
                "import_project": "alive",
                "import_database": "db",
            }
        }


class TestPruneHistoryData:
    def test_drops_deleted_database(self):
        data = {"mike": {"proj": {"sales": ["SELECT 1"]}}}
        cleaned = _prune_history_data(data, {"proj"}, lambda p: {"other"})
        assert cleaned == {}

    def test_keeps_existing_database(self):
        data = {"mike": {"proj": {"sales": ["SELECT 1"]}}}
        cleaned = _prune_history_data(data, {"proj"}, lambda p: {"sales"})
        assert cleaned == data

    def test_drops_deleted_project(self):
        data = {"mike": {"gone": {"sales": ["SELECT 1"]}}}
        cleaned = _prune_history_data(data, {"alive"}, lambda p: {"sales"})
        assert cleaned == {}

    def test_drops_old_flat_format(self):
        data = {"mike": {"sales": ["SELECT 1"]}}
        cleaned = _prune_history_data(data, {"proj"}, lambda p: {"sales"})
        assert cleaned == {}

    def test_drops_empty_users_and_projects(self):
        data = {"mike": {}, "anna": {"proj": {}}}
        cleaned = _prune_history_data(data, {"proj"}, lambda p: {"sales"})
        assert cleaned == {}


class TestPruneUserData:
    """Integration tests for the file-level prune_user_data() cleanup.

    Uses a real StorageEngine on a temp data dir so the prune is
    exercised end-to-end (filesystem scan -> JSON read -> write).
    """

    def _setup(self, monkeypatch, tmp_path):
        from webduck.pages import context
        from webduck.storage.engine import StorageEngine

        store = StorageEngine(tmp_path)
        monkeypatch.setattr(context, "storage", store)
        store.create_project("alive")
        (tmp_path / "alive" / "sales.duckdb").touch()
        return store

    def test_prunes_deleted_project_from_prefs(self, monkeypatch, tmp_path):
        self._setup(monkeypatch, tmp_path)
        from webduck.pages import user_prefs

        user_prefs._save_prefs(
            {"mike": {"query_project": "gone", "query_database": "db"}}
        )
        user_prefs.prune_user_data()
        assert user_prefs._load_prefs() == {}

    def test_prunes_deleted_database_keeps_project(self, monkeypatch, tmp_path):
        self._setup(monkeypatch, tmp_path)
        from webduck.pages import user_prefs

        user_prefs._save_prefs(
            {"mike": {"query_project": "alive", "query_database": "gone"}}
        )
        user_prefs.prune_user_data()
        assert user_prefs._load_prefs() == {
            "mike": {"query_project": "alive"}
        }

    def test_prunes_history_for_deleted_database(self, monkeypatch, tmp_path):
        self._setup(monkeypatch, tmp_path)
        from webduck.pages import user_prefs

        user_prefs._save_history(
            {"mike": {"alive": {"gone": ["SELECT 1"]}}}
        )
        user_prefs.prune_user_data()
        assert user_prefs._load_history() == {}

    def test_keeps_valid_history(self, monkeypatch, tmp_path):
        self._setup(monkeypatch, tmp_path)
        from webduck.pages import user_prefs

        data = {"mike": {"alive": {"sales": ["SELECT 1"]}}}
        user_prefs._save_history(data)
        user_prefs.prune_user_data()
        assert user_prefs._load_history() == data

    def test_does_not_write_when_nothing_stale(self, monkeypatch, tmp_path):
        self._setup(monkeypatch, tmp_path)
        from webduck.pages import user_prefs

        user_prefs._save_prefs(
            {"mike": {"query_project": "alive", "query_database": "sales"}}
        )
        prefs_path = tmp_path / ".user_preferences.json"
        mtime_before = prefs_path.stat().st_mtime_ns
        user_prefs.prune_user_data()
        assert prefs_path.stat().st_mtime_ns == mtime_before

    def test_maybe_prune_at_most_once_per_interval(self, monkeypatch, tmp_path):
        self._setup(monkeypatch, tmp_path)
        from webduck.pages import user_prefs

        calls = []
        monkeypatch.setattr(
            user_prefs, "prune_user_data", lambda: calls.append(1)
        )
        monkeypatch.setattr(user_prefs, "_last_prune", 0.0)
        monkeypatch.setattr(user_prefs.time, "monotonic", lambda: 7200.0)

        user_prefs._maybe_prune()
        user_prefs._maybe_prune()
        assert len(calls) == 1

        monkeypatch.setattr(
            user_prefs.time, "monotonic", lambda: 7200.0 + 7200
        )
        user_prefs._maybe_prune()
        assert len(calls) == 2
