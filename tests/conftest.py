"""Shared test fixtures."""


import pytest
from fastapi.testclient import TestClient

from webduck.api import admin as admin_api
from webduck.api import db as db_api
from webduck.auth.manager import AuthManager, ProjectAuth
from webduck.config import AuthConfig, ServerConfig, WebDuckConfig
from webduck.main import setup_app
from webduck.storage.engine import StorageEngine


@pytest.fixture
def tmp_data(tmp_path):
    """Provide a fresh temporary data directory."""
    return tmp_path


@pytest.fixture
def auth(tmp_data):
    """AuthManager with a temp data dir and a real JWT secret."""
    return AuthManager(tmp_data, "a" * 48, "HS256")


@pytest.fixture
def storage(tmp_data):
    """StorageEngine with a temp data dir."""
    return StorageEngine(tmp_data)


@pytest.fixture
def project_auth(tmp_data):
    """ProjectAuth with a temp data dir."""
    return ProjectAuth(tmp_data)


@pytest.fixture
def config(tmp_data):
    """WebDuckConfig pointing at the temp data dir."""
    return WebDuckConfig(
        server=ServerConfig(data_dir=tmp_data),
        auth=AuthConfig(jwt_secret="a" * 48),
    )


@pytest.fixture
def shared_auth(tmp_data):
    """A single AuthManager shared between test code and the API."""
    return AuthManager(tmp_data, "a" * 48, "HS256")


@pytest.fixture
def shared_storage(tmp_data):
    """A single StorageEngine shared between test code and the API."""
    return StorageEngine(tmp_data)


@pytest.fixture
def fastapi_client(tmp_data, shared_auth, shared_storage):
    """TestClient wrapping the full FastAPI app.

    Injects shared_auth and shared_storage into the API modules
    so the test code and the API use the same instances.
    """
    config = WebDuckConfig(
        server=ServerConfig(data_dir=tmp_data),
        auth=AuthConfig(jwt_secret="a" * 48),
    )
    app = setup_app(config)
    # Override with shared instances
    admin_api.set_dependencies(shared_auth, shared_storage)
    db_api.set_dependencies(shared_storage)
    return TestClient(app)


@pytest.fixture
def auth_token(shared_auth):
    """Create an admin user and return a valid JWT token."""
    shared_auth.create_user("admin", "secret123")
    return shared_auth.create_jwt_token("admin")
