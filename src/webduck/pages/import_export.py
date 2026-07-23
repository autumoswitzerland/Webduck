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

"""Import/Export page — CSV import via drag & drop, CSV export by table selection."""

import asyncio
from pathlib import Path

from nicegui import app as nicegui_app
from nicegui import ui

from webduck.pages import context as ctx
from webduck.pages.context import (
    BG_CARD,
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
    from webduck.i18n import get_user_translator

    @ui.page("/import")
    def import_export_page():
        _ = get_user_translator()
        apply_dark_theme()
        ui.page_title(f"WebDuck {ctx.version} — Import/Export")

        if "token" not in nicegui_app.storage.user:
            ui.navigate.to("/login")
            return

        make_header(_)
        make_drawer(_)
        make_footer(_)

        # ── Card 1: Project & Database Selection ────────────
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
        with ui.card().classes("w-full q-mt-sm"):
            ui.label(_("csv_import")).classes(
                "text-h5"
            ).style(f"color: {YELLOW_LIGHT}")

            table_name_input = ui.input(
                _("table_name"),
            ).classes("w-60 q-mb-sm")

            dsf = _("drop_csv_file")
            drop_html = f"""
            <div id="csv-drop-zone" style="
                border: 2px dashed #444;
                border-radius: 8px;
                padding: 32px;
                text-align: center;
                color: #888;
                cursor: pointer;
                margin-bottom: 12px;
            ">
                {dsf}
                <input type="file" id="csv-file-input"
                    accept=".csv,.txt" style="display:none;">
                <div id="csv-file-info"
                    style="margin-top: 8px; font-size: 0.9em;">
                </div>
            </div>
            """
            ui.html(drop_html)

            max_bytes = ctx.max_upload_mb * 1024 * 1024
            js_setup = f"""
            setTimeout(function() {{
                var zone = document.getElementById('csv-drop-zone');
                var fileInput = document.getElementById('csv-file-input');
                if (!zone || !fileInput) return;

                zone.addEventListener('click', function() {{
                    fileInput.click();
                }});

                zone.addEventListener('dragover', function(e) {{
                    e.preventDefault();
                    zone.style.borderColor = '#FFD54F';
                }});

                zone.addEventListener('dragleave', function(e) {{
                    e.preventDefault();
                    zone.style.borderColor = '#444';
                }});

                zone.addEventListener('drop', function(e) {{
                    e.preventDefault();
                    zone.style.borderColor = '#444';
                    var files = e.dataTransfer.files;
                    if (files.length > 0) {{
                        var file = files[0];
                        if (file.size > {max_bytes}) {{
                            alert('{_("file_too_large").format(ctx.max_upload_mb)}');
                            return;
                        }}
                        var reader = new FileReader();
                        reader.onload = function(ev) {{
                            window._csvUploadContent = ev.target.result;
                            var info = document.getElementById('csv-file-info');
                            if (info) {{
                                info.textContent = file.name + ' (' + (file.size / 1024).toFixed(1) + ' KB)';
                                info.style.color = '#66BB6A';
                            }}
                            zone.style.borderColor = '#66BB6A';
                        }};
                        reader.readAsText(file);
                    }}
                }});

                fileInput.addEventListener('change', function(e) {{
                    var file = e.target.files[0];
                    if (file) {{
                        if (file.size > {max_bytes}) {{
                            alert('{_("file_too_large").format(ctx.max_upload_mb)}');
                            return;
                        }}
                        var reader = new FileReader();
                        reader.onload = function(ev) {{
                            window._csvUploadContent = ev.target.result;
                            var info = document.getElementById('csv-file-info');
                            if (info) {{
                                info.textContent = file.name + ' (' + (file.size / 1024).toFixed(1) + ' KB)';
                                info.style.color = '#66BB6A';
                            }}
                            zone.style.borderColor = '#66BB6A';
                        }};
                        reader.readAsText(file);
                    }}
                }});
            }}, 100);
            """
            ui.run_javascript(js_setup)

            import_result_area = ui.card().classes("w-full mt-2 shadow-none")

            async def execute_import():
                if not database_select.value:
                    ui.notify(_("select_database"), type="warning")
                    return

                if not table_name_input.value:
                    ui.notify(_("table_name_required"), type="warning")
                    return

                content = await ui.run_javascript(
                    "window._csvUploadContent || ''", timeout=3,
                )
                if not content:
                    ui.notify(_("no_file_loaded"), type="warning")
                    return

                with ui.dialog() as dlg, ui.card().style(
                    f"background: {BG_CARD};"
                    " min-width: 320px;"
                    " text-align: center;"
                ):
                    ui.spinner(size="xl", color="amber")
                    ui.label(_("importing")).style(f"color: {YELLOW_LIGHT}")
                dlg.open()

                try:
                    import tempfile
                    with tempfile.NamedTemporaryFile(
                        mode="w", suffix=".csv", delete=False
                    ) as tmp:
                        tmp.write(content)
                        tmp_path = tmp.name

                    result = await asyncio.to_thread(
                        ctx.storage.import_csv,
                        project_select.value,
                        database_select.value,
                        table_name_input.value,
                        Path(tmp_path),
                    )

                    Path(tmp_path).unlink(missing_ok=True)
                except Exception as e:
                    from webduck.logging import log_error
                    log_error(f"CSV import error [{project_select.value}/{database_select.value}]: {e}")
                    result = {"success": False, "error": str(e)}
                finally:
                    dlg.close()

                with import_result_area:
                    import_result_area.clear()
                    if result.get("success"):
                        ui.label(_("import_success")).style("color: #66BB6A")
                        await ui.run_javascript(
                            """
                            window._csvUploadContent = "";
                            var info = document.getElementById('csv-file-info');
                            if (info) { info.textContent = ''; }
                            var zone = document.getElementById('csv-drop-zone');
                            if (zone) { zone.style.borderColor = '#444'; }
                            """,
                            timeout=3,
                        )
                    else:
                        ui.label(result.get("error", "Import failed")).classes("text-negative")

            ui.button(
                _("execute_import"), on_click=execute_import
            ).props("outline color=amber").classes("mt-2 border-button")

        # ── Card 3: CSV Export ──────────────────────────────
        with ui.card().classes("w-full q-mt-sm"):
            ui.label(_("csv_export")).classes(
                "text-h5"
            ).style(f"color: {YELLOW_LIGHT}")

            table_select = ui.select(
                [], label=_("select_table")
            ).classes("w-60")

            def update_tables():
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
                if not database_select.value:
                    ui.notify(_("select_database"), type="warning")
                    return

                if not table_select.value:
                    ui.notify(_("select_table"), type="warning")
                    return

                with ui.dialog() as dlg, ui.card().style(
                    f"background: {BG_CARD};"
                    " min-width: 320px;"
                    " text-align: center;"
                ):
                    ui.spinner(size="xl", color="amber")
                    ui.label(_("exporting")).style(f"color: {YELLOW_LIGHT}")
                dlg.open()

                csv_path = Path(f"/tmp/webduck_export_{table_select.value}.csv")
                try:
                    result = await asyncio.to_thread(
                        ctx.storage.export_csv,
                        project_select.value,
                        database_select.value,
                        table_select.value,
                        csv_path,
                    )
                    if result.get("success") and csv_path.exists():
                        csv_content = csv_path.read_text()
                        import base64
                        b64 = base64.b64encode(csv_content.encode()).decode()
                        filename = f"{table_select.value}.csv"
                        ui.run_javascript(f"""
                            var a = document.createElement('a');
                            a.href = 'data:text/csv;base64,{b64}';
                            a.download = '{filename}';
                            document.body.appendChild(a);
                            a.click();
                            document.body.removeChild(a);
                        """)
                except Exception as e:
                    from webduck.logging import log_error
                    log_error(f"CSV export error [{project_select.value}/{database_select.value}]: {e}")
                    result = {"success": False, "error": str(e)}
                finally:
                    csv_path.unlink(missing_ok=True)
                    dlg.close()

                with export_result_area:
                    export_result_area.clear()
                    if result.get("success"):
                        ui.label(_("export_success")).style("color: #66BB6A")
                    else:
                        ui.label(result.get("error", "Export failed")).classes("text-negative")

            ui.button(
                _("execute_export"), on_click=execute_export
            ).props("outline color=amber").classes("mt-2 border-button")
