"""SQL Upload integration test — validates DuckDB object lifecycle.

Reads the comprehensive SQL script (duckdb_objects.sql) and executes it
via StorageEngine.execute_queries(), simulating the SQL upload feature.
Verifies all object types are created, can be queried, and are cleaned up.
"""

from pathlib import Path

import pytest

from webduck.storage.engine import StorageEngine

SQL_SCRIPT = Path(__file__).parent / "duckdb_objects.sql"


def _read_sql() -> str:
    return SQL_SCRIPT.read_text()


def _create_phase(sql: str) -> str:
    """Return only the CREATE/INSERT/ALTER portion (before DROPs)."""
    lines = sql.splitlines()
    kept = []
    for line in lines:
        stripped = line.strip().upper()
        if stripped.startswith("-- ── 11. DROP"):
            break
        kept.append(line)
    return "\n".join(kept)


class TestDuckDBObjectUpload:
    """Test all DuckDB object types via SQL upload simulation."""

    @pytest.fixture
    def db_setup(self, storage: StorageEngine):
        """Create project + database, return (project, database) names."""
        storage.create_database("test_upload", "lifecycle")
        return "test_upload", "lifecycle"

    def _query(self, storage, project, database, sql) -> dict:
        return storage.execute_query(project, database, sql)


class TestCreatePhase(TestDuckDBObjectUpload):
    """Verify objects exist after running only the create portion."""

    def _run_create(self, storage, project, database) -> list[dict]:
        sql = _create_phase(_read_sql())
        return storage.execute_queries(project, database, sql)

    def test_all_statements_succeed(self, storage, db_setup):
        project, database = db_setup
        results = self._run_create(storage, project, database)
        failures = [r for r in results if not r.get("success")]
        assert not failures, (
            f"{len(failures)} statement(s) failed:\n"
            + "\n".join(
                f"  [{r.get('sql', '?')[:60]}] → {r.get('error', '?')}"
                for r in failures
            )
        )

    def test_statement_count(self, storage, db_setup):
        project, database = db_setup
        results = self._run_create(storage, project, database)
        assert len(results) >= 20, (
            f"Expected at least 20 statements, got {len(results)}"
        )

    def test_tables_created(self, storage, db_setup):
        project, database = db_setup
        self._run_create(storage, project, database)
        expected = {"employees", "departments", "projects", "tasks", "macro_test_results"}
        res = self._query(
            storage, project, database,
            "SELECT table_name FROM duckdb_tables() "
            "WHERE database_name = 'lifecycle' AND schema_name = 'main'",
        )
        actual = {row[0] for row in res["rows"]}
        missing = expected - actual
        assert not missing, f"Missing tables: {missing}"

    def test_views_created(self, storage, db_setup):
        project, database = db_setup
        self._run_create(storage, project, database)
        expected = {"active_employees", "dept_budget", "employee_summary"}
        res = self._query(
            storage, project, database,
            "SELECT view_name FROM duckdb_views() "
            "WHERE database_name = 'lifecycle' AND schema_name = 'main'",
        )
        actual = {row[0] for row in res["rows"]}
        missing = expected - actual
        assert not missing, f"Missing views: {missing}"

    def test_indexes_created(self, storage, db_setup):
        project, database = db_setup
        self._run_create(storage, project, database)
        expected = {"idx_emp_email", "idx_emp_last", "idx_dept_name"}
        res = self._query(
            storage, project, database,
            "SELECT index_name FROM duckdb_indexes() "
            "WHERE database_name = 'lifecycle'",
        )
        actual = {row[0] for row in res["rows"]}
        missing = expected - actual
        assert not missing, f"Missing indexes: {missing}"

    def test_sequences_created(self, storage, db_setup):
        project, database = db_setup
        self._run_create(storage, project, database)
        res = self._query(
            storage, project, database,
            "SELECT sequence_name FROM duckdb_sequences() "
            "WHERE database_name = 'lifecycle'",
        )
        names = {row[0] for row in res["rows"]}
        assert "seq_counter" in names
        assert "seq_high" in names

    def test_macros_created(self, storage, db_setup):
        project, database = db_setup
        self._run_create(storage, project, database)
        res = self._query(
            storage, project, database,
            "SELECT function_name FROM duckdb_functions() "
            "WHERE database_name = 'lifecycle' AND function_type = 'macro'",
        )
        names = {row[0] for row in res["rows"]}
        for macro in ("double_value", "is_high_salary", "full_name"):
            assert macro in names, f"Macro '{macro}' not found"

    def test_custom_types_created(self, storage, db_setup):
        project, database = db_setup
        self._run_create(storage, project, database)
        res = self._query(
            storage, project, database,
            "SELECT type_name FROM duckdb_types() "
            "WHERE database_name = 'lifecycle' "
            "AND type_name IN ('mood_enum', 'status_enum')",
        )
        names = {row[0] for row in res["rows"]}
        assert "mood_enum" in names
        assert "status_enum" in names


class TestDataIntegrity(TestDuckDBObjectUpload):
    """Verify data after running only the create portion."""

    def _run_create(self, storage, project, database) -> list[dict]:
        sql = _create_phase(_read_sql())
        return storage.execute_queries(project, database, sql)

    def test_employee_count(self, storage, db_setup):
        project, database = db_setup
        self._run_create(storage, project, database)
        res = self._query(storage, project, database, "SELECT COUNT(*) FROM employees")
        assert res["success"]
        assert res["rows"][0][0] == 5

    def test_department_count(self, storage, db_setup):
        project, database = db_setup
        self._run_create(storage, project, database)
        res = self._query(storage, project, database, "SELECT COUNT(*) FROM departments")
        assert res["success"]
        assert res["rows"][0][0] == 4

    def test_project_count(self, storage, db_setup):
        project, database = db_setup
        self._run_create(storage, project, database)
        res = self._query(storage, project, database, "SELECT COUNT(*) FROM projects")
        assert res["success"]
        assert res["rows"][0][0] == 3

    def test_task_count(self, storage, db_setup):
        project, database = db_setup
        self._run_create(storage, project, database)
        res = self._query(storage, project, database, "SELECT COUNT(*) FROM tasks")
        assert res["success"]
        assert res["rows"][0][0] == 4

    def test_view_query(self, storage, db_setup):
        project, database = db_setup
        self._run_create(storage, project, database)
        res = self._query(storage, project, database, "SELECT COUNT(*) FROM active_employees")
        assert res["success"]
        assert res["rows"][0][0] == 5

    def test_macro_double_value(self, storage, db_setup):
        project, database = db_setup
        self._run_create(storage, project, database)
        res = self._query(storage, project, database, "SELECT double_value(21)")
        assert res["success"]
        assert res["rows"][0][0] == 42

    def test_macro_is_high_salary(self, storage, db_setup):
        project, database = db_setup
        self._run_create(storage, project, database)
        res = self._query(storage, project, database, "SELECT is_high_salary(150000)")
        assert res["success"]
        assert res["rows"][0][0] is True
        res = self._query(storage, project, database, "SELECT is_high_salary(50000)")
        assert res["success"]
        assert res["rows"][0][0] is False

    def test_macro_full_name(self, storage, db_setup):
        project, database = db_setup
        self._run_create(storage, project, database)
        res = self._query(storage, project, database, "SELECT full_name('Max', 'Mustermann')")
        assert res["success"]
        assert res["rows"][0][0] == "Max Mustermann"


class TestFullLifecycle(TestDuckDBObjectUpload):
    """Run the entire script (create + drop) and verify cleanup."""

    def test_full_script_succeeds(self, storage, db_setup):
        project, database = db_setup
        results = storage.execute_queries(project, database, _read_sql())
        failures = [r for r in results if not r.get("success")]
        assert not failures, (
            f"{len(failures)} statement(s) failed:\n"
            + "\n".join(
                f"  [{r.get('sql', '?')[:60]}] → {r.get('error', '?')}"
                for r in failures
            )
        )

    def test_all_objects_dropped(self, storage, db_setup):
        project, database = db_setup
        storage.execute_queries(project, database, _read_sql())

        res = self._query(
            storage, project, database,
            "SELECT table_name FROM duckdb_tables() "
            "WHERE database_name = 'lifecycle' AND schema_name = 'main'",
        )
        assert res["success"]
        assert len(res["rows"]) == 0, f"Tables remain: {[r[0] for r in res['rows']]}"

        res = self._query(
            storage, project, database,
            "SELECT view_name FROM duckdb_views() "
            "WHERE database_name = 'lifecycle'",
        )
        assert res["success"]
        assert len(res["rows"]) == 0, f"Views remain: {[r[0] for r in res['rows']]}"

        res = self._query(
            storage, project, database,
            "SELECT index_name FROM duckdb_indexes() "
            "WHERE database_name = 'lifecycle'",
        )
        assert res["success"]
        assert len(res["rows"]) == 0, f"Indexes remain: {[r[0] for r in res['rows']]}"

        res = self._query(
            storage, project, database,
            "SELECT sequence_name FROM duckdb_sequences() "
            "WHERE database_name = 'lifecycle'",
        )
        assert res["success"]
        assert len(res["rows"]) == 0, f"Sequences remain: {[r[0] for r in res['rows']]}"


class TestErrorHandling(TestDuckDBObjectUpload):
    """Test execute_queries behavior on errors and edge cases."""

    def test_stop_on_first_error(self, storage, db_setup):
        project, database = db_setup
        results = storage.execute_queries(
            project, database,
            "CREATE TABLE should_exist (id INTEGER); "
            "INVALID SQL GIBBERISH; "
            "CREATE TABLE should_not_exist (id INTEGER);",
        )
        assert len(results) == 2
        assert results[0]["success"] is True
        assert results[1]["success"] is False

    def test_empty_sql_returns_empty(self, storage, db_setup):
        project, database = db_setup
        results = storage.execute_queries(project, database, "")
        assert results == []

    def test_whitespace_only_sql(self, storage, db_setup):
        project, database = db_setup
        results = storage.execute_queries(project, database, "   \n  \t  ")
        assert results == []
