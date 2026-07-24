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

"""Browse page — database object tree + result table with infinite scroll."""

import asyncio
import json

from nicegui import app as nicegui_app
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
)
from webduck.pages.user_prefs import get_user_pref, set_user_pref

_VALID_CAST = {
    "VARCHAR", "INTEGER", "BIGINT",
    "SMALLINT", "TINYINT", "DOUBLE",
    "FLOAT", "DECIMAL", "DATE",
    "TIMESTAMP", "BOOLEAN", "UUID",
}


def register():
    from webduck.i18n import get_user_translator

    @ui.page("/browse")
    def browse_page():
        _ = get_user_translator()
        apply_dark_theme()
        ui.page_title(f"WebDuck {ctx.version} — Browse")

        if "token" not in nicegui_app.storage.user:
            ui.navigate.to("/login")
            return

        make_header(_)
        make_drawer(_)
        make_footer(_)

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
        with ui.row().classes("w-full q-mt-sm gap-4"):
            tree_container = ui.card().classes(
                "col"
            ).style(
                f"min-height: 200px; flex: 0 0 {TREE_WIDTH};"
            )
            result_container = ui.card().classes("col")

        def load_tree():
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

                _browse_timer = [None]
                _edit_timer = [None]

                def on_tree_click(e):
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
                    if not selected:
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

                        if obj_type in ("tables", "views"):
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

                            all_rows = [
                                dict(zip(columns, row))
                                for row in rows_raw
                            ]
                            has_more = total > BROWSE_PAGE_SIZE

                            st = (
                                _("total_rows") % total
                                if total > 0
                                else ""
                            )
                            status_label = ui.label(st).style(
                                f"color: {TEXT_DIM}; "
                                f"font-size: 0.85em;"
                            )

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

                            if has_more:
                                offset = [BROWSE_PAGE_SIZE]
                                loading = [False]
                                done = [False]

                                async def load_more():
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

                                _browse_timer[0] = ui.timer(
                                    0.4, load_more, active=True
                                )

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

                            ui.add_css("""
                                .q-table tbody td:hover {
                                    background: rgba(255,213,79,0.1)
                                        !important;
                                    cursor: pointer;
                                }
                            """)

                            pk_col = columns[0] if columns else None
                            if pk_col and pk_col in col_types:
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
                                    info = (
                                        await ui.run_javascript(
                                            "window._eci || null",
                                            timeout=1,
                                        )
                                    )
                                    if not info:
                                        return
                                    ui.run_javascript(
                                        "window._eci = null"
                                    )
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
                                                "flat color=grey"
                                            )

                                            async def _save():
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
                                                    ui.notification(
                                                        r.get(
                                                            "error",
                                                            "Update "
                                                            "failed",
                                                        ),
                                                        type="negative",
                                                    )

                                            ui.button(
                                                _("save"),
                                                on_click=_save,
                                            ).props(
                                                "flat color=positive"
                                            )
                                    dlg.open()

                                _edit_timer[0] = ui.timer(
                                    0.5,
                                    _check_edit,
                                    active=True,
                                )

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

                ui.tree(
                    list(tree_data.values()),
                    on_select=on_tree_click,
                ).style(
                    f"color: {TEXT_SOFT}; font-size: 0.85em;"
                ).classes("q-tree--dense")

        project_select.on_value_change(load_tree)
        database_select.on_value_change(load_tree)
        load_tree()
