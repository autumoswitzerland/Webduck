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

# =============================================================================
#  WebDuck — Storage Engine
#  ---------------------------------------------------------------------------
#  DuckDB storage engine with file-locking for concurrent access.
#
#  Provides CRUD operations for projects and databases, SQL query/write
#  execution, table listing, and CSV import/export. Uses per-file
#  threading locks for DuckDB's single-writer concurrency model.
#
#  Project:   WebDuck
#  Author:    autumo GmbH
#  Version:   1.0.0
#  Date:      2026-07-20
# =============================================================================

"""WebDuck storage engine - DuckDB operations."""

import json
import threading
from pathlib import Path
from typing import Any

import duckdb


class StorageEngine:
    """DuckDB storage engine with file-locking for concurrent access."""

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self._locks: dict[str, threading.Lock] = {}
        self._locks_lock = threading.Lock()

    def _get_lock(self, db_path: str) -> threading.Lock:
        """Get or create a lock for a specific database file."""
        with self._locks_lock:
            if db_path not in self._locks:
                self._locks[db_path] = threading.Lock()
            return self._locks[db_path]

    # ------------------------------------------------------------------
    #  Project order (JSON)
    # ------------------------------------------------------------------

    def _project_order_path(self) -> Path:
        return self.data_dir / ".projects.json"

    def _load_project_order(self) -> list[str]:
        """Load project order from JSON, sync with filesystem."""
        if not self.data_dir.exists():
            return []

        fs_projects = {
            d.name
            for d in self.data_dir.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        }

        order_path = self._project_order_path()
        if order_path.exists():
            try:
                data = json.loads(
                    order_path.read_text(encoding="utf-8")
                )
                ordered = [
                    p for p in data.get("projects", [])
                    if p in fs_projects
                ]
            except (json.JSONDecodeError, KeyError):
                ordered = []
        else:
            ordered = []

        for p in sorted(fs_projects - set(ordered)):
            ordered.append(p)

        self._save_project_order(ordered)
        return ordered

    def _save_project_order(
        self, projects: list[str]
    ) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        order_path = self._project_order_path()
        order_path.write_text(
            json.dumps(
                {"projects": projects},
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def _get_db_path(self, project: str, database: str) -> Path:
        """Get the full path to a database file."""
        return self.data_dir / project / f"{database}.duckdb"

    def list_projects(self) -> list[str]:
        """List all projects in JSON order, synced with filesystem."""
        return self._load_project_order()

    def create_project(self, project: str) -> bool:
        """Create a new project directory and add to order (at top)."""
        project_dir = self.data_dir / project
        if project_dir.exists():
            return False
        project_dir.mkdir(parents=True, exist_ok=True)
        order = self._load_project_order()
        if project not in order:
            order.insert(0, project)
            self._save_project_order(order)
        return True

    def reorder_projects(
        self, projects: list[str]
    ) -> None:
        """Save a new project order to JSON."""
        self._save_project_order(projects)

    def list_databases(self, project: str) -> list[str]:
        """List all databases in a project."""
        project_dir = self.data_dir / project
        if not project_dir.exists():
            return []
        databases = [
            f.stem
            for f in project_dir.glob("*.duckdb")
            if f.is_file()
        ]
        databases.sort()
        return databases

    def database_exists(self, project: str, database: str) -> bool:
        """Check if a database exists."""
        return self._get_db_path(project, database).exists()

    def create_database(self, project: str, database: str) -> bool:
        """Create a new empty database."""
        project_dir = self.data_dir / project
        project_dir.mkdir(parents=True, exist_ok=True)

        db_path = self._get_db_path(project, database)
        if db_path.exists():
            return False

        lock = self._get_lock(str(db_path))
        with lock:
            con = duckdb.connect(str(db_path))
            con.close()
        return True

    def delete_database(self, project: str, database: str) -> bool:
        """Delete a database."""
        db_path = self._get_db_path(project, database)
        if not db_path.exists():
            return False

        lock = self._get_lock(str(db_path))
        with lock:
            db_path.unlink()
        return True

    def delete_project(self, project: str) -> bool:
        """Delete a project and all its databases."""
        project_dir = self.data_dir / project
        if not project_dir.exists():
            return False

        import shutil
        shutil.rmtree(project_dir)

        order = self._load_project_order()
        if project in order:
            order.remove(project)
            self._save_project_order(order)

        return True

    def execute_query(
        self,
        project: str,
        database: str,
        sql: str,
        params: dict[str, Any] | None = None,
        read_only: bool = True,
    ) -> dict[str, Any]:
        """Execute a SQL query and return results."""
        db_path = self._get_db_path(project, database)
        if not db_path.exists():
            return {
                "success": False,
                "error": f"Database not found: {project}/{database}",
            }

        lock = self._get_lock(str(db_path))
        with lock:
            try:
                con = duckdb.connect(str(db_path), read_only=read_only)
                try:
                    result = con.execute(sql, params or None)
                    if result is not None and result.description:
                        columns = [desc[0] for desc in result.description]
                        rows = [list(r) for r in result.fetchall()]
                        row_count = len(rows)
                    else:
                        columns = []
                        rows = []
                        row_count = 0
                    return {
                        "success": True,
                        "columns": columns,
                        "rows": rows,
                        "row_count": row_count,
                    }
                finally:
                    con.close()
            except Exception as e:
                error_msg = str(e)
                if "Catalog Error" in error_msg:
                    hint = self._get_drop_hint(db_path, sql)
                    if hint:
                        error_msg += f"\n\n{hint}"
                return {"success": False, "error": error_msg}

    def _get_drop_hint(self, db_path, sql: str) -> str | None:
        """Check FK dependencies for DROP TABLE/VIEW and return a hint."""
        import re
        sql_upper = sql.strip().upper()

        is_drop = (
            sql_upper.startswith("DROP TABLE")
            or sql_upper.startswith("DROP VIEW")
        )
        if not is_drop:
            return None

        m = re.search(
            r"DROP\s+(?:TABLE|VIEW)\s+(?:IF\s+EXISTS\s+)?[`\"']?(\w+)",
            sql, re.IGNORECASE,
        )
        if not m:
            return None
        target = m.group(1)

        try:
            con = duckdb.connect(str(db_path), read_only=True)
            try:
                res = con.execute(
                    "SELECT table_name, constraint_type, "
                    "constraint_text "
                    "FROM duckdb_constraints() "
                    "WHERE constraint_type = 'FOREIGN KEY' "
                    "AND schema_name = 'main'"
                )
                rows = res.fetchall()
            finally:
                con.close()
        except Exception:
            return None

        deps = []
        for table_name, _, constraint_text in rows:
            if target.lower() in constraint_text.lower():
                deps.append((table_name, constraint_text))

        if not deps:
            return None

        lines = [f'Table "{target}" is referenced by:']
        for tbl, ctext in deps:
            lines.append(f'  - "{tbl}" ({ctext})')
        lines.append(
            f'Drop "{target}" dependencies first, '
            "or add CASCADE to your statement."
        )
        return "\n".join(lines)

    def execute_queries(
        self,
        project: str,
        database: str,
        sql: str,
        read_only: bool = False,
    ) -> list[dict[str, Any]]:
        """Execute one or more SQL statements and return results for each."""
        statements = [s.strip() for s in sql.split(";") if s.strip()]
        if not statements:
            return []
        results = []
        for stmt in statements:
            r = self.execute_query(project, database, stmt, read_only=read_only)
            r["sql"] = stmt
            results.append(r)
            if not r["success"]:
                break
        return results

    def get_table_info(self, project: str, database: str) -> dict[str, Any]:
        """Get information about all tables in a database."""
        sql = """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'main'
            ORDER BY table_name
        """
        result = self.execute_query(project, database, sql)
        if not result["success"]:
            return result

        tables = []
        for (table_name,) in result["rows"]:
            columns_sql = f"""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = '{table_name}'
                ORDER BY ordinal_position
            """
            cols_result = self.execute_query(project, database, columns_sql)
            tables.append({
                "name": table_name,
                "columns": cols_result.get("rows", []) if cols_result["success"] else [],
            })

        return {"success": True, "tables": tables}

    def import_csv(
        self,
        project: str,
        database: str,
        table_name: str,
        csv_path: Path,
    ) -> dict[str, Any]:
        """Import a CSV file into a table."""
        if not csv_path.exists():
            return {"success": False, "error": f"CSV file not found: {csv_path}"}

        sql = f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM read_csv_auto('{csv_path}')"
        return self.execute_query(project, database, sql, read_only=False)

    def export_csv(
        self,
        project: str,
        database: str,
        table_name: str,
        csv_path: Path,
    ) -> dict[str, Any]:
        """Export a table to CSV."""
        sql = f"COPY {table_name} TO '{csv_path}' (FORMAT CSV, HEADER)"
        return self.execute_query(project, database, sql, read_only=False)
