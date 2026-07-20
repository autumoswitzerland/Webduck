"""Tests for webduck.storage.engine."""




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

    def test_list_projects_finds_dirs(self, storage, tmp_data):
        (tmp_data / "alpha").mkdir()
        (tmp_data / "beta").mkdir()
        (tmp_data / ".hidden").mkdir()
        (tmp_data / "file.txt").touch()
        assert sorted(storage.list_projects()) == ["alpha", "beta"]
