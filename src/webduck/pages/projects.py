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

"""Projects page — CRUD for projects and databases with drag-and-drop reordering.

Users can create/delete projects, create/delete databases within projects,
set per-database API passwords, and reorder projects by dragging the
6-dot grip handle.  Reorder state is persisted via a POST to
``/api/reorder-projects``.
"""

import asyncio
import secrets
from urllib.parse import quote

from nicegui import app as nicegui_app
from nicegui import ui

from webduck.auth.manager import ProjectAuth
from webduck.pages import context as ctx
from webduck.pages.context import (
    BG_CARD,
    TEXT_SOFT,
    YELLOW,
    YELLOW_LIGHT,
)
from webduck.pages.ui_helpers import (
    apply_dark_theme,
    make_drawer,
    make_footer,
    make_header,
    require_user,
)


def _fmt_bytes(num: int) -> str:
    """Format a byte count as a human-readable string (e.g. '1.2 GB').

    Uses decimal units (1000-based), matching what file managers such as
    the macOS Finder and Windows Explorer display.
    """
    value = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1000 or unit == "TB":
            return f"{int(value)} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1000
    return f"{num} B"


# Filled database-cylinder icon with an add-plus knockout, mirroring the
# filled project icon (create_new_folder). The cylinder is filled amber and
# the plus is punched out of it via an evenodd sub-path. Inlined as a data
# URL because Material Icons has no "database" glyph; the amber fill matches
# the "wd-icon-amber" class applied to the button.
_DB_PLUS_ICON = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="#FFC107">'
    '<path fill-rule="evenodd" d="'
    'M3 5.5C3 3.57 7.03 2 12 2C16.97 2 21 3.57 21 5.5V18.5'
    'C21 20.43 16.97 22 12 22C7.03 22 3 20.43 3 18.5Z'
    'M14 8.75h2v3h3v2h-3v3h-2v-3h-3v-2h3z'
    '"/>'
    "</svg>"
)
_DB_PLUS_ICON_URL = (
    "data:image/svg+xml;utf8," + quote(_DB_PLUS_ICON)
)


def register():
    """Register the ``/projects`` page route with NiceGUI."""
    from webduck.i18n import get_user_translator

    @ui.page("/projects")
    def projects_page():
        _ = get_user_translator()
        apply_dark_theme()
        ui.page_title(f"WebDuck {ctx.version} — Projects")

        # Auth guard: redirect to login if the session is invalid or the
        # user account no longer exists (e.g. deleted while logged in).
        if not require_user():
            return

        # Show a flash message queued before a page reload (e.g. after a
        # successful create/delete). A plain ui.notify() would be wiped by
        # the following reload, so the message survives it via user storage.
        flash = nicegui_app.storage.user.pop("flash", None)
        if flash:
            ui.notify(flash, type="positive")

        make_header(_)
        make_drawer(_)
        make_footer(_)

        from webduck.main import (
            COMPRESS_FRAGMENTATION_THRESHOLD,
            COMPRESS_MIN_DB_SIZE,
        )

        # Background fragmentation check: highlights a compress icon in amber
        # when compaction is recommended, without blocking the page render.
        # Only databases above COMPRESS_MIN_DB_SIZE are considered at all —
        # compacting small databases is not worth the effort.
        async def _update_compress_icon(p: str, d: str, btn, tip, size_label=None):
            try:
                size = await asyncio.to_thread(
                    ctx.storage.database_size, p, d
                )
                # Keep the displayed database size in sync (e.g. after a
                # successful compact the file shrank).
                if size is not None and size_label is not None:
                    size_label.set_text(_fmt_bytes(size))
                if size is None or size < COMPRESS_MIN_DB_SIZE:
                    return
                frag = await asyncio.to_thread(
                    ctx.storage.fragmentation, p, d
                )
            except Exception:
                return
            if frag is None:
                return
            if frag >= COMPRESS_FRAGMENTATION_THRESHOLD:
                btn.classes("wd-icon-amber")
                tip.set_text(_("compress_recommended"))
            else:
                btn.classes(remove="wd-icon-amber")
                tip.set_text(_("compress_database"))

        # ── Page title ─────────────────────────────────────
        with ui.card().classes("w-full").style("margin-top: 4px"):
            ui.label(_("projects_title")).classes(
                "text-h5"
            ).style(f"color: {YELLOW_LIGHT}")

        # ── Create project (own card) ──────────────────────
        with ui.card().classes("w-full q-mt-sm"):
            ui.label(_("create_project")).classes(
                "text-subtitle1 text-bold q-mb-sm"
            ).style(f"color: {YELLOW}")
            with ui.row().classes("w-full items-center gap-4"):
                project_name = ui.input(
                    _("project_name")
                ).classes("flex-grow")

                async def create_project():
                    if not require_user():
                        return
                    if project_name.value:
                        ok = ctx.storage.create_project(
                            project_name.value
                        )
                        if ok:
                            nicegui_app.storage.user["flash"] = _("success")
                            ui.navigate.reload()
                        else:
                            ui.notify(
                                _("error"),
                                type="negative",
                            )

                ui.button(
                    on_click=create_project,
                ).props(
                    'icon="create_new_folder" flat dense'
                ).classes("wd-icon-blue").tooltip(
                    _("create_project")
                ).props("tooltip-position=top")
                project_name.on(
                    "keydown.enter",
                    create_project,
                )

        # ── Project list ───────────────────────────────────
        try:
            projects = ctx.storage.list_projects()
        except Exception as e:
            from webduck.logging import log_error
            log_error(f"Projects list error: {e}")
            projects = []

        if projects:
            # Sortable container — project cards can be reordered via drag & drop.
            sortable = ui.column().classes("w-full")
            with sortable:
                for project in projects:
                    with ui.card().classes(
                        "w-full q-mt-sm project-card"
                    ).props(f'data-project="{project}"'):
                        with ui.row().classes(
                            "w-full items-center gap-2"
                        ):
                            # 6-dot grip handle SVG — only this element initiates drag.
                            ui.html(
                                '<svg class="drag-handle" '
                                'width="18" height="18" '
                                'viewBox="0 0 24 24" fill="none" '
                                'stroke="#888" stroke-width="2" '
                                'stroke-linecap="round" '
                                'stroke-linejoin="round" '
                                'style="vertical-align: middle; '
                                'cursor: grab;">'
                                '<circle cx="9" cy="6" r="1"/>'
                                '<circle cx="15" cy="6" r="1"/>'
                                '<circle cx="9" cy="12" r="1"/>'
                                '<circle cx="15" cy="12" r="1"/>'
                                '<circle cx="9" cy="18" r="1"/>'
                                '<circle cx="15" cy="18" r="1"/>'
                                '</svg>'
                            )
                            # Folder icon SVG — visual indicator for project rows.
                            ui.html(
                                '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" '
                                'stroke="#FFE082" stroke-width="2" stroke-linecap="round" '
                                'stroke-linejoin="round" style="vertical-align: middle;">'
                                '<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 '
                                '2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>'
                            )
                            ui.label(project).classes(
                                "text-h6"
                            ).style(f"color: {YELLOW_LIGHT}")
                            ui.space()

                            try:
                                dbs = ctx.storage.list_databases(project)
                            except Exception as e:
                                from webduck.logging import log_error
                                log_error(f"Databases list error [{project}]: {e}")
                                dbs = []

                            ui.label(
                                f"{len(dbs)} {_('databases')}"
                            ).classes("text-caption")

                            # Delete button with confirmation dialog.
                            async def delete_project(p=project):
                                if not require_user():
                                    return
                                with ui.dialog() as dlg, ui.card().classes(
                                    "items-center gap-4"
                                ).style(
                                    "background: #1E1E1E; border-radius: 12px; "
                                    "padding: 24px 32px;"
                                ):
                                    ui.label(_("confirm_delete_project")).style(
                                        f"color: {TEXT_SOFT}"
                                    )
                                    with ui.row().classes("gap-2"):
                                        ui.button(
                                            _("cancel"),
                                            on_click=dlg.close,
                                        ).props("outline color=grey").classes(
                                            "border-button"
                                        )

                                        def do_delete():
                                            if not require_user():
                                                return
                                            dlg.close()
                                            if ctx.storage.trash_project(p):
                                                nicegui_app.storage.user["flash"] = _("moved_to_trash")
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
                                on_click=delete_project,
                            ).props(
                                'icon="delete_outline" flat dense'
                            ).classes("wd-icon-red").tooltip(
                                _("delete")
                            ).props("tooltip-position=top")

                        # ── Existing databases (sub-card) ──────
                        # Lists all databases within this project, with
                        # per-database password management and delete buttons.
                        dbs = ctx.storage.list_databases(project)
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
                                # Collect compress buttons so the background
                                # fragmentation check can highlight them.
                                _compress_btns: list = []
                                for db_name in dbs:
                                    with ui.row().classes(
                                        "w-full items-center gap-2"
                                    ):
                                        # Database cylinder SVG icon.
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
                                        _size = ctx.storage.database_size(
                                            project, db_name
                                        )
                                        _size_label = None
                                        if _size is not None:
                                            _size_label = ui.label(
                                                _fmt_bytes(_size)
                                            ).classes(
                                                "text-caption"
                                            ).style(
                                                "color: #888; "
                                                "font-size: 0.75em;"
                                            )
                                        # Show a lock icon if this database has an API password set.
                                        # Left-click opens a menu with the option to remove the
                                        # password again (backed by a security confirmation).
                                        _pa = ctx.project_auth or ProjectAuth(ctx.storage.data_dir)
                                        has_pw = _pa.has_database_password(
                                            project, db_name
                                        )
                                        if has_pw:
                                            async def remove_pw_confirm(
                                                p=project, d=db_name
                                            ):
                                                if not require_user():
                                                    return
                                                with ui.dialog() as dlg, ui.card().classes(
                                                    "items-center gap-4"
                                                ).style(
                                                    "background: #1E1E1E; border-radius: 12px; "
                                                    "padding: 24px 32px;"
                                                ):
                                                    ui.label(
                                                        _("confirm_remove_password").format(d)
                                                    ).style(f"color: {TEXT_SOFT}")
                                                    with ui.row().classes("gap-2"):
                                                        ui.button(
                                                            _("cancel"),
                                                            on_click=dlg.close,
                                                        ).props("outline color=grey").classes(
                                                            "border-button"
                                                        )

                                                        def do_remove():
                                                            if not require_user():
                                                                return
                                                            dlg.close()
                                                            pa = (
                                                                ctx.project_auth
                                                                or ProjectAuth(
                                                                    ctx.storage.data_dir
                                                                )
                                                            )
                                                            if pa.remove_database_password(p, d):
                                                                nicegui_app.storage.user["flash"] = _(
                                                                    "password_removed"
                                                                )
                                                                ui.navigate.reload()
                                                            else:
                                                                ui.notify(
                                                                    _("error"),
                                                                    type="negative",
                                                                )

                                                        ui.button(
                                                            _("remove_password"),
                                                            on_click=do_remove,
                                                        ).props("outline color=red").classes(
                                                            "border-button"
                                                        )
                                                dlg.open()

                                            with ui.element("div"):
                                                ui.html(
                                                    '<svg width="14" height="14" '
                                                    'viewBox="0 0 24 24" fill="none" '
                                                    'stroke="#FFD54F" stroke-width="2" '
                                                    'stroke-linecap="round" stroke-linejoin="round" '
                                                    'style="vertical-align: middle;">'
                                                    '<rect x="3" y="11" width="18" height="11" '
                                                    'rx="2" ry="2"/>'
                                                    '<path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>'
                                                )
                                                with ui.menu():
                                                    ui.menu_item(
                                                        _("change_password"),
                                                        on_click=lambda p=project, d=db_name: (
                                                            change_db_password(p, d)
                                                        ),
                                                    )
                                                    ui.menu_item(
                                                        _("remove_password"),
                                                        on_click=lambda p=project, d=db_name: (
                                                            remove_pw_confirm(p, d)
                                                        ),
                                                    ).style("color: #F44336;")
                                        ui.space()

                                        # Password change dialog: generate or set a new API password.
                                        async def change_db_password(
                                            p=project, d=db_name
                                        ):
                                            if not require_user():
                                                return
                                            with ui.dialog() as dlg, ui.card().classes(
                                                "items-center gap-4"
                                            ).style(
                                                "background: #1E1E1E; border-radius: 12px; "
                                                "padding: 24px 32px;"
                                            ):
                                                ui.label(
                                                    f"{_('api_password')} — {d}"
                                                ).style(f"color: {YELLOW}")
                                                pw_input = ui.input(
                                                    password=True,
                                                    password_toggle_button=True,
                                                ).classes("w-full").props(
                                                    "autocomplete=new-password"
                                                )

                                                def do_save():
                                                    if not require_user():
                                                        return
                                                    if pw_input.value:
                                                        pa = ctx.project_auth or ProjectAuth(
                                                            ctx.storage.data_dir
                                                        )
                                                        pa.set_database_password(
                                                            p, d, pw_input.value,
                                                        )
                                                        dlg.close()
                                                        nicegui_app.storage.user["flash"] = _("success")
                                                        ui.navigate.reload()

                                                with ui.row().classes("gap-2"):
                                                    # Generate button: fills the input with a random URL-safe token.
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

                                        # Key icon button to open the password change dialog.
                                        ui.button(
                                            on_click=change_db_password,
                                        ).props(
                                            'icon="key" flat dense'
                                        ).style("color: #888;").tooltip(
                                            _("change_password")
                                        ).props("tooltip-position=top")

                                        # Database compress with confirmation dialog.
                                        async def compress_db(
                                            p=project, d=db_name
                                        ):
                                            if not require_user():
                                                return
                                            size = ctx.storage.database_size(p, d)
                                            # Re-check the current state on click: the
                                            # background hint from page load may be stale
                                            # (DuckDB can reclaim trailing free blocks on
                                            # its own in the meantime), so a compact would
                                            # gain nothing — don't offer one then.
                                            frag = None
                                            try:
                                                if (
                                                    size is not None
                                                    and size >= COMPRESS_MIN_DB_SIZE
                                                ):
                                                    frag = await asyncio.to_thread(
                                                        ctx.storage.fragmentation, p, d
                                                    )
                                            except Exception:
                                                frag = None
                                            if (
                                                frag is not None
                                                and frag < COMPRESS_FRAGMENTATION_THRESHOLD
                                            ):
                                                for (
                                                    _p,
                                                    _d,
                                                    _btn,
                                                    _tip,
                                                    _sizelabel,
                                                ) in _compress_btns:
                                                    if (_p, _d) == (p, d):
                                                        _btn.classes(
                                                            remove="wd-icon-amber"
                                                        )
                                                        _tip.set_text(
                                                            _("compress_database")
                                                        )
                                                        if _sizelabel is not None:
                                                            _sizelabel.set_text(
                                                                _fmt_bytes(size)
                                                            )
                                                ui.notify(
                                                    _("compress_no_gain"),
                                                    type="info",
                                                )
                                                return
                                            size_label = (
                                                _fmt_bytes(size)
                                                if size is not None else "?"
                                            )
                                            with ui.dialog() as dlg, ui.card().classes(
                                                "items-center gap-4"
                                            ).style(
                                                "background: #1E1E1E; border-radius: 12px; "
                                                "padding: 24px 32px;"
                                            ):
                                                ui.label(
                                                    _("confirm_compress_database").format(
                                                        d, size_label
                                                    )
                                                ).style(f"color: {TEXT_SOFT}")
                                                with ui.row().classes("gap-2"):
                                                    ui.button(
                                                        _("cancel"),
                                                        on_click=dlg.close,
                                                    ).props("outline color=grey").classes(
                                                        "border-button"
                                                    )

                                                    async def do_compress():
                                                        if not require_user():
                                                            return
                                                        dlg.close()
                                                        # Modal spinner while the compaction runs.
                                                        with ui.dialog() as pdlg, ui.card().classes(
                                                            "items-center gap-4"
                                                        ).style(
                                                            f"background: {BG_CARD}; "
                                                            "border-radius: 12px; "
                                                            "padding: 32px 48px;"
                                                        ):
                                                            ui.spinner(
                                                                size="xl", color="amber"
                                                            )
                                                            ui.label(
                                                                _("compressing")
                                                            ).style(
                                                                f"color: {YELLOW_LIGHT}"
                                                            )
                                                        pdlg.open()
                                                        try:
                                                            result = await asyncio.to_thread(
                                                                ctx.storage.compact_database,
                                                                p,
                                                                d,
                                                            )
                                                        except Exception as e:
                                                            from webduck.logging import log_error
                                                            log_error(
                                                                f"Compress error [{p}/{d}]: {e}"
                                                            )
                                                            result = {
                                                                "success": False,
                                                                "error": str(e),
                                                            }
                                                        pdlg.close()
                                                        if result.get("success"):
                                                            # Re-check fragmentation in the
                                                            # background so the compress icon
                                                            # turns grey again after a
                                                            # successful compaction.
                                                            for (
                                                                _p,
                                                                _d,
                                                                _btn,
                                                                _tip,
                                                                _sizelabel,
                                                            ) in _compress_btns:
                                                                if (_p, _d) == (p, d):
                                                                    asyncio.create_task(
                                                                        _update_compress_icon(
                                                                            _p,
                                                                            _d,
                                                                            _btn,
                                                                            _tip,
                                                                            _sizelabel,
                                                                        )
                                                                    )
                                                            def _result_dialog(text, color):
                                                                with (
                                                                    ui.dialog() as rdlg,
                                                                    ui.card().classes(
                                                                        "items-center gap-4"
                                                                    ).style(
                                                                        "background: #1E1E1E; "
                                                                        "border-radius: 12px; "
                                                                        "padding: 24px 32px;"
                                                                    ),
                                                                ):
                                                                    ui.label(text).style(
                                                                        f"color: {color}"
                                                                    )
                                                                    ui.button(
                                                                        _("close"),
                                                                        on_click=rdlg.close,
                                                                    ).props(
                                                                        "outline color=grey"
                                                                    ).classes(
                                                                        "border-button"
                                                                    )
                                                                rdlg.open()

                                                            if result["saved_bytes"] > 0:
                                                                _result_dialog(
                                                                    _("compress_success").format(
                                                                        _fmt_bytes(
                                                                            result[
                                                                                "size_before"
                                                                            ]
                                                                        ),
                                                                        _fmt_bytes(
                                                                            result["size_after"]
                                                                        ),
                                                                        result["saved_percent"],
                                                                    ),
                                                                    YELLOW_LIGHT,
                                                                )
                                                            elif result["grew_bytes"] > 0:
                                                                _result_dialog(
                                                                    _("compress_grew").format(
                                                                        _fmt_bytes(
                                                                            result[
                                                                                "size_before"
                                                                            ]
                                                                        ),
                                                                        _fmt_bytes(
                                                                            result["size_after"]
                                                                        ),
                                                                        result["grew_percent"],
                                                                    ),
                                                                    TEXT_SOFT,
                                                                )
                                                            else:
                                                                _result_dialog(
                                                                    _("compress_no_gain"),
                                                                    TEXT_SOFT,
                                                                )
                                                        else:
                                                            ui.notify(
                                                                result.get("error")
                                                                or _("error"),
                                                                type="negative",
                                                            )

                                                    ui.button(
                                                        _("compress"),
                                                        on_click=do_compress,
                                                    ).props(
                                                        "outline color=amber"
                                                    ).classes("border-button")
                                            dlg.open()
                                        _compress_btn = ui.button(
                                            on_click=compress_db,
                                        ).props(
                                            'icon="compress" flat dense'
                                        ).style("color: #888;").tooltip(
                                            _("compress_database")
                                        ).props("tooltip-position=top")
                                        # ``tooltip()`` returns the button, not
                                        # the tooltip element, so grab the
                                        # tooltip from the row slot to be able
                                        # to swap its text later.
                                        _compress_tip = (
                                            _compress_btn.parent_slot.children[-1]
                                        )
                                        _compress_btns.append(
                                            (
                                                project,
                                                db_name,
                                                _compress_btn,
                                                _compress_tip,
                                                _size_label,
                                            )
                                        )

                                        # Write-protection toggle: locks the
                                        # database so it can only be opened
                                        # read-only. The edit_off icon turns
                                        # amber while protection is active.
                                        _protected = _pa.is_database_write_protected(
                                            project, db_name
                                        )

                                        async def toggle_write_protection(
                                            p=project, d=db_name
                                        ):
                                            if not require_user():
                                                return
                                            pa = (
                                                ctx.project_auth
                                                or ProjectAuth(
                                                    ctx.storage.data_dir
                                                )
                                            )
                                            new_state = (
                                                not pa.is_database_write_protected(
                                                    p, d
                                                )
                                            )
                                            if pa.set_database_write_protected(
                                                p, d, new_state
                                            ):
                                                nicegui_app.storage.user["flash"] = _(
                                                    "write_protection_on"
                                                    if new_state
                                                    else "write_protection_off"
                                                )
                                                ui.navigate.reload()
                                            else:
                                                ui.notify(
                                                    _("error"),
                                                    type="negative",
                                                )

                                        ui.button(
                                            on_click=toggle_write_protection,
                                        ).props(
                                            'icon="edit_off" flat dense'
                                        ).classes(
                                            "wd-icon-amber" if _protected else ""
                                        ).style("color: #888;").tooltip(
                                            _("write_protection")
                                        ).props("tooltip-position=top")

                                        # Database delete with confirmation dialog.
                                        async def delete_db(
                                            p=project, d=db_name
                                        ):
                                            if not require_user():
                                                return
                                            with ui.dialog() as dlg, ui.card().classes(
                                                "items-center gap-4"
                                            ).style(
                                                "background: #1E1E1E; border-radius: 12px; "
                                                "padding: 24px 32px;"
                                            ):
                                                ui.label(_("confirm_delete_database")).style(
                                                    f"color: {TEXT_SOFT}"
                                                )
                                                with ui.row().classes("gap-2"):
                                                    ui.button(
                                                        _("cancel"),
                                                        on_click=dlg.close,
                                                    ).props("outline color=grey").classes(
                                                        "border-button"
                                                    )

                                                    def do_delete():
                                                        if not require_user():
                                                            return
                                                        dlg.close()
                                                        pa = (
                                                            ctx.project_auth
                                                            or ProjectAuth(
                                                                ctx.storage.data_dir
                                                            )
                                                        )
                                                        if ctx.storage.trash_database(
                                                            p, d
                                                        ):
                                                            pa.remove_database_config_entry(
                                                                p, d
                                                            )
                                                            nicegui_app.storage.user["flash"] = _("moved_to_trash")
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
                                            on_click=delete_db,
                                        ).props(
                                            'icon="delete" flat dense'
                                        ).classes("wd-icon-red").tooltip(
                                            _("delete")
                                        ).props("tooltip-position=top")

                                # Fire one background fragmentation check per
                                # database, right after the list is rendered.
                                for _p, _d, _btn, _tip, _sizelabel in _compress_btns:
                                    asyncio.create_task(
                                        _update_compress_icon(
                                            _p, _d, _btn, _tip, _sizelabel
                                        )
                                    )

                        # ── Create database (sub-card) ─────────
                        # Input for new database name + optional API password
                        # with a random password generator button.
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
                                    """Fill the password field with a random 16-byte URL-safe token."""
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
                                    if not require_user():
                                        return
                                    if db_name.value:
                                        from webduck.storage.engine import RESERVED_DUCKDB_NAMES
                                        if db_name.value.lower() in RESERVED_DUCKDB_NAMES:
                                            ui.notify(
                                                _("reserved_name"),
                                                type="negative",
                                            )
                                            return
                                        ok = ctx.storage.create_database(
                                            p, db_name.value
                                        )
                                        if ok:
                                            # Optionally set API password on the newly created database.
                                            if db_password.value:
                                                pa = (
                                                    ctx.project_auth
                                                    or ProjectAuth(
                                                        ctx.storage.data_dir
                                                    )
                                                )
                                                pa.set_database_password(
                                                    p, db_name.value,
                                                    db_password.value,
                                                )
                                            nicegui_app.storage.user["flash"] = _("success")
                                            ui.navigate.reload()
                                        else:
                                            ui.notify(
                                                _("error"),
                                                type="negative",
                                            )

                                ui.button(
                                    on_click=create_db,
                                ).props(
                                    f'icon="img:{_DB_PLUS_ICON_URL}" flat dense'
                                ).classes("wd-icon-amber").tooltip(
                                    _("create_database")
                                ).props("tooltip-position=top")
                                new_db_name.on(
                                    "keydown.enter",
                                    create_db,
                                )

        else:
            with ui.card().classes("w-full q-mt-sm"):
                ui.label(_("no_projects_found")).classes(
                    "text-caption"
                )

        # ── Client-side drag & drop reordering ─────────────
        # Injects JavaScript that makes project cards draggable via
        # the 6-dot grip handle.  On drop, the new order is sent to
        # the server via the _wdReorder() helper function.
        if projects:
            ui.run_javascript("""
                const container = document.querySelector(
                    '.project-card'
                );
                if (!container) return;
                const parent = container.parentNode;
                const cards = parent.querySelectorAll(
                    '.project-card'
                );
                let dragged = null;

                cards.forEach(card => {
                    const h = card.querySelector(
                        '.drag-handle'
                    );
                    if (!h) return;

                    // Enable dragging only when mousedown occurs on the grip handle.
                    h.addEventListener('mousedown', () => {
                        card.draggable = true;
                    });

                    card.addEventListener('dragstart', e => {
                        dragged = card;
                        card.style.opacity = '0.4';
                        e.dataTransfer.effectAllowed = 'move';
                    });

                    card.addEventListener('dragend', () => {
                        card.style.opacity = '1';
                        dragged = null;
                        // Clear all drop indicators.
                        parent.querySelectorAll(
                            '.project-card'
                        ).forEach(c => {
                            c.style.borderTop = '';
                        });
                    });

                    // Show a yellow top-border as a drop indicator.
                    card.addEventListener('dragover', e => {
                        e.preventDefault();
                        e.dataTransfer.dropEffect = 'move';
                        card.style.borderTop =
                            '2px solid #FFD54F';
                    });

                    card.addEventListener(
                        'dragleave', () => {
                            card.style.borderTop = '';
                        }
                    );

                    // On drop: reorder DOM nodes, then persist the new order.
                    card.addEventListener('drop', e => {
                        e.preventDefault();
                        card.style.borderTop = '';
                        if (dragged && dragged !== card) {
                            const all = [
                                ...parent.querySelectorAll(
                                    '.project-card'
                                )
                            ];
                            const di = all.indexOf(dragged);
                            const ti = all.indexOf(card);
                            if (di < ti) {
                                parent.insertBefore(
                                    dragged,
                                    card.nextSibling
                                );
                            } else {
                                parent.insertBefore(
                                    dragged,
                                    card
                                );
                            }
                            // Read the new project order from the DOM and send to server.
                            const order = [
                                ...parent.querySelectorAll(
                                    '.project-card'
                                )
                            ].map(c =>
                                c.getAttribute(
                                    'data-project'
                                )
                            );
                            window._wdReorder(order);
                        }
                    });
                });
            """)
            # Server-side reorder helper: POSTs the new project order to the API.
            ui.run_javascript("""
                window._wdReorder = async function(o) {
                    try {
                        const r = await fetch(
                            '/api/reorder-projects',
                            {
                                method: 'POST',
                                headers: {
                                    'Content-Type':
                                        'application/json',
                                },
                                body: JSON.stringify(
                                    { projects: o }
                                )
                            }
                        );
                        console.log(
                            'REORDER:', r.status,
                            await r.json()
                        );
                    } catch(e) {
                        console.error('Reorder failed:', e);
                    }
                };
            """)
