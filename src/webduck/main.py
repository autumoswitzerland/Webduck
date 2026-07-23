# ------------------------------------------------------------------------------
# Copyright (c) 2026 autumo GmbH. All rights reserved.
#
# Licensed under the MIT License. See LICENSE file in the project root for
# full license information.
#
# NOTICE: This file is part of WebDuck. The above copyright notice and this
# permission notice shall be included in all copies or substantial portions
# of this software.
# ------------------------------------------------------------------------------

# =============================================================================
#  WebDuck — Main Application
#  ---------------------------------------------------------------------------
#  Application entry point, CLI commands, and app setup.
#  All UI pages are registered via modules under webduck.pages.
#
#  Project:   WebDuck
#  Author:    autumo GmbH
#  Version:   1.0.0
#  Date:      2026-07-20
# =============================================================================

"""WebDuck - Main application entry point."""

import secrets
import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from nicegui import ui

from webduck.api import admin as admin_api
from webduck.api import db as db_api
from webduck.auth.manager import AuthManager, ProjectAuth
from webduck.config import WebDuckConfig, load_config

# Import theme constants from context (single source of truth)
from webduck.pages.context import (
    BG_CARD,
    BG_DARK,
    BORDER,
    TEXT_DIM,
    TEXT_SOFT,
    YELLOW,
    YELLOW_DARK,
)
from webduck.storage.engine import StorageEngine

# Module-level references (set by setup_app)
_config: WebDuckConfig | None = None
_storage: StorageEngine | None = None
_auth: AuthManager | None = None
_project_auth: ProjectAuth | None = None
_version: str = ""
_icon: str = ""

# CSS theme
_DARK_CSS = f"""
<style>
body {{
    background: {BG_DARK} !important;
    color: {TEXT_SOFT} !important;
}}
html {{
    font-size: 110%;
}}
* {{
    box-shadow: none !important;
}}
.q-page {{
    padding-top: 6px !important;
}}
.q-card {{
    background: {BG_CARD};
    border: 1px solid {BORDER};
}}
.q-card .q-card {{
    background: #1c1c1c;
    border-color: #2a2a2a;
}}
.q-item__label {{
    color: {TEXT_SOFT} !important;
}}
.q-field__label {{
    color: {YELLOW_DARK} !important;
}}
.q-field__control:before {{
    border-color: #333 !important;
}}
.q-field__native::placeholder {{
    color: #777 !important;
    opacity: 1 !important;
}}
.q-field__control {{
    background: #1e1e1e !important;
}}
.q-menu {{
    background: #333 !important;
}}
.q-table {{
    color: {TEXT_SOFT} !important;
}}
.q-table thead tr th {{
    color: {YELLOW} !important;
}}
.q-drawer {{
    background: #1a1a1a !important;
}}
.q-header {{
    border-bottom: 1px solid #2a2a2a !important;
}}
.q-drawer .q-item {{
    padding: 4px 12px !important;
    margin: 1px 0 !important;
    border-radius: 6px !important;
    min-height: 32px !important;
}}
.q-drawer .q-item:hover,
.q-drawer .q-item:focus {{
    border-radius: 6px !important;
}}
.q-btn {{
    border-radius: 8px !important;
    box-shadow: none !important;
}}
.q-btn--flat .q-btn__content {{
    color: {TEXT_SOFT} !important;
}}
.q-btn--outline {{
    border-color: #555 !important;
}}
.q-separator {{
    display: none !important;
}}
.text-caption {{
    color: {TEXT_DIM} !important;
}}
.text-negative {{
    color: #f64337 !important;
    font-weight: bold !important;
}}
.nicegui-error-popup {{
    border-radius: 12px !important;
    border: 1px solid #444 !important;
    background-color: {BG_CARD} !important;
    color: {TEXT_SOFT} !important;
}}
.border-button.q-btn--outline:before {{
    border-color: #333333 !important;
    background-color: #282828 !important;
}}
.q-tooltip {{
    background: #1a1a1a !important;
    color: #c0c0c0 !important;
    font-size: 0.85rem !important;
    border: 1px solid #333 !important;
    border-radius: 6px !important;
}}
</style>
"""


def setup_app(cfg: WebDuckConfig) -> FastAPI:
    """Setup FastAPI application with all routers and static files."""
    global _config, _storage, _auth, _project_auth, _version, _icon

    _config = cfg
    _version = cfg.version
    _icon = cfg.icon

    cfg.server.data_dir.mkdir(parents=True, exist_ok=True)

    _storage = StorageEngine(cfg.server.data_dir)

    _auth = AuthManager(
        cfg.server.data_dir,
        cfg.auth.jwt_secret,
        cfg.auth.jwt_algorithm,
    )

    _project_auth = ProjectAuth(cfg.server.data_dir)

    app = FastAPI(
        title="WebDuck API",
        description="DuckDB-as-a-Service REST API",
        version=cfg.version,
    )

    # Mount static files
    static_dir = Path(__file__).resolve().parent.parent.parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # Include API routers
    app.include_router(admin_api.router)
    app.include_router(db_api.router)

    # Health check endpoint
    @app.get("/health")
    async def health():
        return {"status": "ok"}

    # Redirect root to UI
    from fastapi.responses import RedirectResponse

    @app.get("/")
    async def root():
        return RedirectResponse(url="/ui")

    return app


# --- CLI ---


def main():
    """Main entry point for CLI."""
    import click

    from webduck.config import save_config

    @click.group()
    @click.version_option()
    def cli():
        """WebDuck - A DuckDB server with REST API and Web UI."""
        pass

    @cli.command()
    @click.option(
        "--config", type=click.Path(), default=None,
        help="Config file path",
    )
    def init(config):
        """Initialize WebDuck (create admin user)."""
        config_path = Path(config) if config else Path("webduck.yaml")
        cfg = load_config(config_path)

        click.echo("WebDuck Initialization")
        click.echo("=" * 40)

        username = click.prompt("Admin username")
        password = click.prompt("Admin password", hide_input=True)
        password_confirm = click.prompt(
            "Confirm password", hide_input=True
        )

        if password != password_confirm:
            click.echo("Error: Passwords don't match", err=True)
            sys.exit(1)

        cfg.server.data_dir.mkdir(parents=True, exist_ok=True)

        if "CHANGE-ME" in cfg.auth.jwt_secret:
            cfg.auth.jwt_secret = secrets.token_urlsafe(48)
            click.echo("Generated new JWT secret")

        auth = AuthManager(
            cfg.server.data_dir,
            cfg.auth.jwt_secret,
            cfg.auth.jwt_algorithm,
        )

        if auth.create_user(username, password):
            click.echo(
                f"Admin user '{username}' created successfully"
            )
        else:
            click.echo(
                f"Error: User '{username}' already exists",
                err=True,
            )
            sys.exit(1)

        if not config_path.exists():
            save_config(cfg, config_path)
            click.echo(f"Config saved to {config_path}")

        click.echo("Initialization complete!")

    @cli.command()
    @click.option("--host", default="0.0.0.0", help="Host to bind")
    @click.option(
        "--port", default=8998, type=int, help="Port to listen on"
    )
    @click.option(
        "--config", type=click.Path(), default=None,
        help="Config file path",
    )
    def start(host, port, config):
        """Start the WebDuck server."""
        config_path = Path(config) if config else Path("webduck.yaml")
        cfg = load_config(config_path)

        if host != "0.0.0.0":
            cfg.server.host = host
        if port != 8998:
            cfg.server.port = port

        cfg.server.data_dir.mkdir(parents=True, exist_ok=True)

        from webduck.logging import setup_logging
        setup_logging(
            cfg.server.data_dir,
            enabled=cfg.logging.file.enabled,
            max_size_mb=cfg.logging.file.max_size_mb,
            max_files=cfg.logging.file.max_files,
            query_log=cfg.logging.file.query_log,
            log_dir=cfg.logging.file.log_dir,
            level=cfg.logging.file.level,
            console_enabled=cfg.logging.console.enabled,
        )

        fastapi_app = setup_app(cfg)

        from webduck.pages.context import init_context
        init_context(cfg, _storage, _auth, _project_auth)

        # Register all UI pages
        from webduck.pages import browse as browse_page
        from webduck.pages import dashboard as dashboard_page
        from webduck.pages import import_export as import_export_page
        from webduck.pages import login as login_page
        from webduck.pages import projects as projects_page
        from webduck.pages import query as query_page

        login_page.register()
        dashboard_page.register()
        projects_page.register()
        query_page.register()
        browse_page.register()
        import_export_page.register()

        favicon_path = None
        if cfg.icon:
            candidate = (
                Path(__file__).resolve().parent.parent.parent
                / "static" / cfg.icon
            )
            if candidate.exists() and candidate.suffix == ".svg":
                favicon_path = candidate.read_text()
            elif candidate.exists():
                favicon_path = str(candidate)

        ui.run_with(
            fastapi_app,
            mount_path="/ui",
            storage_secret=cfg.auth.jwt_secret,
            favicon=favicon_path,
        )

        click.echo("")
        click.echo("  WebDuck v" + _version)
        click.echo("  Copyright (c) 2026 autumo GmbH")
        click.echo("  Licensed under the MIT License")
        click.echo("")
        click.echo(
            f"  Listening on  {cfg.server.host}:{cfg.server.port}"
        )
        click.echo(f"  Data directory {cfg.server.data_dir}")
        click.echo("")
        click.echo("  Press Ctrl+C to stop")
        click.echo("")

        uvicorn.run(
            fastapi_app,
            host=cfg.server.host,
            port=cfg.server.port,
            log_level=(
                cfg.logging.console.level
                if cfg.logging.console.enabled
                else "warning"
            ),
            access_log=(
                cfg.logging.console.access_log
                if cfg.logging.console.enabled
                else False
            ),
        )

    @cli.command()
    @click.option(
        "--config", type=click.Path(), default=None,
        help="Config file path",
    )
    def status(config):
        """Show WebDuck status."""
        config_path = Path(config) if config else Path("webduck.yaml")
        cfg = load_config(config_path)

        click.echo("WebDuck Status")
        click.echo("=" * 40)
        click.echo(f"Data directory: {cfg.server.data_dir}")

        if not cfg.server.data_dir.exists():
            click.echo("Data directory does not exist")
            return

        storage = StorageEngine(cfg.server.data_dir)
        projects = storage.list_projects()

        click.echo(f"Projects: {len(projects)}")
        for project in projects:
            databases = storage.list_databases(project)
            click.echo(f"  {project}: {len(databases)} databases")

        auth = AuthManager(
            cfg.server.data_dir,
            cfg.auth.jwt_secret,
            cfg.auth.jwt_algorithm,
        )
        users = auth.list_users()
        click.echo(
            f"Admin users: {', '.join(users) if users else 'none'}"
        )

    cli()


if __name__ == "__main__":
    main()
