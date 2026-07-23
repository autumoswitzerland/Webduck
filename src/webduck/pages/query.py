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

"""SQL Queries + Upload page."""

import asyncio
import re

from nicegui import app as nicegui_app
from nicegui import ui

from webduck.pages import context as ctx
from webduck.pages.context import (
    TEXT_DIM,
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
from webduck.pages.user_prefs import get_user_pref, set_user_pref


def register():
    from webduck.i18n import get_user_translator

    @ui.page("/query")
    def query_page():
        _ = get_user_translator()
        apply_dark_theme()
        ui.page_title(f"WebDuck {ctx.version} — SQL Queries")

        if "token" not in nicegui_app.storage.user:
            ui.navigate.to("/login")
            return

        make_header(_)
        make_drawer(_)
        make_footer(_)

        # ── Card 1: Project & DB Selection (shared) ────────────
        with ui.card().classes("w-full"):
            ui.label(_("select_database")).classes(
                "text-h5"
            ).style(f"color: {YELLOW_LIGHT}")

            with ui.row().classes("w-full gap-4"):
                projects = ctx.storage.list_projects()
                saved_proj = get_user_pref("query", "project")
                default_proj = (
                    saved_proj if saved_proj in projects
                    else (projects[0] if projects else None)
                )
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
                        saved_db = get_user_pref("query", "database")
                        target = (
                            saved_db if saved_db in databases
                            else (databases[0] if databases else None)
                        )
                        database_select.set_options(
                            databases, value=target
                        )
                        set_user_pref(
                            "query", "project", project_select.value
                        )
                        if target:
                            set_user_pref("query", "database", target)
                    else:
                        database_select.set_options([], value=None)

                project_select.on_value_change(update_databases)
                database_select.on_value_change(
                    lambda: set_user_pref(
                        "query", "database", database_select.value
                    ) if database_select.value else None
                )
                update_databases()

        # ── Card 2: SQL Queries ────────────────────────────────
        with ui.card().classes("w-full q-mt-sm"):
            ui.label(_("sql_queries")).classes(
                "text-h5"
            ).style(f"color: {YELLOW_LIGHT}")

            ui.label("SQL").classes("text-caption text-bold q-mb-xs")
            sql_input = ui.textarea(
                placeholder="SELECT * FROM table_name",
            ).classes("w-full")

            result_area = ui.card().classes("w-full mt-4 shadow-none")

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
                    m = re.search(
                        r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?'
                        r'[`"\']?(\w+)',
                        sql_text, re.IGNORECASE,
                    )
                    tbl = m.group(1) if m else "?"
                    return "text", f"Table '{tbl}' created"
                elif sql_upper.startswith("DROP TABLE"):
                    m = re.search(
                        r'DROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?'
                        r'[`"\']?(\w+)',
                        sql_text, re.IGNORECASE,
                    )
                    tbl = m.group(1) if m else "?"
                    return "text", f"Table '{tbl}' dropped"
                else:
                    return "text", _("query_executed")

            async def execute_query():
                if not sql_input.value or not database_select.value:
                    return

                try:
                    results = ctx.storage.execute_queries(
                        project_select.value,
                        database_select.value,
                        sql_input.value,
                    )
                except Exception as e:
                    from webduck.logging import log_error
                    log_error(
                        f"SQL query error "
                        f"[{project_select.value}"
                        f"/{database_select.value}]: {e}"
                    )
                    results = [
                        {
                            "success": False,
                            "error": str(e),
                            "sql": sql_input.value,
                        }
                    ]

                with result_area:
                    result_area.clear()
                    all_ok = True
                    for result in results:
                        kind, data = _result_message(
                            result, result.get("sql", "")
                        )
                        if kind == "table":
                            ui.table(
                                columns=[
                                    {"name": c, "label": c, "field": c}
                                    for c in data["columns"]
                                ],
                                rows=[
                                    {
                                        c: v
                                        for c, v in zip(
                                            data["columns"], row
                                        )
                                    }
                                    for row in data["rows"]
                                ],
                            ).classes("w-full").props(
                                "flat bordered"
                            )
                            rc = data["row_count"]
                            key = (
                                "row_returned"
                                if rc == 1
                                else "rows_returned"
                            )
                            ui.label(_(key) % rc).classes(
                                "text-caption q-mt-sm"
                            )
                        elif kind == "text":
                            ui.label(data).style(
                                f"color: {TEXT_DIM}"
                            )
                        else:
                            ui.label(data).classes("text-negative")
                            all_ok = False
                    if all_ok:
                        sql_input.value = ""

            ui.button(
                _("execute_query"), on_click=execute_query
            ).props("outline color=amber").classes(
                "mt-2 border-button"
            )

        # ── Card 3: SQL Upload ─────────────────────────────────
        with ui.card().classes("w-full q-mt-sm"):
            ui.label(_("sql_upload")).classes(
                "text-h5"
            ).style(f"color: {YELLOW_LIGHT}")

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
                    zone.style.borderColor = '{YELLOW}';
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
                    if (file.size > {ctx.max_upload_mb * 1024 * 1024}) {{
                        alert('{_("file_too_large").format(ctx.max_upload_mb)}');
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
                            info.style.color = '{TEXT_SOFT}';
                        }}
                    }};
                    reader.readAsText(file);
                }}
            }}, 100);
            """
            ui.run_javascript(js_setup)

            upload_result_area = ui.card().classes(
                "w-full mt-4 shadow-none"
            )

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
                    "background: #1E1E1E; "
                    "border-radius: 12px; "
                    "padding: 32px 48px;"
                ):
                    ui.spinner(size="xl", color="amber")
                    ui.label(_("sql_upload")).style(
                        f"color: {TEXT_SOFT}; font-size: 1.1em;"
                    )
                progress_dialog.open()

                results = await asyncio.to_thread(
                    ctx.storage.execute_queries,
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
                            ui.label(result["error"]).classes(
                                "text-negative"
                            )

                    if error_count == 0 and success_count > 0:
                        key = (
                            "statement_executed"
                            if success_count == 1
                            else "statements_executed"
                        )
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
                            f"color: {TEXT_DIM}"
                        )

            ui.button(
                _("execute_upload"), on_click=execute_upload
            ).props("outline color=amber").classes(
                "mt-2 border-button"
            )
