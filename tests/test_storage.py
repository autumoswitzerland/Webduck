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
