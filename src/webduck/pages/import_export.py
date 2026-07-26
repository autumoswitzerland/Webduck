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

"""Import/Export page — CSV import via drag & drop, CSV export by table selection.

**Import:** The user specifies a target table name and drags a file
onto the upload zone (or clicks to open a file picker).  The file is
sent directly to the server via HTTP multipart (no WebSocket limit),
saved to a temp file, and imported via DuckDB's ``read_csv_auto``.

**Export:** The user selects a table from the chosen database; the
server writes it to a temp CSV file, which is then base64-encoded and
triggered as a browser download via a data URL.
"""

import asyncio
from pathlib import Path

from nicegui import app as nicegui_app
from nicegui import ui

from webduck.pages import context as ctx
from webduck.pages.context import (
    BG_CARD,
    TEXT_DIM,
    YELLOW_LIGHT,
)
from webduck.pages.ui_helpers import (
    apply_dark_theme,
    make_drawer,
    make_footer,
    make_header,
)
from webduck.pages.user_prefs import get_user_pref, set_user_pref


def register():
    """Register the ``/import`` page route with NiceGUI."""
    from webduck.i18n import get_user_translator

    @ui.page("/import")
    def import_export_page():
        _ = get_user_translator()
        apply_dark_theme()
        ui.page_title(f"WebDuck {ctx.version} — Import/Export")

        # Auth guard: redirect to login if no session token exists.
        if "token" not in nicegui_app.storage.user:
            ui.navigate.to("/login")
            return

        make_header(_)
        make_drawer(_)
        make_footer(_)

        # ── Card 1: Project & Database Selection ────────────
        # Shared dropdowns for both import and export sections.
        # Selections are persisted per-user via the user_prefs system.
        with ui.card().classes("w-full"):
            ui.label(_("import_export")).classes(
                "text-h5"
            ).style(f"color: {YELLOW_LIGHT}")

            with ui.row().classes("w-full gap-4"):
                projects = ctx.storage.list_projects()
                saved_proj = get_user_pref("import", "project")
                default_proj = saved_proj if saved_proj in projects else (projects[0] if projects else None)
                project_select = ui.select(
                    projects,
                    label=_("projects"),
                    value=default_proj,
                ).classes("w-40")

                database_select = ui.select(
                    [], label=_("databases")
                ).classes("w-40")

                def update_databases():
                    """Refresh the database dropdown when the project changes.

                    Restores the previously selected database if it still
                    exists in the new project, otherwise selects the first one.
                    """
                    if project_select.value:
                        databases = ctx.storage.list_databases(
                            project_select.value
                        )
                        saved_db = get_user_pref("import", "database")
                        target = saved_db if saved_db in databases else (databases[0] if databases else None)
                        database_select.set_options(databases, value=target)
                        set_user_pref("import", "project", project_select.value)
                        if target:
                            set_user_pref("import", "database", target)
                    else:
                        database_select.set_options([], value=None)

                project_select.on_value_change(update_databases)
                database_select.on_value_change(
                    lambda: set_user_pref("import", "database", database_select.value) if database_select.value else None
                )
                update_databases()

        # ── Card 2: CSV Import ──────────────────────────────
        # File upload via HTTP multipart (NiceGUI ui.upload).
        # No WebSocket size limit — files go directly to the server.
        with ui.card().classes("w-full q-mt-sm"):
            ui.label(_("csv_import")).classes(
                "text-h5"
            ).style(f"color: {YELLOW_LIGHT}")

            table_name_input = ui.input(
                _("table_name"),
            ).classes("w-60 q-mb-sm")

            # Track the uploaded temp file path for the import step.
            _uploaded_file = [None]
            _uploaded_name = [None]

            async def on_upload(e):
                """Handle file upload via HTTP multipart.

                Saves the uploaded file content to a temp file on disk
                so DuckDB can import it directly.
                """
                import tempfile
                tmp = tempfile.NamedTemporaryFile(
                    delete=False, suffix=".upload"
                )
                tmp.close()
                await e.file.save(tmp.name)
                _uploaded_file[0] = tmp.name
                _uploaded_name[0] = e.file.name

            upload = ui.upload(
                on_upload=on_upload,
                auto_upload=True,
                max_file_size=ctx.max_upload_mb * 1024 * 1024,
                label=_("drop_csv_file"),
                multiple=False,
            ).classes("w-full")

            # Style the QUploader to match our dark theme.
            ui.add_css("""
                .q-uploader__header {
                    background: #1a1a1a !important;
                }
                .q-uploader__list {
                    background: #1a1a1a !important;
                    color: #E0E0E0 !important;
                }
                .q-uploader__list scroll {
                    background: #1a1a1a !important;
                }
                .q-uploader {
                    border: 2px dashed #444 !important;
                    border-radius: 8px !important;
                    box-shadow: none !important;
                }
                .q-uploader__dnd {
                    background: rgba(255,213,79,0.05) !important;
                    border-color: #FFD54F !important;
                }
            """)

            # Hint: supported formats, delimiter, max file size.
            ui.label(
                _("import_hint").format(ctx.max_upload_mb)
            ).style(
                f"color: {TEXT_DIM}; font-size: 0.85em;"
            )

            import_result_area = ui.card().classes("w-full mt-2 shadow-none")

            async def execute_import():
                """Execute the CSV import workflow.

                1. Validate that a database and table name are selected.
                2. Check that a file was uploaded.
                3. Show a spinner dialog while the import runs.
                4. Call ``import_csv`` in a background thread, then
                   clean up the temp file.
                5. Display success/error and reset the upload zone on success.
                """
                if not database_select.value:
                    ui.notify(_("select_database"), type="warning")
                    return

                if not table_name_input.value:
                    ui.notify(_("table_name_required"), type="warning")
                    return

                if not _uploaded_file[0]:
                    ui.notify(_("no_file_loaded"), type="warning")
                    return

                # Show a modal spinner while the import runs.
                with ui.dialog() as dlg, ui.card().classes(
                    "items-center gap-4"
                ).style(
                    f"background: {BG_CARD}; "
                    "border-radius: 12px; "
                    "padding: 32px 48px;"
                ):
                    ui.spinner(size="xl", color="amber")
                    ui.label(_("importing")).style(f"color: {YELLOW_LIGHT}")
                dlg.open()

                try:
                    # Run the import in a background thread to keep the UI responsive.
                    result = await asyncio.to_thread(
                        ctx.storage.import_csv,
                        project_select.value,
                        database_select.value,
                        table_name_input.value,
                        Path(_uploaded_file[0]),
                    )

                    # Only clean up on success — keep file for retry on error.
                    if result.get("success"):
                        Path(_uploaded_file[0]).unlink(missing_ok=True)
                        _uploaded_file[0] = None
                        _uploaded_name[0] = None
                except Exception as e:
                    from webduck.logging import log_error
                    log_error(f"CSV import error [{project_select.value}/{database_select.value}]: {e}")
                    result = {"success": False, "error": str(e)}
                finally:
                    dlg.close()

                # Display result and reset the upload zone on success.
                with import_result_area:
                    import_result_area.clear()
                    if result.get("success"):
                        ui.label(_("import_success")).style("color: #66BB6A")
                        # Reset upload, table name, and refresh export list.
                        upload.reset()
                        table_name_input.value = ""
                        update_tables()
                    else:
                        ui.label(result.get("error", "Import failed")).style("color: #f64337")

            ui.button(
                _("execute_import"), on_click=execute_import
            ).props("outline color=amber").classes("mt-2 border-button")

        # ── Card 3: CSV Export ──────────────────────────────
        # Select a table and download its contents as a CSV file.
        # The export runs server-side; the result is sent to the
        # browser as a base64 data URL for automatic download.
        with ui.card().classes("w-full q-mt-sm"):
            ui.label(_("csv_export")).classes(
                "text-h5"
            ).style(f"color: {YELLOW_LIGHT}")

            table_select = ui.select(
                [], label=_("select_table")
            ).classes("w-60")

            def update_tables():
                """Refresh the table dropdown when the database changes.

                Queries ``get_table_info()`` for the list of user tables
                in the selected database and populates the dropdown.
                """
                if database_select.value:
                    try:
                        result = ctx.storage.get_table_info(
                            project_select.value,
                            database_select.value,
                        )
                        raw = result.get("tables", []) if isinstance(result, dict) else []
                        tables = [t["name"] for t in raw if isinstance(t, dict) and "name" in t]
                        table_select.set_options(tables, value=tables[0] if tables else None)
                    except Exception as e:
                        from webduck.logging import log_error
                        log_error(f"Tables list error [{project_select.value}/{database_select.value}]: {e}")
                        table_select.set_options([], value=None)
                else:
                    table_select.set_options([], value=None)

            database_select.on_value_change(update_tables)
            update_tables()

            export_result_area = ui.card().classes("w-full mt-2 shadow-none")

            async def execute_export():
                """Execute the CSV export workflow.

                1. Validate that a database and table are selected.
                2. Show a spinner dialog while the export runs.
                3. Call ``export_csv`` in a background thread to write
                   a temp CSV file.
                4. Register a download token and redirect the browser
                   to ``/export/<token>`` — no base64, no WebSocket.
                5. Clean up the temp file after a short delay.
                """
                if not database_select.value:
                    ui.notify(_("select_database"), type="warning")
                    return

                if not table_select.value:
                    ui.notify(_("select_table"), type="warning")
                    return

                # Show a modal spinner while the export runs.
                with ui.dialog() as dlg, ui.card().style(
                    f"background: {BG_CARD}; "
                    "border-radius: 12px; "
                    "padding: 32px 48px;"
                ):
                    ui.spinner(size="xl", color="amber")
                    ui.label(_("exporting")).style(f"color: {YELLOW_LIGHT}")
                dlg.open()

                import secrets
                token = secrets.token_urlsafe(16)
                csv_path = Path(f"/tmp/webduck_export_{table_select.value}.csv")
                try:
                    # Run the export in a background thread to keep the UI responsive.
                    result = await asyncio.to_thread(
                        ctx.storage.export_csv,
                        project_select.value,
                        database_select.value,
                        table_select.value,
                        csv_path,
                    )
                    if result.get("success") and csv_path.exists():
                        from webduck.main import _export_tokens
                        _export_tokens[token] = csv_path
                        filename = f"{table_select.value}.csv"
                        ui.run_javascript(f"""
                            var a = document.createElement('a');
                            a.href = '/export/{token}';
                            a.download = '{filename}';
                            document.body.appendChild(a);
                            a.click();
                            document.body.removeChild(a);
                        """)
                    else:
                        csv_path.unlink(missing_ok=True)
                except Exception as e:
                    from webduck.logging import log_error
                    log_error(f"CSV export error [{project_select.value}/{database_select.value}]: {e}")
                    result = {"success": False, "error": str(e)}
                    csv_path.unlink(missing_ok=True)
                finally:
                    dlg.close()

                with export_result_area:
                    export_result_area.clear()
                    if result.get("success"):
                        ui.label(_("export_success")).style("color: #66BB6A")
                    else:
                        ui.label(result.get("error", "Export failed")).style("color: #f64337")

            ui.button(
                _("execute_export"), on_click=execute_export
            ).props("outline color=amber").classes("mt-2 border-button")
