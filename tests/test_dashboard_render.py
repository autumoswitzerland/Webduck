"""Smoke test: dashboard page renders with the new cards, chart, and table."""

import pytest


@pytest.mark.asyncio
async def test_dashboard_renders(create_user, tmp_data):
    from webduck.config import AuthConfig, ServerConfig, WebDuckConfig
    from webduck.main import _auth, _project_auth, _storage, setup_app
    from webduck.pages import dashboard as dashboard_page
    from webduck.pages import login as login_page
    from webduck.pages.context import init_context

    cfg = WebDuckConfig(
        server=ServerConfig(data_dir=tmp_data),
        auth=AuthConfig(jwt_secret="a" * 48),
    )
    setup_app(cfg)
    init_context(cfg, _storage, _auth, _project_auth)
    login_page.register()
    dashboard_page.register()

    _auth.create_user("admin", "admin")

    user = create_user()
    await user.open("/login")
    await user.find("Benutzername").type("admin")
    await user.find("Passwort").type("admin")
    await user.find("Anmelden").click()
    await user.open("/")
    await user.should_see("Traffic-Monitor")
    await user.should_see("Speicher-Übersicht")
    await user.should_see("Projekte")
    await user.should_see("Datenbanken")
