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

"""Trash page — restore soft-deleted projects/databases, or empty the trash.

Soft-deleted projects and databases land here instead of being removed for
good. Every entry can be restored into its original location; when a same-
named live project or database already exists, the user decides between
cancelling and overwriting (the live object then moves into the trash itself,
so nothing is ever permanently deleted). Emptying the trash is destructive
and therefore guarded by a confirmation dialog.
"""

import asyncio

from nicegui import app as nicegui_app
from nicegui import ui

from webduck.pages import context as ctx
from webduck.pages.context import TEXT_SOFT, YELLOW_LIGHT
from webduck.pages.ui_helpers import (
    apply_dark_theme,
    make_drawer,
    make_footer,
    make_header,
)


def _fmt_bytes(num: int) -> str:
    """Format a byte count as a human-readable string (decimal units)."""
    value = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1000 or unit == "TB":
            return f"{int(value)} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1000
    return f"{num} B"


def register():
    """Register the ``/trash`` page route with NiceGUI."""
    from webduck.i18n import get_user_translator

    @ui.page("/trash")
    def trash_page():
        _ = get_user_translator()
        apply_dark_theme()
        ui.page_title(f"WebDuck {ctx.version} — Trash")

        # Auth guard: redirect to login if no session token exists.
        if "token" not in nicegui_app.storage.user:
            ui.navigate.to("/login")
            return

        # Show a flash message queued before a page reload (e.g. after a
        # successful restore or emptying the trash). A plain ui.notify()
        # would be wiped by the following reload.
        flash = nicegui_app.storage.user.pop("flash", None)
        if flash:
            ui.notify(flash, type="positive")

        make_header(_, _("trash"))
        make_drawer(_)
        make_footer(_)

        # ── Restore entry with conflict detection ──────────
        # Asks the user before overwriting an existing live project/database.
        def ask_overwrite(result: dict, trash_name: str):
            with ui.dialog() as dlg, ui.card().classes(
                "items-center gap-4"
            ).style(
                "background: #1E1E1E; border-radius: 12px; "
                "padding: 24px 32px;"
            ):
                if result["type"] == "database":
                    ui.label(
                        _("restore_conflict_db").format(
                            result["database"], result["project"]
                        )
                    ).style(f"color: {TEXT_SOFT}")
                else:
                    ui.label(
                        _("restore_conflict_project").format(result["project"])
                    ).style(f"color: {TEXT_SOFT}")
                ui.label(_("restore_conflict_hint")).classes(
                    "text-caption"
                ).style("color: #999; max-width: 420px; text-align: center;")
                with ui.row().classes("gap-2"):
                    ui.button(
                        _("cancel"),
                        on_click=dlg.close,
                    ).props("outline color=grey").classes("border-button")

                    async def do_overwrite():
                        dlg.close()
                        if result["type"] == "database":
                            res = await asyncio.to_thread(
                                ctx.storage.restore_database,
                                trash_name,
                                True,
                            )
                        else:
                            res = await asyncio.to_thread(
                                ctx.storage.restore_project,
                                trash_name,
                                True,
                            )
                        if res.get("success"):
                            nicegui_app.storage.user["flash"] = _("restore_success")
                            ui.navigate.reload()
                        else:
                            ui.notify(
                                res.get("error") or _("error"),
                                type="negative",
                            )

                    ui.button(
                        _("overwrite"),
                        on_click=do_overwrite,
                    ).props("outline color=amber").classes("border-button")
            dlg.open()

        def restore_entry(entry: dict):
            async def do_restore():
                trash_name = entry["name"]
                if entry["type"] == "database":
                    result = await asyncio.to_thread(
                        ctx.storage.restore_database, trash_name
                    )
                else:
                    result = await asyncio.to_thread(
                        ctx.storage.restore_project, trash_name
                    )
                if result.get("success"):
                    nicegui_app.storage.user["flash"] = _("restore_success")
                    ui.navigate.reload()
                elif result.get("conflict"):
                    ask_overwrite(result, trash_name)
                else:
                    ui.notify(
                        result.get("error") or _("error"), type="negative"
                    )

            return do_restore

        # ── Page title + empty-trash action ────────────────
        with ui.card().classes("w-full").style("margin-top: 4px"):
            with ui.row().classes("w-full items-center gap-4"):
                ui.label(_("trash_title")).classes("text-h5").style(
                    f"color: {YELLOW_LIGHT}"
                )
                ui.space()

                async def empty_trash():
                    with ui.dialog() as dlg, ui.card().classes(
                        "items-center gap-4"
                    ).style(
                        "background: #1E1E1E; border-radius: 12px; "
                        "padding: 24px 32px;"
                    ):
                        ui.label(_("confirm_empty_trash")).style(
                            f"color: {TEXT_SOFT}"
                        )
                        with ui.row().classes("gap-2"):
                            ui.button(
                                _("cancel"),
                                on_click=dlg.close,
                            ).props("outline color=grey").classes(
                                "border-button"
                            )

                            def do_empty():
                                dlg.close()
                                n = ctx.storage.empty_trash()
                                nicegui_app.storage.user["flash"] = _("trash_emptied").format(n)
                                ui.navigate.reload()

                            ui.button(
                                _("empty_trash"),
                                on_click=do_empty,
                            ).props("outline color=red").classes(
                                "border-button"
                            )
                    dlg.open()

                ui.button(
                    icon="delete_sweep",
                    on_click=empty_trash,
                ).props("outline color=red").tooltip(
                    _("empty_trash")
                ).props("tooltip-position=top")

        entries = ctx.storage.list_trash()

        if not entries:
            with ui.card().classes("w-full q-mt-sm"):
                ui.label(_("trash_empty")).classes("text-caption")
            return

        # ── Trash entries ──────────────────────────────────
        for entry in entries:
            deleted_at = entry["deleted_at"].replace("T", " ")
            with ui.card().classes("w-full q-mt-sm"):
                with ui.row().classes("w-full items-center gap-2"):
                    if entry["type"] == "project":
                        # Folder icon — same visual as the projects page.
                        ui.html(
                            '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" '
                            'stroke="#FFE082" stroke-width="2" stroke-linecap="round" '
                            'stroke-linejoin="round" style="vertical-align: middle;">'
                            '<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 '
                            '2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>'
                        )
                        ui.label(entry["project"]).classes("text-h6").style(
                            f"color: {YELLOW_LIGHT}"
                        )
                        ui.label(_("project")).classes("text-caption")
                    else:
                        # Database cylinder icon — same visual as the projects page.
                        ui.html(
                            '<svg width="16" height="16" viewBox="0 0 24 24" '
                            'fill="none" stroke="#999" stroke-width="2" '
                            'stroke-linecap="round" stroke-linejoin="round" '
                            'style="vertical-align: middle;">'
                            '<ellipse cx="12" cy="5" rx="9" ry="3"/>'
                            '<path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/>'
                            '<path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/></svg>'
                        )
                        ui.label(entry["database"]).classes("text-body1")
                        ui.label(
                            f"{_('project')}: {entry['project']}"
                        ).classes("text-caption").style("color: #888;")
                    ui.space()
                    ui.label(_fmt_bytes(entry["size"])).classes(
                        "text-caption"
                    ).style("color: #888; font-size: 0.75em;")
                    ui.label(
                        f"{_('deleted_at')}: {deleted_at[:16]}"
                    ).classes("text-caption").style(
                        "color: #888; font-size: 0.75em;"
                    )
                    ui.button(
                        on_click=restore_entry(entry),
                    ).props(
                        'icon="restore" flat dense'
                    ).style("color: #FFD54F;").tooltip(
                        _("restore")
                    ).props("tooltip-position=top")

                # A trashed project keeps its databases — list them below.
                if entry["type"] == "project" and entry.get("databases"):
                    with ui.row().classes("items-center gap-2 q-pl-1"):
                        ui.html(
                            '<svg width="14" height="14" viewBox="0 0 24 24" '
                            'fill="none" stroke="#999" stroke-width="2" '
                            'stroke-linecap="round" stroke-linejoin="round" '
                            'style="vertical-align: middle;">'
                            '<ellipse cx="12" cy="5" rx="9" ry="3"/>'
                            '<path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/>'
                            '<path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/></svg>'
                        )
                        ui.label(
                            f"{_('databases')}: {', '.join(entry['databases'])}"
                        ).classes("text-caption").style("color: #888;")
