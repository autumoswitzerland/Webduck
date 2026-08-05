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

"""Dashboard page — landing page showing server status and live metrics.

Displays four stat cards (server online status, projects, databases, trash),
a live traffic monitor for REST-API database accesses (rolling 60-second
window, Grafana-style line chart), and a storage overview table with pure
file-size values. Nothing on this page writes to a database — sizes come
from ``database_size()`` which is a plain file stat.
"""

from nicegui import app as nicegui_app
from nicegui import ui

from webduck.pages import context as ctx
from webduck.pages.context import (
    TEXT_DIM,
    YELLOW,
    YELLOW_LIGHT,
)
from webduck.pages.ui_helpers import (
    apply_dark_theme,
    make_drawer,
    make_footer,
    make_header,
)

# CSS styles
TOP_CARD_STYLE = (
    "background: #1c1c1c; "
    "border: 1px solid #333; "
    "height: 180px; "
)
TOP_CARD_CURSOR_STYLE = (
    "background: #1c1c1c; "
    "border: 1px solid #333; "
    "height: 180px; "
    "cursor: pointer; "
)
TOP_CARD_CLASSES = (
    "w-full "
    "flex flex-col justify-center items-center"
)

def _fmt_bytes(num: int) -> str:
    """Format a byte count as a human-readable string (decimal units)."""
    value = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1000 or unit == "TB":
            return f"{int(value)} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1000
    return f"{num} B"


def _ws_count() -> int:
    """Return the number of active NiceGUI websocket connections."""
    try:
        return sum(1 for _ in nicegui_app.clients())
    except Exception:
        return 0


def _storage_footer_lines(
    has_rows: bool,
    total_dbs: int,
    total_size: int,
    trash_objects: int,
    trash_size: int,
    translate,
) -> list[str]:
    """Return the storage footer lines to display.

    The total line is only shown when the table has rows; the trash line
    only when there is something in the trash.
    """
    lines = []
    if has_rows:
        lines.append(
            f'<strong><span style="display: inline-block; width: 40px;">'
            f'{translate("total")}</span></strong>: {total_dbs} '
            f'{translate("databases")}, {_fmt_bytes(total_size)}'
        )
    if trash_objects > 0:
        lines.append(
            f'<strong><span style="display: inline-block; width: 40px;">'
            f'{translate("trash")}</span></strong>: {trash_objects} '
            f'{translate("objects")}, {_fmt_bytes(trash_size)}'
        )
    return lines


def _traffic_labels(bucket_seconds: float = 2.0) -> list[str]:
    """Return relative time labels for the 60s traffic window (e.g. '-58'..'0')."""
    steps = int(60.0 / bucket_seconds)
    return [str(-60 + (i + 1) * int(bucket_seconds)) for i in range(steps)]


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

        # Load trash stats (count + total size), clickable -> /trash.
        # One hierarchical list: count = projects + contained databases,
        # size = top-level sizes only (no double counting).
        try:
            trash_entries = ctx.storage.list_trash()
            trash_objects = sum(
                1 + len(e.get("databases") or []) for e in trash_entries
            )
            trash_size = sum(
                e.get("size") or 0 for e in trash_entries
            )

        except Exception:
            trash_objects = 0
            trash_size = 0

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

            # -- Four stat cards laid out in a horizontal row.
            with ui.element("div").classes(
                "grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 w-full"
            ):
                # Card 1: Server status — always shows "Online" if the page loaded.
                with ui.card().classes(TOP_CARD_CLASSES).style(TOP_CARD_STYLE):
                    with ui.column().classes("items-center justify-center"):
                        ui.badge(
                            _("online"), color="green"
                        ).classes("text-h5 q-pa-sm q-px-lg")
                        ui.label(_("server_status")).classes("text-h6")

                # Card 2: Total number of projects.
                with ui.card().classes(TOP_CARD_CLASSES).style(TOP_CARD_CURSOR_STYLE).on(
                    "click", lambda: ui.navigate.to("/projects")
                ):
                    with ui.column().classes("items-center justify-center"):
                        ui.label(str(len(projects))).classes(
                            "text-h3"
                        ).style(f"color: {YELLOW_LIGHT}")
                        ui.label(_("projects")).classes("text-h6")

                # Card 3: Total number of databases.
                with ui.card().classes(TOP_CARD_CLASSES).style(TOP_CARD_CURSOR_STYLE).on(
                    "click", lambda: ui.navigate.to("/browse")
                ):
                    with ui.column().classes("items-center justify-center"):
                        ui.label(str(total_databases)).classes(
                            "text-h3"
                        ).style(f"color: {YELLOW_LIGHT}")
                        ui.label(_("databases")).classes("text-h6")

                # Card 4: Trash.
                with ui.card().classes(TOP_CARD_CLASSES).style(TOP_CARD_CURSOR_STYLE).on(
                    "click", lambda: ui.navigate.to("/trash")
                ):
                    with ui.column().classes("items-center justify-center"):
                        ui.label(str(trash_objects)).classes(
                            "text-h3"
                        ).style(f"color: {YELLOW_LIGHT}")
                        ui.label(_("trash")).classes("text-h6")

        # -- Traffic monitor card (REST API DB accesses only, live).
        with ui.card().classes("w-full"):
            ui.label(_("traffic_monitor")).classes(
                "text-h6 text-bold"
            ).style(f"color: {YELLOW}")

            # Two large live numbers: queries/min and active websocket count.
            with ui.row().classes("w-full items-center gap-8 q-mt-sm"):
                with ui.column().classes("items-center"):
                    qpm_label = ui.label("0").classes( # 0 = initial only
                        "text-h3"
                    ).style(f"color: {YELLOW_LIGHT}")
                    ui.label(_("queries_per_min")).classes("text-h6")
                with ui.column().classes("items-center"):
                    ws_label = ui.label(str(_ws_count())).classes(
                        "text-h3"
                    ).style(f"color: {YELLOW_LIGHT}")
                    ui.label(_("active_sessions")).classes("text-h6")

            # Grafana-style live line chart: accesses per 2s over 60s.
            bucket_seconds = 2.0
            labels = _traffic_labels(bucket_seconds)
            chart = ui.echart(
                {
                    "backgroundColor": "transparent",
                    "tooltip": {
                        "trigger": "axis",
                        "backgroundColor": "#1c1c1c",
                        "borderColor": "#333333",
                        "borderWidth": 1,
                        "textStyle": {
                            "color": "#e0e0e0",
                        },
                    },
                    "grid": {
                        "left": 44, "right": 16, "top": 16, "bottom": 28,
                    },
                    "xAxis": {
                        "type": "category",
                        "data": labels,
                        "axisLabel": {"color": TEXT_DIM},
                        "axisLine": {"lineStyle": {"color": "#333333"}},
                    },
                    "yAxis": {
                        "type": "value",
                        "minInterval": 1,
                        "axisLabel": {"color": TEXT_DIM},
                        "splitLine": {"lineStyle": {"color": "#2a2a2a"}},
                    },
                    "series": [
                        {
                            "type": "line",
                            "data": [],
                            "smooth": True,
                            "showSymbol": False,
                            "lineStyle": {"color": YELLOW, "width": 2},
                            "itemStyle": {"color": YELLOW},
                            "areaStyle": {
                                "opacity": 0.25, "color": YELLOW,
                            },
                        }
                    ],
                }
            ).classes("w-full").style("height: 240px")

            def refresh_traffic():
                """Refresh chart data + live numbers (called every 2s)."""
                try:
                    series = ctx.storage.db_access_series(60, bucket_seconds)
                except Exception:
                    series = []
                chart.options["xAxis"]["data"] = labels
                chart.options["series"][0]["data"] = series
                chart.update()
                qpm_label.text = str(sum(series))
                ws_label.text = str(_ws_count())

            refresh_traffic()
            ui.timer(2.0, refresh_traffic)

        # -- Storage overview card (pure file sizes, no DB writes).
        with ui.card().classes("w-full"):
            ui.label(_("storage_overview")).classes(
                "text-h6 text-bold"
            ).style(f"color: {YELLOW}")

            total_dbs = 0
            total_size = 0
            rows = []
            try:
                for project in projects:
                    dbs = ctx.storage.list_databases(project)
                    size = sum(
                        ctx.storage.database_size(project, d) or 0
                        for d in dbs
                    )
                    rows.append(
                        {
                            "project": project,
                            "count": len(dbs),
                            "size": size,
                        }
                    )
                    total_dbs += len(dbs)
                    total_size += size
            except Exception as e:
                from webduck.logging import log_error
                log_error(f"Dashboard storage overview error: {e}")

            table = ui.table(
                columns=[
                    {
                        "name": "project",
                        "label": _("project"),
                        "field": "project",
                        "align": "left",
                    },
                    {
                        "name": "count",
                        "label": _("databases"),
                        "field": "count",
                        "align": "right",
                    },
                    {
                        "name": "size",
                        "label": _("size"),
                        "field": "size",
                        "align": "right",
                    },
                ],
                rows=[
                    {
                        "project": r["project"],
                        "count": r["count"],
                        "size": _fmt_bytes(r["size"]),
                    }
                    for r in rows
                ],
                row_key="project",
            ).classes("w-full dash-table").props("flat bordered").style("border-color: #333333;")

            ui.add_css("""
                .dash-table tbody td {
                    border-bottom: 1px solid #333333 !important;
                }
                .dash-table thead th {
                    border-bottom: 1px solid #333333 !important;
                }
            """)

            table.on("rowClick", lambda e: ui.navigate.to("/projects"))

            footer_lines = _storage_footer_lines(
                bool(rows),
                total_dbs,
                total_size,
                trash_objects,
                trash_size,
                _,
            )
            if footer_lines:
                with ui.element("div").classes("w-full q-mt-sm").style(
                    f"color: {TEXT_DIM};"
                ):
                    separator = '<span style="margin: 0 10px;">&bull;</span>'
                    ui.html(separator.join(footer_lines))
