"""Tests for webduck.storage.engine."""

import json

import duckdb


class TestStorageEngine:
    def test_list_projects_empty(self, storage):
        assert storage.list_projects() == []

    def test_create_and_list_databases(self, storage, tmp_data):
        (tmp_data / "myproj").mkdir()
        assert storage.create_database("myproj", "db1") is True
        assert storage.database_exists("myproj", "db1") is True
        assert storage.list_databases("myproj") == ["db1"]

    def test_create_duplicate_database(self, storage, tmp_data):
        (tmp_data / "myproj").mkdir()
        storage.create_database("myproj", "db1")
        assert storage.create_database("myproj", "db1") is False

    def test_delete_database(self, storage, tmp_data):
        (tmp_data / "myproj").mkdir()
        storage.create_database("myproj", "db1")
        assert storage.delete_database("myproj", "db1") is True
        assert storage.database_exists("myproj", "db1") is False

    def test_delete_nonexistent_database(self, storage, tmp_data):
        (tmp_data / "myproj").mkdir()
        assert storage.delete_database("myproj", "nope") is False

    def test_delete_project(self, storage, tmp_data):
        (tmp_data / "myproj").mkdir()
        storage.create_database("myproj", "db1")
        assert storage.delete_project("myproj") is True
        assert storage.list_projects() == []

    def test_delete_nonexistent_project(self, storage):
        assert storage.delete_project("nope") is False

    def test_execute_query(self, storage, tmp_data):
        (tmp_data / "p").mkdir()
        storage.create_database("p", "db")
        result = storage.execute_query(
            "p", "db",
            "CREATE TABLE t (id INTEGER, name VARCHAR); "
            "INSERT INTO t VALUES (1, 'Alice'), (2, 'Bob');",
            read_only=False,
        )
        assert result["success"] is True

        result = storage.execute_query("p", "db", "SELECT * FROM t ORDER BY id")
        assert result["success"] is True
        assert result["columns"] == ["id", "name"]
        assert result["rows"] == [[1, "Alice"], [2, "Bob"]]
        assert result["row_count"] == 2

    def test_query_nonexistent_database(self, storage):
        result = storage.execute_query("no", "no", "SELECT 1")
        assert result["success"] is False
        assert "not found" in result["error"].lower()

    def test_query_syntax_error(self, storage, tmp_data):
        (tmp_data / "p").mkdir()
        storage.create_database("p", "db")
        result = storage.execute_query("p", "db", "SELCT FRO nonexistent")
        assert result["success"] is False

    def test_get_table_info(self, storage, tmp_data):
        (tmp_data / "p").mkdir()
        storage.create_database("p", "db")
        storage.execute_query(
            "p", "db",
            "CREATE TABLE users (id INTEGER, name VARCHAR)",
            read_only=False,
        )
        info = storage.get_table_info("p", "db")
        assert info["success"] is True
        assert len(info["tables"]) == 1
        assert info["tables"][0]["name"] == "users"

    def test_import_export_csv(self, storage, tmp_data):
        (tmp_data / "p").mkdir()
        storage.create_database("p", "db")

        # Write CSV
        csv_file = tmp_data / "data.csv"
        csv_file.write_text("id,name\n1,Alice\n2,Bob\n")

        result = storage.import_csv("p", "db", "people", csv_file)
        assert result["success"] is True

        result = storage.execute_query("p", "db", "SELECT * FROM people ORDER BY id")
        assert result["rows"] == [[1, "Alice"], [2, "Bob"]]

        # Export
        out = tmp_data / "out.csv"
        result = storage.export_csv("p", "db", "people", out)
        assert result["success"] is True
        assert out.exists()
        assert "Alice" in out.read_text()

    def test_import_export_parquet(self, storage, tmp_data):
        (tmp_data / "p").mkdir()
        storage.create_database("p", "db")

        # Create Parquet file
        pq_file = tmp_data / "data.parquet"
        con = duckdb.connect()
        con.execute(
            "CREATE TABLE t (id INTEGER, name VARCHAR, score DOUBLE)"
        )
        con.execute("INSERT INTO t VALUES (1, 'Alice', 95.5), (2, 'Bob', 87.3)")
        con.execute(f"COPY t TO '{pq_file}' (FORMAT PARQUET)")
        con.close()

        result = storage.import_parquet("p", "db", "people", pq_file)
        assert result["success"] is True

        result = storage.execute_query("p", "db", "SELECT * FROM people ORDER BY id")
        assert result["rows"] == [[1, "Alice", 95.5], [2, "Bob", 87.3]]

        # Export
        out = tmp_data / "out.parquet"
        result = storage.export_parquet("p", "db", "people", out)
        assert result["success"] is True
        assert out.exists()

        result = duckdb.sql(f"SELECT * FROM read_parquet('{out}') ORDER BY id").fetchall()
        assert result == [(1, "Alice", 95.5), (2, "Bob", 87.3)]

    def test_import_export_json(self, storage, tmp_data):
        (tmp_data / "p").mkdir()
        storage.create_database("p", "db")

        # Write JSON
        json_file = tmp_data / "data.json"
        rows = [
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"},
        ]
        json_file.write_text(json.dumps(rows))

        result = storage.import_json("p", "db", "people", json_file)
        assert result["success"] is True

        result = storage.execute_query("p", "db", "SELECT * FROM people ORDER BY id")
        assert len(result["rows"]) == 2
        assert result["rows"][0][1] == "Alice"
        assert result["rows"][1][1] == "Bob"

        # Export
        out = tmp_data / "out.json"
        result = storage.export_json("p", "db", "people", out)
        assert result["success"] is True
        assert out.exists()

        exported = json.loads(out.read_text())
        assert len(exported) == 2
        assert exported[0]["name"] == "Alice"

    def test_import_parquet_missing_file(self, storage, tmp_data):
        (tmp_data / "p").mkdir()
        storage.create_database("p", "db")
        result = storage.import_parquet("p", "db", "t", tmp_data / "nope.parquet")
        assert result["success"] is False

    def test_import_json_missing_file(self, storage, tmp_data):
        (tmp_data / "p").mkdir()
        storage.create_database("p", "db")
        result = storage.import_json("p", "db", "t", tmp_data / "nope.json")
        assert result["success"] is False

    def test_import_data_dispatch(self, storage, tmp_data):
        (tmp_data / "p").mkdir()
        storage.create_database("p", "db")

        # CSV dispatch
        csv_file = tmp_data / "d.csv"
        csv_file.write_text("id,name\n1,Alice\n")
        result = storage.import_data("p", "db", "t_csv", csv_file)
        assert result["success"] is True

        # Parquet dispatch
        pq_file = tmp_data / "d.parquet"
        con = duckdb.connect()
        con.execute("CREATE TABLE t AS SELECT 1 AS id, 'Bob' AS name")
        con.execute(f"COPY t TO '{pq_file}' (FORMAT PARQUET)")
        con.close()
        result = storage.import_data("p", "db", "t_pq", pq_file)
        assert result["success"] is True

        # JSON dispatch
        json_file = tmp_data / "d.json"
        json_file.write_text(json.dumps([{"id": 3, "name": "Charlie"}]))
        result = storage.import_data("p", "db", "t_json", json_file)
        assert result["success"] is True

    def test_detect_format(self):
        from pathlib import Path

        from webduck.storage.engine import StorageEngine
        assert StorageEngine.detect_format(Path("data.csv")) == "csv"
        assert StorageEngine.detect_format(Path("data.tsv")) == "csv"
        assert StorageEngine.detect_format(Path("data.txt")) == "csv"
        assert StorageEngine.detect_format(Path("data.parquet")) == "parquet"
        assert StorageEngine.detect_format(Path("data.json")) == "json"
        assert StorageEngine.detect_format(Path("data.jsonl")) == "json"
        assert StorageEngine.detect_format(Path("data.ndjson")) == "json"
        assert StorageEngine.detect_format(Path("data.unknown")) == "csv"

    def test_list_projects_finds_dirs(self, storage, tmp_data):
        (tmp_data / "alpha").mkdir()
        (tmp_data / "beta").mkdir()
        (tmp_data / ".hidden").mkdir()
        (tmp_data / "file.txt").touch()
        assert sorted(storage.list_projects()) == ["alpha", "beta"]

    def test_compact_database_with_foreign_keys(self, storage, tmp_data):
        (tmp_data / "p").mkdir()
        storage.create_database("p", "db")

        # Tables with foreign keys referencing each other. COPY FROM DATABASE
        # copies tables in arbitrary order and trips FK checks on valid data
        # (duckdb#16785); the engine must order tables so parents come first.
        storage.execute_query(
            "p", "db",
            "CREATE TABLE departments (dept_id INTEGER PRIMARY KEY, name VARCHAR); "
            "CREATE TABLE projects (project_id INTEGER PRIMARY KEY, "
            "dept_id INTEGER, FOREIGN KEY (dept_id) REFERENCES departments(dept_id)); "
            "CREATE TABLE tasks (task_id INTEGER PRIMARY KEY, "
            "project_id INTEGER, FOREIGN KEY (project_id) REFERENCES projects(project_id)); "
            "INSERT INTO departments VALUES (1, 'Engineering'); "
            "INSERT INTO projects VALUES (10, 1); "
            "INSERT INTO tasks VALUES (100, 10);",
            read_only=False,
        )

        result = storage.compact_database("p", "db")
        assert result["success"] is True

        # Data survived intact after the compact.
        query = storage.execute_query(
            "p", "db", "SELECT * FROM tasks JOIN projects USING (project_id) "
            "JOIN departments USING (dept_id)"
        )
        assert query["success"] is True
        assert query["row_count"] == 1

    def test_compact_database_missing(self, storage):
        result = storage.compact_database("p", "db")
        assert result["success"] is False
        assert "not found" in result["error"].lower()

    def test_compact_database_self_referential_fk(self, storage, tmp_data):
        (tmp_data / "p").mkdir()
        storage.create_database("p", "db")

        # A self-referential foreign key cannot be populated with a multi-row
        # INSERT in DuckDB (duckdb#7168); the engine must copy such tables
        # row-by-row during compaction.
        storage.execute_query(
            "p", "db",
            "CREATE TABLE emp (id INTEGER PRIMARY KEY, name VARCHAR, "
            "manager_id INTEGER, "
            "FOREIGN KEY (manager_id) REFERENCES emp(id)); "
            "INSERT INTO emp VALUES (1, 'ceo', NULL); "
            "INSERT INTO emp VALUES (2, 'vp', 1); "
            "INSERT INTO emp VALUES (3, 'eng', 2);",
            read_only=False,
        )

        result = storage.compact_database("p", "db")
        assert result["success"] is True

        query = storage.execute_query("p", "db", "SELECT * FROM emp ORDER BY id")
        assert query["success"] is True
        assert query["rows"] == [[1, "ceo", None], [2, "vp", 1], [3, "eng", 2]]

    def test_fragmentation_missing_database(self, storage):
        assert storage.fragmentation("p", "db") is None

    def test_fragmentation_fresh_database(self, storage, tmp_data):
        (tmp_data / "p").mkdir()
        storage.create_database("p", "db")
        storage.execute_query(
            "p", "db",
            "CREATE TABLE t (id INTEGER, val VARCHAR); "
            "INSERT INTO t VALUES (1, 'a'), (2, 'b');",
            read_only=False,
        )
        frag = storage.fragmentation("p", "db")
        assert frag is not None
        assert 0.0 <= frag < 0.5

    def test_fragmentation_after_drop_table(self, storage, tmp_data):
        (tmp_data / "p").mkdir()
        storage.create_database("p", "db")
        storage.execute_query(
            "p", "db",
            "CREATE TABLE big (id INTEGER, val VARCHAR); "
            "INSERT INTO big SELECT i, 'row' || i FROM range(200000) r(i);",
            read_only=False,
        )
        # Dropping a large table frees its blocks; the fragmentation ratio
        # should clearly rise, which is what the compress hint detects.
        storage.execute_query("p", "db", "DROP TABLE big", read_only=False)
        frag = storage.fragmentation("p", "db")
        assert frag is not None
        assert frag >= 0.3


class TestTrash:
    def test_trash_and_restore_database(self, storage, tmp_data):
        (tmp_data / "p").mkdir()
        storage.create_database("p", "db")
        storage.execute_query(
            "p", "db",
            "CREATE TABLE t (id INTEGER); INSERT INTO t VALUES (1)",
            read_only=False,
        )
        assert storage.trash_database("p", "db") is True
        assert storage.database_exists("p", "db") is False

        entries = storage.list_trash()
        assert len(entries) == 1
        assert entries[0]["type"] == "database"
        assert entries[0]["project"] == "p"
        assert entries[0]["database"] == "db"

        result = storage.restore_database(entries[0]["name"])
        assert result["success"] is True
        assert storage.database_exists("p", "db") is True
        # Data survived the round trip.
        query = storage.execute_query("p", "db", "SELECT id FROM t")
        assert query["rows"] == [[1]]
        assert storage.list_trash() == []

    def test_trash_and_restore_project(self, storage, tmp_data):
        (tmp_data / "p").mkdir()
        storage.create_database("p", "db")
        storage.create_project("q")
        assert storage.trash_project("p") is True
        assert storage.list_projects() == ["q"]

        entries = storage.list_trash()
        assert len(entries) == 1
        assert entries[0]["type"] == "project"

        result = storage.restore_project(entries[0]["name"])
        assert result["success"] is True
        assert storage.database_exists("p", "db") is True
        # Restored projects land at the top of the order.
        assert storage.list_projects() == ["p", "q"]

    def test_trash_project_lists_contained_databases(self, storage, tmp_data):
        (tmp_data / "p").mkdir()
        storage.create_database("p", "db1")
        storage.create_database("p", "db2")
        assert storage.trash_project("p") is True

        entries = storage.list_trash()
        assert len(entries) == 1
        assert entries[0]["type"] == "project"
        assert [d["name"] for d in entries[0]["databases"]] == ["db1", "db2"]
        assert all(
            isinstance(d["size"], int) and d["size"] > 0
            for d in entries[0]["databases"]
        )

        # Database trash entries carry an empty list.
        storage.create_project("q")
        storage.create_database("q", "dbx")
        assert storage.trash_database("q", "dbx") is True
        db_entries = [e for e in storage.list_trash() if e["type"] == "database"]
        assert db_entries[0]["databases"] == []

    def test_trash_project_strips_credentials(self, storage, project_auth, tmp_data):
        (tmp_data / "p").mkdir()
        storage.create_database("p", "db")
        project_auth.set_database_password("p", "db", "secret", "write")
        assert storage.trash_project("p") is True
        # The trashed copy must not carry any stored credentials.
        entries = storage.list_trash()
        trash_proj = storage.trash_dir / entries[0]["name"]
        assert not (trash_proj / ".project.json").exists()

    def test_trash_restore_conflict(self, storage, tmp_data):
        (tmp_data / "p").mkdir()
        storage.create_database("p", "db")
        storage.execute_query(
            "p", "db",
            "CREATE TABLE t (id INTEGER); INSERT INTO t VALUES (1)",
            read_only=False,
        )
        assert storage.trash_database("p", "db") is True
        storage.create_database("p", "db")
        storage.execute_query(
            "p", "db",
            "CREATE TABLE t (id INTEGER); INSERT INTO t VALUES (2)",
            read_only=False,
        )

        entries = storage.list_trash()
        result = storage.restore_database(entries[0]["name"])
        assert result["success"] is False
        assert result["conflict"] is True

        # Overwrite: the live database moves to the trash, the trashed copy
        # takes its place — nothing is permanently deleted.
        result = storage.restore_database(entries[0]["name"], overwrite=True)
        assert result["success"] is True
        query = storage.execute_query("p", "db", "SELECT id FROM t")
        assert query["rows"] == [[1]]

        trash = storage.list_trash()
        assert len(trash) == 1
        assert trash[0]["database"] == "db"

    def test_empty_trash(self, storage, tmp_data):
        (tmp_data / "p").mkdir()
        storage.create_database("p", "db")
        storage.create_project("q")
        storage.create_database("q", "db2")
        storage.trash_database("p", "db")
        storage.trash_project("q")
        assert len(storage.list_trash()) == 2
        assert storage.empty_trash() == 2
        assert storage.list_trash() == []
        assert not storage.trash_dir.exists()

    def test_delete_single_trash_entry(self, storage, tmp_data):
        (tmp_data / "p").mkdir()
        storage.create_database("p", "db")
        storage.create_project("q")
        storage.create_database("q", "db2")
        storage.trash_database("p", "db")
        storage.trash_project("q")

        entries = storage.list_trash()
        db_entry = [e for e in entries if e["type"] == "database"][0]
        assert storage.delete_trash_entry(db_entry["name"]) is True
        assert storage.delete_trash_entry(db_entry["name"]) is False
        assert len(storage.list_trash()) == 1
        assert storage.list_trash()[0]["type"] == "project"

    def test_delete_single_trash_entry_missing_is_false(self, storage, tmp_data):
        (tmp_data / "p").mkdir()
        assert storage.delete_trash_entry("nonexistent") is False

    def test_trash_database_recreates_missing_project(self, storage, tmp_data):
        (tmp_data / "p").mkdir()
        storage.create_database("p", "db")
        assert storage.trash_database("p", "db") is True
        # The project disappears entirely afterwards (edge case).
        import shutil
        shutil.rmtree(tmp_data / "p")

        entries = storage.list_trash()
        result = storage.restore_database(entries[0]["name"])
        assert result["success"] is True
        assert storage.database_exists("p", "db") is True
        assert "p" in storage.list_projects()

    def test_trash_dir_not_listed_as_project(self, storage, tmp_data):
        (tmp_data / "p").mkdir()
        storage.create_database("p", "db")
        storage.trash_database("p", "db")
        assert storage.list_projects() == ["p"]

    def test_create_project_trash_name_blocked(self, storage, tmp_data):
        assert storage.create_project("trash") is False


class TestTrafficCounter:
    def test_record_increments_series(self, storage):
        assert storage.db_access_series(60, 2) == [0] * 30
        storage.record_db_access()
        storage.record_db_access()
        series = storage.db_access_series(60, 2)
        assert sum(series) == 2
        assert all(v >= 0 for v in series)

    def test_bucket_distribution(self, storage):
        storage.record_db_access()
        series = storage.db_access_series(60, 2)
        assert series[-1] == 1
        assert sum(series[:-1]) == 0

    def test_old_events_pruned(self, storage):
        import time

        with storage._traffic_lock:
            storage._db_access_events.clear()
            storage._db_access_events.append(time.monotonic() - 65.0)
        # Access older than the window must not be counted.
        assert storage.db_access_series(60, 2) == [0] * 30
        # record_db_access prunes stale entries from the deque.
        storage.record_db_access()
        with storage._traffic_lock:
            assert len(storage._db_access_events) == 1

    def test_gui_traffic_not_counted(self, storage, tmp_data):
        (tmp_data / "p").mkdir()
        storage.create_database("p", "db")
        # GUI-style engine use never calls record_db_access().
        result = storage.execute_query("p", "db", "SELECT 1")
        assert result["success"] is True
        assert storage.db_access_series(60, 2) == [0] * 30
