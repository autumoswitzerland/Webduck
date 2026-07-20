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
#  Version:   0.1.0
#  Date:      2026-07-20
# =============================================================================

"""WebDuck storage engine - DuckDB operations."""

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

    def _get_db_path(self, project: str, database: str) -> Path:
        """Get the full path to a database file."""
        return self.data_dir / project / f"{database}.duckdb"

    def list_projects(self) -> list[str]:
        """List all projects in the data directory."""
        if not self.data_dir.exists():
            return []
        return [
            d.name
            for d in self.data_dir.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        ]

    def list_databases(self, project: str) -> list[str]:
        """List all databases in a project."""
        project_dir = self.data_dir / project
        if not project_dir.exists():
            return []
        return [
            f.stem
            for f in project_dir.glob("*.duckdb")
            if f.is_file()
        ]

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
                    if result.description:
                        columns = [desc[0] for desc in result.description]
                        rows = [list(r) for r in result.fetchall()]
                    else:
                        columns = []
                        rows = []
                    return {
                        "success": True,
                        "columns": columns,
                        "rows": rows,
                        "row_count": len(rows),
                    }
                finally:
                    con.close()
            except Exception as e:
                return {"success": False, "error": str(e)}

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
