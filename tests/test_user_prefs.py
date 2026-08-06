"""Tests for the query-history list logic in webduck.pages.user_prefs.

Only the pure list/dict helpers are exercised here — the file I/O and
accessor functions need a running NiceGUI session context.
"""

from webduck.pages.user_prefs import (
    _prune_history_data,
    _prune_prefs_data,
    _push_history_entry,
    _remove_history_refs,
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


class TestRemoveHistoryRefs:
    def test_removes_single_database_keeps_others(self):
        data = {"mike": {"proj": {"sales": ["SELECT 1"], "other": ["SELECT 2"]}}}
        cleaned = _remove_history_refs(data, "proj", "sales")
        assert cleaned == {"mike": {"proj": {"other": ["SELECT 2"]}}}

    def test_removes_whole_project_without_database(self):
        data = {"mike": {"proj": {"sales": ["SELECT 1"], "other": ["SELECT 2"]}}}
        cleaned = _remove_history_refs(data, "proj")
        assert cleaned == {}

    def test_removes_project_across_all_users(self):
        data = {
            "mike": {"proj": {"sales": ["SELECT 1"]}},
            "anna": {"proj": {"sales": ["SELECT 2"]}, "other": {"db": ["SELECT 3"]}},
        }
        cleaned = _remove_history_refs(data, "proj")
        assert cleaned == {"anna": {"other": {"db": ["SELECT 3"]}}}

    def test_cascades_empty_projects_and_users(self):
        data = {"mike": {"proj": {"sales": ["SELECT 1"]}}, "anna": {}}
        cleaned = _remove_history_refs(data, "proj", "sales")
        assert cleaned == {"anna": {}}

    def test_leaves_unrelated_users_untouched(self):
        data = {
            "mike": {"proj": {"sales": ["SELECT 1"]}},
            "anna": {"other": {"db": ["SELECT 2"]}},
        }
        cleaned = _remove_history_refs(data, "proj", "sales")
        assert cleaned == {"anna": {"other": {"db": ["SELECT 2"]}}}

    def test_no_change_when_target_missing(self):
        data = {"mike": {"proj": {"sales": ["SELECT 1"]}}}
        cleaned = _remove_history_refs(data, "proj", "missing")
        assert cleaned == data

    def test_no_change_when_project_missing(self):
        data = {"mike": {"proj": {"sales": ["SELECT 1"]}}}
        cleaned = _remove_history_refs(data, "gone")
        assert cleaned == data


class TestPruneUserData:
    """Integration tests for the prefs cleanup at server startup.

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

    def test_prune_does_not_touch_query_history(self, monkeypatch, tmp_path):
        """Query history is never pruned — only targeted removal deletes it."""
        self._setup(monkeypatch, tmp_path)
        from webduck.pages import user_prefs

        data = {"mike": {"alive": {"gone": ["SELECT 1"]}}}
        user_prefs._save_history(data)
        user_prefs.prune_user_data()
        assert user_prefs._load_history() == data


class TestPruneHistoryData:
    def test_drops_project_that_is_fully_gone(self):
        data = {"mike": {"gone": {"sales": ["SELECT 1"]}}}
        cleaned = _prune_history_data(data, set(), set(), lambda p: set(), lambda p: set())
        assert cleaned == {}

    def test_drops_database_that_is_fully_gone(self):
        data = {"mike": {"alive": {"sales": ["SELECT 1"]}}}
        cleaned = _prune_history_data(data, {"alive"}, set(), lambda p: {"other"}, lambda p: set())
        assert cleaned == {}

    def test_keeps_live_project_and_database(self):
        data = {"mike": {"alive": {"sales": ["SELECT 1"]}}}
        cleaned = _prune_history_data(data, {"alive"}, set(), lambda p: {"sales"}, lambda p: set())
        assert cleaned == data

    def test_keeps_history_for_trashed_database(self):
        data = {"mike": {"alive": {"sales": ["SELECT 1"]}}}
        cleaned = _prune_history_data(
            data, {"alive"}, set(), lambda p: set(), lambda p: {"sales"}
        )
        assert cleaned == data

    def test_keeps_whole_trashed_project(self):
        data = {"mike": {"gone": {"sales": ["SELECT 1"]}}}
        cleaned = _prune_history_data(
            data, set(), {"gone"}, lambda p: set(), lambda p: set()
        )
        assert cleaned == data

    def test_mixed_scenario(self):
        data = {
            "mike": {
                "alive": {"sales": ["S1"], "gone_db": ["S2"]},
                "trashed": {"x": ["S3"]},
                "gone": {"z": ["S4"]},
            }
        }
        cleaned = _prune_history_data(
            data,
            {"alive"},
            {"trashed"},
            lambda p: {"sales"},
            lambda p: set(),
        )
        assert cleaned == {
            "mike": {
                "alive": {"sales": ["S1"]},
                "trashed": {"x": ["S3"]},
            }
        }

    def test_cascades_empty_users(self):
        data = {"mike": {"gone": {"sales": ["SELECT 1"]}}, "anna": {}}
        cleaned = _prune_history_data(data, set(), set(), lambda p: set(), lambda p: set())
        assert cleaned == {}

    def test_leaves_unrelated_users_untouched(self):
        data = {
            "mike": {"alive": {"sales": ["SELECT 1"]}},
            "anna": {"other": {"db": ["SELECT 2"]}},
        }
        cleaned = _prune_history_data(
            data, {"alive", "other"}, set(), lambda p: {"sales", "db"}, lambda p: set()
        )
        assert cleaned == data


class TestPruneHistorySweep:
    """Integration tests for the query-history sweep at server startup."""

    def _setup(self, monkeypatch, tmp_path):
        from webduck.pages import context
        from webduck.storage.engine import StorageEngine

        store = StorageEngine(tmp_path)
        monkeypatch.setattr(context, "storage", store)
        store.create_project("alive")
        (tmp_path / "alive" / "sales.duckdb").touch()

        store.create_project("trashed_proj")
        (tmp_path / "trashed_proj" / "x.duckdb").touch()
        store.trash_project("trashed_proj")

        store.create_project("trashed_db_proj")
        (tmp_path / "trashed_db_proj" / "db.duckdb").touch()
        store.trash_database("trashed_db_proj", "db")
        return store

    def test_removes_history_for_fully_deleted_objects(self, monkeypatch, tmp_path):
        self._setup(monkeypatch, tmp_path)
        from webduck.pages import user_prefs

        user_prefs._save_history(
            {
                "mike": {
                    "alive": {"sales": ["S1"], "gone_db": ["S2"]},
                    "trashed_proj": {"x": ["S3"]},
                    "trashed_db_proj": {"db": ["S4"]},
                    "fullygone": {"z": ["S5"]},
                }
            }
        )
        user_prefs.prune_history_data()
        assert user_prefs._load_history() == {
            "mike": {
                "alive": {"sales": ["S1"]},
                "trashed_proj": {"x": ["S3"]},
                "trashed_db_proj": {"db": ["S4"]},
            }
        }

    def test_does_not_write_when_nothing_stale(self, monkeypatch, tmp_path):
        self._setup(monkeypatch, tmp_path)
        from webduck.pages import user_prefs

        user_prefs._save_history(
            {"mike": {"alive": {"sales": ["SELECT 1"]}}}
        )
        history_path = tmp_path / ".query_history.json"
        mtime_before = history_path.stat().st_mtime_ns
        user_prefs.prune_history_data()
        assert history_path.stat().st_mtime_ns == mtime_before


class TestRemoveQueryHistory:
    def _setup(self, monkeypatch, tmp_path):
        from webduck.pages import context
        from webduck.storage.engine import StorageEngine

        store = StorageEngine(tmp_path)
        monkeypatch.setattr(context, "storage", store)
        return store

    def test_removes_database_history(self, monkeypatch, tmp_path):
        self._setup(monkeypatch, tmp_path)
        from webduck.pages import user_prefs

        user_prefs._save_history(
            {"mike": {"proj": {"sales": ["SELECT 1"], "other": ["SELECT 2"]}}}
        )
        user_prefs.remove_query_history("proj", "sales")
        assert user_prefs._load_history() == {
            "mike": {"proj": {"other": ["SELECT 2"]}}
        }

    def test_removes_whole_project_history(self, monkeypatch, tmp_path):
        self._setup(monkeypatch, tmp_path)
        from webduck.pages import user_prefs

        user_prefs._save_history(
            {"mike": {"proj": {"sales": ["SELECT 1"]}}, "anna": {"proj": {"x": ["S"]}}}
        )
        user_prefs.remove_query_history("proj")
        assert user_prefs._load_history() == {}

    def test_does_not_write_when_nothing_to_remove(self, monkeypatch, tmp_path):
        self._setup(monkeypatch, tmp_path)
        from webduck.pages import user_prefs

        data = {"mike": {"proj": {"sales": ["SELECT 1"]}}}
        user_prefs._save_history(data)
        history_path = tmp_path / ".query_history.json"
        mtime_before = history_path.stat().st_mtime_ns
        user_prefs.remove_query_history("proj", "missing")
        assert history_path.stat().st_mtime_ns == mtime_before


class TestRemoveUserData:
    def _setup(self, monkeypatch, tmp_path):
        from webduck.pages import context
        from webduck.storage.engine import StorageEngine

        store = StorageEngine(tmp_path)
        monkeypatch.setattr(context, "storage", store)
        return store

    def test_removes_user_from_prefs_and_history(self, monkeypatch, tmp_path):
        self._setup(monkeypatch, tmp_path)
        from webduck.pages import user_prefs

        user_prefs._save_prefs(
            {"mike": {"query_project": "proj"}, "anna": {"query_project": "proj"}}
        )
        user_prefs._save_history(
            {"mike": {"proj": {"sales": ["SELECT 1"]}}, "anna": {"proj": {"x": ["S"]}}}
        )
        user_prefs.remove_user_data("mike")
        assert user_prefs._load_prefs() == {"anna": {"query_project": "proj"}}
        assert user_prefs._load_history() == {"anna": {"proj": {"x": ["S"]}}}

    def test_missing_user_is_noop(self, monkeypatch, tmp_path):
        self._setup(monkeypatch, tmp_path)
        from webduck.pages import user_prefs

        data = {"mike": {"proj": {"sales": ["SELECT 1"]}}}
        user_prefs._save_history(data)
        user_prefs.remove_user_data("nobody")
        assert user_prefs._load_history() == data
