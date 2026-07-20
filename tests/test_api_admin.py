"""Tests for admin REST API endpoints."""


class TestAdminLogin:
    def test_login_success(self, fastapi_client, shared_auth):
        shared_auth.create_user("admin", "pass123")
        resp = fastapi_client.post(
            "/admin/login",
            json={"username": "admin", "password": "pass123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert data["token_type"] == "bearer"

    def test_login_wrong_password(self, fastapi_client, shared_auth):
        shared_auth.create_user("admin", "pass123")
        resp = fastapi_client.post(
            "/admin/login",
            json={"username": "admin", "password": "wrong"},
        )
        assert resp.status_code == 401

    def test_login_nonexistent_user(self, fastapi_client):
        resp = fastapi_client.post(
            "/admin/login",
            json={"username": "nobody", "password": "pass"},
        )
        assert resp.status_code == 401


class TestProjects:
    def _auth_header(self, token):
        return {"Authorization": f"Bearer {token}"}

    def test_create_project(self, fastapi_client, auth_token):
        resp = fastapi_client.post(
            "/admin/projects",
            json={"name": "myproj"},
            headers=self._auth_header(auth_token),
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_create_duplicate_project(self, fastapi_client, auth_token):
        h = self._auth_header(auth_token)
        fastapi_client.post(
            "/admin/projects", json={"name": "p"}, headers=h,
        )
        resp = fastapi_client.post(
            "/admin/projects", json={"name": "p"}, headers=h,
        )
        assert resp.status_code == 400

    def test_list_projects(self, fastapi_client, auth_token):
        h = self._auth_header(auth_token)
        fastapi_client.post(
            "/admin/projects", json={"name": "a"}, headers=h,
        )
        fastapi_client.post(
            "/admin/projects", json={"name": "b"}, headers=h,
        )
        resp = fastapi_client.get("/admin/projects", headers=h)
        assert resp.status_code == 200
        assert sorted(resp.json()) == ["a", "b"]

    def test_delete_project(self, fastapi_client, auth_token):
        h = self._auth_header(auth_token)
        fastapi_client.post(
            "/admin/projects", json={"name": "p"}, headers=h,
        )
        resp = fastapi_client.delete("/admin/projects/p", headers=h)
        assert resp.status_code == 200

    def test_delete_nonexistent_project(self, fastapi_client, auth_token):
        h = self._auth_header(auth_token)
        resp = fastapi_client.delete("/admin/projects/nope", headers=h)
        assert resp.status_code == 404

    def test_unauthorized_no_token(self, fastapi_client):
        resp = fastapi_client.get("/admin/projects")
        # HTTPBearer returns 401/403 when no credentials
        assert resp.status_code in (401, 403)


class TestDatabases:
    def _auth_header(self, token):
        return {"Authorization": f"Bearer {token}"}

    def test_create_database(self, fastapi_client, auth_token):
        h = self._auth_header(auth_token)
        fastapi_client.post(
            "/admin/projects", json={"name": "p"}, headers=h,
        )
        resp = fastapi_client.post(
            "/admin/projects/p/databases",
            json={"name": "db1"}, headers=h,
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_list_databases(self, fastapi_client, auth_token):
        h = self._auth_header(auth_token)
        fastapi_client.post(
            "/admin/projects", json={"name": "p"}, headers=h,
        )
        fastapi_client.post(
            "/admin/projects/p/databases",
            json={"name": "db1"}, headers=h,
        )
        fastapi_client.post(
            "/admin/projects/p/databases",
            json={"name": "db2"}, headers=h,
        )
        resp = fastapi_client.get(
            "/admin/projects/p/databases", headers=h,
        )
        assert resp.status_code == 200
        assert sorted(resp.json()) == ["db1", "db2"]

    def test_delete_database(self, fastapi_client, auth_token):
        h = self._auth_header(auth_token)
        fastapi_client.post(
            "/admin/projects", json={"name": "p"}, headers=h,
        )
        fastapi_client.post(
            "/admin/projects/p/databases",
            json={"name": "db1"}, headers=h,
        )
        resp = fastapi_client.delete(
            "/admin/projects/p/databases/db1", headers=h,
        )
        assert resp.status_code == 200


class TestPassword:
    def _auth_header(self, token):
        return {"Authorization": f"Bearer {token}"}

    def test_set_database_password(self, fastapi_client, auth_token):
        h = self._auth_header(auth_token)
        fastapi_client.post(
            "/admin/projects", json={"name": "p"}, headers=h,
        )
        fastapi_client.post(
            "/admin/projects/p/databases",
            json={"name": "db1"}, headers=h,
        )
        resp = fastapi_client.put(
            "/admin/projects/p/databases/db1/password",
            json={"password": "secret", "access_level": "write"},
            headers=h,
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True


class TestUsers:
    def _auth_header(self, token):
        return {"Authorization": f"Bearer {token}"}

    def test_list_users(self, fastapi_client, auth_token):
        h = self._auth_header(auth_token)
        resp = fastapi_client.get("/admin/users", headers=h)
        assert resp.status_code == 200
        assert "admin" in resp.json()

    def test_create_user(self, fastapi_client, auth_token):
        resp = fastapi_client.post(
            "/admin/users",
            json={"username": "newuser", "password": "pass123"},
            headers=self._auth_header(auth_token),
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_delete_user(self, fastapi_client, auth_token):
        h = self._auth_header(auth_token)
        fastapi_client.post(
            "/admin/users",
            json={"username": "to_delete", "password": "pass"},
            headers=h,
        )
        resp = fastapi_client.delete(
            "/admin/users/to_delete", headers=h,
        )
        assert resp.status_code == 200

    def test_cannot_delete_self(self, fastapi_client, auth_token):
        h = self._auth_header(auth_token)
        resp = fastapi_client.delete("/admin/users/admin", headers=h)
        assert resp.status_code == 400
