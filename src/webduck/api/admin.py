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
from webduck.storage.engine import StorageEngine

router = APIRouter(prefix="/admin", tags=["admin"])
security = HTTPBearer()

# These will be set by the main app
auth_manager: AuthManager | None = None
storage_engine: StorageEngine | None = None


def set_dependencies(auth: AuthManager, storage: StorageEngine) -> None:
    """Set dependencies for admin endpoints."""
    global auth_manager, storage_engine
    auth_manager = auth
    storage_engine = storage


async def verify_admin(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """Verify admin JWT token."""
    if not auth_manager:
        raise HTTPException(status_code=500, detail="Auth manager not initialized")

    username = auth_manager.verify_jwt_token(credentials.credentials)
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
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
    password: str
    access_level: str = "read"


# --- Endpoints ---

@router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest) -> LoginResponse:
    """Login and get JWT token."""
    if not auth_manager:
        raise HTTPException(status_code=500, detail="Auth manager not initialized")

    if not auth_manager.verify_user(req.username, req.password):
        from webduck.logging import log_warning
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
        raise HTTPException(status_code=500, detail="Storage engine not initialized")
    return storage_engine.list_projects()


@router.post("/projects")
async def create_project(
    req: ProjectRequest, username: str = Depends(verify_admin)
) -> dict:
    """Create a new project."""
    if not storage_engine:
        raise HTTPException(status_code=500, detail="Storage engine not initialized")

    project_dir = storage_engine.data_dir / req.name
    if project_dir.exists():
        raise HTTPException(status_code=400, detail="Project already exists")

    project_dir.mkdir(parents=True, exist_ok=True)
    return {"success": True, "message": f"Project '{req.name}' created"}


@router.delete("/projects/{project}")
async def delete_project(project: str, username: str = Depends(verify_admin)) -> dict:
    """Delete a project and all its databases."""
    if not storage_engine:
        raise HTTPException(status_code=500, detail="Storage engine not initialized")

    if not storage_engine.delete_project(project):
        raise HTTPException(status_code=404, detail="Project not found")

    return {"success": True, "message": f"Project '{project}' deleted"}


@router.get("/projects/{project}/databases")
async def list_databases(project: str, username: str = Depends(verify_admin)) -> list[str]:
    """List all databases in a project."""
    if not storage_engine:
        raise HTTPException(status_code=500, detail="Storage engine not initialized")
    return storage_engine.list_databases(project)


@router.post("/projects/{project}/databases")
async def create_database(
    project: str, req: DatabaseRequest, username: str = Depends(verify_admin)
) -> dict:
    """Create a new database in a project."""
    if not storage_engine:
        raise HTTPException(status_code=500, detail="Storage engine not initialized")

    if storage_engine.database_exists(project, req.name):
        raise HTTPException(status_code=400, detail="Database already exists")

    if not storage_engine.create_database(project, req.name):
        raise HTTPException(status_code=500, detail="Failed to create database")

    return {"success": True, "message": f"Database '{req.name}' created in project '{project}'"}


@router.delete("/projects/{project}/databases/{database}")
async def delete_database(
    project: str, database: str, username: str = Depends(verify_admin)
) -> dict:
    """Delete a database."""
    if not storage_engine:
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
    """Set password for database access."""
    from webduck.auth.manager import ProjectAuth

    project_auth = ProjectAuth(storage_engine.data_dir)

    if not project_auth.set_database_password(project, database, req.password, req.access_level):
        raise HTTPException(status_code=500, detail="Failed to set password")

    return {"success": True, "message": f"Password set for '{database}' ({req.access_level})"}


@router.get("/users")
async def list_users(username: str = Depends(verify_admin)) -> list[str]:
    """List all admin users."""
    if not auth_manager:
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
        raise HTTPException(status_code=500, detail="Auth manager not initialized")

    if auth_manager.user_exists(req.username):
        raise HTTPException(status_code=400, detail="User already exists")

    if not auth_manager.create_user(req.username, req.password):
        raise HTTPException(status_code=500, detail="Failed to create user")

    return {"success": True, "message": f"User '{req.username}' created"}


@router.delete("/users/{target_username}")
async def delete_user(
    target_username: str, username: str = Depends(verify_admin)
) -> dict:
    """Delete an admin user."""
    if not auth_manager:
        raise HTTPException(status_code=500, detail="Auth manager not initialized")

    if target_username == username:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")

    if not auth_manager.delete_user(target_username):
        raise HTTPException(status_code=404, detail="User not found")

    return {"success": True, "message": f"User '{target_username}' deleted"}
