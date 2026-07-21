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
#  Application entry point, CLI commands, NiceGUI pages and UI layout.
#
#  This module wires together FastAPI, NiceGUI, auth, storage, and API routers.
#  It defines the shared header/drawer components, page routes (login,
#  dashboard, projects, SQL editor), and the CLI commands (init, start, status).
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
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from nicegui import app as nicegui_app
from nicegui import ui

from webduck.api import admin as admin_api
from webduck.api import db as db_api
from webduck.auth.manager import AuthManager
from webduck.config import WebDuckConfig, load_config
from webduck.storage.engine import StorageEngine

# Module-level references (set by setup_app)
_config: WebDuckConfig | None = None
_storage: StorageEngine | None = None
_auth: AuthManager | None = None
_version: str = ""
_icon: str = ""

# ── Theme colors ──────────────────────────────────────────────
_YELLOW = "#FFD54F"
_YELLOW_LIGHT = "#FFE082"
_YELLOW_DARK = "#FFC107"
_TEXT_SOFT = "#E0E0E0"
_TEXT_DIM = "#999999"
_BG_DARK = "#121212"
_BG_CARD = "#1E1E1E"
_BORDER = "#333333"
_BORDER_BTN = "#2a2a2a"
_NAV_COLOR = "#BBBBBB"

_DARK_CSS = f"""
<style>
body {{
    background: {_BG_DARK} !important;
    color: {_TEXT_SOFT} !important;
}}
* {{
    box-shadow: none !important;
}}
.q-page {{
    padding-top: 6px !important;
}}
.q-card {{
    background: {_BG_CARD};
    border: 1px solid {_BORDER};
}}
.q-card .q-card {{
    background: #1c1c1c;
    border-color: #2a2a2a;
}}
.q-item__label {{
    color: {_TEXT_SOFT} !important;
}}
.q-field__label {{
    color: {_YELLOW_LIGHT} !important;
}}
.q-field__control:before {{
    border-color: #333 !important;
}}
.q-field__native::placeholder {{
    color: #555 !important;
    opacity: 1 !important;
}}
.q-table {{
    color: {_TEXT_SOFT} !important;
}}
.q-table thead tr th {{
    color: {_YELLOW} !important;
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
    color: {_TEXT_SOFT} !important;
}}
.q-btn--outline {{
    border-color: #555 !important;
    color: inherit;
}}
.q-separator {{
    display: none !important;
}}
.nicegui-error-popup {{
    border-radius: 12px !important;
    border: 1px solid #444 !important;
    background-color: {_BG_CARD} !important;
    color: {_TEXT_SOFT} !important;
}}
.border-button.q-btn--outline:before {{
    border-color: #333333 !important;
}}
</style>
"""


def setup_app(config: WebDuckConfig) -> FastAPI:
    """Set up FastAPI app with NiceGUI integration."""
    global _config, _storage, _auth, _version, _icon

    _config = config
    _version = config.version
    _icon = config.icon
    import webduck
    webduck.__version__ = _version
    _storage = StorageEngine(config.server.data_dir)
    _auth = AuthManager(
        config.server.data_dir,
        config.auth.jwt_secret,
        config.auth.jwt_algorithm,
    )

    fastapi_app = FastAPI(
        title="WebDuck",
        description="A DuckDB server with REST API and Web UI",
        version=_version,
    )

    @fastapi_app.get("/")
    async def root():
        return RedirectResponse(url="/ui")

    admin_api.set_dependencies(_auth, _storage)
    db_api.set_dependencies(_storage)

    fastapi_app.include_router(admin_api.router)
    fastapi_app.include_router(db_api.router)

    @fastapi_app.get("/health")
    async def health():
        return {"status": "ok"}

    static_dir = Path(__file__).resolve().parent.parent.parent / "static"
    if static_dir.exists():
        fastapi_app.mount(
            "/static", StaticFiles(directory=str(static_dir)),
            name="static",
        )

    return fastapi_app


def _apply_dark_theme():
    """Enable dark mode and inject custom yellow-accent CSS."""
    ui.dark_mode(True)
    ui.add_head_html(_DARK_CSS)


def _do_logout():
    nicegui_app.storage.user.clear()
    ui.navigate.to("/login")


def _make_header(_, page_title: str = ""):
    """Shared header with versioned title, icon, and bold username."""
    title_text = f"WebDuck {_version}"
    if page_title:
        title_text += f" — {page_title}"

    with ui.header().classes("bg-[#1a1a1a] items-center"):
        with ui.row().classes("items-center gap-2"):
            if _icon:
                ui.html(
                    f'<img src="/static/{_icon}" alt="icon" '
                    f'style="height:28px; vertical-align:middle;">'
                )
            ui.label(title_text).classes("text-h5 text-bold").style(
                f"color: {_YELLOW}"
            )
            ui.html(
                '<span style="color: #888; font-style: italic; '
                'font-size: 0.85em; position: relative; top: 4px;">powered by '
                '<a href="https://autumo.ch" target="_blank" '
                'style="color: #aaa; text-decoration: none;">'
                'autumo GmbH</a></span>'
            )
        ui.space()
        with ui.row().classes("items-center gap-4"):
            ui.label(
                nicegui_app.storage.user.get("username", "")
            ).classes("text-bold").style(f"color: {_TEXT_DIM}")
            ui.button(
                _("logout"), on_click=_do_logout
            ).props("outline color=red").classes("border-button")


def _make_drawer(_):
    """Shared left navigation drawer."""
    with ui.left_drawer().classes("bg-[#1a1a1a]"):
        ui.item_label(_("navigation")).classes(
            "text-h6 text-bold q-mb-xs"
        ).style(f"color: {_YELLOW}")
        for label, target in [
            (_("dashboard"), "/"),
            (_("projects"), "/projects"),
            (_("sql_editor"), "/query"),
        ]:
            ui.item(
                label, on_click=lambda t=target: ui.navigate.to(t)
            ).style(f"color: {_NAV_COLOR}")


def create_ui_pages():
    """Create all NiceGUI pages. Must be called before ui.run_with()."""
    from webduck.i18n import (
        get_language_name,
        get_supported_languages,
        get_translator,
        get_user_translator,
    )

    # ── Login ──────────────────────────────────────────────────
    @ui.page("/login")
    def login_page(request: Request):
        browser_lang = request.headers.get(
            "accept-language", "en"
        )[:2]
        saved_lang = nicegui_app.storage.user.get(
            "language", browser_lang
        )
        if saved_lang not in get_supported_languages():
            saved_lang = "en"
        nicegui_app.storage.user["language"] = saved_lang

        _ = get_translator(saved_lang)
        _apply_dark_theme()
        ui.page_title(f"WebDuck {_version} — Login")

        with ui.card().classes("absolute-center").style(
            f"background: {_BG_CARD}"
        ):
            with ui.row().classes("items-center gap-2"):
                if _icon:
                    ui.html(
                        f'<img src="/static/{_icon}" alt="icon" '
                        f'style="height:36px; vertical-align:middle;">'
                    )
                ui.label(f"WebDuck {_version}").classes(
                    "text-h4 text-bold"
                ).style(f"color: {_YELLOW}")

            ui.space().classes("h-3")

            username = ui.input(_("username")).classes("w-full")
            password = ui.input(
                _("password"), password=True
            ).classes("w-full")

            def handle_login():
                if _auth.verify_user(username.value, password.value):
                    token = _auth.create_jwt_token(username.value)
                    nicegui_app.storage.user["token"] = token
                    nicegui_app.storage.user["username"] = (
                        username.value
                    )
                    ui.navigate.to("/")
                else:
                    ui.notify(
                        _("invalid_credentials"), type="negative"
                    )

            ui.on("keydown.enter", handle_login)

            ui.button(
                _("login_button"), on_click=handle_login
            ).classes("w-full")

            ui.space().classes("h-3")

            lang_options = {
                code: get_language_name(code)
                for code in get_supported_languages()
            }

            lang_select = ui.select(
                lang_options,
                value=saved_lang,
                on_change=lambda e: (
                    nicegui_app.storage.user.update(
                        {"language": e.value}
                    ),
                    ui.navigate.reload(),
                ),
            ).classes("w-full q-mt-sm").props(
                "outlined dense"
            )

    # ── Dashboard ──────────────────────────────────────────────
    @ui.page("/")
    def dashboard_page():
        _ = get_user_translator()
        _apply_dark_theme()
        ui.page_title(f"WebDuck {_version} — Dashboard")

        if "token" not in nicegui_app.storage.user:
            ui.navigate.to("/login")
            return

        _make_header(_)
        _make_drawer(_)

        with ui.card().classes("w-full"):
            ui.label(_("dashboard_title")).classes(
                "text-h5"
            ).style(f"color: {_YELLOW}")

            projects = _storage.list_projects()
            total_databases = sum(
                len(_storage.list_databases(p)) for p in projects
            )

            with ui.row().classes("w-full gap-4"):
                with ui.card().classes("flex-grow justify-center items-center").style(
                    "background: #1c1c1c; border: 1px solid #333"
                ):
                    ui.badge(
                        _("online"), color="green"
                    ).classes("text-h5 q-pa-sm q-px-lg")
                    ui.label(_("server_status")).classes("text-h6")

                with ui.card().classes("flex-grow justify-center items-center").style(
                    "background: #1c1c1c; border: 1px solid #333"
                ):
                    ui.label(str(len(projects))).classes(
                        "text-h3"
                    ).style(f"color: {_YELLOW_LIGHT}")
                    ui.label(_("total_projects")).classes("text-h6")

                with ui.card().classes("flex-grow justify-center items-center").style(
                    "background: #1c1c1c; border: 1px solid #333"
                ):
                    ui.label(str(total_databases)).classes(
                        "text-h3"
                    ).style(f"color: {_YELLOW_LIGHT}")
                    ui.label(_("total_databases")).classes("text-h6")

    # ── Projects ───────────────────────────────────────────────
    @ui.page("/projects")
    def projects_page():
        _ = get_user_translator()
        _apply_dark_theme()
        ui.page_title(f"WebDuck {_version} — Projects")

        if "token" not in nicegui_app.storage.user:
            ui.navigate.to("/login")
            return

        _make_header(_)
        _make_drawer(_)

        # ── Page title ─────────────────────────────────────
        with ui.card().classes("w-full").style("margin-top: 4px"):
            ui.label(_("projects_title")).classes(
                "text-h5"
            ).style(f"color: {_YELLOW}")

        # ── Create project (own card) ──────────────────────
        with ui.card().classes("w-full q-mt-sm"):
            ui.label(_("create_project")).classes(
                "text-subtitle1 text-bold q-mb-sm"
            ).style(f"color: {_YELLOW_LIGHT}")
            with ui.row().classes("w-full items-center gap-4"):
                project_name = ui.input(
                    _("project_name")
                ).classes("flex-grow")

                async def create_project():
                    if project_name.value:
                        project_dir = (
                            _storage.data_dir / project_name.value
                        )
                        project_dir.mkdir(
                            parents=True, exist_ok=True
                        )
                        ui.notify(_("success"), type="positive")
                        ui.navigate.reload()

                ui.button(
                    _("create_project"), on_click=create_project
                ).props("outline").classes("border-button")

        # ── Project list ───────────────────────────────────
        projects = _storage.list_projects()
        if projects:
            for project in projects:
                with ui.card().classes("w-full q-mt-sm"):
                    # ── Project header row ─────────────────
                    with ui.row().classes(
                        "w-full items-center gap-2"
                    ):
                        ui.html(
                            '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" '
                            'stroke="#FFE082" stroke-width="2" stroke-linecap="round" '
                            'stroke-linejoin="round" style="vertical-align: middle;">'
                            '<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 '
                            '2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>'
                        )
                        ui.label(project).classes(
                            "text-h6"
                        ).style(f"color: {_YELLOW_LIGHT}")
                        ui.space()

                        dbs = _storage.list_databases(project)
                        ui.label(
                            f"{len(dbs)} {_('databases')}"
                        ).classes("text-caption")

                        async def delete_project(p=project):
                            if _storage.delete_project(p):
                                ui.notify(
                                    _("success"),
                                    type="positive",
                                )
                                ui.navigate.reload()
                            else:
                                ui.notify(
                                    _("error"),
                                    type="negative",
                                )

                        ui.button(
                            _("delete"),
                            on_click=delete_project,
                        ).props("outline color=red").classes("border-button")

                    # ── Existing databases (sub-card) ──────
                    dbs = _storage.list_databases(project)
                    if dbs:
                        with ui.card().classes(
                            "w-full q-mt-sm"
                        ).style(
                            "background: #1c1c1c; "
                            "border-color: #2a2a2a"
                        ):
                            ui.label(_("databases")).classes(
                                "text-caption text-bold q-mb-xs"
                            ).style(f"color: {_YELLOW_DARK}")
                            for db_name in dbs:
                                with ui.row().classes(
                                    "w-full items-center gap-2"
                                ):
                                    ui.html(
                                        '<svg width="16" height="16" viewBox="0 0 24 24" '
                                        'fill="none" stroke="#999" stroke-width="2" '
                                        'stroke-linecap="round" stroke-linejoin="round" '
                                        'style="vertical-align: middle;">'
                                        '<ellipse cx="12" cy="5" rx="9" ry="3"/>'
                                        '<path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/>'
                                        '<path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/></svg>'
                                    )
                                    ui.label(db_name).classes("text-body2")
                                    ui.space()
                                    async def delete_db(
                                        p=project, d=db_name
                                    ):
                                        if _storage.delete_database(
                                            p, d
                                        ):
                                            ui.notify(
                                                _("success"),
                                                type="positive",
                                            )
                                            ui.navigate.reload()
                                        else:
                                            ui.notify(
                                                _("error"),
                                                type="negative",
                                            )
                                    ui.button(
                                        _("delete"),
                                        on_click=delete_db,
                                    ).props(
                                        "outline color=red size=md"
                                    ).classes("border-button")

                    # ── Create database (sub-card) ─────────
                    with ui.card().classes(
                        "w-full q-mt-sm"
                    ).style(
                        "background: #1c1c1c; "
                        "border-color: #2a2a2a"
                    ):
                        ui.label(_("create_database")).classes(
                            "text-caption text-bold"
                        ).style(f"color: {_YELLOW_DARK}")
                        with ui.row().classes(
                            "w-full items-center gap-4"
                        ):
                            new_db_name = ui.input(
                                _("database_name")
                            ).classes("flex-grow")

                            async def create_db(p=project):
                                if new_db_name.value:
                                    ok = _storage.create_database(
                                        p, new_db_name.value
                                    )
                                    if ok:
                                        ui.notify(
                                            _("success"),
                                            type="positive",
                                        )
                                        ui.navigate.reload()
                                    else:
                                        ui.notify(
                                            _("error"),
                                            type="negative",
                                        )

                            ui.button(
                                _("create_database"),
                                on_click=create_db,
                            ).props("outline color=amber").classes("border-button")
        else:
            with ui.card().classes("w-full q-mt-sm"):
                ui.label(_("no_projects_found")).classes(
                    "text-caption"
                )

    # ── SQL Editor ─────────────────────────────────────────────
    @ui.page("/query")
    def query_page():
        _ = get_user_translator()
        _apply_dark_theme()
        ui.page_title(f"WebDuck {_version} — SQL Editor")

        if "token" not in nicegui_app.storage.user:
            ui.navigate.to("/login")
            return

        _make_header(_)
        _make_drawer(_)

        with ui.card().classes("w-full"):
            ui.label(_("sql_editor")).classes(
                "text-h5"
            ).style(f"color: {_YELLOW}")

            with ui.row().classes("w-full gap-4"):
                projects = _storage.list_projects()
                default_proj = projects[0] if projects else None
                project_select = ui.select(
                    projects,
                    label=_("projects"),
                    value=default_proj,
                ).classes("w-40")

                database_select = ui.select(
                    [], label=_("databases")
                ).classes("w-40")

                def update_databases():
                    if project_select.value:
                        databases = _storage.list_databases(
                            project_select.value
                        )
                        database_select.options = databases
                        database_select.value = (
                            databases[0] if databases else None
                        )

                project_select.on("change", update_databases)
                update_databases()

            ui.label("SQL").classes("text-caption text-bold q-mb-xs").style(
                f"color: {_YELLOW_LIGHT}"
            )
            sql_input = ui.textarea(
                placeholder="SELECT * FROM table_name",
            ).classes("w-full")

            result_area = ui.card().classes("w-full mt-4 shadow-none")

            import re as _re

            def _result_message(result, sql_text):
                if not result["success"]:
                    return None, result["error"]
                sql_upper = sql_text.strip().upper()
                is_ddl_dml = sql_upper.split()[0] in (
                    "CREATE", "DROP", "ALTER", "INSERT",
                    "UPDATE", "DELETE", "TRUNCATE",
                )
                if result["columns"] and not is_ddl_dml:
                    return "table", result
                rc = result.get("row_count", 0)
                if sql_upper.startswith("INSERT"):
                    key = "row_inserted" if rc == 1 else "rows_inserted"
                    return "text", _(key) % rc
                elif sql_upper.startswith("UPDATE"):
                    key = "row_updated" if rc == 1 else "rows_updated"
                    return "text", _(key) % rc
                elif sql_upper.startswith("DELETE"):
                    key = "row_deleted" if rc == 1 else "rows_deleted"
                    return "text", _(key) % rc
                elif sql_upper.startswith("CREATE TABLE"):
                    m = _re.search(
                        r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[`"\']?(\w+)',
                        sql_text, _re.IGNORECASE,
                    )
                    tbl = m.group(1) if m else "?"
                    return "text", f"Table '{tbl}' created"
                elif sql_upper.startswith("DROP TABLE"):
                    m = _re.search(
                        r'DROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?[`"\']?(\w+)',
                        sql_text, _re.IGNORECASE,
                    )
                    tbl = m.group(1) if m else "?"
                    return "text", f"Table '{tbl}' dropped"
                else:
                    return "text", _("query_executed")

            async def execute_query():
                if not sql_input.value or not database_select.value:
                    return

                results = _storage.execute_queries(
                    project_select.value,
                    database_select.value,
                    sql_input.value,
                )

                with result_area:
                    result_area.clear()
                    all_ok = True
                    for result in results:
                        kind, data = _result_message(result, result.get("sql", ""))
                        if kind == "table":
                            ui.table(
                                columns=[
                                    {"name": c, "label": c, "field": c}
                                    for c in data["columns"]
                                ],
                                rows=[
                                    {c: v for c, v in zip(data["columns"], row)}
                                    for row in data["rows"]
                                ],
                            ).classes("w-full").props("flat bordered")
                            rc = data["row_count"]
                            key = "row_returned" if rc == 1 else "rows_returned"
                            ui.label(_(key) % rc).classes(
                                "text-caption q-mt-sm"
                            ).style(f"color: {_TEXT_DIM}")
                        elif kind == "text":
                            ui.label(data).style(f"color: {_TEXT_DIM}")
                        else:
                            ui.label(data).classes("text-negative")
                            all_ok = False
                    if all_ok:
                        sql_input.value = ""

            ui.button(
                _("execute_query"), on_click=execute_query
            ).props("outline color=amber").classes("mt-2 border-button")


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
            enabled=cfg.logging.enabled,
            max_size_mb=cfg.logging.max_size_mb,
            max_files=cfg.logging.max_files,
            query_log=cfg.logging.query_log,
        )

        fastapi_app = setup_app(cfg)
        create_ui_pages()

        favicon_path = None
        if cfg.icon:
            candidate = Path(__file__).resolve().parent.parent.parent / "static" / cfg.icon
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
        click.echo(f"  Listening on  {cfg.server.host}:{cfg.server.port}")
        click.echo(f"  Data directory {cfg.server.data_dir}")
        click.echo("")
        click.echo("  Press Ctrl+C to stop")
        click.echo("")

        uvicorn.run(
            fastapi_app,
            host=cfg.server.host,
            port=cfg.server.port,
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
