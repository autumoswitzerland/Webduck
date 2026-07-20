"""Tests for webduck.auth.manager."""

from webduck.auth.manager import AuthManager


class TestAuthManager:
    def test_create_and_verify_user(self, auth):
        assert auth.create_user("alice", "pass123") is True
        assert auth.verify_user("alice", "pass123") is True

    def test_create_duplicate_user(self, auth):
        auth.create_user("alice", "pass123")
        assert auth.create_user("alice", "other") is False

    def test_verify_wrong_password(self, auth):
        auth.create_user("alice", "pass123")
        assert auth.verify_user("alice", "wrong") is False

    def test_verify_nonexistent_user(self, auth):
        assert auth.verify_user("nobody", "pass") is False

    def test_user_exists(self, auth):
        assert auth.user_exists("alice") is False
        auth.create_user("alice", "pass123")
        assert auth.user_exists("alice") is True

    def test_list_users(self, auth):
        auth.create_user("a", "p")
        auth.create_user("b", "p")
        assert sorted(auth.list_users()) == ["a", "b"]

    def test_delete_user(self, auth):
        auth.create_user("alice", "pass123")
        assert auth.delete_user("alice") is True
        assert auth.user_exists("alice") is False

    def test_delete_nonexistent_user(self, auth):
        assert auth.delete_user("nobody") is False

    def test_jwt_roundtrip(self, auth):
        token = auth.create_jwt_token("admin")
        username = auth.verify_jwt_token(token)
        assert username == "admin"

    def test_jwt_invalid_token(self, auth):
        assert auth.verify_jwt_token("garbage") is None

    def test_users_persist_to_file(self, auth, tmp_data):
        auth.create_user("alice", "pass123")
        # Create a new AuthManager reading the same file
        auth2 = AuthManager(tmp_data, "a" * 48, "HS256")
        assert auth2.verify_user("alice", "pass123") is True


class TestProjectAuth:
    def test_set_and_verify_password(self, project_auth, tmp_data):
        # Create project dir
        (tmp_data / "proj").mkdir()
        assert project_auth.set_database_password("proj", "db1", "secret", "write") is True
        assert project_auth.verify_database_password("proj", "db1", "secret", "write") is True

    def test_wrong_password(self, project_auth, tmp_data):
        (tmp_data / "proj").mkdir()
        project_auth.set_database_password("proj", "db1", "secret", "write")
        assert project_auth.verify_database_password("proj", "db1", "wrong", "write") is False

    def test_read_access_grants_write(self, project_auth, tmp_data):
        """Write access also grants read."""
        (tmp_data / "proj").mkdir()
        project_auth.set_database_password("proj", "db1", "secret", "write")
        assert project_auth.has_database_access("proj", "db1", "secret", "read") is True

    def test_read_does_not_grant_write(self, project_auth, tmp_data):
        (tmp_data / "proj").mkdir()
        project_auth.set_database_password("proj", "db1", "secret", "read")
        assert project_auth.has_database_access("proj", "db1", "secret", "write") is False

    def test_nonexistent_project(self, project_auth):
        assert project_auth.has_database_access("nope", "nope", "pass", "read") is False
