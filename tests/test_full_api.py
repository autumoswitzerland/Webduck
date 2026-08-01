"""Full E2E REST API test client for WebDuck.

Tests run against a LIVE server so you can verify results in the GUI.

Usage:
  1. Start server:  webduck start
  2. Run tests:     pytest tests/test_full_api.py -s --interactive

  By default, tests connect to:
     http://127.0.0.1:8998

  Or specify another server:
     pytest tests/test_full_api.py -s --server-url http://127.0.0.1:8998
"""

import csv
import json
import threading
import time

import duckdb
import httpx
import pytest

# ---------------------------------------------------------------------------
# HTTP client for live server
# ---------------------------------------------------------------------------

class ServerClient:
    """Sends real HTTP requests to a running WebDuck server."""

    def __init__(self, base_url: str):
        self._base = base_url.rstrip("/")
        self.base_url = self._base
        self._http = httpx.Client(base_url=self._base, timeout=30)

    def get(self, path, **kw):
        r = self._http.get(path, **kw)
        return FakeResp(r)

    def post(self, path, json=None, params=None, headers=None, **kw):
        r = self._http.post(path, json=json, params=params, headers=headers, **kw)
        return FakeResp(r)

    def put(self, path, json=None, headers=None, **kw):
        r = self._http.put(path, json=json, headers=headers, **kw)
        return FakeResp(r)

    def delete(self, path, headers=None, **kw):
        r = self._http.delete(path, headers=headers, **kw)
        return FakeResp(r)


class FakeResp:
    """Wrap httpx.Response to match TestClient's API."""
    def __init__(self, resp):
        self._r = resp
        self.status_code = resp.status_code
    def json(self):
        return self._r.json()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _h(token):
    return {"Authorization": f"Bearer {token}"}

def _k(project, password):
    return {"X-Project-Key": f"{project}:{password}"}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client(request):
    """Return a ServerClient pointing at a running WebDuck server.

    If --server-url is omitted, the default server URL is checked.
    """

    url = request.config.getoption("--server-url")

    if not url:
        url = "http://127.0.0.1:8998"

    try:
        response = httpx.get(
            f"{url.rstrip('/')}/health",
            timeout=2.0,
        )

        if response.status_code != 200:
            pytest.skip(
                f"WebDuck server is not available at {url} "
                f"(HTTP {response.status_code})"
            )

    except httpx.RequestError:
        pytest.skip(
            f"\n"
            f"WebDuck server is not running at {url}.\n"
            f"Start it with:\n"
            f"  webduck start\n"
            f"\n"
            f"Or specify another server:\n"
            f"  pytest tests/test_full_api.py -s "
            f"--server-url http://127.0.0.1:8998"
        )

    return ServerClient(url)


@pytest.fixture
def csv_file(tmp_path):
    """Write a small CSV file for import tests."""
    p = tmp_path / "test_data.csv"
    with open(p, "w", newline="") as f:
        csv.writer(f).writerows([
            ["id", "name", "score"],
            ["1", "Alice", "95.5"],
            ["2", "Bob", "87.3"],
            ["3", "Charlie", "91.0"],
        ])
    return p


@pytest.fixture
def parquet_file(tmp_path):
    """Write a small Parquet file for import tests."""
    p = tmp_path / "test_data.parquet"
    con = duckdb.connect()
    con.execute("CREATE TABLE t (id INTEGER, name VARCHAR, score DOUBLE)")
    con.execute("INSERT INTO t VALUES (1, 'Alice', 95.5), (2, 'Bob', 87.3), (3, 'Charlie', 91.0)")
    con.execute(f"COPY t TO '{p}' (FORMAT PARQUET)")
    con.close()
    return p


@pytest.fixture
def json_file(tmp_path):
    """Write a small JSON file for import tests."""
    p = tmp_path / "test_data.json"
    rows = [
        {"id": 1, "name": "Alice", "score": 95.5},
        {"id": 2, "name": "Bob", "score": 87.3},
        {"id": 3, "name": "Charlie", "score": 91.0},
    ]
    with open(p, "w") as f:
        json.dump(rows, f)
    return p


# ---------------------------------------------------------------------------
#  Step printer
# ---------------------------------------------------------------------------

_n = 0

def step(msg, interactive):
    global _n
    _n += 1
    line = f"--- Step {_n}: {msg} ---"
    print(f"\n{'=' * len(line)}")
    print(line)
    print(f"{'=' * len(line)}")
    if interactive:
        input("Press ENTER to continue...")


# ===========================================================================
#  1. LOGIN
# ===========================================================================

class TestLogin:
    def test_login(self, client, request):
        ia = request.config.getoption("--interactive")
        step("Login as admin", ia)

        resp = client.post("/admin/login", json={"username": "admin", "password": "admin"})
        assert resp.status_code == 200
        token = resp.json()["token"]
        assert len(token) > 20
        print(f"  Token: {token[:30]}...")
        # Store token for later tests — not possible via fixture, so we use globals
        _store_token(token)

    def test_login_wrong_password(self, client, request):
        ia = request.config.getoption("--interactive")
        step("Login with wrong password (expect 401)", ia)

        resp = client.post("/admin/login", json={"username": "admin", "password": "falsch"})
        assert resp.status_code == 401
        print("  Correctly rejected")

    def test_login_nonexistent(self, client, request):
        ia = request.config.getoption("--interactive")
        step("Login with nonexistent user (expect 401)", ia)

        resp = client.post("/admin/login", json={"username": "nobody", "password": "x"})
        assert resp.status_code == 401
        print("  Correctly rejected")

    def test_admin_no_token(self, client, request):
        ia = request.config.getoption("--interactive")
        step("Admin endpoint without JWT (expect 401)", ia)

        resp = client.get("/admin/projects")
        assert resp.status_code in (401, 403)
        print("  Correctly rejected")


# ---------------------------------------------------------------------------
#  Token storage — shared across tests in live mode
# ---------------------------------------------------------------------------

_TOKEN = None

def _store_token(t):
    global _TOKEN
    _TOKEN = t

def _get_token():
    return _TOKEN

def _auth():
    return _h(_get_token())


# ===========================================================================
#  2. PROJECTS
# ===========================================================================

class TestProjects:
    def test_create_projects(self, client, request):
        ia = request.config.getoption("--interactive")
        step("Create 3 projects: alpha, beta, gamma", ia)

        for name in ["alpha", "beta", "gamma"]:
            resp = client.post("/admin/projects", json={"name": name}, headers=_auth())
            assert resp.status_code == 200
            print(f"  Created '{name}'")

        resp = client.get("/admin/projects", headers=_auth())
        print(f"  Server lists: {resp.json()}")

    def test_verify_projects_gui(self, client, request):
        ia = request.config.getoption("--interactive")
        step("VERIFY: Check projects in GUI — alpha, beta, gamma visible?", ia)

        resp = client.get("/admin/projects", headers=_auth())
        projects = resp.json()
        assert "alpha" in projects
        assert "beta" in projects
        assert "gamma" in projects
        print(f"  Confirmed: {projects}")

    def test_reorder_projects(self, client, request):
        ia = request.config.getoption("--interactive")
        step("Reorder: gamma -> alpha -> beta", ia)

        resp = client.post(
            "/admin/reorder-projects",
            json={"projects": ["gamma", "alpha", "beta"]},
            headers=_auth(),
        )
        assert resp.status_code == 200

        resp = client.get("/admin/projects", headers=_auth())
        print(f"  New order: {resp.json()}")
        assert resp.json() == ["gamma", "alpha", "beta"]

    def test_verify_reorder_gui(self, client, request):
        ia = request.config.getoption("--interactive")
        step("VERIFY: Check order in GUI — gamma first, then alpha, then beta?", ia)
        print("  Visually confirm the order in the sidebar")

    def test_duplicate_project(self, client, request):
        ia = request.config.getoption("--interactive")
        step("Create duplicate project 'alpha' (expect 400)", ia)

        resp = client.post("/admin/projects", json={"name": "alpha"}, headers=_auth())
        assert resp.status_code == 400
        print("  Correctly rejected")


# ===========================================================================
#  3. DATABASES
# ===========================================================================

class TestDatabases:
    def test_create_databases(self, client, request):
        ia = request.config.getoption("--interactive")
        step("Create 2 databases in 'alpha': db_main, analytics", ia)

        for db in ["db_main", "analytics"]:
            resp = client.post(
                "/admin/projects/alpha/databases",
                json={"name": db},
                headers=_auth(),
            )
            assert resp.status_code == 200
            print(f"  Created '{db}'")

    def test_verify_databases_gui(self, client, request):
        ia = request.config.getoption("--interactive")
        step("VERIFY: Check 'alpha' in GUI — db_main + analytics visible?", ia)

        resp = client.get("/admin/projects/alpha/databases", headers=_auth())
        dbs = resp.json()
        assert "db_main" in dbs
        assert "analytics" in dbs
        print(f"  Confirmed: {dbs}")

    def test_duplicate_database(self, client, request):
        ia = request.config.getoption("--interactive")
        step("Create duplicate database 'db_main' (expect 400)", ia)

        resp = client.post(
            "/admin/projects/alpha/databases",
            json={"name": "db_main"},
            headers=_auth(),
        )
        assert resp.status_code == 400
        print("  Correctly rejected")

    def test_reserved_database_name(self, client, request):
        ia = request.config.getoption("--interactive")
        step("Create database with reserved name 'main' (expect 400)", ia)

        resp = client.post(
            "/admin/projects/alpha/databases",
            json={"name": "main"},
            headers=_auth(),
        )
        assert resp.status_code == 400
        print("  Correctly rejected as reserved")


# ===========================================================================
#  4. PASSWORD
# ===========================================================================

class TestPassword:
    def test_set_password(self, client, request):
        ia = request.config.getoption("--interactive")
        step("Set write password for 'db_main' database", ia)

        resp = client.put(
            "/admin/projects/alpha/databases/db_main/password",
            json={"password": "dbpass123", "access_level": "write"},
            headers=_auth(),
        )
        assert resp.status_code == 200
        print("  Password set")

    def test_verify_lock_icon_gui(self, client, request):
        ia = request.config.getoption("--interactive")
        step("VERIFY: Check 'db_main' in GUI — lock icon visible?", ia)
        print("  Visually confirm the lock icon next to 'db_main'")

    def test_query_no_key_rejected(self, client, request):
        ia = request.config.getoption("--interactive")
        step("Query 'db_main' without X-Project-Key (expect 401)", ia)

        resp = client.post(
            "/db/projects/alpha/databases/db_main/query",
            json={"sql": "SELECT 1"},
        )
        assert resp.status_code == 401
        print("  Correctly rejected")

    def test_query_wrong_key_rejected(self, client, request):
        ia = request.config.getoption("--interactive")
        step("Query 'db_main' with wrong password (expect 401)", ia)

        resp = client.post(
            "/db/projects/alpha/databases/db_main/query",
            json={"sql": "SELECT 1"},
            headers=_k("alpha", "falsch"),
        )
        assert resp.status_code == 401
        print("  Correctly rejected")

    def test_query_correct_key(self, client, request):
        ia = request.config.getoption("--interactive")
        step("Query 'db_main' with correct password", ia)

        resp = client.post(
            "/db/projects/alpha/databases/db_main/query",
            json={"sql": "SELECT 42 AS answer"},
            headers=_k("alpha", "dbpass123"),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["rows"] == [[42]]
        print(f"  Result: {data['rows']}")

    def test_open_db_no_password(self, client, request):
        ia = request.config.getoption("--interactive")
        step("Query 'analytics' (no password set, open access)", ia)

        resp = client.post(
            "/db/projects/alpha/databases/analytics/query",
            json={"sql": "SELECT 1 AS x"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        print(f"  Result: {data['rows']}")


# ===========================================================================
#  5. SQL
# ===========================================================================

class TestSQL:
    def test_create_table(self, client, request):
        ia = request.config.getoption("--interactive")
        step("Create table 'employees' with 3 rows", ia)

        resp = client.post(
            "/db/projects/alpha/databases/db_main/write",
            json={
                "sql": (
                    "CREATE TABLE employees ("
                    "id INTEGER, name VARCHAR, department VARCHAR, salary DECIMAL(10,2)"
                    ");"
                    "INSERT INTO employees VALUES (1, 'Alice', 'Engineering', 95000);"
                    "INSERT INTO employees VALUES (2, 'Bob', 'Marketing', 78000);"
                    "INSERT INTO employees VALUES (3, 'Charlie', 'Engineering', 88000);"
                )
            },
            headers=_k("alpha", "dbpass123"),
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        print("  Table created, 3 rows inserted")

    def test_verify_table_gui(self, client, request):
        ia = request.config.getoption("--interactive")
        step("VERIFY: Check in Browse view — 'employees' table with 3 rows visible?", ia)

        resp = client.get(
            "/db/projects/alpha/databases/db_main/tables",
            headers=_k("alpha", "dbpass123"),
        )
        names = [t["name"] for t in resp.json()["tables"]]
        assert "employees" in names
        print(f"  Tables: {names}")

    def test_select_all(self, client, request):
        ia = request.config.getoption("--interactive")
        step("SELECT * FROM employees", ia)

        resp = client.post(
            "/db/projects/alpha/databases/db_main/query",
            json={"sql": "SELECT * FROM employees ORDER BY id"},
            headers=_k("alpha", "dbpass123"),
        )
        data = resp.json()
        assert data["success"] is True
        for r in data["rows"]:
            print(f"  {r}")

    def test_filtered_query(self, client, request):
        ia = request.config.getoption("--interactive")
        step("SELECT Engineering employees only", ia)

        resp = client.post(
            "/db/projects/alpha/databases/db_main/query",
            json={
                "sql": "SELECT name, salary FROM employees "
                        "WHERE department = 'Engineering' ORDER BY salary DESC"
            },
            headers=_k("alpha", "dbpass123"),
        )
        data = resp.json()
        assert data["success"] is True
        assert len(data["rows"]) == 2
        for r in data["rows"]:
            print(f"  {r}")

    def test_create_view(self, client, request):
        ia = request.config.getoption("--interactive")
        step("Create view 'high_earners', then SELECT from it", ia)

        resp = client.post(
            "/db/projects/alpha/databases/db_main/write",
            json={
                "sql": "CREATE OR REPLACE VIEW high_earners AS "
                        "SELECT name, salary FROM employees WHERE salary > 80000;"
            },
            headers=_k("alpha", "dbpass123"),
        )
        assert resp.json()["success"] is True

        resp = client.post(
            "/db/projects/alpha/databases/db_main/query",
            json={"sql": "SELECT * FROM high_earners ORDER BY salary DESC"},
            headers=_k("alpha", "dbpass123"),
        )
        data = resp.json()
        assert data["success"] is True
        for r in data["rows"]:
            print(f"  {r}")

    def test_invalid_sql(self, client, request):
        ia = request.config.getoption("--interactive")
        step("Run invalid SQL (expect error)", ia)

        resp = client.post(
            "/db/projects/alpha/databases/db_main/query",
            json={"sql": "SELCT * FROM nonexistent"},
            headers=_k("alpha", "dbpass123"),
        )
        assert resp.json()["success"] is False
        print(f"  Error: {resp.json()['error']}")


# ===========================================================================
#  6. CSV IMPORT / EXPORT
# ===========================================================================

class TestCSV:
    def test_import_csv(self, client, csv_file, request):
        ia = request.config.getoption("--interactive")
        step(f"Import CSV into 'imported_data' (file: {csv_file})", ia)

        resp = client.post(
            "/db/projects/alpha/databases/db_main/import/imported_data",
            params={"path": str(csv_file)},
            headers=_k("alpha", "dbpass123"),
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        print("  Imported")

    def test_verify_import_gui(self, client, request):
        ia = request.config.getoption("--interactive")
        step("VERIFY: Check in Browse view — 'imported_data' table with 3 rows?", ia)

        resp = client.post(
            "/db/projects/alpha/databases/db_main/query",
            json={"sql": "SELECT * FROM imported_data ORDER BY id"},
            headers=_k("alpha", "dbpass123"),
        )
        data = resp.json()
        assert data["success"] is True
        assert len(data["rows"]) == 3
        for r in data["rows"]:
            print(f"  {r}")

    def test_export_csv(self, client, csv_file, tmp_path, request):
        ia = request.config.getoption("--interactive")
        step("Export 'imported_data' to CSV file", ia)

        export_path = tmp_path / "exported.csv"
        resp = client.get(
            "/db/projects/alpha/databases/db_main/export/imported_data",
            params={"path": str(export_path)},
            headers=_k("alpha", "dbpass123"),
        )
        assert resp.json()["success"] is True
        assert export_path.exists()

        with open(export_path) as f:
            rows = list(csv.reader(f))
        print(f"  Exported {len(rows)} rows (incl. header)")
        for r in rows:
            print(f"  {r}")

    def test_import_nonexistent_file(self, client, request):
        ia = request.config.getoption("--interactive")
        step("Import from missing file (expect error)", ia)

        resp = client.post(
            "/db/projects/alpha/databases/db_main/import/x",
            params={"path": "/no/such/file.csv"},
            headers=_k("alpha", "dbpass123"),
        )
        assert resp.json()["success"] is False
        print(f"  Error: {resp.json().get('error')}")


# ===========================================================================
#  6b. PARQUET IMPORT / EXPORT
# ===========================================================================

class TestParquet:
    def test_import_parquet(self, client, parquet_file, request):
        ia = request.config.getoption("--interactive")
        step(f"Import Parquet into 'imported_parquet' (file: {parquet_file})", ia)

        resp = client.post(
            "/db/projects/alpha/databases/db_main/import/imported_parquet",
            params={"path": str(parquet_file)},
            headers=_k("alpha", "dbpass123"),
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        print("  Imported")

    def test_verify_parquet_import(self, client, request):
        ia = request.config.getoption("--interactive")
        step("VERIFY: Check 'imported_parquet' table has 3 rows?", ia)

        resp = client.post(
            "/db/projects/alpha/databases/db_main/query",
            json={"sql": "SELECT * FROM imported_parquet ORDER BY id"},
            headers=_k("alpha", "dbpass123"),
        )
        data = resp.json()
        assert data["success"] is True
        assert len(data["rows"]) == 3
        for r in data["rows"]:
            print(f"  {r}")

    def test_export_parquet(self, client, tmp_path, request):
        ia = request.config.getoption("--interactive")
        step("Export 'imported_parquet' to Parquet file", ia)

        export_path = tmp_path / "exported.parquet"
        resp = client.get(
            "/db/projects/alpha/databases/db_main/export/imported_parquet",
            params={
                "path": str(export_path),
                "format": "parquet",
            },
            headers=_k("alpha", "dbpass123"),
        )
        assert resp.json()["success"] is True
        assert export_path.exists()

        result = duckdb.sql(f"SELECT * FROM read_parquet('{export_path}') ORDER BY id").fetchall()
        print(f"  Exported {len(result)} rows")
        for r in result:
            print(f"  {r}")

    def test_import_nonexistent_parquet(self, client, request):
        ia = request.config.getoption("--interactive")
        step("Import missing .parquet file (expect error)", ia)

        resp = client.post(
            "/db/projects/alpha/databases/db_main/import/x",
            params={"path": "/no/such/file.parquet"},
            headers=_k("alpha", "dbpass123"),
        )
        assert resp.json()["success"] is False
        print(f"  Error: {resp.json().get('error')}")


# ===========================================================================
#  6c. JSON IMPORT / EXPORT
# ===========================================================================

class TestJSON:
    def test_import_json(self, client, json_file, request):
        ia = request.config.getoption("--interactive")
        step(f"Import JSON into 'imported_json' (file: {json_file})", ia)

        resp = client.post(
            "/db/projects/alpha/databases/db_main/import/imported_json",
            params={"path": str(json_file)},
            headers=_k("alpha", "dbpass123"),
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        print("  Imported")

    def test_verify_json_import(self, client, request):
        ia = request.config.getoption("--interactive")
        step("VERIFY: Check 'imported_json' table has 3 rows?", ia)

        resp = client.post(
            "/db/projects/alpha/databases/db_main/query",
            json={"sql": "SELECT * FROM imported_json ORDER BY id"},
            headers=_k("alpha", "dbpass123"),
        )
        data = resp.json()
        assert data["success"] is True
        assert len(data["rows"]) == 3
        for r in data["rows"]:
            print(f"  {r}")

    def test_export_json(self, client, tmp_path, request):
        ia = request.config.getoption("--interactive")
        step("Export 'imported_json' to JSON file", ia)

        export_path = tmp_path / "exported.json"
        resp = client.get(
            "/db/projects/alpha/databases/db_main/export/imported_json",
            params={"path": str(export_path), "format": "json"},
            headers=_k("alpha", "dbpass123"),
        )
        assert resp.json()["success"] is True
        assert export_path.exists()

        with open(export_path) as f:
            data = json.load(f)
        print(f"  Exported {len(data)} records")
        for r in data:
            print(f"  {r}")

    def test_import_nonexistent_json(self, client, request):
        ia = request.config.getoption("--interactive")
        step("Import missing .json file (expect error)", ia)

        resp = client.post(
            "/db/projects/alpha/databases/db_main/import/x",
            params={"path": "/no/such/file.json"},
            headers=_k("alpha", "dbpass123"),
        )
        assert resp.json()["success"] is False
        print(f"  Error: {resp.json().get('error')}")

class TestPublic:
    def test_list_projects_public(self, client, request):
        ia = request.config.getoption("--interactive")
        step("GET /db/projects (no auth)", ia)

        resp = client.get("/db/projects")
        assert resp.status_code == 200
        print(f"  Projects: {resp.json()}")

    def test_list_databases_public(self, client, request):
        ia = request.config.getoption("--interactive")
        step("GET /db/projects/alpha/databases (no auth)", ia)

        resp = client.get("/db/projects/alpha/databases")
        assert resp.status_code == 200
        print(f"  Databases: {resp.json()}")


# ===========================================================================
#  8. CLEANUP — deletes everything, only after visual verification
# ===========================================================================

class TestCleanup:
    def test_delete_database(self, client, request):
        ia = request.config.getoption("--interactive")
        step("DELETE database 'analytics' from 'alpha'", ia)

        resp = client.delete("/admin/projects/alpha/databases/analytics", headers=_auth())
        assert resp.status_code == 200
        print("  Deleted 'analytics'")

    def test_verify_database_deleted_gui(self, client, request):
        ia = request.config.getoption("--interactive")
        step("VERIFY: 'analytics' gone from GUI?", ia)

        resp = client.get("/admin/projects/alpha/databases", headers=_auth())
        assert "analytics" not in resp.json()
        print(f"  Remaining: {resp.json()}")

    def test_delete_project(self, client, request):
        ia = request.config.getoption("--interactive")
        step("DELETE project 'alpha'", ia)

        resp = client.delete("/admin/projects/alpha", headers=_auth())
        assert resp.status_code == 200
        print("  Deleted 'alpha'")

    def test_verify_project_deleted_gui(self, client, request):
        ia = request.config.getoption("--interactive")
        step("VERIFY: 'alpha' gone from GUI?", ia)

        resp = client.get("/admin/projects", headers=_auth())
        assert "alpha" not in resp.json()
        print(f"  Remaining: {resp.json()}")

    def test_delete_remaining(self, client, request):
        ia = request.config.getoption("--interactive")
        step("DELETE remaining projects: beta, gamma", ia)

        for name in ["beta", "gamma"]:
            resp = client.delete(f"/admin/projects/{name}", headers=_auth())
            if resp.status_code == 200:
                print(f"  Deleted '{name}'")
            else:
                print(f"  '{name}' not found (already gone)")

        resp = client.get("/admin/projects", headers=_auth())
        print(f"  All projects: {resp.json()}")


# ===========================================================================
#  9. HEALTH
# ===========================================================================

class TestHealth:
    def test_health(self, client, request):
        ia = request.config.getoption("--interactive")
        step("GET /health", ia)
        resp = client.get("/health")
        assert resp.status_code == 200
        print(f"  {resp.json()}")


# ===========================================================================
#  10. CONCURRENCY — parallel reads over HTTP must overlap
# ===========================================================================
#  Proves the RW-lock + asyncio.to_thread path end-to-end: concurrent
#  /query requests to the same database run in parallel (wall time ≈ one
#  query instead of N). Self-contained: creates its own project/db so it
#  works regardless of test ordering, and cleans up afterwards.

class TestConcurrency:
    def test_parallel_reads_over_http(self, client, request):
        ia = request.config.getoption("--interactive")
        step("Parallel /query reads must overlap (RW-lock + to_thread)", ia)

        # Self-contained setup (idempotent: delete leftover project first)
        if _get_token() is None:
            r = client.post(
                "/admin/login", json={"username": "admin", "password": "admin"}
            )
            assert r.status_code == 200
            _store_token(r.json()["token"])
        client.delete("/admin/projects/conc", headers=_auth())
        resp = client.post("/admin/projects", json={"name": "conc"}, headers=_auth())
        assert resp.status_code == 200
        resp = client.post(
            "/admin/projects/conc/databases",
            json={"name": "conc_db"},
            headers=_auth(),
        )
        assert resp.status_code == 200

        url = client.base_url + "/db/projects/conc/databases/conc_db/query"
        payload = {"sql": "SELECT count(*) FROM range(200000000)"}

        def one():
            with httpx.Client(timeout=60) as http:
                r = http.post(url, json=payload)
            assert r.status_code == 200, r.text
            assert r.json()["success"]

        one()  # warm up (also verifies the DB is reachable)

        t0 = time.perf_counter()
        for _ in range(3):
            one()
        t_seq = time.perf_counter() - t0

        t0 = time.perf_counter()
        threads = [threading.Thread(target=one) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        t_par = time.perf_counter() - t0

        print(f"  3 sequential: {t_seq:.3f}s   3 parallel: {t_par:.3f}s")
        assert t_par < 0.75 * t_seq, (
            f"parallel reads did NOT overlap: "
            f"t_par={t_par:.3f}s vs 0.75*t_seq={0.75 * t_seq:.3f}s"
        )
        print("  Parallel reads overlap — RW-lock works over HTTP")

        client.delete("/admin/projects/conc", headers=_auth())
