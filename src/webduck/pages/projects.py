# ------------------------------------------------------------------------------
# Copyright (c) 2026 autusto GmbH. All rights reserved.
#
# Licensed under the MIT License. See LICENSE file in the project root for
# full license information.
#
# NOTICE: This file is part of WebDuck. The above copyright notice and this
# permission notice shall be included in all copies or substantial portions
# of this software.
# ------------------------------------------------------------------------------

"""Projects page."""

import secrets

from nicegui import app as nicegui_app
from nicegui import ui

from webduck.auth.manager import ProjectAuth
from webduck.pages import context as ctx
from webduck.pages.context import (
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


def register():
    from webduck.i18n import get_user_translator

    @ui.page("/projects")
    def projects_page():
        _ = get_user_translator()
        apply_dark_theme()
        ui.page_title(f"WebDuck {ctx.version} — Projects")

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
                        project_dir = (
                            ctx.storage.data_dir / project_name.value
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
        try:
            projects = ctx.storage.list_projects()
        except Exception as e:
            from webduck.logging import log_error
            log_error(f"Projects list error: {e}")
            projects = []

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
                            _("delete"),
                            on_click=delete_project,
                        ).props("outline color=red").classes("border-button")

                    # ── Existing databases (sub-card) ──────
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
                                    ok = ctx.storage.create_database(
                                        p, db_name.value
                                    )
                                    if ok:
                                        if db_password.value:
                                            pa = ctx.project_auth or ProjectAuth(ctx.storage.data_dir)
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
