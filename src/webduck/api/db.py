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
#  WebDuck — Database REST API
#  ---------------------------------------------------------------------------
#  Project-key protected endpoints for SQL query execution and database access.
#
#  Authentication via X-Project-Key header (project:password).
#
#  Endpoints:
#    GET  /db/projects                                           — List projects
#    GET  /db/projects/{project}/databases                       — List databases
#    POST /db/projects/{project}/databases/{db}/query            — Execute SELECT
#    POST /db/projects/{project}/databases/{db}/write            — Execute INSERT/UPDATE/DELETE
#    GET  /db/projects/{project}/databases/{db}/tables           — List tables
#    POST /db/projects/{project}/databases/{db}/import/{tbl}     — Import CSV, JSON, Parquet
#    GET  /db/projects/{project}/databases/{db}/export/{tbl}     — Export CSV, JSON, Parquet
#
#  Project:   WebDuck
#  Author:    autumo GmbH
#  Date:      2026-07-20
# =============================================================================

"""WebDuck REST API - Database endpoints (project/db/password protected)."""

from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel

from webduck.auth.manager import ProjectAuth
from webduck.logging import log_error, log_query, log_warning
from webduck.storage.engine import StorageEngine

router = APIRouter(prefix="/db", tags=["database"])

# These will be set by the main app
storage_engine: StorageEngine | None = None
project_auth: ProjectAuth | None = None


def set_dependencies(storage: StorageEngine) -> None:
    """Set dependencies for database endpoints."""
    global storage_engine, project_auth
    storage_engine = storage
    project_auth = ProjectAuth(storage.data_dir)


# ---------------------------------------------------------------------------
#  X-Project-Key Authentication
# ---------------------------------------------------------------------------
#  Clients authenticate by sending the X-Project-Key header with value
#  "project:password". The header is parsed by splitting on the first ':'.
#
#  The flow is:
#    1. Check if the target database has ANY password configured (read or write).
#       - If NO password is set, the database is "open access" — any request
#         is allowed without credentials. This is the default for local/dev.
#    2. If a password IS configured, the header must be present and well-formed.
#    3. The password portion is verified against bcrypt hashes stored in the
#       project's .project.json config file (see ProjectAuth for details).
#
#  Access level escalation:
#    - A write-level password also grants read access (checked in
#      ProjectAuth.has_database_access), so a single credential can cover
#      both read and write operations.
#    - A read-level password does NOT grant write access.
# ---------------------------------------------------------------------------

def verify_project_key(
    project: str,
    database: str,
    x_project_key: str | None = Header(None, description="Format: project:password"),
) -> str | None:
    """Verify project key and return password. Optional if no password is set."""
    if not project_auth:
        log_error("verify_project_key: Project auth not initialized")
        raise HTTPException(status_code=500, detail="Project auth not initialized")

    # Fast path: if no password is configured for this database, grant open access.
    # has_database_password checks both read and write hashes — if neither exists,
    # the database is unprotected and we return None (no password needed).
    if not project_auth.has_database_password(project, database):
        return None

    # Password is configured, so the header MUST be present.
    if not x_project_key:
        log_warning(f"verify_project_key: Missing auth header for '{project}/{database}'")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "This database requires authentication. "
                "Use X-Project-Key header (format: project:password)"
            ),
        )

    # Parse "project:password" — split on first ':' only so passwords containing
    # ':' are handled correctly (e.g. "myproject:p:ass:word").
    try:
        _, password = x_project_key.split(":", 1)
    except ValueError:
        log_warning(f"verify_project_key: Invalid key format for '{project}/{database}'")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid project key format. Use: project:password",
        )

    # has_database_access checks the requested access level (read) and also
    # tries write-level as a fallback (write grants read). Passwords are
    # bcrypt-hashed and verified via constant-time comparison.
    if not project_auth.has_database_access(project, database, password, "read"):
        log_warning(f"verify_project_key: Invalid credentials for '{project}/{database}'")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    return password


# --- Request/Response Models ---

class QueryRequest(BaseModel):
    sql: str
    params: dict | None = None


class QueryResponse(BaseModel):
    success: bool
    columns: list[str] = []
    rows: list[list] = []
    row_count: int = 0
    error: str = ""


# --- Endpoints ---

@router.get("/projects")
async def list_projects() -> list[str]:
    """List all projects (public)."""
    if not storage_engine:
        log_error("list_projects: Storage engine not initialized")
        raise HTTPException(status_code=500, detail="Storage engine not initialized")
    return storage_engine.list_projects()


@router.get("/projects/{project}/databases")
async def list_databases(project: str) -> list[str]:
    """List all databases in a project (public)."""
    if not storage_engine:
        log_error("list_databases: Storage engine not initialized")
        raise HTTPException(status_code=500, detail="Storage engine not initialized")
    return storage_engine.list_databases(project)


@router.post("/projects/{project}/databases/{database}/query", response_model=QueryResponse)
async def execute_query(
    project: str,
    database: str,
    req: QueryRequest,
    password: str = Depends(verify_project_key),
) -> QueryResponse:
    """Execute a SQL query (read-only).

    Runs the query with read_only=True, which restricts execution to
    SELECT statements. DuckDB enforces this at the connection level —
    any INSERT/UPDATE/DELETE will raise an error even if passed here.
    The engine still uses execute_query (not execute_queries) because
    read-only queries return result sets.
    """
    if not storage_engine:
        log_error("execute_query: Storage engine not initialized")
        raise HTTPException(status_code=500, detail="Storage engine not initialized")

    result = storage_engine.execute_query(project, database, req.sql, req.params, read_only=True)
    log_query(project, database, req.sql, result["success"],
              row_count=result.get("row_count", 0), error=result.get("error", ""))
    if not result["success"]:
        log_error(f"Query failed [{project}/{database}]: {result.get('error', 'unknown')}")
    return QueryResponse(**result)


@router.post("/projects/{project}/databases/{database}/write", response_model=QueryResponse)
async def execute_write(
    project: str,
    database: str,
    req: QueryRequest,
    password: str = Depends(verify_project_key),
) -> QueryResponse:
    """Execute a SQL query (read-write).

    Accepts DDL (CREATE, ALTER, DROP) and DML (INSERT, UPDATE, DELETE).
    Requires explicit "write" access level — read-only credentials are
    rejected here even though verify_project_key passed.
    """
    if not storage_engine:
        log_error("execute_write: Storage engine not initialized")
        raise HTTPException(status_code=500, detail="Storage engine not initialized")

    # verify_project_key already validated "read" access. We now need to
    # additionally check "write" access, since read credentials should not
    # be able to modify data.
    if not project_auth:
        log_error("execute_write: Project auth not initialized")
        raise HTTPException(status_code=500, detail="Project auth not initialized")

    if not project_auth.has_database_access(project, database, password, "write"):
        log_warning(f"execute_write: Write access denied for '{project}/{database}'")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Write access denied",
        )

    result = storage_engine.execute_query(project, database, req.sql, req.params, read_only=False)
    log_query(project, database, req.sql, result["success"],
              row_count=result.get("row_count", 0), error=result.get("error", ""))
    if not result["success"]:
        log_error(f"Write failed [{project}/{database}]: {result.get('error', 'unknown')}")
    return QueryResponse(**result)


@router.get("/projects/{project}/databases/{database}/tables")
async def list_tables(
    project: str,
    database: str,
    password: str = Depends(verify_project_key),
) -> dict:
    """List all tables in a database.

    Returns table metadata including column names and row counts.
    Internally queries DuckDB's information_schema.
    """
    if not storage_engine:
        log_error("list_tables: Storage engine not initialized")
        raise HTTPException(status_code=500, detail="Storage engine not initialized")

    result = storage_engine.get_table_info(project, database)
    return result


# ---------------------------------------------------------------------------
#  Import
# ---------------------------------------------------------------------------
#  Imports a file from disk into a DuckDB table.
#
#  The path must be an absolute path on the server filesystem that
#  DuckDB can access. The file format can be specified explicitly via
#  `format`. If no format is specified, the format is auto-detected from
#  the file extension.
#
#  Supported formats include:
#    - CSV and delimiter-separated text files
#    - JSON and NDJSON
#    - Parquet
#
#  CSV and other delimiter-separated text files are processed using
#  DuckDB's automatic CSV detection. For non-standard delimiters, the
#  storage engine performs additional delimiter detection before passing
#  the detected delimiter to DuckDB.
#
#  Column names and data types are inferred for CSV/text and JSON files,
#  or read from the embedded schema for Parquet files.
#  The target table is created or replaced during the import. If a table
#  with the same name already exists, it is completely replaced.
#
#  Note: The max upload size is configured via `server.max_upload_mb` in
#  webduck.yaml, but this endpoint operates on server-side file paths,
#  not on uploaded file content — the size limit applies to the NiceGUI UI
#  upload path, not to this REST endpoint directly.
# ---------------------------------------------------------------------------

@router.post("/projects/{project}/databases/{database}/import/{table_name}")
async def import_file(
    project: str,
    database: str,
    table_name: str,
    path: str,
    format: str | None = None,
    password: str = Depends(verify_project_key),
) -> dict:
    """Import a file into a table.

    Supported formats include CSV and delimiter-separated text files,
    JSON/NDJSON, and Parquet. The format is auto-detected from the file
    extension if not specified.

    The target table is created or replaced. If a table with the same name
    already exists, it is completely replaced.

    The path is a server-local file path.
    """    
    if not storage_engine:
        log_error("import: Storage engine not initialized")
        raise HTTPException(status_code=500, detail="Storage engine not initialized")

    # Write access is required — import creates or modifies table data.
    if not project_auth:
        log_error("import: Project auth not initialized")
        raise HTTPException(status_code=500, detail="Project auth not initialized")

    if not project_auth.has_database_access(project, database, password, "write"):
        log_warning(f"import: Write access denied for '{project}/{database}'")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Write access denied",
        )

    # Path is wrapped in a Path object by the engine for safe resolution.
    # DuckDB's read functions handle the actual file I/O.
    result = storage_engine.import_data(project, database, table_name, Path(path), fmt=format)
    if not result.get("success"):
        log_error(f"Import failed [{project}/{database}]: {result.get('error', 'unknown')}")
    return result


# ---------------------------------------------------------------------------
#  Export
# ---------------------------------------------------------------------------
#  Exports a DuckDB table to a file on the server filesystem.
#
#  The output format must be specified via `format` or is set to CSV by
#  default. Supported formats include:
#    - CSV
#    - JSON
#    - Parquet
#
#  The target table must already exist and be a regular table (not a view).
#  The output file is written to the specified server-local path.
#
#  Existing files may be overwritten depending on the behavior of the
#  underlying DuckDB COPY operation.
# ---------------------------------------------------------------------------

@router.get("/projects/{project}/databases/{database}/export/{table_name}")
async def export_file(
    project: str,
    database: str,
    table_name: str,
    path: str,
    format: str = "csv",
    password: str = Depends(verify_project_key),
) -> dict:
    """Export a table to a file.

    Supported formats include CSV, JSON, and Parquet.
    CSV is used by default if no format is specified.

    The path is a server-local destination path.
    """
    if not storage_engine:
        log_error("export: Storage engine not initialized")
        raise HTTPException(status_code=500, detail="Storage engine not initialized")

    # Write access is required — export writes a file to the server filesystem.
    if not project_auth:
        log_error("export: Project auth not initialized")
        raise HTTPException(status_code=500, detail="Project auth not initialized")

    if not project_auth.has_database_access(project, database, password, "write"):
        log_warning(f"export: Write access denied for '{project}/{database}'")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Write access denied",
        )

    result = storage_engine.export_data(project, database, table_name, Path(path), fmt=format)
    if not result.get("success"):
        log_error(f"Export failed [{project}/{database}]: {result.get('error', 'unknown')}")
    return result
