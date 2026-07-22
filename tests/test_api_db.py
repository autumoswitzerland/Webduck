"""Tests for database REST API endpoints."""

import pytest


@pytest.fixture
def setup_db(fastapi_client, auth_token, tmp_data):
    """Create a project, database, and set write password."""
    h = {"Authorization": f"Bearer {auth_token}"}
    fastapi_client.post("/admin/projects", json={"name": "myproj"}, headers=h)
    fastapi_client.post("/admin/projects/myproj/databases", json={"name": "db1"}, headers=h)
    fastapi_client.put(
        "/admin/projects/myproj/databases/db1/password",
        json={"password": "dbpass", "access_level": "write"},
        headers=h,
    )
    return {"X-Project-Key": "myproj:dbpass"}


class TestQuery:
    def test_select(self, fastapi_client, setup_db):
        h = setup_db
        # Create table + insert via write endpoint
        resp = fastapi_client.post(
            "/db/projects/myproj/databases/db1/write",
            json={
                "sql": (
                    "CREATE TABLE t (id INTEGER, val VARCHAR); "
                    "INSERT INTO t VALUES (1, 'hello');"
                ),
            },
            headers=h,
        )
        assert resp.status_code == 200

        # Read via query endpoint
        resp = fastapi_client.post(
            "/db/projects/myproj/databases/db1/query",
            json={"sql": "SELECT * FROM t"},
            headers=h,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["columns"] == ["id", "val"]
        assert data["rows"] == [[1, "hello"]]

    def test_invalid_sql(self, fastapi_client, setup_db):
        resp = fastapi_client.post(
            "/db/projects/myproj/databases/db1/query",
            json={"sql": "SELCT BAD"},
            headers=setup_db,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False

    def test_query_nonexistent_db(self, fastapi_client, setup_db):
        # No password set for "nope" → open access, storage returns error
        resp = fastapi_client.post(
            "/db/projects/myproj/databases/nope/query",
            json={"sql": "SELECT 1"},
            headers=setup_db,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False


class TestWrite:
    def test_ddl_and_dml(self, fastapi_client, setup_db):
        h = setup_db
        resp = fastapi_client.post(
            "/db/projects/myproj/databases/db1/write",
            json={"sql": "CREATE TABLE x (a INTEGER); INSERT INTO x VALUES (42);"},
            headers=h,
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

        resp = fastapi_client.post(
            "/db/projects/myproj/databases/db1/query",
            json={"sql": "SELECT a FROM x"},
            headers=h,
        )
        assert resp.json()["rows"] == [[42]]


class TestUnauthorized:
    def test_no_project_key_no_password(self, fastapi_client):
        # No password set → open access without header
        resp = fastapi_client.post(
            "/db/projects/myproj/databases/db1/query",
            json={"sql": "SELECT 1"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False  # DB doesn't exist

    def test_wrong_password(self, fastapi_client, auth_token):
        h = {"Authorization": f"Bearer {auth_token}"}
        fastapi_client.post("/admin/projects", json={"name": "p"}, headers=h)
        fastapi_client.post("/admin/projects/p/databases", json={"name": "d"}, headers=h)
        fastapi_client.put(
            "/admin/projects/p/databases/d/password",
            json={"password": "correct", "access_level": "write"},
            headers=h,
        )
        resp = fastapi_client.post(
            "/db/projects/p/databases/d/query",
            json={"sql": "SELECT 1"},
            headers={"X-Project-Key": "p:wrong"},
        )
        assert resp.status_code == 401

    def test_password_set_no_header(self, fastapi_client, auth_token):
        h = {"Authorization": f"Bearer {auth_token}"}
        fastapi_client.post("/admin/projects", json={"name": "p2"}, headers=h)
        fastapi_client.post("/admin/projects/p2/databases", json={"name": "d2"}, headers=h)
        fastapi_client.put(
            "/admin/projects/p2/databases/d2/password",
            json={"password": "secret", "access_level": "write"},
            headers=h,
        )
        resp = fastapi_client.post(
            "/db/projects/p2/databases/d2/query",
            json={"sql": "SELECT 1"},
        )
        assert resp.status_code == 401


class TestTables:
    def test_list_tables(self, fastapi_client, setup_db):
        h = setup_db
        fastapi_client.post(
            "/db/projects/myproj/databases/db1/write",
            json={"sql": "CREATE TABLE mytable (id INTEGER, name VARCHAR)"},
            headers=h,
        )
        resp = fastapi_client.get(
            "/db/projects/myproj/databases/db1/tables",
            headers=h,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert any(t["name"] == "mytable" for t in data["tables"])


class TestPublicEndpoints:
    def test_list_projects(self, fastapi_client, auth_token, tmp_data):
        h = {"Authorization": f"Bearer {auth_token}"}
        fastapi_client.post("/admin/projects", json={"name": "p1"}, headers=h)
        resp = fastapi_client.get("/db/projects")
        assert resp.status_code == 200
        assert "p1" in resp.json()

    def test_list_databases(self, fastapi_client, auth_token):
        h = {"Authorization": f"Bearer {auth_token}"}
        fastapi_client.post("/admin/projects", json={"name": "p1"}, headers=h)
        fastapi_client.post("/admin/projects/p1/databases", json={"name": "d1"}, headers=h)
        resp = fastapi_client.get("/db/projects/p1/databases")
        assert resp.status_code == 200
        assert "d1" in resp.json()
