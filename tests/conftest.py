"""Shared test fixtures."""

import sys
import json

import pytest


# ---------------------------------------------------------------------------
#  Colored terminal output — replaces default F/. with speaking messages
# ---------------------------------------------------------------------------

# ANSI color codes
_GREEN = "\033[92m"
_RED = "\033[91m"
_YELLOW = "\033[93m"
_CYAN = "\033[96m"
_BOLD = "\033[1m"
_RESET = "\033[0m"


def pytest_addoption(parser):
    """Add --interactive and --server-url flags for E2E tests."""
    parser.addoption(
        "--interactive",
        action="store_true",
        default=False,
        help="Enable interactive mode: pause after each step for manual inspection",
    )
    parser.addoption(
        "--server-url",
        action="store",
        default=None,
        metavar="URL",
        help="Run tests against a live server (e.g. http://localhost:8998)",
    )


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Replace default F/. output with colored pass/fail messages."""
    outcome = yield
    report = outcome.get_result()

    # Only act on the "call" phase (not setup/teardown)
    if report.when != "call":
        return

    # Print our own colored result line
    test_name = item.name

    if report.passed:
        print(f"  {_GREEN}{_BOLD}PASS{_RESET}  {test_name}")
    elif report.failed:
        print(f"  {_RED}{_BOLD}FAIL{_RESET}  {test_name}")
        if report.longreprtext:
            for line in report.longreprtext.splitlines()[-4:]:
                print(f"         {_RED}{line}{_RESET}")
    elif report.skipped:
        print(f"  {_YELLOW}SKIP{_RESET}  {test_name}")


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """Print a colorful summary at the end."""
    passed = len(terminalreporter.getreports("passed"))
    failed = len(terminalreporter.getreports("failed"))
    total = passed + failed

    print()
    if failed == 0:
        print(f"  {_GREEN}{_BOLD}{passed}/{total} tests passed{_RESET}")
    else:
        print(f"  {_GREEN}{passed} passed{_RESET}  {_RED}{failed} failed{_RESET}  ({total} total)")


# ---------------------------------------------------------------------------
#  LiveClient — sends real HTTP requests to a running WebDuck server
# ---------------------------------------------------------------------------

class LiveClient:
    """Minimal HTTP client that mimics TestClient's .get/.post/.delete API.

    Used when --server-url is provided so tests hit the actual server
    and the user can see results in the browser.
    """

    def __init__(self, base_url: str):
        import httpx
        self._base = base_url.rstrip("/")
        self._http = httpx.Client(base_url=self._base, timeout=30)

    def _url(self, path: str) -> str:
        return path

    def get(self, path: str, **kwargs):
        resp = self._http.get(self._url(path), **kwargs)
        return _FakeResponse(resp)

    def post(self, path: str, json=None, params=None, headers=None, **kwargs):
        resp = self._http.post(
            self._url(path), json=json, params=params, headers=headers, **kwargs,
        )
        return _FakeResponse(resp)

    def delete(self, path: str, headers=None, **kwargs):
        resp = self._http.delete(self._url(path), headers=headers, **kwargs)
        return _FakeResponse(resp)

    def put(self, path: str, json=None, headers=None, **kwargs):
        resp = self._http.put(self._url(path), json=json, headers=headers, **kwargs)
        return _FakeResponse(resp)


class _FakeResponse:
    """Wraps httpx.Response to match TestClient's response API."""

    def __init__(self, resp):
        self._resp = resp
        self.status_code = resp.status_code

    def json(self):
        return self._resp.json()


# ---------------------------------------------------------------------------
#  Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fastapi_client(request, tmp_data, shared_auth, shared_storage):
    """Return either a LiveClient (against running server) or in-memory TestClient."""
    server_url = request.config.getoption("--server-url")
    if server_url:
        print(f"\n  {_CYAN}Live mode{_RESET} → {server_url}")
        return LiveClient(server_url)

    # In-memory mode (default)
    from fastapi.testclient import TestClient
    from webduck.api import admin as admin_api
    from webduck.api import db as db_api
    from webduck.config import AuthConfig, ServerConfig, WebDuckConfig
    from webduck.main import setup_app

    config = WebDuckConfig(
        server=ServerConfig(data_dir=tmp_data),
        auth=AuthConfig(jwt_secret="a" * 48),
    )
    app = setup_app(config)
    admin_api.set_dependencies(shared_auth, shared_storage)
    db_api.set_dependencies(shared_storage)
    return TestClient(app)


@pytest.fixture
def tmp_data(tmp_path):
    """Provide a fresh temporary data directory."""
    return tmp_path


@pytest.fixture
def auth(tmp_data):
    """AuthManager with a temp data dir and a real JWT secret."""
    from webduck.auth.manager import AuthManager
    return AuthManager(tmp_data, "a" * 48, "HS256")


@pytest.fixture
def storage(tmp_data):
    """StorageEngine with a temp data dir."""
    from webduck.storage.engine import StorageEngine
    return StorageEngine(tmp_data)


@pytest.fixture
def project_auth(tmp_data):
    """ProjectAuth with a temp data dir."""
    from webduck.auth.manager import ProjectAuth
    return ProjectAuth(tmp_data)


@pytest.fixture
def config(tmp_data):
    """WebDuckConfig pointing at the temp data dir."""
    from webduck.config import AuthConfig, ServerConfig, WebDuckConfig
    return WebDuckConfig(
        server=ServerConfig(data_dir=tmp_data),
        auth=AuthConfig(jwt_secret="a" * 48),
    )


@pytest.fixture
def shared_auth(tmp_data):
    """A single AuthManager shared between test code and the API."""
    from webduck.auth.manager import AuthManager
    return AuthManager(tmp_data, "a" * 48, "HS256")


@pytest.fixture
def shared_storage(tmp_data):
    """A single StorageEngine shared between test code and the API."""
    from webduck.storage.engine import StorageEngine
    return StorageEngine(tmp_data)


@pytest.fixture
def auth_token(shared_auth):
    """Create an admin user and return a valid JWT token."""
    shared_auth.create_user("admin", "admin")
    return shared_auth.create_jwt_token("admin")
