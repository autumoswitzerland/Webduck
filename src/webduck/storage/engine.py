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
#  execution, table listing, and CSV/Parquet/JSON import/export. Uses per-file
#  reader-writer locks: parallel reads (read-only connections) and exclusive
#  writes, mirroring DuckDB's concurrency model.
#
#  Project:   WebDuck
#  Author:    autumo GmbH
#  Date:      2026-07-20
# =============================================================================

"""WebDuck storage engine - DuckDB operations."""

import json
import threading
import weakref
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import duckdb

# DuckDB reserved catalog / database names.
# "main", "temp", and "system" are internal catalog names — using them as
# a user-defined database filename causes ambiguous references and silent
# failures (e.g. duckdb_tables() returns wrong database_name).
RESERVED_DUCKDB_NAMES = {"main", "temp", "system"}


class _RWLock:
    """Readers-writer lock with writer preference.

    Multiple readers may hold the lock simultaneously (shared); a writer
    is exclusive. Once a writer is waiting, new readers queue behind it so
    a steady stream of reads cannot starve writes.

    This mirrors DuckDB's concurrency model: several read-only connections
    to the same database file run in parallel, while writes are serialized
    (DuckDB allows a single writer per database). It also guarantees that a
    read-only and a read-write connection to the same file are never open
    at the same time — a combination DuckDB rejects in one process.
    """

    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._readers = 0
        self._writer = False
        self._waiting_writers = 0

    def acquire_read(self) -> None:
        with self._cond:
            while self._writer or self._waiting_writers:
                self._cond.wait()
            self._readers += 1

    def release_read(self) -> None:
        with self._cond:
            self._readers -= 1
            if self._readers == 0:
                self._cond.notify_all()

    def acquire_write(self) -> None:
        with self._cond:
            self._waiting_writers += 1
            try:
                while self._writer or self._readers:
                    self._cond.wait()
                self._writer = True
            finally:
                self._waiting_writers -= 1

    def release_write(self) -> None:
        with self._cond:
            self._writer = False
            self._cond.notify_all()


class _DBLock:
    """Wrapper class so an RW-lock can live in a WeakValueDictionary.

    The ``_locks`` dict in StorageEngine holds these wrappers via weak
    references. As long as any thread holds a strong reference (waiting on
    or holding the lock), the entry stays alive; once no thread uses the
    lock anymore, the entry is collected by GC automatically. This avoids
    unbounded dict growth without an explicit ``pop()``, which would race
    against a new lock object being created for the same path.

    ``__weakref__`` must be declared in ``__slots__`` so the wrapper itself
    is weak-referenceable.
    """

    __slots__ = ("rwlock", "__weakref__")

    def __init__(self) -> None:
        self.rwlock = _RWLock()

    @contextmanager
    def read(self) -> Generator[None, None, None]:
        """Acquire the lock in shared (read) mode."""
        self.rwlock.acquire_read()
        try:
            yield
        finally:
            self.rwlock.release_read()

    @contextmanager
    def write(self) -> Generator[None, None, None]:
        """Acquire the lock in exclusive (write) mode."""
        self.rwlock.acquire_write()
        try:
            yield
        finally:
            self.rwlock.release_write()

    def acquire_write(self) -> None:
        self.rwlock.acquire_write()

    def release_write(self) -> None:
        self.rwlock.release_write()


class StorageEngine:
    """DuckDB storage engine with file-locking for concurrent access."""

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        # Per-file reader-writer locks guard concurrent access to the same
        # .duckdb file. DuckDB allows several read-only connections to run in
        # parallel, but only one writer per database — and mixing a read-only
        # connection with a read-write connection to the same file in one
        # process is not allowed either. The shared (read) mode lets reads
        # run in parallel; the exclusive (write) mode serializes writes and
        # guarantees read-only and read-write connections never overlap.
        # `_locks` is a WeakValueDictionary holding `_DBLock` wrappers —
        # entries vanish via GC once no thread uses the lock anymore, keeping
        # the dict from growing unboundedly.
        # `_locks_lock` guards creation of new entries (not the locks
        # themselves).
        self._locks: weakref.WeakValueDictionary[str, _DBLock] = (
            weakref.WeakValueDictionary()
        )
        self._locks_lock = threading.Lock()

    def _get_lock(self, db_path: str) -> _DBLock:
        """Get or create the lock wrapper for a specific database file."""
        with self._locks_lock:
            wrapper = self._locks.get(db_path)
            if wrapper is None:
                wrapper = _DBLock()
                self._locks[db_path] = wrapper
            return wrapper

    # ------------------------------------------------------------------
    #  Project order (JSON)
    # ------------------------------------------------------------------

    def _project_order_path(self) -> Path:
        return self.data_dir / ".projects.json"

    def _load_project_order(self) -> list[str]:
        """Load project order from JSON, sync with filesystem.

        Projects can be created outside the app (e.g. by mounting a volume),
        so we always reconcile the JSON list against the actual directories on
        disk. Missing entries are appended at the end in sorted order.
        """
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
                # Only keep entries that still exist on disk; drop deleted ones
                ordered = [
                    p for p in data.get("projects", [])
                    if p in fs_projects
                ]
            except (json.JSONDecodeError, KeyError):
                ordered = []
        else:
            ordered = []

        # Append any new directories not yet in the JSON (alphabetically)
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
        """Create a new empty database.

        We open and immediately close a DuckDB connection here because
        DuckDB creates the .duckdb file lazily on connect — the file
        won't exist until a connection is opened at least once.

        Returns False if the database name is reserved by DuckDB
        (e.g. "main", "temp", "system") or already exists.
        """
        if database.lower() in RESERVED_DUCKDB_NAMES:
            return False

        project_dir = self.data_dir / project
        project_dir.mkdir(parents=True, exist_ok=True)

        db_path = self._get_db_path(project, database)
        if db_path.exists():
            return False

        # Lock is acquired to avoid a race where two concurrent calls try to
        # create the same database file simultaneously.
        lock = self._get_lock(str(db_path))
        with lock.write():
            con = duckdb.connect(str(db_path))
            con.close()
        return True

    def delete_database(self, project: str, database: str) -> bool:
        """Delete a database."""
        db_path = self._get_db_path(project, database)
        if not db_path.exists():
            return False

        lock = self._get_lock(str(db_path))
        with lock.write():
            db_path.unlink()
        return True

    def database_size(self, project: str, database: str) -> int | None:
        """Return the current database file size in bytes.

        Returns ``None`` if the database does not exist.  This is a pure
        file-stat — no DuckDB connection is opened.
        """
        db_path = self._get_db_path(project, database)
        if not db_path.exists():
            return None
        return db_path.stat().st_size

    def fragmentation(self, project: str, database: str) -> float | None:
        """Return the fragmentation ratio (free_blocks / total_blocks).

        Reads ``PRAGMA database_size`` on a read-only connection under the
        shared lock, so it never blocks other readers and cannot overlap a
        writer.  Returns ``None`` if the database does not exist or has no
        blocks yet.  ``0.0`` means no free blocks, ``0.5`` means half of the
        blocks are free (i.e. reclaimable by ``compact_database``).
        """
        db_path = self._get_db_path(project, database)
        if not db_path.exists():
            return None

        lock = self._get_lock(str(db_path))
        with lock.read():
            con = duckdb.connect(str(db_path), read_only=True)
            try:
                row = con.execute("PRAGMA database_size").fetchone()
            finally:
                con.close()
        if row is None:
            return None
        total = int(row[4])
        free = int(row[5])
        if total <= 0:
            return None
        return free / total

    def compact_database(self, project: str, database: str) -> dict[str, Any]:
        """Compact a database to reclaim unused space.

        DuckDB cannot compact a file in place: ``VACUUM`` does not reclaim
        space and ``CHECKPOINT`` only reclaims it partially (row groups
        with heavy deletes).  The documented way to fully reclaim space is
        to copy the database into a fresh file with ``COPY FROM DATABASE``.

        ``COPY FROM DATABASE`` with both schema and data copies tables in an
        arbitrary order, which trips DuckDB's foreign-key checks on valid
        data (known issue, duckdb#16785/#24215): a child table is inserted
        before its parent and DuckDB rejects it.  We therefore copy the
        schema first (``COPY FROM DATABASE ... (SCHEMA)``) and then stream
        the data table-by-table, ordered by foreign-key dependencies so
        parents always precede their children.  Tables with self-referential
        foreign keys are copied row-by-row (duckdb#7168).

        The copy runs under the exclusive (write) lock so no other
        connection can touch the file in the meantime:

          1. flush the WAL into the main file (``CHECKPOINT``),
          2. copy the source (attached read-only) into a temporary file
             in the same directory — schema first, then data ordered by
             foreign-key dependencies,
          3. atomically replace the original file with the compacted one.

        A temporary file next to the original keeps the final ``replace()``
        on the same filesystem (atomic).  It requires free disk space
        roughly equal to the current database size for the copy — checked
        up front so we fail with a clear message instead of mid-copy.

        Returns ``size_before`` / ``size_after`` (bytes) and
        ``saved_percent`` on success.
        """
        db_path = self._get_db_path(project, database)
        if not db_path.exists():
            return {
                "success": False,
                "error": f"Database not found: {project}/{database}",
            }

        size_before = db_path.stat().st_size

        import shutil
        free = shutil.disk_usage(db_path.parent).free
        if free < size_before:
            return {
                "success": False,
                "error": (
                    f"Not enough free disk space to compact "
                    f"'{project}/{database}': need ~{size_before} bytes, "
                    f"only {free} bytes available"
                ),
            }

        lock = self._get_lock(str(db_path))
        tmp_path = db_path.with_name(db_path.name + ".compact.tmp")
        with lock.write():
            try:
                # Remove any stale temp file from a previous failed run.
                tmp_path.unlink(missing_ok=True)

                # 1. Flush the WAL into the main file so the copy is complete.
                con = duckdb.connect(str(db_path))
                try:
                    con.execute("CHECKPOINT")
                finally:
                    con.close()

                # 2. Copy the source (read-only) into a fresh file.
                mem = duckdb.connect(":memory:")
                try:
                    mem.execute(f"ATTACH '{db_path}' AS src (READ_ONLY)")
                    mem.execute(f"ATTACH '{tmp_path}' AS dst")
                    # Schema first (tables, constraints, sequences, views,
                    # macros), then data. A single "COPY FROM DATABASE" would
                    # insert tables in an arbitrary order and fail DuckDB's
                    # foreign-key checks on valid data (duckdb#16785).
                    mem.execute("COPY FROM DATABASE src TO dst (SCHEMA)")
                    order, self_refs = self._fk_ordered_tables(mem, "src")
                    for table in order:
                        if table in self_refs:
                            # duckdb#7168: a self-referential foreign key
                            # cannot be populated with a multi-row INSERT;
                            # rows must be inserted one at a time.
                            rows = mem.execute(
                                f'SELECT * FROM src."{table}"'
                            ).fetchall()
                            if rows:
                                placeholders = ", ".join("?" * len(rows[0]))
                                for row in rows:
                                    mem.execute(
                                        f'INSERT INTO dst."{table}" '
                                        f"VALUES ({placeholders})",
                                        row,
                                    )
                        else:
                            mem.execute(
                                f'INSERT INTO dst."{table}" SELECT * FROM src."{table}"'
                            )
                finally:
                    mem.close()

                # 3. Atomically swap the compacted file in.
                tmp_path.replace(db_path)
            except Exception as e:
                tmp_path.unlink(missing_ok=True)
                return {"success": False, "error": str(e)}

        size_after = db_path.stat().st_size
        saved_bytes = max(0, size_before - size_after)
        saved_percent = round(saved_bytes / size_before * 100, 1) if size_before else 0
        grew_bytes = max(0, size_after - size_before)
        grew_percent = round(grew_bytes / size_before * 100, 1) if size_before else 0
        return {
            "success": True,
            "size_before": size_before,
            "size_after": size_after,
            "saved_bytes": saved_bytes,
            "saved_percent": saved_percent,
            "grew_bytes": grew_bytes,
            "grew_percent": grew_percent,
        }

    @staticmethod
    def _fk_ordered_tables(
        con: duckdb.DuckDBPyConnection, catalog: str
    ) -> tuple[list[str], set[str]]:
        """Return base-table names ordered so referenced tables come first.

        A single ``COPY FROM DATABASE`` inserts tables in an arbitrary order
        and trips DuckDB's foreign-key checks on otherwise valid data
        (duckdb#16785/#24215).  Copying each table's data separately in
        dependency order — parents before children — sidesteps the bug.

        The foreign-key graph of a DuckDB database is acyclic (``ALTER TABLE``
        support for adding constraints is not implemented), so a plain
        post-order DFS is sufficient.  Self-referential foreign keys are a
        special case: DuckDB cannot insert multiple rows referencing each
        other in one statement (duckdb#7168), so those tables must be copied
        row-by-row.  The second return value lists them.
        """
        tables = [r[0] for r in con.execute(
            f"SELECT table_name FROM information_schema.tables "
            f"WHERE table_catalog = '{catalog}' AND table_schema = 'main' "
            f"AND table_type = 'BASE TABLE'"
        ).fetchall()]
        referenced_by = {t: set() for t in tables}
        self_refs: set[str] = set()
        for t in tables:
            rows = con.execute(
                f"SELECT referenced_table FROM duckdb_constraints() "
                f"WHERE database_name = '{catalog}' AND schema_name = 'main' "
                f"AND table_name = '{t}' AND constraint_type = 'FOREIGN KEY'"
            ).fetchall()
            for (ref,) in rows:
                if not ref or ref not in referenced_by:
                    continue
                if ref == t:
                    self_refs.add(t)
                else:
                    referenced_by[t].add(ref)

        ordered: list[str] = []
        visited: set[str] = set()

        def visit(table: str) -> None:
            if table in visited:
                return
            visited.add(table)
            for ref in sorted(referenced_by[table]):
                visit(ref)
            ordered.append(table)

        for table in tables:
            visit(table)
        return ordered, self_refs

    def delete_project(self, project: str) -> bool:
        """Delete a project and all its databases."""
        project_dir = self.data_dir / project
        if not project_dir.exists():
            return False

        # Acquire the locks of all contained databases first, so a running
        # query on one of them cannot collide with the recursive delete
        # (which would surface as a file-not-found error mid-query or a
        # lost write). Locks are taken in sorted path order and released
        # in reverse — harmless here since no other path acquires multiple
        # locks at once, so no deadlock can occur.
        db_files = sorted(
            p for p in project_dir.glob("*.duckdb") if p.is_file()
        )
        locks = [self._get_lock(str(p)) for p in db_files]
        for lock in locks:
            lock.acquire_write()
        try:
            import shutil
            shutil.rmtree(project_dir)
        finally:
            for lock in reversed(locks):
                lock.release_write()

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
        """Execute a SQL query and return results.

        The per-file lock is held for the entire duration of the query.
        ``read_only`` selects the lock mode: True acquires a shared lock and
        opens a read-only connection (parallel readers), False acquires the
        exclusive lock and opens a read-write connection. Holding the lock
        guarantees that a read-only and a read-write connection to the same
        file never overlap — a combination DuckDB rejects in one process.
        """
        db_path = self._get_db_path(project, database)
        if not db_path.exists():
            return {
                "success": False,
                "error": f"Database not found: {project}/{database}",
            }

        lock = self._get_lock(str(db_path))
        with (lock.read() if read_only else lock.write()):
            try:
                con = duckdb.connect(str(db_path), read_only=read_only)
                try:
                    result = con.execute(sql, params or None)
                    # `result` is None for DDL/DML statements that don't return
                    # rows (CREATE, INSERT, DROP, etc.). `description` is only
                    # set when there is a result set (SELECT, EXPLAIN, etc.).
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
                # DuckDB throws "Catalog Error" when you try to DROP a table
                # that is referenced by a foreign key. Since the error message
                # itself is not very helpful, we scan for FK dependencies and
                # append a human-readable hint listing the dependent tables.
                if "Catalog Error" in error_msg:
                    hint = self._get_drop_hint(db_path, sql)
                    if hint:
                        error_msg += f"\n\n{hint}"
                return {"success": False, "error": error_msg}

    def _get_drop_hint(self, db_path, sql: str) -> str | None:
        """Check FK dependencies for DROP TABLE/VIEW and return a hint.

        DuckDB enforces foreign key constraints on DROP — you cannot drop a
        table that is referenced by another table's FK without CASCADE.  The
        native error is a generic "Catalog Error" which is not actionable, so
        this method queries `duckdb_constraints()` to build a list of
        dependent tables and suggests the user drops dependencies first or
        uses CASCADE.

        NOTE: We only check the `main` schema. Other schemas (e.g. `temp`)
        are unlikely to have user-defined FK relationships in this context.
        """
        import re
        sql_upper = sql.strip().upper()

        is_drop = (
            sql_upper.startswith("DROP TABLE")
            or sql_upper.startswith("DROP VIEW")
        )
        if not is_drop:
            return None

        # Extract the unqualified table/view name, tolerating IF EXISTS and
        # optional quoting (backticks, double-quotes, single-quotes).
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
                # `duckdb_constraints()` is a system catalog function that
                # returns all constraints across all tables. We filter to
                # FOREIGN KEY only to find which tables reference `target`.
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
            # Match case-insensitively since the FK text may use mixed case
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
        """Execute one or more SQL statements and return results for each.

        Statements are split by `;` and executed sequentially.  On the first
        failure execution stops — later statements are not attempted.  This
        is intentional: multi-statement uploads (CREATE + INSERT, etc.)
        should be atomic-ish from the user's perspective; running later
        statements after an earlier failure could leave the database in an
        inconsistent state.

        NOTE: This is a naive split — semicolons inside string literals or
        comments will break parsing.  DuckDB's own `execute()` would handle
        that correctly, but we need per-statement error reporting which
        requires individual calls.
        """
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
        """Get information about all tables in a database.

        Queries `information_schema` which is DuckDB's SQL-standard catalog.
        Note the N+1 query pattern: one query to list tables, then one
        additional query per table for its columns.  For the small number of
        tables typical in this app this is fine — a single self-join query
        would be more efficient at scale but harder to read.
        """
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
        """Import a CSV file into a table.

        Uses DuckDB's ``read_csv_auto()`` which infers column types and
        handles headers, quoted fields, and various delimiters
        automatically.  For non-standard delimiters (e.g. ``$`` in
        FAERS/Pharma TXT files) the delimiter is detected by counting
        the most consistent separator in the first 50 lines and passed
        explicitly via ``delim=``.

        The ``CREATE OR REPLACE`` means an existing table with the same
        name will be silently overwritten — this is intentional for
        re-imports.
        """
        if not csv_path.exists():
            return {"success": False, "error": f"CSV file not found: {csv_path}"}

        delim = self._detect_delimiter(csv_path)
        delim_param = f", delim='{delim}'" if delim else ""
        sql = (
            f"CREATE OR REPLACE TABLE {table_name} AS "
            f"SELECT * FROM read_csv_auto('{csv_path}'{delim_param})"
        )
        return self.execute_query(project, database, sql, read_only=False)

    @staticmethod
    def _detect_delimiter(csv_path: Path) -> str | None:
        """Detect the most likely delimiter for a CSV/TXT file.

        Reads the first 50 non-empty lines, counts column splits for
        each candidate delimiter, and returns the one with the most
        consistent (stable) column count.  Returns ``None`` for
        standard CSV/TSV files where DuckDB's built-in detection
        already works.
        """
        candidates = ["$", "|", ":", "~", ";"]
        try:
            with open(csv_path, errors="replace") as f:
                lines = [line.rstrip("\n\r") for _, line in zip(range(50), f)]
        except Exception:
            return None

        lines = [line for line in lines if line.strip()]
        if len(lines) < 2:
            return None

        best_delim = None
        best_score = 0

        for d in candidates:
            counts = [line.count(d) for line in lines]
            if all(c == 0 for c in counts):
                continue
            # Use the median column count as target.
            col_counts = [c + 1 for c in counts]
            col_counts.sort()
            median = col_counts[len(col_counts) // 2]
            if median < 2:
                continue
            # Score = how many lines match the median column count.
            matches = sum(1 for c in col_counts if c == median)
            score = matches / len(col_counts)
            if score > best_score or (score == best_score and
                                      best_delim is None):
                best_score = score
                best_delim = d

        # Only return if confidence is high (> 80% consistent).
        return best_delim if best_score > 0.8 else None

    def export_csv(
        self,
        project: str,
        database: str,
        table_name: str,
        csv_path: Path,
    ) -> dict[str, Any]:
        """Export a table to CSV.

        Uses DuckDB's `COPY ... TO` statement.  The HEADER option writes
        column names as the first row.  DuckDB writes CSVs very efficiently
        (C++ backend) so even large tables are fast.
        """
        sql = f"COPY {table_name} TO '{csv_path}' (FORMAT CSV, HEADER)"
        return self.execute_query(project, database, sql, read_only=False)

    # ------------------------------------------------------------------
    #  Import/Export — Parquet
    # ------------------------------------------------------------------

    def import_parquet(
        self,
        project: str,
        database: str,
        table_name: str,
        parquet_path: Path,
    ) -> dict[str, Any]:
        """Import a Parquet file into a table."""
        if not parquet_path.exists():
            return {"success": False, "error": f"Parquet file not found: {parquet_path}"}

        sql = (
            f"CREATE OR REPLACE TABLE {table_name} AS "
            f"SELECT * FROM read_parquet('{parquet_path}')"
        )
        return self.execute_query(project, database, sql, read_only=False)

    def export_parquet(
        self,
        project: str,
        database: str,
        table_name: str,
        parquet_path: Path,
    ) -> dict[str, Any]:
        """Export a table to Parquet."""
        sql = f"COPY {table_name} TO '{parquet_path}' (FORMAT PARQUET)"
        return self.execute_query(project, database, sql, read_only=False)

    # ------------------------------------------------------------------
    #  Import/Export — JSON
    # ------------------------------------------------------------------

    def import_json(
        self,
        project: str,
        database: str,
        table_name: str,
        json_path: Path,
    ) -> dict[str, Any]:
        """Import a JSON/NDJSON file into a table.

        DuckDB's ``read_json_auto()`` handles both newline-delimited
        JSON (NDJSON) and JSON arrays automatically.
        """
        if not json_path.exists():
            return {"success": False, "error": f"JSON file not found: {json_path}"}

        sql = (
            f"CREATE OR REPLACE TABLE {table_name} AS "
            f"SELECT * FROM read_json_auto('{json_path}')"
        )
        return self.execute_query(project, database, sql, read_only=False)

    def export_json(
        self,
        project: str,
        database: str,
        table_name: str,
        json_path: Path,
    ) -> dict[str, Any]:
        """Export a table to NDJSON (one JSON object per line)."""
        sql = f"COPY {table_name} TO '{json_path}' (FORMAT JSON, ARRAY true)"
        return self.execute_query(project, database, sql, read_only=False)

    # ------------------------------------------------------------------
    #  Import/Export — Format dispatcher
    # ------------------------------------------------------------------

    @staticmethod
    def detect_format(file_path: Path) -> str:
        """Detect file format by extension.

        Returns one of: ``"csv"``, ``"parquet"``, ``"json"``.
        Falls back to ``"csv"`` for unknown extensions.
        """
        ext = file_path.suffix.lower()
        if ext == ".parquet":
            return "parquet"
        if ext in (".json", ".jsonl", ".ndjson"):
            return "json"
        return "csv"

    def import_data(
        self,
        project: str,
        database: str,
        table_name: str,
        file_path: Path,
        fmt: str | None = None,
    ) -> dict[str, Any]:
        """Import a file into a table. Auto-detects format if not specified."""
        if fmt is None:
            fmt = self.detect_format(file_path)
        if fmt == "parquet":
            return self.import_parquet(project, database, table_name, file_path)
        if fmt == "json":
            return self.import_json(project, database, table_name, file_path)
        return self.import_csv(project, database, table_name, file_path)

    def export_data(
        self,
        project: str,
        database: str,
        table_name: str,
        file_path: Path,
        fmt: str = "csv",
    ) -> dict[str, Any]:
        """Export a table to a file in the given format."""
        if fmt == "parquet":
            return self.export_parquet(project, database, table_name, file_path)
        if fmt == "json":
            return self.export_json(project, database, table_name, file_path)
        return self.export_csv(project, database, table_name, file_path)
