# ------------------------------------------------------------------------------
# Copyright (c) 2026 autumo GmbH. All rights reserved.
#
# Licensed under the GNU Affero General Public License v3.0 (AGPLv3).
# See LICENSE file in the project root for full license information.
#
# This file is part of WebDuck. WebDuck is free software: you can redistribute
# it and/or modify it under the terms of the GNU Affero General Public License
# as published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
# ------------------------------------------------------------------------------

# =============================================================================
#  WebDuck — Main Application
#  ---------------------------------------------------------------------------
#  Application entry point, CLI commands, and app setup.
#  All UI pages are registered via modules under webduck.pages.
#
#  Startup sequence (``start`` command):
#    1. Load YAML config via ``load_config()``.
#    2. Override host/port if CLI flags differ from config defaults.
#    3. Ensure the data directory exists.
#    4. Initialise rotating file logger (``setup_logging()``).
#    5. Build the FastAPI app (``setup_app()``) — creates StorageEngine,
#       AuthManager, mounts static files, registers REST routers.
#    6. Initialise the page context singleton with shared services.
#    7. Register all NiceGUI pages (login, dashboard, projects, …).
#    8. Hand off to ``ui.run_with()`` which wraps FastAPI and starts uvicorn.
#
#  Project:   WebDuck
#  Author:    autumo GmbH
#  Date:      2026-07-20
# =============================================================================

"""WebDuck - Main application entry point.

This module is the central orchestrator.  It wires together FastAPI (REST),
NiceGUI (Web UI), DuckDB storage, and authentication into a single process
served on one port.  The ``main()`` function exposes three CLI commands:

* ``webduck init``  — create the first admin user and write a config file.
* ``webduck start`` — boot the full server (FastAPI + NiceGUI + uvicorn).
* ``webduck status`` — print project/database/user counts from the data dir.
"""

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

# ---------------------------------------------------------------------------
# Module-level singletons — populated once by setup_app() / start command.
# Kept at module level so page modules can import them via the context
# singleton rather than passing references through every function call.
# ---------------------------------------------------------------------------
_config: WebDuckConfig | None = None
_storage: StorageEngine | None = None
_auth: AuthManager | None = None
_project_auth: ProjectAuth | None = None
_version: str = ""
_icon: str = ""

# In-memory store for pending exports: token -> Path.
_export_tokens: dict[str, Path] = {}

# Max number of saved queries per user per database (query history).
QUERY_HISTORY_MAX = 20

# Fragmentation threshold (free_blocks / total_blocks) above which the
# compress icon lights up amber to suggest a database compaction. Only
# databases at least COMPRESS_MIN_DB_SIZE bytes in size are considered, as
# compacting small databases is not worth the effort.
COMPRESS_FRAGMENTATION_THRESHOLD = 0.20
COMPRESS_MIN_DB_SIZE = 10 * 1000 * 1000

# ---------------------------------------------------------------------------
# Global dark-theme CSS injected into every NiceGUI page via ui.add_head_html().
#
# Design rules (never break these):
#   • Background #12121a, cards #1E1E1E, drawer #1a1a1a
#   • Accent yellow/amber (#FFD54F title, #FFE082 subtitles)
#   • NO box-shadows anywhere — forced to none via * selector
#   • Quasar tables use flat bordered props
#   • Rounded buttons, compact drawer items
# ---------------------------------------------------------------------------
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
.q-btn--flat.wd-icon-blue .q-btn__content {{
    color: #5898d4 !important;
}}
.q-btn--flat.wd-icon-red .q-btn__content {{
    color: #F44336 !important;
}}
.q-btn--flat.wd-icon-amber .q-btn__content {{
    color: #FFC107 !important;
}}
.q-btn--outline {{
    border-color: #555 !important;
}}
.q-separator {{
    display: none !important;
}}
.q-tree__icon {{
    color: #d0d0d0 !important;
}}
.q-query-history {{
    background: #282828 !important;
}}
.query-history-entry {{
    cursor: pointer;
    color: #E0E0E0;
    font-size: 0.85em;
    white-space: nowrap;
    padding: 0.2rem 0.2rem 0.2rem 0.2rem;
    overflow: hidden;
    text-overflow: ellipsis;
    border-radius: 4px;
    transition: background-color 0.15s ease, color 0.15s ease;
}}
.query-history-entry:hover {{
    background-color: rgba(255, 255, 255, 0.08);
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


# =========================================================================
#  FastAPI app factory
# =========================================================================

def setup_app(cfg: WebDuckConfig) -> FastAPI:
    """Create and configure the FastAPI application.

    This is called once during ``start``.  It initialises the core services
    (storage, auth), mounts static assets, registers the REST API routers,
    and adds a few lightweight utility endpoints (health, root redirect,
    project reorder).

    Args:
        cfg: The fully-loaded application configuration.

    Returns:
        A configured ``FastAPI`` instance ready for ``uvicorn.run()``.
    """
    global _config, _storage, _auth, _project_auth, _version, _icon

    _config = cfg
    _version = cfg.version
    _icon = cfg.icon

    # Ensure the data directory exists before opening any DuckDB files
    cfg.server.data_dir.mkdir(parents=True, exist_ok=True)

    # Storage engine — wraps all DuckDB operations behind a file-locked API
    _storage = StorageEngine(cfg.server.data_dir)

    # Auth manager — JWT signing/verification and bcrypt password hashing
    _auth = AuthManager(
        cfg.server.data_dir,
        cfg.auth.jwt_secret,
        cfg.auth.jwt_algorithm,
    )

    # Per-project auth — tracks which users may access which projects
    _project_auth = ProjectAuth(cfg.server.data_dir)

    app = FastAPI(
        title="WebDuck API",
        description="DuckDB-as-a-Service REST API",
        version=cfg.version,
    )

    # --- Static files (icons, CSS, JS) ---
    # Static files live inside the package (src/webduck/static/)
    static_dir = Path(__file__).resolve().parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # --- REST API routers ---
    admin_api.set_dependencies(_auth, _storage)
    db_api.set_dependencies(_storage)
    app.include_router(admin_api.router)
    app.include_router(db_api.router)

    # --- Utility endpoints ---

    @app.get("/health")
    async def health():
        """Health check — used by load balancers and container probes."""
        return {"status": "ok"}

    from fastapi.responses import RedirectResponse

    @app.get("/")
    async def root():
        """Redirect bare ``/`` to the NiceGUI web UI."""
        return RedirectResponse(url="/ui")

    from fastapi import Request
    from fastapi.responses import FileResponse, JSONResponse

    @app.get("/export/{token}")
    async def export_download(token: str):
        """Serve a pending export and clean up after download."""
        export_entry = _export_tokens.pop(token, None)
        if export_entry is None:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Export not found or expired")
        export_path = export_entry["path"]
        filename = export_entry["filename"]
        if not export_path.exists():
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Export not found or expired")
        suffix = export_path.suffix.lower()
        media_types = {
            ".csv": "text/csv; charset=utf-8",
            ".parquet": "application/vnd.apache.parquet",
            ".json": "application/json; charset=utf-8",
            ".jsonl": "application/json; charset=utf-8",
            ".ndjson": "application/json; charset=utf-8",
        }
        return FileResponse(
            path=str(export_path),
            filename=filename,
            media_type=media_types.get(suffix, "application/octet-stream"),
        )

    @app.post("/api/reorder-projects")
    async def reorder_projects_ui(request: Request):
        """Reorder projects via a JS ``fetch()`` call from the UI.

        Expects a JSON body ``{"projects": ["name1", "name2", ...]}``.
        Called from drag-and-drop handlers in the projects page.
        """
        try:
            body = await request.json()
            projects = body.get("projects", [])
            _storage.reorder_projects(projects)
            return JSONResponse({"success": True, "count": len(projects)})
        except Exception as e:
            from webduck.logging import log_error
            log_error(f"Reorder projects error: {e}")
            return JSONResponse(
                {"error": str(e)}, status_code=500
            )

    return app


# =========================================================================
#  CLI — built with Click
# =========================================================================

def main():
    """Main entry point for CLI.

    Registers three Click commands under the ``webduck`` group:

    * ``webduck init``  — interactive or non-interactive admin user creation;
      auto-generates a JWT secret on first run and saves a starter config.
    * ``webduck start`` — boots the full stack (FastAPI + NiceGUI + uvicorn).
    * ``webduck status`` — reads the data directory and prints project,
      database, and user counts.
    """
    import click

    from webduck.config import save_config

    @click.group()
    @click.version_option()
    def cli():
        """WebDuck - A DuckDB server with REST API and Web UI."""
        pass

    # -----------------------------------------------------------------
    #  webduck init
    # -----------------------------------------------------------------
    @cli.command()
    @click.option(
        "--config", type=click.Path(), default=None,
        help="Config file path",
    )
    @click.option("--username", default=None, help="Admin username (non-interactive)")
    @click.option("--password", default=None, help="Admin password (non-interactive)")
    def init(config, username, password):
        """Initialize WebDuck (create admin user).

        If ``--username`` and ``--password`` are both provided the command
        runs non-interactively (useful for CI / Docker ENTRYPOINT scripts).
        Otherwise it prompts for credentials and confirms the password.
        """
        config_path = Path(config) if config else Path("webduck.yaml")
        cfg = load_config(config_path)

        click.echo("WebDuck Initialization")
        click.echo("=" * 40)

        if username and password:
            # Non-interactive mode — both flags supplied
            click.echo(f"Creating admin user '{username}'")
        else:
            # Interactive mode — prompt for credentials
            username = click.prompt("Admin username")
            password = click.prompt("Admin password", hide_input=True)
            password_confirm = click.prompt(
                "Confirm password", hide_input=True
            )
            if password != password_confirm:
                click.echo("Error: Passwords don't match", err=True)
                sys.exit(1)

        cfg.server.data_dir.mkdir(parents=True, exist_ok=True)

        # Auto-generate a secure JWT secret if the placeholder is still set
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

        # Only write a new config file if one didn't already exist
        if not config_path.exists():
            save_config(cfg, config_path)
            click.echo(f"Config saved to {config_path}")

        click.echo("Initialization complete!")

    # -----------------------------------------------------------------
    #  webduck start
    # -----------------------------------------------------------------
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
        """Start the WebDuck server.

        Loads config, overrides host/port if CLI flags differ from defaults,
        sets up logging, builds the FastAPI app, registers NiceGUI pages,
        and starts uvicorn.  The CLI banner is printed *before* uvicorn
        takes over the terminal.
        """
        config_path = Path(config) if config else Path("webduck.yaml")
        cfg = load_config(config_path)

        # CLI flags override config values only when explicitly provided
        if host != "0.0.0.0":
            cfg.server.host = host
        if port != 8998:
            cfg.server.port = port

        cfg.server.data_dir.mkdir(parents=True, exist_ok=True)

        # --- Logging setup ---
        # File logging uses RotatingFileHandler; console logging is separate
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

        # --- Build FastAPI app (storage, auth, routes) ---
        fastapi_app = setup_app(cfg)

        # --- Page context singleton ---
        # Provides shared services (config, storage, auth) to all page modules
        from webduck.pages.context import init_context
        init_context(cfg, _storage, _auth, _project_auth)

        # --- Prune stale user data (prefs + query history) ---
        # Drop references to projects/databases that no longer exist.
        # Afterwards it also runs lazily at most once per hour whenever a
        # page accessor is called, so long-running servers stay clean.
        from webduck.pages.user_prefs import prune_user_data
        prune_user_data()

        # --- Register NiceGUI pages ---
        # Each page module exposes a ``register()`` that binds a URL route
        # and defines the page's UI via NiceGUI decorators.
        from webduck.pages import browse as browse_page
        from webduck.pages import dashboard as dashboard_page
        from webduck.pages import import_export as import_export_page
        from webduck.pages import login as login_page
        from webduck.pages import projects as projects_page
        from webduck.pages import query as query_page
        from webduck.pages import trash as trash_page

        login_page.register()
        dashboard_page.register()
        projects_page.register()
        query_page.register()
        browse_page.register()
        import_export_page.register()
        trash_page.register()

        # --- Favicon ---
        # SVG favicons are inlined as data-URLs; other formats are passed
        # as file paths to NiceGUI which handles embedding.
        favicon_path = None
        if cfg.icon:
            candidate = (
                Path(__file__).resolve().parent
                / "static" / cfg.icon
            )
            if candidate.exists() and candidate.suffix == ".svg":
                favicon_path = candidate.read_text()
            elif candidate.exists():
                favicon_path = str(candidate)

        # --- Hand off to NiceGUI ---
        # ``ui.run_with()`` wraps the FastAPI app and mounts the NiceGUI
        # WebSocket + page routes under ``/ui``.  The ``storage_secret``
        # encrypts NiceGUI's browser-local user session cookies.
        ui.run_with(
            fastapi_app,
            mount_path="/ui",
            storage_secret=cfg.auth.jwt_secret,
            favicon=favicon_path,
        )

        click.echo("")
        click.echo("  WebDuck v" + _version)
        click.echo("  Copyright (c) 2026 autumo GmbH")
        click.echo("  Licensed under the GNU Affero General Public License v3.0 (AGPLv3)")
        click.echo("")
        click.echo(
            f"  Listening on  {cfg.server.host}:{cfg.server.port}"
        )
        click.echo(f"  Data directory {cfg.server.data_dir}")
        click.echo("")
        click.echo("  Press Ctrl+C to stop")
        click.echo("")

        # --- Start uvicorn ---
        # uvicorn.run() blocks until Ctrl+C.  When console logging is
        # disabled, we suppress uvicorn's noisy access log and lower the
        # log level to "warning" so only errors reach stderr.
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

    # -----------------------------------------------------------------
    #  webduck status
    # -----------------------------------------------------------------
    @cli.command()
    @click.option(
        "--config", type=click.Path(), default=None,
        help="Config file path",
    )
    def status(config):
        """Show WebDuck status.

        Opens the data directory, counts projects, databases per project,
        and lists admin users.  Read-only — never modifies any files.
        """
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
