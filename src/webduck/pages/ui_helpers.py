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

"""Shared UI components — header, drawer, footer, dark theme."""

from nicegui import app as nicegui_app
from nicegui import ui

from webduck.pages import context as ctx
from webduck.pages.context import (
    NAV_COLOR,
    YELLOW,
)

_drawer = None


def apply_dark_theme():
    """Enable dark mode and inject custom yellow-accent CSS."""
    from webduck.main import _DARK_CSS
    ui.dark_mode(True)
    ui.add_head_html(_DARK_CSS)
    ui.add_css('''
        .q-separator--vertical.nicegui-separator {
            width: 1px !important;
        }
    ''', shared=True)


def do_logout():
    nicegui_app.storage.user.clear()
    ui.navigate.to("/login")


def make_header(_, page_title: str = ""):
    """Shared header with versioned title, icon."""
    title_text = f"WebDuck {ctx.version}"
    if page_title:
        title_text += f" — {page_title}"

    with ui.header().classes("bg-[#1a1a1a] items-center"):
        with ui.row().classes("items-center gap-2"):
            if ctx.icon:
                ui.html(
                    f'<img src="/static/{ctx.icon}" alt="icon" '
                    f'style="height:28px; vertical-align:middle;">'
                )
            ui.label(title_text).classes("text-h5 text-bold").style(
                f"color: {YELLOW}"
            )
        ui.space()
        with ui.row().classes("items-center gap-4"):
            ui.button(
                icon="menu",
                on_click=lambda: _drawer.toggle() if _drawer else None
            ).props("outline color=grey").classes("border-button")


def make_drawer(_):
    """Shared left navigation drawer."""
    global _drawer
    with ui.left_drawer().classes("bg-[#1a1a1a]").props("bordered width=200") as _drawer:
        
        """
        ui.item_label(_("navigation")).classes(
            "text-h6 text-bold q-mb-xs"
        ).style(f"color: {YELLOW}")
        """
        
        for label, target, icon in [
            (_("dashboard"), "/", "dashboard"),
            (_("projects"), "/projects", "folder_open"),
            (_("browse"), "/browse", "account_tree"),
            (_("sql_editor"), "/query", "code"),
            (_("import_export"), "/import", "upload_file"),
        ]:
            with ui.item(
                on_click=lambda t=target: ui.navigate.to(t)
            ).style(f"color: {NAV_COLOR}").props("clickable"):
                with ui.item_section().props("side"):
                    ui.icon(icon).style(f"color: {NAV_COLOR}")
                ui.item_section(label)

        with ui.item(
            on_click=lambda: ui.run_javascript('window.open("/docs", "_blank")')
        ).style("color: #2296f3;").props("clickable"):
            with ui.item_section().props("side"):
                ui.icon("api").style("color: #2296f3;")
            ui.item_section("API")

        with ui.item(
            on_click=lambda: ui.run_javascript(f'window.open("{ctx.DOCS_URL}", "_blank")')
        ).style("color: #2296f3;").props("clickable"):
            with ui.item_section().props("side"):
                ui.icon("menu_book").style("color: #2296f3;")
            ui.item_section("Docs")

        with ui.item(
            on_click=do_logout
        ).style("color: #f54336;").props("clickable"):
            with ui.item_section().props("side"):
                ui.icon("logout").style("color: #f54336;")
            ui.item_section(_("logout"))


def make_footer(_):
    """Shared footer for all pages."""
    from webduck.pages.context import AUTUMO_URL, YELLOW_DARKER
    with ui.footer().classes("bg-[#040d12] items-center").style("border-top: 0.9px solid #0c2736;"):
        with ui.row().classes("items-center gap-4 w-full justify-center"):

            with ui.row().classes("items-center gap-1"):
                ui.html(
                    '<img src="/static/footer-logo.png" style="height: 16px; width: auto; filter: brightness(0.65);">'
                )
                ui.html(
                    f'<span style="color: #666; font-size: 0.9em;">'
                    f'&copy; 2026 <a href="{AUTUMO_URL}" target="_blank" '
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
                ctx.DOCS_URL,
                new_tab=True
            ).style("color: #666; font-size: 0.9em; text-decoration: none;")

            ui.label("|").style("font-size: 0.9em; color: #444;")

            ui.label("GitHub").style("color: #666; font-size: 0.9em; cursor: pointer;").on(
                "click", lambda: ui.run_javascript('window.open("https://github.com/autumo/webduck", "_blank")')
            )

            ui.label("|").style("font-size: 0.9em; color: #444;")

            username = nicegui_app.storage.user.get("username", "")
            with ui.row().classes("items-center gap-1"):
                ui.label(f"{_('username')}:").style("color: #666; font-size: 0.9em;")
                ui.label(username).style(f"color: {YELLOW_DARKER}; font-size: 0.9em;")
