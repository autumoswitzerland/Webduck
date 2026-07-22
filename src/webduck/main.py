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

import asyncio
import json
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
from webduck.auth.manager import AuthManager, ProjectAuth
from webduck.config import WebDuckConfig, load_config
from webduck.storage.engine import StorageEngine

# Module-level references (set by setup_app)
_config: WebDuckConfig | None = None
_storage: StorageEngine | None = None
_auth: AuthManager | None = None
_project_auth: ProjectAuth | None = None
_version: str = ""
_icon: str = ""
_drawer = None

# ── General constants ─────────────────────────────────────────
_AUTUMO_URL = "https://autumo.ch"
_DOCS_URL = "https://webduck.autumo.ch"

# ── Theme colors ──────────────────────────────────────────────
_YELLOW = "#FFD54F"
_YELLOW_LIGHT = "#FFE082"
_YELLOW_DARK = "#FFC107"
_YELLOW_DARKER = "#806002"
_TEXT_SOFT = "#E0E0E0"
_TEXT_DIM = "#999999"
_TEXT_PLACEHOLDER = "#666666"
_BG_DARK = "#121212"
_BG_CARD = "#1E1E1E"
_BORDER = "#333333"
_BORDER_BTN = "#2a2a2a"
_NAV_COLOR = "#BBBBBB"
_TREE_WIDTH = "20%"
_BROWSE_PAGE_SIZE = 100

_DARK_CSS = f"""
<style>
body {{
    background: {_BG_DARK} !important;
    color: {_TEXT_SOFT} !important;
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
    color: {_YELLOW_DARK} !important;
}}
.q-field__control:before {{
    border-color: #333 !important;
}}
.q-field__native::placeholder {{
    color: #777 !important;
    opacity: 1 !important;
}}
.q-field__control {{
    background: #1a1a1a !important;
}}
.q-menu {{
    background: #333 !important;
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
}}
.q-separator {{
    display: none !important;
}}
.text-caption {{
    color: {_TEXT_DIM} !important;
}}
.nicegui-error-popup {{
    border-radius: 12px !important;
    border: 1px solid #444 !important;
    background-color: {_BG_CARD} !important;
    color: {_TEXT_SOFT} !important;
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

def setup_app(config: WebDuckConfig) -> FastAPI:
    """Set up FastAPI app with NiceGUI integration."""
    global _config, _storage, _auth, _project_auth, _version, _icon

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
    _project_auth = ProjectAuth(config.server.data_dir)

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
    ui.add_css('''
        .q-separator--vertical.nicegui-separator {
            width: 1px !important;
        }
    ''', shared=True)


def _do_logout():
    nicegui_app.storage.user.clear()
    ui.navigate.to("/login")


def _make_header(_, page_title: str = ""):
    """Shared header with versioned title, icon."""
    global _drawer
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
        ui.space()
        with ui.row().classes("items-center gap-4"):
            
            """
            ui.button(
                "API", 
                on_click=lambda: ui.run_javascript('window.open("/docs", "_blank")')
            ).props("outline color=blue").classes("border-button")
            ui.button(
                "Docs", 
                on_click=lambda: ui.run_javascript(f'window.open("{_DOCS_URL}", "_blank")')
            ).props("outline color=blue").classes("border-button")
            ui.button(
                _("logout"), on_click=_do_logout
            ).props("outline color=red").classes("border-button")
            
            """
            
            ui.button(
                icon="menu", 
                on_click=lambda: _drawer.toggle() if _drawer else None
            ).props("outline color=grey").classes("border-button")


def _make_drawer(_):
    """Shared left navigation drawer."""
    global _drawer
    with ui.left_drawer().classes("bg-[#1a1a1a]").props("bordered width=200") as _drawer:
        ui.item_label(_("navigation")).classes(
            "text-h6 text-bold q-mb-xs"
        ).style(f"color: {_YELLOW}")
        for label, target, icon in [
            (_("dashboard"), "/", "dashboard"),
            (_("projects"), "/projects", "folder_open"),
            (_("browse"), "/browse", "account_tree"),
            (_("sql_editor"), "/query", "code"),
        ]:
            with ui.item(
                on_click=lambda t=target: ui.navigate.to(t)
            ).style(f"color: {_NAV_COLOR}").props("clickable"):
                with ui.item_section().props("side"):
                    ui.icon(icon).style(f"color: {_NAV_COLOR}")
                ui.item_section(label)

        with ui.item(
            on_click=lambda: ui.run_javascript('window.open("/docs", "_blank")')
        ).style("color: #2296f3;").props("clickable"):
            with ui.item_section().props("side"):
                ui.icon("api").style("color: #2296f3;")
            ui.item_section("API")

        with ui.item(
            on_click=lambda: ui.run_javascript(f'window.open("{_DOCS_URL}", "_blank")')
        ).style("color: #2296f3;").props("clickable"):
            with ui.item_section().props("side"):
                ui.icon("menu_book").style("color: #2296f3;")
            ui.item_section("Docs")

        with ui.item(
            on_click=_do_logout
        ).style("color: #f54336;").props("clickable"):
            with ui.item_section().props("side"):
                ui.icon("logout").style("color: #f54336;")
            ui.item_section(_("logout"))
        

def _make_footer(_):
    """Shared footer for all pages."""
    with ui.footer().classes("bg-[#040d12] items-center").style("border-top: 0.9px solid #0c2736;"):
        with ui.row().classes("items-center gap-4 w-full justify-center"):
            
            with ui.row().classes("items-center gap-1"):
                ui.html(
                    f'<img src="/static/footer-logo.png" style="height: 16px; width: auto; filter: brightness(0.65);">'
                )
                ui.html(
                    f'<span style="color: #666; font-size: 0.9em;">'
                    f'&copy; 2026 <a href="{_AUTUMO_URL}" target="_blank" '
                    f'style="color: #666; text-decoration: none;">autumo GmbH</a>'
                    f' &mdash; Licensed under MIT'
                    f'</span>'
                )
            
            ui.label("|").style("color: #444;")

            ui.label("API").style("color: #565656; font-size: 0.9em; cursor: pointer;").on(
                "click", lambda: ui.run_javascript('window.open("/docs", "_blank")')
            ).on("mouseover", lambda e: e.sender.style("color: #444")).on(
                "mouseout", lambda e: e.sender.style("color: #565656")
            )

            ui.label("|").style("font-size: 0.9em; color: #444;")
            
            ui.link(
                "Docs", 
                _DOCS_URL, 
                new_tab=True
            ).style("color: #666; font-size: 0.9em; text-decoration: none;")
            
            ui.label("|").style("font-size: 0.9em; color: #444;")
            
            ui.link(
                "GitHub",
                "https://github.com/autumo/webduck",
                new_tab=True
            ).style("color: #666; font-size: 0.9em; text-decoration: none;")

            ui.label("|").style("font-size: 0.9em; color: #444;")
            
            username = nicegui_app.storage.user.get("username", "")
            with ui.row().classes("items-center gap-1"):
                ui.label(f"{_('username')}:").style("color: #666; font-size: 0.9em;")
                ui.label(username).style(f"color: {_YELLOW_DARKER}; font-size: 0.9em;")


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

        with ui.column().classes("fixed-center items-center gap-6"):
            
            with ui.card().style(
                f"background: {_BG_CARD}; padding: 20px 24px 20px 24px;"
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
    
                ui.space().classes("h-3")
    
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
            
            ui.html(
                f'<span style="color: #777; font-size: 0.9em; text-align: center; white-space: nowrap;">'
                f'powered by <a href="{_AUTUMO_URL}" target="_blank" '
                f'style="color: #777; text-decoration: none;">'
                f'autumo GmbH</a></span>'
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
        _make_footer(_)
        
        with ui.card().classes("w-full"):
            ui.label(_("dashboard_title")).classes(
                "text-h5"
            ).style(f"color: {_YELLOW_LIGHT}")

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
        _make_footer(_)

        # ── Page title ─────────────────────────────────────
        with ui.card().classes("w-full").style("margin-top: 4px"):
            ui.label(_("projects_title")).classes(
                "text-h5"
            ).style(f"color: {_YELLOW_LIGHT}")

        # ── Create project (own card) ──────────────────────
        with ui.card().classes("w-full q-mt-sm"):
            ui.label(_("create_project")).classes(
                "text-subtitle1 text-bold q-mb-sm"
            ).style(f"color: {_YELLOW}")
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
                            with ui.dialog() as dlg, ui.card().classes(
                                "items-center gap-4"
                            ).style(
                                "background: #1E1E1E; border-radius: 12px; "
                                "padding: 24px 32px;"
                            ):
                                ui.label(_("confirm_delete_project")).style(
                                    f"color: {_TEXT_SOFT}"
                                )
                                with ui.row().classes("gap-2"):
                                    ui.button(
                                        _("cancel"),
                                        on_click=dlg.close,
                                    ).props("outline color=grey").classes(
                                        "border-button"
                                    )

                                    def do_delete():
                                        dlg.close()
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
                                        on_click=do_delete,
                                    ).props("outline color=red").classes(
                                        "border-button"
                                    )
                            dlg.open()

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
                            )
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
                                    _pa = _project_auth or ProjectAuth(_storage.data_dir)
                                    has_pw = _pa.has_database_password(
                                        project, db_name
                                    )
                                    if has_pw:
                                        ui.html(
                                            '<svg width="14" height="14" viewBox="0 0 24 24" '
                                            'fill="none" stroke="#FFD54F" stroke-width="2" '
                                            'stroke-linecap="round" stroke-linejoin="round" '
                                            'style="vertical-align: middle;">'
                                            '<rect x="3" y="11" width="18" height="11" '
                                            'rx="2" ry="2"/>'
                                            '<path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>'
                                        ).tooltip(_("password_set")).props(
                                            "tooltip-position=top"
                                        )
                                    ui.space()

                                    async def change_db_password(
                                        p=project, d=db_name
                                    ):
                                        with ui.dialog() as dlg, ui.card().classes(
                                            "items-center gap-4"
                                        ).style(
                                            "background: #1E1E1E; border-radius: 12px; "
                                            "padding: 24px 32px;"
                                        ):
                                            ui.label(
                                                f"{_('api_password')} — {d}"
                                            ).style(f"color: {_YELLOW}")
                                            pw_input = ui.input(
                                                password=True,
                                                password_toggle_button=True,
                                            ).classes("w-full").props(
                                                "autocomplete=new-password"
                                            )

                                            def do_save():
                                                if pw_input.value:
                                                    pa = _project_auth or ProjectAuth(
                                                        _storage.data_dir
                                                    )
                                                    pa.set_database_password(
                                                        p, d, pw_input.value,
                                                    )
                                                    dlg.close()
                                                    ui.notify(
                                                        _("success"),
                                                        type="positive",
                                                    )
                                                    ui.navigate.reload()

                                            with ui.row().classes("gap-2"):
                                                ui.button(
                                                    _("generate_password"),
                                                    on_click=lambda: setattr(
                                                        pw_input, 'value',
                                                        secrets.token_urlsafe(16),
                                                    ),
                                                ).props("outline color=amber").classes(
                                                    "border-button"
                                                )
                                                ui.button(
                                                    _("save"),
                                                    on_click=do_save,
                                                ).props("outline color=green").classes(
                                                    "border-button"
                                                )
                                        dlg.open()

                                    ui.button(
                                        on_click=change_db_password,
                                    ).props(
                                        'icon="key" flat dense'
                                    ).style("color: #888;").tooltip(
                                        _("change_password")
                                    ).props("tooltip-position=top")

                                    async def delete_db(
                                        p=project, d=db_name
                                    ):
                                        with ui.dialog() as dlg, ui.card().classes(
                                            "items-center gap-4"
                                        ).style(
                                            "background: #1E1E1E; border-radius: 12px; "
                                            "padding: 24px 32px;"
                                        ):
                                            ui.label(_("confirm_delete_database")).style(
                                                f"color: {_TEXT_SOFT}"
                                            )
                                            with ui.row().classes("gap-2"):
                                                ui.button(
                                                    _("cancel"),
                                                    on_click=dlg.close,
                                                ).props("outline color=grey").classes(
                                                    "border-button"
                                                )

                                                def do_delete():
                                                    dlg.close()
                                                    if _storage.delete_database(p, d):
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
                                                    on_click=do_delete,
                                                ).props("outline color=red").classes(
                                                    "border-button"
                                                )
                                        dlg.open()
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
                        )
                        with ui.row().classes(
                            "w-full items-center gap-4"
                        ):
                            new_db_name = ui.input(
                                _("database_name")
                            ).classes("flex-grow")

                            new_db_password = ui.input(
                                f"{_('api_password')} ({_('optional')})",
                                password=True,
                                password_toggle_button=True,
                            ).classes("flex-grow").props('autocomplete="new-password"')

                            def generate_db_password(pw=new_db_password):
                                pw.value = secrets.token_urlsafe(16)

                            ui.button(
                                on_click=generate_db_password,
                            ).props(
                                'icon="casino" flat dense'
                            ).tooltip(_("generate_password")).props(
                                "tooltip-position=top"
                            )

                            async def create_db(
                                p=project,
                                db_name=new_db_name,
                                db_password=new_db_password,
                            ):
                                if db_name.value:
                                    ok = _storage.create_database(
                                        p, db_name.value
                                    )
                                    if ok:
                                        if db_password.value:
                                            pa = _project_auth or ProjectAuth(_storage.data_dir)
                                            pa.set_database_password(
                                                p, db_name.value,
                                                db_password.value,
                                            )
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

    # ── SQL Queries + Upload ────────────────────────────────────
    @ui.page("/query")
    def query_page():
        _ = get_user_translator()
        _apply_dark_theme()
        ui.page_title(f"WebDuck {_version} — SQL Queries")

        if "token" not in nicegui_app.storage.user:
            ui.navigate.to("/login")
            return

        _make_header(_)
        _make_drawer(_)
        _make_footer(_)
        
        # ── Card 1: Project & DB Selection (shared) ────────────
        with ui.card().classes("w-full"):
            ui.label(_("select_database")).classes(
                "text-h5"
            ).style(f"color: {_YELLOW_LIGHT}")

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
                        database_select.set_options(
                            databases,
                            value=databases[0] if databases else None,
                        )
                    else:
                        database_select.set_options([], value=None)

                project_select.on_value_change(update_databases)
                update_databases()

        # ── Card 2: SQL Queries ────────────────────────────────
        with ui.card().classes("w-full q-mt-sm"):
            ui.label(_("sql_queries")).classes(
                "text-h5"
            ).style(f"color: {_YELLOW_LIGHT}")

            ui.label("SQL").classes("text-caption text-bold q-mb-xs")
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
                            )
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

        # ── Card 3: SQL Upload ─────────────────────────────────
        with ui.card().classes("w-full q-mt-sm"):
            ui.label(_("sql_upload")).classes(
                "text-h5"
            ).style(f"color: {_YELLOW_LIGHT}")

            dsf = _("drop_sql_file")
            drop_html = f"""
            <div id="sql-drop-zone" style="
                border: 2px dashed #444;
                border-radius: 8px;
                padding: 32px;
                text-align: center;
                color: #888;
                cursor: pointer;
                margin-bottom: 12px;
            ">
                {dsf}
                <input type="file" id="sql-file-input"
                    accept=".sql,.txt" style="display:none;">
                <div id="sql-file-info"
                    style="margin-top: 8px; font-size: 0.9em;">
                </div>
            </div>
            """
            ui.html(drop_html)

            js_setup = f"""
            setTimeout(function() {{
                var zone = document.getElementById('sql-drop-zone');
                var fileInput = document.getElementById('sql-file-input');
                if (!zone || !fileInput) return;

                zone.addEventListener('click', function() {{
                    fileInput.click();
                }});

                zone.addEventListener('dragover', function(e) {{
                    e.preventDefault();
                    zone.style.borderColor = '{_YELLOW}';
                    zone.style.background = '#1a1a1a';
                }});

                zone.addEventListener('dragleave', function() {{
                    zone.style.borderColor = '#444';
                    zone.style.background = 'transparent';
                }});

                zone.addEventListener('drop', function(e) {{
                    e.preventDefault();
                    zone.style.borderColor = '#444';
                    zone.style.background = 'transparent';
                    var file = e.dataTransfer.files[0];
                    if (file) readFile(file);
                }});

                fileInput.addEventListener('change', function(e) {{
                    var file = e.target.files[0];
                    if (file) readFile(file);
                }});

                function readFile(file) {{
                    if (file.size > 2097152) {{
                        alert('{_("file_too_large")}');
                        return;
                    }}
                    var reader = new FileReader();
                    reader.onload = function(e) {{
                        window._sqlUploadContent = e.target.result;
                        var info = document.getElementById('sql-file-info');
                        if (info) {{
                            var sizeKB = (file.size / 1024).toFixed(1);
                            var msg = '{_("file_loaded")}'.replace(
                                '%s', file.name + ' (' + sizeKB + ' KB)'
                            );
                            info.textContent = msg;
                            info.style.color = '{_TEXT_SOFT}';
                        }}
                    }};
                    reader.readAsText(file);
                }}
            }}, 100);
            """
            ui.run_javascript(js_setup)

            upload_result_area = ui.card().classes("w-full mt-4 shadow-none")

            async def execute_upload():
                if not database_select.value:
                    return

                js_result = await ui.run_javascript(
                    'window._sqlUploadContent || ""',
                    timeout=3,
                )
                sql_text = js_result
                if not sql_text:
                    return

                with ui.dialog() as progress_dialog, ui.card().classes(
                    "items-center gap-4"
                ).style(
                    "background: #1E1E1E; border-radius: 12px; padding: 32px 48px;"
                ):
                    ui.spinner(size="xl", color="amber")
                    ui.label(_("sql_upload")).style(
                        f"color: {_TEXT_SOFT}; font-size: 1.1em;"
                    )
                progress_dialog.open()

                results = await asyncio.to_thread(
                    _storage.execute_queries,
                    project_select.value,
                    database_select.value,
                    sql_text,
                )

                progress_dialog.close()

                with upload_result_area:
                    upload_result_area.clear()
                    error_count = 0
                    success_count = 0
                    for result in results:
                        if result["success"]:
                            success_count += 1
                        else:
                            error_count += 1
                            ui.label(result["error"]).classes("text-negative")

                    if error_count == 0 and success_count > 0:
                        key = "statement_executed" if success_count == 1 else "statements_executed"
                        ui.label(_(key) % success_count).style(
                            "color: #66BB6A"
                        )
                        await ui.run_javascript(
                            """
                            window._sqlUploadContent = "";
                            var info = document.getElementById('sql-file-info');
                            if (info) { info.textContent = ''; }
                            var zone = document.getElementById('sql-drop-zone');
                            if (zone) { zone.style.borderColor = '#444'; }
                            """,
                            timeout=3,
                        )
                    elif error_count == 0 and success_count == 0:
                        ui.label(_("no_file_loaded")).style(
                            f"color: {_TEXT_DIM}"
                        )

            ui.button(
                _("execute_upload"), on_click=execute_upload
            ).props("outline color=amber").classes("mt-2 border-button")

    # ── Browse ────────────────────────────────────────────────
    @ui.page("/browse")
    def browse_page():
        _ = get_user_translator()
        _apply_dark_theme()
        ui.page_title(f"WebDuck {_version} — Browse")

        if "token" not in nicegui_app.storage.user:
            ui.navigate.to("/login")
            return

        _make_header(_)
        _make_drawer(_)
        _make_footer(_)

        with ui.card().classes("w-full"):
            ui.label(_("browse")).classes("text-h5").style(
                f"color: {_YELLOW_LIGHT}"
            )

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
                        database_select.set_options(
                            databases,
                            value=databases[0] if databases else None,
                        )
                    else:
                        database_select.set_options([], value=None)

                project_select.on_value_change(update_databases)
                update_databases()

        # ── Tree + Result ──────────────────────────────────────
        with ui.row().classes("w-full q-mt-sm gap-4"):
            tree_container = ui.card().classes(
                "col"
            ).style(f"min-height: 200px; flex: 0 0 {_TREE_WIDTH};")

            result_container = ui.card().classes("col")

        def load_tree():
            tree_container.clear()
            result_container.clear()

            proj = project_select.value
            db = database_select.value
            if not proj or not db:
                return

            with tree_container:
                ui.label(_("database_objects")).classes(
                    "text-h6 q-mb-sm"
                ).style(f"color: {_YELLOW}")

                tree_data = {}

                for obj_type, icon, query in [
                    ("tables", "table_chart",
                     f"SELECT table_name FROM duckdb_tables() WHERE database_name = '{db}' ORDER BY table_name"),
                    ("views", "visibility",
                     f"SELECT view_name AS table_name FROM duckdb_views() WHERE database_name = '{db}' ORDER BY view_name"),
                    ("indexes", "tag",
                     f"SELECT index_name AS table_name FROM duckdb_indexes() WHERE database_name = '{db}' ORDER BY index_name"),
                    ("sequences", "pin",
                     f"SELECT sequence_name AS table_name FROM duckdb_sequences() WHERE database_name = '{db}' ORDER BY sequence_name"),
                    ("macros", "settings",
                     f"SELECT function_name AS table_name FROM duckdb_functions() WHERE database_name = '{db}' AND function_type = 'macro' ORDER BY function_name"),
                ]:
                    res = _storage.execute_query(proj, db, query)
                    items = []
                    if res.get("success") and res.get("rows"):
                        for row in res["rows"]:
                            name = row[0]
                            items.append({
                                "id": f"{obj_type}/{name}",
                                "label": name,
                                "icon": icon,
                            })

                    if items:
                        tree_data[obj_type] = {
                            "id": obj_type,
                            "label": _(obj_type),
                            "icon": "folder",
                            "children": items,
                        }

                if not tree_data:
                    ui.label(_("no_data_found")).style(
                        f"color: {_TEXT_DIM}"
                    )
                    return

                _browse_timer = [None]
                _edit_timer = [None]

                def on_tree_click(e):
                    if _browse_timer[0]:
                        _browse_timer[0].cancel()
                        _browse_timer[0] = None
                    if _edit_timer[0]:
                        _edit_timer[0].cancel()
                        _edit_timer[0] = None

                    selected = e.value if isinstance(e.value, list) else [e.value]
                    if not selected:
                        return
                    node_id = selected[0]
                    if "/" not in node_id:
                        return
                    obj_type, name = node_id.split("/", 1)
                    result_container.clear()

                    proj = project_select.value
                    db = database_select.value

                    with result_container:
                        ui.label(
                            f"{obj_type}: {name}"
                        ).classes("text-h6 q-mb-sm").style(
                            f"color: {_YELLOW}"
                        )

                        if obj_type in ("tables", "views"):
                            count_res = _storage.execute_query(
                                proj, db,
                                f'SELECT COUNT(*) FROM "{name}"',
                            )
                            total = (
                                count_res["rows"][0][0]
                                if count_res.get("success") and count_res.get("rows")
                                else 0
                            )

                            q = f'SELECT * FROM "{name}" LIMIT {_BROWSE_PAGE_SIZE} OFFSET 0'
                            res = _storage.execute_query(proj, db, q)
                            if not res.get("success"):
                                ui.label(res.get("error", "")).style("color: #f44336")
                                return

                            columns = res.get("columns", [])
                            rows_raw = res.get("rows", [])
                            if not columns:
                                ui.label(_("no_data_found")).style(f"color: {_TEXT_DIM}")
                                return

                            all_rows = [dict(zip(columns, row)) for row in rows_raw]
                            has_more = total > _BROWSE_PAGE_SIZE

                            st = _("total_rows") % total if total > 0 else ""
                            status_label = ui.label(st).style(
                                f"color: {_TEXT_DIM}; font-size: 0.85em;"
                            )

                            tbl = ui.table(
                                columns=[
                                    {"name": c, "label": c, "field": c}
                                    for c in columns
                                ],
                                rows=all_rows,
                                row_key=columns[0] if columns else None,
                            ).classes("w-full").props("flat bordered")

                            if has_more:
                                offset = [_BROWSE_PAGE_SIZE]
                                loading = [False]
                                done = [False]

                                async def load_more():
                                    if loading[0] or done[0]:
                                        return
                                    loading[0] = True
                                    try:
                                        need = await ui.run_javascript(
                                            "window._webduckNeedMore || false",
                                            timeout=2,
                                        )
                                        if not need:
                                            return
                                        ui.run_javascript(
                                            "window._webduckNeedMore = false"
                                        )
                                        new_offset = offset[0]
                                        q2 = (
                                            f'SELECT * FROM "{name}"'
                                            f" LIMIT {_BROWSE_PAGE_SIZE}"
                                            f" OFFSET {new_offset}"
                                        )
                                        res2 = await asyncio.to_thread(
                                            _storage.execute_query, proj, db, q2
                                        )
                                        if res2.get("success"):
                                            new_rows = [
                                                dict(zip(columns, r))
                                                for r in res2.get("rows", [])
                                            ]
                                            if new_rows:
                                                all_rows.extend(new_rows)
                                                tbl.rows = all_rows
                                                tbl.update()
                                                offset[0] = new_offset + len(
                                                    new_rows
                                                )
                                                if (
                                                    len(all_rows) >= total
                                                    or len(new_rows) < _BROWSE_PAGE_SIZE
                                                ):
                                                    done[0] = True
                                                status_label.text = _(
                                                    "total_rows"
                                                ) % total
                                            else:
                                                done[0] = True
                                    finally:
                                        loading[0] = False

                                _browse_timer[0] = ui.timer(
                                    0.4, load_more, active=True
                                )

                                ui.run_javascript("""
                                setTimeout(function() {
                                    var tables = document.querySelectorAll('.q-table');
                                    var lastTable = tables[tables.length - 1];
                                    if (!lastTable) return;
                                    var c = lastTable.closest('.q-card') || lastTable.parentElement;
                                    c.style.maxHeight = '70vh';
                                    c.style.overflowY = 'auto';
                                    c.addEventListener('scroll', function() {
                                        if (c.scrollTop + c.clientHeight >= c.scrollHeight - 100) {
                                            window._webduckNeedMore = true;
                                        }
                                    });
                                }, 200);
                                """)

                            # ── Cell editing ──────────────────────
                            type_res = _storage.execute_query(
                                proj, db,
                                "SELECT column_name, data_type "
                                "FROM information_schema.columns "
                                f"WHERE table_name = '{name}' "
                                "AND table_schema = 'main'",
                            )
                            col_types = {}
                            if type_res.get("success"):
                                for row in type_res["rows"]:
                                    col_types[row[0]] = row[1]

                            _VALID_CAST = {
                                "VARCHAR", "INTEGER", "BIGINT",
                                "SMALLINT", "TINYINT", "DOUBLE",
                                "FLOAT", "DECIMAL", "DATE",
                                "TIMESTAMP", "BOOLEAN", "UUID",
                            }

                            ui.add_css("""
                                .q-table tbody td:hover {
                                    background: rgba(255,213,79,0.1) !important;
                                    cursor: pointer;
                                }
                            """)

                            pk_col = columns[0] if columns else None
                            if pk_col and pk_col in col_types:
                                ui.run_javascript("""
                                setTimeout(function() {
                                    var ts = document.querySelectorAll('.q-table');
                                    var t = ts[ts.length - 1];
                                    if (!t) return;
                                    t.addEventListener('dblclick', function(e) {
                                        var td = e.target.closest('td');
                                        if (!td) return;
                                        var tr = td.closest('tr');
                                        if (!tr) return;
                                        var ri = Array.from(
                                            t.querySelectorAll('tbody tr')
                                        ).indexOf(tr);
                                        var hi = t.querySelectorAll('thead th');
                                        var ci = Array.from(
                                            tr.querySelectorAll('td')
                                        ).indexOf(td);
                                        var cn = hi[ci]
                                            ? hi[ci].textContent.trim() : '';
                                        var ov = td.textContent.trim();
                                        window._eci = JSON.stringify(
                                            {r:ri, c:cn, v:ov}
                                        );
                                    });
                                }, 300);
                                """)

                                async def _check_edit():
                                    info = await ui.run_javascript(
                                        "window._eci || null", timeout=1,
                                    )
                                    if not info:
                                        return
                                    ui.run_javascript("window._eci = null")
                                    d = json.loads(info)
                                    ri, cn, ov = d["r"], d["c"], d["v"]
                                    if cn not in col_types:
                                        ui.notification(
                                            "Unknown column",
                                            type="warning",
                                        )
                                        return
                                    ct = col_types[cn]
                                    if ct not in _VALID_CAST:
                                        ui.notification(
                                            "Column type not editable",
                                            type="warning",
                                        )
                                        return

                                    with ui.dialog() as dlg, ui.card().style(
                                        f"background: {_BG_CARD};"
                                        " min-width: 320px;"
                                    ):
                                        ui.label(cn).style(
                                            f"color: {_YELLOW}"
                                        )
                                        inp = ui.input(value=ov).classes(
                                            "w-full"
                                        )
                                        with ui.row().classes(
                                            "w-full gap-2 justify-end mt-2"
                                        ):
                                            ui.button(
                                                _("cancel"),
                                                on_click=dlg.close,
                                            ).props("flat color=grey")

                                            async def _save():
                                                nv = inp.value
                                                if nv == ov:
                                                    dlg.close()
                                                    return
                                                # ── validate ──
                                                import re as _re
                                                _ok = True
                                                if ct in ("INTEGER", "BIGINT", "SMALLINT", "TINYINT"):
                                                    _ok = _re.fullmatch(r"-?\d+", nv) is not None
                                                elif ct in ("DOUBLE", "FLOAT", "DECIMAL"):
                                                    _ok = _re.fullmatch(r"-?\d+(\.\d+)?", nv) is not None
                                                elif ct == "BOOLEAN":
                                                    _ok = nv.lower() in ("true", "false", "1", "0")
                                                elif ct == "DATE":
                                                    _ok = _re.fullmatch(r"\d{4}-\d{2}-\d{2}", nv) is not None
                                                elif ct == "TIMESTAMP":
                                                    _ok = _re.fullmatch(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}", nv) is not None
                                                if not _ok:
                                                    ui.notification(
                                                        _("invalid_value") % (nv, ct),
                                                        type="warning",
                                                    )
                                                    return
                                                sql = (
                                                    f'UPDATE "{name}"'
                                                    f' SET "{cn}" = CAST(?'
                                                    f" AS {ct})"
                                                    f' WHERE "{pk_col}" = ?'
                                                )
                                                pk_val = all_rows[ri][pk_col]
                                                r = await asyncio.to_thread(
                                                    _storage.execute_query,
                                                    proj, db, sql,
                                                    params=[nv, pk_val],
                                                    read_only=False,
                                                )
                                                if r.get("success"):
                                                    all_rows[ri][cn] = nv
                                                    tbl.rows = list(all_rows)
                                                    tbl.update()
                                                    ui.notification(
                                                        _("updated"),
                                                        type="positive",
                                                    )
                                                    dlg.close()
                                                else:
                                                    ui.notification(
                                                        r.get(
                                                            "error",
                                                            "Update failed",
                                                        ),
                                                        type="negative",
                                                    )

                                            ui.button(
                                                _("save"), on_click=_save,
                                            ).props("flat color=positive")
                                    dlg.open()

                                _edit_timer[0] = ui.timer(
                                    0.5, _check_edit, active=True,
                                )

                        else:
                            if obj_type == "indexes":
                                q = f"SELECT schema_name, index_name, table_name, is_unique, is_primary, expressions, sql FROM duckdb_indexes() WHERE index_name = '{name}'"
                            elif obj_type == "sequences":
                                q = f"SELECT schema_name, sequence_name, start_value, min_value, max_value, increment_by, cycle, last_value, sql FROM duckdb_sequences() WHERE sequence_name = '{name}'"
                            elif obj_type == "macros":
                                q = f"SELECT schema_name, function_name, function_type, return_type, parameters, parameter_types, macro_definition FROM duckdb_functions() WHERE function_name = '{name}' AND function_type = 'macro'"
                            else:
                                ui.label(_("error")).style(f"color: {_TEXT_DIM}")
                                return

                            res = _storage.execute_query(proj, db, q)
                            if not res.get("success"):
                                ui.label(res.get("error", "")).style(
                                    f"color: #f44336"
                                )
                                return

                            columns = res.get("columns", [])
                            rows_raw = res.get("rows", [])
                            if not columns:
                                ui.label(_("no_data_found")).style(
                                    f"color: {_TEXT_DIM}"
                                )
                                return

                            rows = [
                                {k: ", ".join(v) if isinstance(v, list) else v
                                 for k, v in dict(zip(columns, row)).items()}
                                for row in rows_raw
                            ]
                            ui.table(
                                columns=[
                                    {"name": c, "label": c, "field": c}
                                    for c in columns
                                ],
                                rows=rows,
                                row_key=columns[0] if columns else None,
                            ).classes("w-full").props("flat bordered")

                ui.tree(
                    list(tree_data.values()),
                    on_select=on_tree_click,
                ).style(
                    f"color: {_TEXT_SOFT}; font-size: 0.85em;"
                ).classes("q-tree--dense")

        project_select.on_value_change(load_tree)
        database_select.on_value_change(load_tree)
        load_tree()


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
