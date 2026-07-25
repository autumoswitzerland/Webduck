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

"""Dashboard page — landing page showing server status and project/database counts.

Displays three stat cards in a horizontal row: server online status,
total number of projects, and total number of databases across all
projects.
"""

from nicegui import app as nicegui_app
from nicegui import ui

from webduck.pages import context as ctx
from webduck.pages.context import YELLOW_LIGHT
from webduck.pages.ui_helpers import (
    apply_dark_theme,
    make_drawer,
    make_footer,
    make_header,
)


def register():
    """Register the ``/`` (dashboard) page route with NiceGUI."""
    from webduck.i18n import get_user_translator

    @ui.page("/")
    def dashboard_page():
        _ = get_user_translator()
        apply_dark_theme()
        ui.page_title(f"WebDuck {ctx.version} — Dashboard")

        # Auth guard: redirect to login if no session token exists.
        if "token" not in nicegui_app.storage.user:
            ui.navigate.to("/login")
            return

        make_header(_)
        make_drawer(_)
        make_footer(_)

        # -- Page title card
        with ui.card().classes("w-full"):
            ui.label(_("dashboard_title")).classes(
                "text-h5"
            ).style(f"color: {YELLOW_LIGHT}")

            # Load project and database counts; gracefully degrade on error.
            try:
                projects = ctx.storage.list_projects()
                total_databases = sum(
                    len(ctx.storage.list_databases(p)) for p in projects
                )
            except Exception as e:
                from webduck.logging import log_error
                log_error(f"Dashboard load error: {e}")
                projects = []
                total_databases = 0

            # -- Three stat cards laid out in a horizontal row.
            with ui.row().classes("w-full gap-4"):
                # Card 1: Server status — always shows "Online" if the page loaded.
                with ui.card().classes("flex-grow justify-center items-center").style(
                    "background: #1c1c1c; border: 1px solid #333"
                ):
                    ui.badge(
                        _("online"), color="green"
                    ).classes("text-h5 q-pa-sm q-px-lg")
                    ui.label(_("server_status")).classes("text-h6")

                # Card 2: Total number of projects.
                with ui.card().classes("flex-grow justify-center items-center").style(
                    "background: #1c1c1c; border: 1px solid #333"
                ):
                    ui.label(str(len(projects))).classes(
                        "text-h3"
                    ).style(f"color: {YELLOW_LIGHT}")
                    ui.label(_("total_projects")).classes("text-h6")

                # Card 3: Total number of databases (sum across all projects).
                with ui.card().classes("flex-grow justify-center items-center").style(
                    "background: #1c1c1c; border: 1px solid #333"
                ):
                    ui.label(str(total_databases)).classes(
                        "text-h3"
                    ).style(f"color: {YELLOW_LIGHT}")
                    ui.label(_("total_databases")).classes("text-h6")
