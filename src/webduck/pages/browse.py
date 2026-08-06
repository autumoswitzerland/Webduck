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

"""Browse page — database object tree + result table with infinite scroll.

The left panel shows a tree of database objects (tables, views, indexes,
sequences, macros) queried from DuckDB system tables.  Selecting a table
or view displays its rows in a Quasar table with:

- **Infinite scroll** — initially loads 100 rows, fetches more as the
  user scrolls near the bottom (polling via a UI timer).
- **Inline cell editing** — double-click any cell to edit it; the value
  is validated against the column's DuckDB type and written back via a
  parameterized UPDATE with CAST.
"""

import asyncio
import json

from nicegui import ui

from webduck.pages import context as ctx
from webduck.pages.context import (
    BG_CARD,
    BROWSE_PAGE_SIZE,
    TEXT_DIM,
    TEXT_SOFT,
    TREE_WIDTH,
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
from webduck.pages.user_prefs import get_user_pref, set_user_pref

# DuckDB types that allow inline cell editing.  Complex types like
# STRUCT, LIST, MAP, etc. are excluded because their text representation
# is ambiguous without a full parser.
_VALID_CAST = {
    "VARCHAR", "INTEGER", "BIGINT",
    "SMALLINT", "TINYINT", "DOUBLE",
    "FLOAT", "DECIMAL", "DATE",
    "TIMESTAMP", "BOOLEAN", "UUID",
}


def register():
    """Register the ``/browse`` page route with NiceGUI."""
    from webduck.i18n import get_user_translator

    @ui.page("/browse")
    def browse_page():
        _ = get_user_translator()
        apply_dark_theme()
        ui.page_title(f"WebDuck {ctx.version} — Browse")

        # Auth guard: redirect to login if the session is invalid or the
        # user account no longer exists (e.g. deleted while logged in).
        if not require_user():
            return

        make_header(_)
        make_drawer(_)
        make_footer(_)

        # -- Project & Database selection card (shared with query page pattern).
        with ui.card().classes("w-full"):
            ui.label(_("browse")).classes("text-h5").style(
                f"color: {YELLOW_LIGHT}"
            )

            with ui.row().classes("w-full gap-4"):
                projects = ctx.storage.list_projects()
                saved_proj = get_user_pref("browse", "project")
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
                    """Refresh the database dropdown when the project changes.

                    Restores the previously selected database if it still
                    exists in the new project, otherwise selects the first one.
                    """
                    if project_select.value:
                        databases = ctx.storage.list_databases(
                            project_select.value
                        )
                        saved_db = get_user_pref("browse", "database")
                        target = (
                            saved_db if saved_db in databases
                            else (databases[0] if databases else None)
                        )
                        database_select.set_options(
                            databases, value=target
                        )
                        set_user_pref(
                            "browse", "project", project_select.value
                        )
                        if target:
                            set_user_pref(
                                "browse", "database", target
                            )
                    else:
                        database_select.set_options([], value=None)

                project_select.on_value_change(update_databases)
                database_select.on_value_change(
                    lambda: set_user_pref(
                        "browse", "database", database_select.value
                    ) if database_select.value else None
                )
                update_databases()

        # ── Tree + Result ──────────────────────────────────────
        # Two-column layout: left = object tree (fixed width), right = result table.
        with ui.row().classes("w-full q-mt-sm gap-4"):
            tree_container = ui.card().classes(
                "col"
            ).style(
                f"min-height: 200px; flex: 0 0 {TREE_WIDTH};"
            )
            result_container = ui.card().classes("col")

        def load_tree():
            """Query DuckDB system tables and build the object tree.

            For each object type (tables, views, indexes, sequences,
            macros) a SQL query is run against the corresponding
            ``duckdb_*()`` table function.  Results are grouped under
            typed parent nodes with appropriate icons.
            """
            tree_container.clear()
            result_container.clear()

            proj = project_select.value
            db = database_select.value
            if not proj or not db:
                return

            with tree_container:
                ui.label(_("database_objects")).classes(
                    "text-h6 q-mb-sm"
                ).style(f"color: {YELLOW}")

                tree_data = {}

                # Query each DuckDB system table for object names.
                for obj_type, icon, query in [
                    ("tables", "table_chart",
                     f"SELECT table_name FROM duckdb_tables()"
                     f" WHERE database_name = '{db}'"
                     f" ORDER BY table_name"),
                    ("views", "visibility",
                     f"SELECT view_name AS table_name"
                     f" FROM duckdb_views()"
                     f" WHERE database_name = '{db}'"
                     f" ORDER BY view_name"),
                    ("indexes", "tag",
                     f"SELECT index_name AS table_name"
                     f" FROM duckdb_indexes()"
                     f" WHERE database_name = '{db}'"
                     f" ORDER BY index_name"),
                    ("sequences", "pin",
                     f"SELECT sequence_name AS table_name"
                     f" FROM duckdb_sequences()"
                     f" WHERE database_name = '{db}'"
                     f" ORDER BY sequence_name"),
                    ("macros", "settings",
                     f"SELECT function_name AS table_name"
                     f" FROM duckdb_functions()"
                     f" WHERE database_name = '{db}'"
                     f" AND function_type = 'macro'"
                     f" ORDER BY function_name"),
                ]:
                    try:
                        res = ctx.storage.execute_query(
                            proj, db, query
                        )
                    except Exception as e:
                        from webduck.logging import log_error
                        log_error(
                            f"Browse query error "
                            f"[{proj}/{db}] {obj_type}: {e}"
                        )
                        res = {
                            "success": False,
                            "error": str(e),
                        }

                    items = []
                    if res.get("success") and res.get("rows"):
                        for row in res["rows"]:
                            name = row[0]
                            items.append({
                                "id": f"{obj_type}/{name}",
                                "label": name,
                                "icon": icon,
                            })

                    if items:
                        tree_data[obj_type] = {
                            "id": obj_type,
                            "label": _(obj_type),
                            "icon": "folder",
                            "children": items,
                        }

                if not tree_data:
                    ui.label(_("no_data_found")).style(
                        f"color: {TEXT_DIM}"
                    )
                    return

                # Timers for infinite scroll polling and cell-edit detection.
                # Stored in lists so nested closures can mutate them.
                _browse_timer = [None]
                _edit_timer = [None]

                def on_tree_click(e):
                    """Handle tree node selection.

                    Parses the node ID as ``obj_type/name``.  For tables
                    and views, loads rows with infinite scroll and enables
                    inline editing.  For indexes/sequences/macros, loads
                    metadata from DuckDB system tables.
                    """
                    # Cancel any active timers from a previous selection.
                    if _browse_timer[0]:
                        _browse_timer[0].cancel()
                        _browse_timer[0] = None
                    if _edit_timer[0]:
                        _edit_timer[0].cancel()
                        _edit_timer[0] = None

                    selected = (
                        e.value
                        if isinstance(e.value, list)
                        else [e.value]
                    )
                    if not selected or selected[0] is None:
                        return

                    node_id = selected[0]
                    if "/" not in node_id:
                        return
                    obj_type, name = node_id.split("/", 1)
                    result_container.clear()

                    proj = project_select.value
                    db = database_select.value

                    with result_container:
                        ui.label(
                            f"{obj_type}: {name}"
                        ).classes(
                            "text-h6 q-mb-sm"
                        ).style(f"color: {YELLOW}")

                        # ── Tables & Views: paginated row display ─────
                        if obj_type in ("tables", "views"):
                            # Get total row count for the status label.
                            try:
                                count_res = ctx.storage.execute_query(
                                    proj, db,
                                    f'SELECT COUNT(*) FROM "{name}"',
                                )
                            except Exception as e:
                                from webduck.logging import log_error
                                log_error(
                                    f"Browse count error "
                                    f"[{proj}/{db}] {name}: {e}"
                                )
                                count_res = {
                                    "success": False,
                                }

                            total = (
                                count_res["rows"][0][0]
                                if count_res.get("success")
                                and count_res.get("rows")
                                else 0
                            )

                            # Load the first page of rows.
                            q = (
                                f'SELECT * FROM "{name}"'
                                f" LIMIT {BROWSE_PAGE_SIZE}"
                                f" OFFSET 0"
                            )
                            try:
                                res = ctx.storage.execute_query(
                                    proj, db, q
                                )
                            except Exception as e:
                                from webduck.logging import log_error
                                log_error(
                                    f"Browse query error "
                                    f"[{proj}/{db}] {name}: {e}"
                                )
                                res = {
                                    "success": False,
                                    "error": str(e),
                                }

                            if not res.get("success"):
                                ui.label(
                                    res.get("error", "")
                                ).style(
                                    "color: #f64337"
                                )
                                return

                            columns = res.get("columns", [])
                            rows_raw = res.get("rows", [])
                            if not columns:
                                ui.label(
                                    _("no_data_found")
                                ).style(
                                    f"color: {TEXT_DIM}"
                                )
                                return

                            # Convert raw rows to dicts keyed by column name.
                            all_rows = [
                                dict(zip(columns, row))
                                for row in rows_raw
                            ]
                            has_more = total > BROWSE_PAGE_SIZE

                            # Status label showing total row count.
                            st = (
                                _("total_rows") % total
                                if total > 0
                                else ""
                            )
                            status_label = ui.label(st).style(
                                f"color: {TEXT_DIM}; "
                                f"font-size: 0.85em;"
                            )

                            # Render the Quasar table with flat bordered style.
                            tbl = ui.table(
                                columns=[
                                    {
                                        "name": c,
                                        "label": c,
                                        "field": c,
                                    }
                                    for c in columns
                                ],
                                rows=all_rows,
                                row_key=(
                                    columns[0] if columns else None
                                ),
                            ).classes("w-full").props(
                                "flat bordered"
                            )

                            # ── Infinite scroll setup ────────────────
                            # If the table has more rows than one page,
                            # set up a polling timer that fetches the next
                            # page when the user scrolls near the bottom.
                            if has_more:
                                offset = [BROWSE_PAGE_SIZE]
                                loading = [False]
                                done = [False]

                                async def load_more():
                                    """Fetch the next page of rows if the user scrolled near the bottom.

                                    Uses a JS flag (``_webduckNeedMore``) set by a scroll
                                    event listener.  The flag avoids unnecessary server
                                    calls when the user hasn't scrolled far enough.
                                    """
                                    if not require_user():
                                        return
                                    if loading[0] or done[0]:
                                        return
                                    loading[0] = True
                                    try:
                                        need = (
                                            await ui.run_javascript(
                                                "window._webduckNeedMore"
                                                " || false",
                                                timeout=2,
                                            )
                                        )
                                        if not need:
                                            return
                                        ui.run_javascript(
                                            "window._webduckNeedMore"
                                            " = false"
                                        )
                                        new_offset = offset[0]
                                        q2 = (
                                            f'SELECT * FROM "{name}"'
                                            f" LIMIT "
                                            f"{BROWSE_PAGE_SIZE}"
                                            f" OFFSET "
                                            f"{new_offset}"
                                        )
                                        res2 = (
                                            await asyncio.to_thread(
                                                ctx.storage.execute_query,
                                                proj, db, q2,
                                            )
                                        )
                                        if res2.get("success"):
                                            new_rows = [
                                                dict(
                                                    zip(columns, r)
                                                )
                                                for r in res2.get(
                                                    "rows", []
                                                )
                                            ]
                                            if new_rows:
                                                all_rows.extend(
                                                    new_rows
                                                )
                                                tbl.rows = all_rows
                                                tbl.update()
                                                offset[0] = (
                                                    new_offset
                                                    + len(new_rows)
                                                )
                                                # Stop loading if we've fetched all rows or
                                                # the last page was smaller than PAGE_SIZE.
                                                if (
                                                    len(all_rows)
                                                    >= total
                                                    or len(new_rows)
                                                    < BROWSE_PAGE_SIZE
                                                ):
                                                    done[0] = True
                                                status_label.text = _(
                                                    "total_rows"
                                                ) % total
                                            else:
                                                done[0] = True
                                    finally:
                                        loading[0] = False

                                # Poll every 400ms for scroll proximity.
                                _browse_timer[0] = ui.timer(
                                    0.4, load_more, active=True
                                )

                                # Inject JS to detect when the user scrolls near the
                                # bottom of the table container and set the flag.
                                ui.run_javascript("""
                                setTimeout(function() {
                                    var tables = document
                                        .querySelectorAll('.q-table');
                                    var lastTable =
                                        tables[tables.length - 1];
                                    if (!lastTable) return;
                                    var c =
                                        lastTable
                                        .closest('.q-card')
                                        || lastTable.parentElement;
                                    c.style.maxHeight = '70vh';
                                    c.style.overflowY = 'auto';
                                    c.addEventListener(
                                        'scroll', function() {
                                        if (
                                            c.scrollTop
                                            + c.clientHeight
                                            >= c.scrollHeight - 100
                                        ) {
                                            window
                                            ._webduckNeedMore = true;
                                        }
                                    });
                                }, 200);
                                """)

                            # ── Cell editing ──────────────
                            # Fetch column types from information_schema to
                            # determine which columns are editable and how
                            # to validate new values.
                            type_res = ctx.storage.execute_query(
                                proj, db,
                                "SELECT column_name, data_type "
                                "FROM information_schema.columns "
                                f"WHERE table_name = '{name}' "
                                "AND table_schema = 'main'",
                            )
                            col_types = {}
                            if type_res.get("success"):
                                for row in type_res["rows"]:
                                    col_types[row[0]] = row[1]

                            # CSS highlight on cell hover to indicate editability.
                            ui.add_css("""
                                .q-table tbody td:hover {
                                    background: rgba(255,213,79,0.1)
                                        !important;
                                    cursor: pointer;
                                }
                            """)

                            # Use the first column as the primary key for UPDATE statements.
                            pk_col = columns[0] if columns else None
                            if pk_col and pk_col in col_types:
                                # JS double-click handler: captures the clicked row index,
                                # column name, and old value, storing them in a global.
                                ui.run_javascript("""
                                setTimeout(function() {
                                    var ts = document
                                        .querySelectorAll('.q-table');
                                    var t = ts[ts.length - 1];
                                    if (!t) return;
                                    t.addEventListener(
                                        'dblclick', function(e) {
                                        var td =
                                            e.target.closest('td');
                                        if (!td) return;
                                        var tr =
                                            td.closest('tr');
                                        if (!tr) return;
                                        var ri = Array.from(
                                            t.querySelectorAll(
                                                'tbody tr'
                                            )
                                        ).indexOf(tr);
                                        var hi =
                                            t.querySelectorAll(
                                                'thead th'
                                            );
                                        var ci = Array.from(
                                            tr.querySelectorAll('td')
                                        ).indexOf(td);
                                        var cn = hi[ci]
                                            ? hi[ci].textContent
                                                .trim()
                                            : '';
                                        var ov =
                                            td.textContent.trim();
                                        window._eci =
                                            JSON.stringify(
                                                {r:ri, c:cn, v:ov}
                                            );
                                    });
                                }, 300);
                                """)

                                async def _check_edit():
                                    """Poll for double-click edit events.

                                    Reads the ``_eci`` JS global set by the double-click
                                    handler.  If present, validates the column type, opens
                                    an edit dialog, and (on save) executes a parameterized
                                    UPDATE with CAST to ensure type safety.
                                    """
                                    if not require_user():
                                        return
                                    info = (
                                        await ui.run_javascript(
                                            "window._eci || null",
                                            timeout=1,
                                        )
                                    )
                                    if not info:
                                        return

                                    # Consume the event immediately.
                                    ui.run_javascript(
                                        "window._eci = null"
                                    )

                                    # Views are not editable.
                                    if obj_type == "views":
                                        return

                                    d = json.loads(info)
                                    ri, cn, ov = (
                                        d["r"], d["c"], d["v"]
                                    )
                                    if cn not in col_types:
                                        ui.notification(
                                            "Unknown column",
                                            type="warning",
                                        )
                                        return
                                    ct = col_types[cn]
                                    # Only allow editing types in the whitelist.
                                    if ct not in _VALID_CAST:
                                        ui.notification(
                                            "Column type not "
                                            "editable",
                                            type="warning",
                                        )
                                        return

                                    with ui.dialog() as dlg, \
                                            ui.card().style(
                                                f"background: "
                                                f"{BG_CARD};"
                                                " min-width: 320px;"
                                            ):
                                        ui.label(cn).style(
                                            f"color: {YELLOW}"
                                        )
                                        inp = ui.input(
                                            value=ov
                                        ).classes("w-full")

                                        with ui.row().classes(
                                            "w-full gap-2 "
                                            "justify-end mt-2"
                                        ):
                                            ui.button(
                                                _("cancel"),
                                                on_click=dlg.close,
                                            ).props(
                                                "outline color=grey"
                                            )

                                            async def _save():
                                                """Validate the new value against the column type and execute UPDATE.

                                                Type-specific regex validation:
                                                - INTEGER/BIGINT/SMALLINT/TINYINT: optional minus + digits
                                                - DOUBLE/FLOAT/DECIMAL: optional minus + digits + optional decimal
                                                - BOOLEAN: true/false/1/0
                                                - DATE: YYYY-MM-DD
                                                - TIMESTAMP: YYYY-MM-DD HH:MM or YYYY-MM-DDTHH:MM
                                                - VARCHAR/UUID: any string (no validation)
                                                """
                                                if not require_user():
                                                    return
                                                nv = inp.value
                                                if nv == ov:
                                                    dlg.close()
                                                    return
                                                import re as _re
                                                _ok = True
                                                int_types = (
                                                    "INTEGER",
                                                    "BIGINT",
                                                    "SMALLINT",
                                                    "TINYINT",
                                                )
                                                float_types = (
                                                    "DOUBLE",
                                                    "FLOAT",
                                                    "DECIMAL",
                                                )
                                                if ct in int_types:
                                                    _ok = (
                                                        _re.fullmatch(
                                                            r"-?\d+",
                                                            nv,
                                                        )
                                                        is not None
                                                    )
                                                elif ct in float_types:
                                                    _ok = (
                                                        _re.fullmatch(
                                                            r"-?\d+"
                                                            r"(\.\d+)?",
                                                            nv,
                                                        )
                                                        is not None
                                                    )
                                                elif ct == "BOOLEAN":
                                                    _ok = (
                                                        nv.lower()
                                                        in (
                                                            "true",
                                                            "false",
                                                            "1",
                                                            "0",
                                                        )
                                                    )
                                                elif ct == "DATE":
                                                    _ok = (
                                                        _re.fullmatch(
                                                            r"\d{4}"
                                                            r"-\d{2}"
                                                            r"-\d{2}",
                                                            nv,
                                                        )
                                                        is not None
                                                    )
                                                elif ct == "TIMESTAMP":
                                                    _ok = (
                                                        _re.fullmatch(
                                                            r"\d{4}"
                                                            r"-\d{2}"
                                                            r"-\d{2}"
                                                            r"[T ]"
                                                            r"\d{2}"
                                                            r":\d{2}",
                                                            nv,
                                                        )
                                                        is not None
                                                    )
                                                if not _ok:
                                                    ui.notification(
                                                        _(
                                                            "invalid_value"
                                                        )
                                                        % (nv, ct),
                                                        type="warning",
                                                    )
                                                    return
                                                # Parameterized UPDATE with CAST for type safety.
                                                sql = (
                                                    f'UPDATE "{name}"'
                                                    f' SET "{cn}"'
                                                    f" = CAST(?"
                                                    f" AS {ct})"
                                                    f' WHERE'
                                                    f' "{pk_col}"'
                                                    f" = ?"
                                                )
                                                pk_val = all_rows[
                                                    ri
                                                ][pk_col]

                                                # print(f"SQL: {sql}")
                                                # print(f"VAL: {nv}")
                                                # print(f"PK : {pk_val}")

                                                r = (
                                                    await asyncio.to_thread(
                                                        ctx.storage.execute_query,
                                                        proj,
                                                        db,
                                                        sql,
                                                        params=[
                                                            nv,
                                                            pk_val,
                                                        ],
                                                        read_only=False,
                                                    )
                                                )
                                                if r.get("success"):
                                                    # Update the in-memory row and refresh the table.
                                                    all_rows[ri][
                                                        cn
                                                    ] = nv
                                                    tbl.rows = list(
                                                        all_rows
                                                    )
                                                    tbl.update()
                                                    ui.notification(
                                                        _(
                                                            "updated"
                                                        ),
                                                        type="positive",
                                                    )
                                                    dlg.close()
                                                else:
                                                    # Note: DuckDB may report constraint errors when updating tables
                                                    # with foreign-key relationships.
                                                    error = str(r.get("error", "Update failed"))

                                                    if "Constraint Error" in error:
                                                        err_msg = _("duckdb_fk_note") + " " + error
                                                    else:
                                                        err_msg = error

                                                    ui.notification(
                                                        err_msg,
                                                        type="negative",
                                                        timeout=None,
                                                        close_button=True
                                                    )

                                            ui.button(
                                                _("save"),
                                                on_click=_save,
                                            ).props(
                                                "outline color=positive"
                                            )
                                            inp.on(
                                                "keydown.enter",
                                                _save,
                                            )

                                        inp.run_method("focus")
                                    dlg.open()

                                # Poll every 500ms for double-click edit events.
                                _edit_timer[0] = ui.timer(
                                    0.5,
                                    _check_edit,
                                    active=True,
                                )

                        # ── Indexes / Sequences / Macros: metadata display ──
                        # These object types show read-only metadata from
                        # DuckDB system tables rather than row data.
                        else:
                            if obj_type == "indexes":
                                q = (
                                    "SELECT schema_name,"
                                    " index_name, table_name,"
                                    " is_unique, is_primary,"
                                    " expressions, sql"
                                    " FROM duckdb_indexes()"
                                    " WHERE index_name"
                                    f" = '{name}'"
                                )
                            elif obj_type == "sequences":
                                q = (
                                    "SELECT schema_name,"
                                    " sequence_name,"
                                    " start_value, min_value,"
                                    " max_value,"
                                    " increment_by, cycle,"
                                    " last_value, sql"
                                    " FROM duckdb_sequences()"
                                    " WHERE sequence_name"
                                    f" = '{name}'"
                                )
                            elif obj_type == "macros":
                                q = (
                                    "SELECT schema_name,"
                                    " function_name,"
                                    " function_type,"
                                    " return_type,"
                                    " parameters,"
                                    " parameter_types,"
                                    " macro_definition"
                                    " FROM duckdb_functions()"
                                    " WHERE function_name"
                                    f" = '{name}'"
                                    " AND function_type"
                                    " = 'macro'"
                                )
                            else:
                                ui.label(_("error")).style(
                                    f"color: {TEXT_DIM}"
                                )
                                return

                            res = ctx.storage.execute_query(
                                proj, db, q
                            )
                            if not res.get("success"):
                                ui.label(
                                    res.get("error", "")
                                ).style("color: #f64337")
                                return

                            columns = res.get("columns", [])
                            rows_raw = res.get("rows", [])
                            if not columns:
                                ui.label(
                                    _("no_data_found")
                                ).style(
                                    f"color: {TEXT_DIM}"
                                )
                                return

                            # Flatten list values (e.g. parameter lists) to comma-separated strings.
                            rows = [
                                {
                                    k: (
                                        ", ".join(v)
                                        if isinstance(v, list)
                                        else v
                                    )
                                    for k, v in dict(
                                        zip(columns, row)
                                    ).items()
                                }
                                for row in rows_raw
                            ]
                            ui.table(
                                columns=[
                                    {
                                        "name": c,
                                        "label": c,
                                        "field": c,
                                    }
                                    for c in columns
                                ],
                                rows=rows,
                                row_key=(
                                    columns[0] if columns else None
                                ),
                            ).classes("w-full").props(
                                "flat bordered"
                            )

                # Render the NiceGUI tree widget with on_select callback.
                ui.tree(
                    list(tree_data.values()),
                    on_select=on_tree_click,
                ).style(
                    f"color: {TEXT_SOFT}; font-size: 0.85em;"
                ).classes("q-tree--dense")

        # Rebuild the tree whenever the project or database changes.
        project_select.on_value_change(load_tree)
        database_select.on_value_change(load_tree)
        load_tree()
