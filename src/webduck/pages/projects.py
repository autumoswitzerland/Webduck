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

"""Projects page — CRUD for projects and databases with drag-and-drop reordering.

Users can create/delete projects, create/delete databases within projects,
set per-database API passwords, and reorder projects by dragging the
6-dot grip handle.  Reorder state is persisted via a POST to
``/api/reorder-projects``.
"""

import asyncio
import secrets

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
)


def _fmt_bytes(num: int) -> str:
    """Format a byte count as a human-readable string (e.g. '1.2 GB')."""
    value = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{int(value)} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{num} B"


def register():
    """Register the ``/projects`` page route with NiceGUI."""
    from webduck.i18n import get_user_translator

    @ui.page("/projects")
    def projects_page():
        _ = get_user_translator()
        apply_dark_theme()
        ui.page_title(f"WebDuck {ctx.version} — Projects")

        # Auth guard: redirect to login if no session token exists.
        if "token" not in nicegui_app.storage.user:
            ui.navigate.to("/login")
            return

        make_header(_)
        make_drawer(_)
        make_footer(_)

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
                    if project_name.value:
                        ok = ctx.storage.create_project(
                            project_name.value
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
                                            dlg.close()
                                            if ctx.storage.delete_project(p):
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
                                        # Show a lock icon if this database has an API password set.
                                        _pa = ctx.project_auth or ProjectAuth(ctx.storage.data_dir)
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

                                        # Password change dialog: generate or set a new API password.
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
                                                ).style(f"color: {YELLOW}")
                                                pw_input = ui.input(
                                                    password=True,
                                                    password_toggle_button=True,
                                                ).classes("w-full").props(
                                                    "autocomplete=new-password"
                                                )

                                                def do_save():
                                                    if pw_input.value:
                                                        pa = ctx.project_auth or ProjectAuth(
                                                            ctx.storage.data_dir
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
                                            size = ctx.storage.database_size(p, d)
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
                                                                ui.label(
                                                                    _("compress_success").format(
                                                                        _fmt_bytes(
                                                                            result["size_before"]
                                                                        ),
                                                                        _fmt_bytes(
                                                                            result["size_after"]
                                                                        ),
                                                                        result["saved_percent"],
                                                                    )
                                                                ).style(
                                                                    f"color: {YELLOW_LIGHT}"
                                                                )
                                                                ui.button(
                                                                    _("close"),
                                                                    on_click=rdlg.close,
                                                                ).props(
                                                                    "outline color=grey"
                                                                ).classes("border-button")
                                                            rdlg.open()
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
                                        ui.button(
                                            on_click=compress_db,
                                        ).props(
                                            'icon="compress" flat dense'
                                        ).style("color: #888;").tooltip(
                                            _("compress_database")
                                        ).props("tooltip-position=top")

                                        # Database delete with confirmation dialog.
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
                                                        dlg.close()
                                                        if ctx.storage.delete_database(p, d):
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
                                            on_click=delete_db,
                                        ).props(
                                            'icon="delete" flat dense'
                                        ).classes("wd-icon-red").tooltip(
                                            _("delete")
                                        ).props("tooltip-position=top")

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
                                    on_click=create_db,
                                ).props(
                                    'icon="storage" flat dense'
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
