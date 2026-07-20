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
#    GET  /db/projects                                          — List projects
#    GET  /db/projects/{project}/databases                       — List databases
#    POST /db/projects/{project}/databases/{db}/query            — Execute SELECT
#    POST /db/projects/{project}/databases/{db}/write            — Execute INSERT/UPDATE/DELETE
#    GET  /db/projects/{project}/databases/{db}/tables           — List tables
#    POST /db/projects/{project}/databases/{db}/import/csv       — Import CSV
#    GET  /db/projects/{project}/databases/{db}/export/csv/{tbl} — Export CSV
#
#  Project:   WebDuck
#  Author:    autumo GmbH
#  Version:   0.1.0
#  Date:      2026-07-20
# =============================================================================

"""WebDuck REST API - Database endpoints (project/db/password protected)."""

from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel

from webduck.auth.manager import ProjectAuth
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


def verify_project_key(
    project: str,
    database: str,
    x_project_key: str = Header(..., description="Format: project:password"),
) -> str:
    """Verify project key and return password."""
    if not project_auth:
        raise HTTPException(status_code=500, detail="Project auth not initialized")

    try:
        _, password = x_project_key.split(":", 1)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid project key format. Use: project:password",
        )

    if not project_auth.has_database_access(project, database, password, "read"):
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
        raise HTTPException(status_code=500, detail="Storage engine not initialized")
    return storage_engine.list_projects()


@router.get("/projects/{project}/databases")
async def list_databases(project: str) -> list[str]:
    """List all databases in a project (public)."""
    if not storage_engine:
        raise HTTPException(status_code=500, detail="Storage engine not initialized")
    return storage_engine.list_databases(project)


@router.post("/projects/{project}/databases/{database}/query", response_model=QueryResponse)
async def execute_query(
    project: str,
    database: str,
    req: QueryRequest,
    password: str = Depends(verify_project_key),
) -> QueryResponse:
    """Execute a SQL query (read-only)."""
    if not storage_engine:
        raise HTTPException(status_code=500, detail="Storage engine not initialized")

    result = storage_engine.execute_query(project, database, req.sql, req.params, read_only=True)
    from webduck.logging import log_query
    log_query(project, database, req.sql, result["success"],
              row_count=result.get("row_count", 0), error=result.get("error", ""))
    return QueryResponse(**result)


@router.post("/projects/{project}/databases/{database}/write", response_model=QueryResponse)
async def execute_write(
    project: str,
    database: str,
    req: QueryRequest,
    password: str = Depends(verify_project_key),
) -> QueryResponse:
    """Execute a SQL query (read-write)."""
    if not storage_engine:
        raise HTTPException(status_code=500, detail="Storage engine not initialized")

    # Verify write access
    if not project_auth:
        raise HTTPException(status_code=500, detail="Project auth not initialized")

    if not project_auth.has_database_access(project, database, password, "write"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Write access denied",
        )

    result = storage_engine.execute_query(project, database, req.sql, req.params, read_only=False)
    from webduck.logging import log_query
    log_query(project, database, req.sql, result["success"],
              row_count=result.get("row_count", 0), error=result.get("error", ""))
    return QueryResponse(**result)


@router.get("/projects/{project}/databases/{database}/tables")
async def list_tables(
    project: str,
    database: str,
    password: str = Depends(verify_project_key),
) -> dict:
    """List all tables in a database."""
    if not storage_engine:
        raise HTTPException(status_code=500, detail="Storage engine not initialized")

    result = storage_engine.get_table_info(project, database)
    return result


@router.post("/projects/{project}/databases/{database}/import")
async def import_csv(
    project: str,
    database: str,
    table_name: str,
    csv_path: str,
    password: str = Depends(verify_project_key),
) -> dict:
    """Import a CSV file into a table."""
    if not storage_engine:
        raise HTTPException(status_code=500, detail="Storage engine not initialized")

    # Verify write access
    if not project_auth:
        raise HTTPException(status_code=500, detail="Project auth not initialized")

    if not project_auth.has_database_access(project, database, password, "write"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Write access denied",
        )

    result = storage_engine.import_csv(project, database, table_name, Path(csv_path))
    return result


@router.get("/projects/{project}/databases/{database}/export")
async def export_csv(
    project: str,
    database: str,
    table_name: str,
    csv_path: str,
    password: str = Depends(verify_project_key),
) -> dict:
    """Export a table to CSV."""
    if not storage_engine:
        raise HTTPException(status_code=500, detail="Storage engine not initialized")

    # Verify write access
    if not project_auth:
        raise HTTPException(status_code=500, detail="Project auth not initialized")

    if not project_auth.has_database_access(project, database, password, "write"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Write access denied",
        )

    result = storage_engine.export_csv(project, database, table_name, Path(csv_path))
    return result
