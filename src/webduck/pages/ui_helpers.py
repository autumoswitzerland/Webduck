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

"""Shared UI components — header, drawer, footer, dark theme.

Every authenticated page calls apply_dark_theme(), make_header(),
make_drawer(), and make_footer() to get a consistent look and feel.
"""

from nicegui import app as nicegui_app
from nicegui import ui

from webduck.pages import context as ctx
from webduck.pages.context import (
    NAV_COLOR,
    YELLOW,
)

# Holds the left-drawer instance so the header menu button can toggle it.
_drawer = None


def apply_dark_theme():
    """Enable Quasar dark mode and inject the project-wide dark CSS.

    Imports the _DARK_CSS block from main.py (which sets the global
    ``box-shadow: none`` rule, background colors, etc.) and adds a small
    fix for NiceGUI vertical separators.
    """
    from webduck.main import _DARK_CSS
    ui.dark_mode(True)
    ui.add_head_html(_DARK_CSS)
    # Force vertical separators to 1 px so they don't appear thick in dark mode.
    ui.add_css('''
        .q-separator--vertical.nicegui-separator {
            width: 1px !important;
        }
    ''', shared=True)


def do_logout():
    """Clear user session and redirect to the login page."""
    nicegui_app.storage.user.clear()
    ui.navigate.to("/login")


def make_header(_, page_title: str = ""):
    """Build the shared top header bar.

    Left side  — project icon (if configured) + version string + page title.
    Right side — hamburger button that toggles the navigation drawer.
    """
    title_text = f"WebDuck {ctx.version}"
    if page_title:
        title_text += f" — {page_title}"

    with ui.header().classes("bg-[#1a1a1a] items-center"):
        # -- Title row: optional icon + "WebDuck vX.Y.Z — Page Title"
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
        # -- Menu toggle button (right-aligned)
        with ui.row().classes("items-center gap-4"):
            ui.button(
                icon="menu",
                on_click=lambda: _drawer.toggle() if _drawer else None
            ).props("outline color=grey").classes("border-button")


def make_drawer(_):
    """Build the shared left navigation drawer.

    Contains navigation links (Dashboard, Projects, Browse, SQL Editor,
    Import/Export), external links (API docs, documentation), and a
    logout button.  The drawer instance is stored in the module-level
    ``_drawer`` variable so the header menu button can toggle it.
    """
    global _drawer
    with ui.left_drawer().classes("bg-[#1a1a1a]").props("bordered width=200") as _drawer:

        """
        ui.item_label(_("navigation")).classes(
            "text-h6 text-bold q-mb-xs"
        ).style(f"color: {YELLOW}")
        """

        # -- Navigation links: each item navigates to its target route.
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

        # -- External link: opens the Swagger/OpenAPI docs in a new tab.
        with ui.item(
            on_click=lambda: ui.run_javascript('window.open("/docs", "_blank")')
        ).style("color: #2296f3;").props("clickable"):
            with ui.item_section().props("side"):
                ui.icon("api").style("color: #2296f3;")
            ui.item_section("API")

        # -- External link: opens the project documentation in a new tab.
        with ui.item(
            on_click=lambda: ui.run_javascript(f'window.open("{ctx.DOCS_URL}", "_blank")')
        ).style("color: #2296f3;").props("clickable"):
            with ui.item_section().props("side"):
                ui.icon("menu_book").style("color: #2296f3;")
            ui.item_section("Docs")

        # -- Logout: clears session and redirects to /login.
        with ui.item(
            on_click=do_logout
        ).style("color: #f54336;").props("clickable"):
            with ui.item_section().props("side"):
                ui.icon("logout").style("color: #f54336;")
            ui.item_section(_("logout"))


def make_footer(_):
    """Build the shared bottom footer bar.

    Displays copyright notice, quick links (API, Docs, GitHub, Donate),
    and the currently logged-in username.  All links open in new tabs.
    """
    from webduck.pages.context import AUTUMO_URL, DONATE_URL, YELLOW_DARKER
    with ui.footer().classes("bg-[#040d12] items-center").style("border-top: 0.9px solid #0c2736;"):
        with ui.row().classes("items-center gap-4 w-full justify-center"):

            # -- Copyright block: autumo logo + "© 2026 autumo GmbH — Licensed under AGPLv3"
            with ui.row().classes("items-center gap-1"):
                ui.html(
                    '<img src="/static/footer-logo.png" style="height: 16px; width: auto; filter: brightness(0.65);">'
                )
                ui.html(
                    f'<span style="color: #666; font-size: 0.9em;">'
                    f'&copy; 2026 <a href="{AUTUMO_URL}" target="_blank" '
                    f'style="color: #666; text-decoration: none;">autumo GmbH</a>'
                    f' &mdash; Licensed under AGPLv3'
                    f'</span>'
                )

            ui.label("|").style("color: #444;")

            # -- Landing page.
            ui.label("Website").style("color: #666; font-size: 0.9em; cursor: pointer;").on(
                "click", lambda: ui.run_javascript('window.open("https://webduck.autumo.ch/", "_blank")')
            ).on("mouseover", lambda e: e.sender.style("color: #444")).on(
                "mouseout", lambda e: e.sender.style("color: #666")
            )

            ui.label("|").style("font-size: 0.9em; color: #444;")

            # -- GitHub link: opens the source repository.
            ui.label("GitHub").style("color: #666; font-size: 0.9em; cursor: pointer;").on(
                "click", lambda: ui.run_javascript('window.open("https://github.com/autumoswitzerland/Webduck", "_blank")')
            ).on("mouseover", lambda e: e.sender.style("color: #444")).on(
                "mouseout", lambda e: e.sender.style("color: #666")
            )

            ui.label("|").style("font-size: 0.9em; color: #444;")

            # -- Donate link: opens the PayPal donation page.
            ui.label("Donate").style("color: #666; font-size: 0.9em; cursor: pointer;").on(
                "click", lambda: ui.run_javascript(f'window.open("{DONATE_URL}", "_blank")')
            ).on("mouseover", lambda e: e.sender.style("color: #444")).on(
                "mouseout", lambda e: e.sender.style("color: #666")
            )

            ui.label("|").style("font-size: 0.9em; color: #444;")

            # -- Logged-in username display (read from NiceGUI user storage).
            username = nicegui_app.storage.user.get("username", "")
            with ui.row().classes("items-center gap-1"):
                ui.label(f"{_('username')}:").style("color: #666; font-size: 0.9em;")
                ui.label(username).style(f"color: {YELLOW_DARKER}; font-size: 0.9em;")
