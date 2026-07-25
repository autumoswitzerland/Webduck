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
#  WebDuck — Admin REST API
#  ---------------------------------------------------------------------------
#  JWT-protected admin endpoints for user, project, and database management.
#
#  Endpoints:
#    POST   /admin/login                              — Authenticate, get JWT
#    GET    /admin/projects                           — List projects
#    POST   /admin/projects                           — Create project
#    DELETE /admin/projects/{project}                  — Delete project
#    GET    /admin/projects/{project}/databases        — List databases
#    POST   /admin/projects/{project}/databases        — Create database
#    DELETE /admin/projects/{project}/databases/{db}    — Delete database
#    PUT    /admin/projects/{p}/databases/{db}/password — Set DB password
#    GET    /admin/users                              — List admin users
#    POST   /admin/users                              — Create admin user
#    DELETE /admin/users/{username}                    — Delete admin user
#
#  Project:   WebDuck
#  Author:    autumo GmbH
#  Version:   1.0.0
#  Date:      2026-07-20
# =============================================================================

"""WebDuck REST API - Admin endpoints (JWT protected)."""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from webduck.auth.manager import AuthManager
from webduck.logging import log_error, log_warning
from webduck.storage.engine import StorageEngine

router = APIRouter(prefix="/admin", tags=["admin"])

# HTTPBearer extracts the "Authorization: Bearer <token>" header on each request.
# FastAPI's Depends(security) injects the parsed credentials into endpoints.
security = HTTPBearer()

# These module-level globals are injected once at startup via set_dependencies().
# They act as singletons for the auth and storage layers used by every endpoint.
auth_manager: AuthManager | None = None
storage_engine: StorageEngine | None = None


def set_dependencies(auth: AuthManager, storage: StorageEngine) -> None:
    """Set dependencies for admin endpoints.

    Called once during app startup from main.py to wire in the real
    AuthManager and StorageEngine instances. All admin endpoints depend
    on these being set before serving requests.
    """
    global auth_manager, storage_engine
    auth_manager = auth
    storage_engine = storage


async def verify_admin(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """Verify admin JWT token.

    JWT Authentication Flow:
    1. Client sends request with "Authorization: Bearer <jwt>" header.
    2. HTTPBearer (Depends(security)) extracts the raw token string.
    3. verify_jwt_token() decodes and validates the JWT (expiry, signature).
    4. On success the embedded username is returned and injected into the
       endpoint via the 'username' parameter — proving the caller is authenticated.
    5. On failure (None returned) a 401 is raised before any endpoint logic runs.

    This dependency is attached to every protected endpoint:
        username: str = Depends(verify_admin)
    """
    if not auth_manager:
        log_error("verify_admin: Auth manager not initialized")
        raise HTTPException(status_code=500, detail="Auth manager not initialized")

    # Decode JWT and extract username; returns None if expired/invalid.
    username = auth_manager.verify_jwt_token(credentials.credentials)
    if not username:
        log_warning("verify_admin: Invalid or expired token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    # Return value is injected as 'username' into the calling endpoint.
    return username


# --- Request/Response Models ---

class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    token_type: str = "bearer"


class ProjectRequest(BaseModel):
    name: str


class DatabaseRequest(BaseModel):
    name: str


class PasswordRequest(BaseModel):
    """Request to set a database password.

    access_level controls what operations the password holder can perform
    against the specific database: 'read' (SELECT only), 'write' (INSERT,
    UPDATE, DELETE), or 'admin' (full DDL + DML).
    """
    password: str
    access_level: str = "read"


# --- Endpoints ---

@router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest) -> LoginResponse:
    """Login and get JWT token.

    This is the only unauthenticated admin endpoint. It accepts username +
    password, verifies credentials against the stored bcrypt hash, and
    returns a signed JWT that must be included in all subsequent requests.
    """
    if not auth_manager:
        log_error("login: Auth manager not initialized")
        raise HTTPException(status_code=500, detail="Auth manager not initialized")

    if not auth_manager.verify_user(req.username, req.password):
        log_warning(f"Failed login attempt for user '{req.username}'")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    token = auth_manager.create_jwt_token(req.username)
    return LoginResponse(token=token)


@router.get("/projects")
async def list_projects(username: str = Depends(verify_admin)) -> list[str]:
    """List all projects."""
    if not storage_engine:
        log_error("list_projects: Storage engine not initialized")
        raise HTTPException(status_code=500, detail="Storage engine not initialized")
    return storage_engine.list_projects()


@router.post("/projects")
async def create_project(
    req: ProjectRequest, username: str = Depends(verify_admin)
) -> dict:
    """Create a new project."""
    if not storage_engine:
        log_error("create_project: Storage engine not initialized")
        raise HTTPException(
            status_code=500,
            detail="Storage engine not initialized",
        )

    if not storage_engine.create_project(req.name):
        log_warning(f"create_project: Project '{req.name}' already exists")
        raise HTTPException(
            status_code=400,
            detail="Project already exists",
        )

    return {
        "success": True,
        "message": f"Project '{req.name}' created",
    }


@router.delete("/projects/{project}")
async def delete_project(project: str, username: str = Depends(verify_admin)) -> dict:
    """Delete a project and all its databases."""
    if not storage_engine:
        log_error("delete_project: Storage engine not initialized")
        raise HTTPException(status_code=500, detail="Storage engine not initialized")

    if not storage_engine.delete_project(project):
        raise HTTPException(status_code=404, detail="Project not found")

    return {"success": True, "message": f"Project '{project}' deleted"}


class ReorderRequest(BaseModel):
    """Expects the full desired order as a list of project names.

    The list must contain every existing project exactly once. The storage
    engine persists this ordering so that subsequent list_projects() calls
    return projects in the user-defined sequence (e.g. for a sidebar or
    dashboard layout).
    """
    projects: list[str]


@router.post("/reorder-projects")
async def reorder_projects(
    req: ReorderRequest,
    username: str = Depends(verify_admin),
) -> dict:
    """Reorder projects.

    Accepts the complete ordered list of project names and persists the
    new display order. This is used by the UI to let admins drag-and-drop
    projects into a custom sequence.
    """
    if not storage_engine:
        log_error("reorder_projects: Storage engine not initialized")
        raise HTTPException(
            status_code=500,
            detail="Storage engine not initialized",
        )
    storage_engine.reorder_projects(req.projects)
    return {
        "success": True,
        "message": "Projects reordered",
    }


# --- Project-Scoped Database Endpoints ---
# All database endpoints are nested under a project: /admin/projects/{project}/databases.
# This enforces a two-level hierarchy: a project groups related databases, and every
# database operation requires specifying its parent project. This prevents name
# collisions across projects and keeps the storage layout organized on disk.


@router.get(
    "/projects/{project}/databases"
)
async def list_databases(project: str, username: str = Depends(verify_admin)) -> list[str]:
    """List all databases in a project."""
    if not storage_engine:
        log_error("list_databases: Storage engine not initialized")
        raise HTTPException(status_code=500, detail="Storage engine not initialized")
    return storage_engine.list_databases(project)


@router.post("/projects/{project}/databases")
async def create_database(
    project: str, req: DatabaseRequest, username: str = Depends(verify_admin)
) -> dict:
    """Create a new database in a project."""
    if not storage_engine:
        log_error("create_database: Storage engine not initialized")
        raise HTTPException(status_code=500, detail="Storage engine not initialized")

    if storage_engine.database_exists(project, req.name):
        log_warning(f"create_database: Database '{req.name}' already exists in '{project}'")
        raise HTTPException(status_code=400, detail="Database already exists")

    if not storage_engine.create_database(project, req.name):
        log_error(f"create_database: Failed to create database '{req.name}' in '{project}'")
        raise HTTPException(status_code=500, detail="Failed to create database")

    return {"success": True, "message": f"Database '{req.name}' created in project '{project}'"}


@router.delete("/projects/{project}/databases/{database}")
async def delete_database(
    project: str, database: str, username: str = Depends(verify_admin)
) -> dict:
    """Delete a database."""
    if not storage_engine:
        log_error("delete_database: Storage engine not initialized")
        raise HTTPException(status_code=500, detail="Storage engine not initialized")

    if not storage_engine.delete_database(project, database):
        raise HTTPException(status_code=404, detail="Database not found")

    return {"success": True, "message": f"Database '{database}' deleted"}


@router.put("/projects/{project}/databases/{database}/password")
async def set_database_password(
    project: str,
    database: str,
    req: PasswordRequest,
    username: str = Depends(verify_admin),
) -> dict:
    """Set password for database access.

    This endpoint uses ProjectAuth (a separate auth layer from the admin JWT
    system) to manage per-database credentials. The local import avoids a
    circular dependency since ProjectAuth lives in the same auth.manager module
    that admin.py already imports at module level for AuthManager.

    The access_level ('read', 'write', or 'admin') is stored alongside the
    password and enforced when non-admin clients connect to the database.
    """
    from webduck.auth.manager import ProjectAuth

    project_auth = ProjectAuth(storage_engine.data_dir)

    if not project_auth.set_database_password(project, database, req.password, req.access_level):
        log_error(f"set_database_password: Failed to set password for '{database}' in '{project}'")
        raise HTTPException(status_code=500, detail="Failed to set password")

    return {"success": True, "message": f"Password set for '{database}' ({req.access_level})"}


@router.get("/users")
async def list_users(username: str = Depends(verify_admin)) -> list[str]:
    """List all admin users."""
    if not auth_manager:
        log_error("list_users: Auth manager not initialized")
        raise HTTPException(status_code=500, detail="Auth manager not initialized")
    return auth_manager.list_users()


class CreateUserRequest(BaseModel):
    username: str
    password: str


@router.post("/users")
async def create_user(
    req: CreateUserRequest, username: str = Depends(verify_admin)
) -> dict:
    """Create a new admin user."""
    if not auth_manager:
        log_error("create_user: Auth manager not initialized")
        raise HTTPException(status_code=500, detail="Auth manager not initialized")

    if auth_manager.user_exists(req.username):
        log_warning(f"create_user: User '{req.username}' already exists")
        raise HTTPException(status_code=400, detail="User already exists")

    if not auth_manager.create_user(req.username, req.password):
        log_error(f"create_user: Failed to create user '{req.username}'")
        raise HTTPException(status_code=500, detail="Failed to create user")

    return {"success": True, "message": f"User '{req.username}' created"}


@router.delete("/users/{target_username}")
async def delete_user(
    target_username: str, username: str = Depends(verify_admin)
) -> dict:
    """Delete an admin user."""
    if not auth_manager:
        log_error("delete_user: Auth manager not initialized")
        raise HTTPException(status_code=500, detail="Auth manager not initialized")

    if target_username == username:
        # Prevent an admin from deleting their own account. Without this guard
        # an admin could lock themselves out, leaving the system with zero admins.
        log_warning(f"delete_user: User '{username}' attempted to delete themselves")
        raise HTTPException(status_code=400, detail="Cannot delete yourself")

    if not auth_manager.delete_user(target_username):
        raise HTTPException(status_code=404, detail="User not found")

    return {"success": True, "message": f"User '{target_username}' deleted"}
