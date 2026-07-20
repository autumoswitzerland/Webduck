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
#  WebDuck — Authentication Manager
#  ---------------------------------------------------------------------------
#  JWT token generation/verification and bcrypt password hashing.
#
#  Provides AdminManager for admin user CRUD with JWT-based auth, and
#  ProjectAuth for project-scoped database access via project keys.
#
#  Project:   WebDuck
#  Author:    autumo GmbH
#  Version:   0.1.0
#  Date:      2026-07-20
# =============================================================================

"""WebDuck authentication module - JWT and bcrypt."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import bcrypt
import jwt


class AuthManager:
    """Authentication manager for admin users."""

    def __init__(self, data_dir: Path, jwt_secret: str, jwt_algorithm: str = "HS256"):
        self.data_dir = data_dir
        self.users_file = data_dir / ".users.json"
        self.jwt_secret = jwt_secret
        self.jwt_algorithm = jwt_algorithm
        self._users: dict[str, dict] = {}
        self._load_users()

    def _load_users(self) -> None:
        """Load users from file."""
        if self.users_file.exists():
            with open(self.users_file) as f:
                self._users = json.load(f)

    def _save_users(self) -> None:
        """Save users to file."""
        with open(self.users_file, "w") as f:
            json.dump(self._users, f, indent=2)

    def create_user(self, username: str, password: str) -> bool:
        """Create a new admin user."""
        if username in self._users:
            return False

        password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        self._users[username] = {
            "password_hash": password_hash,
            "created_at": datetime.now(UTC).isoformat(),
        }
        self._save_users()
        return True

    def verify_user(self, username: str, password: str) -> bool:
        """Verify user credentials."""
        user = self._users.get(username)
        if not user:
            return False
        return bcrypt.checkpw(password.encode(), user["password_hash"].encode())

    def user_exists(self, username: str) -> bool:
        """Check if user exists."""
        return username in self._users

    def list_users(self) -> list[str]:
        """List all usernames."""
        return list(self._users.keys())

    def delete_user(self, username: str) -> bool:
        """Delete a user."""
        if username not in self._users:
            return False
        del self._users[username]
        self._save_users()
        return True

    def create_jwt_token(self, username: str, expire_minutes: int = 60) -> str:
        """Create a JWT token."""
        payload = {
            "sub": username,
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(minutes=expire_minutes),
        }
        return jwt.encode(payload, self.jwt_secret, algorithm=self.jwt_algorithm)

    def verify_jwt_token(self, token: str) -> str | None:
        """Verify JWT token and return username."""
        try:
            payload = jwt.decode(token, self.jwt_secret, algorithms=[self.jwt_algorithm])
            return payload.get("sub")
        except jwt.InvalidTokenError:
            return None


class ProjectAuth:
    """Project-level authentication for database access."""

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir

    def _get_project_config_path(self, project: str) -> Path:
        """Get path to project config file."""
        return self.data_dir / project / ".project.json"

    def get_project_config(self, project: str) -> dict:
        """Get project configuration."""
        config_path = self._get_project_config_path(project)
        if not config_path.exists():
            return {}
        with open(config_path) as f:
            return json.load(f)

    def set_database_password(
        self, project: str, database: str, password: str, access_level: str = "read"
    ) -> bool:
        """Set password for database access."""
        config_path = self._get_project_config_path(project)
        config = self.get_project_config(project)

        if "databases" not in config:
            config["databases"] = {}
        if database not in config["databases"]:
            config["databases"][database] = {}

        password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        config["databases"][database][f"{access_level}_password_hash"] = password_hash

        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)
        return True

    def verify_database_password(
        self, project: str, database: str, password: str, access_level: str = "read"
    ) -> bool:
        """Verify database password."""
        config = self.get_project_config(project)
        db_config = config.get("databases", {}).get(database, {})
        password_hash = db_config.get(f"{access_level}_password_hash")

        if not password_hash:
            return False

        return bcrypt.checkpw(password.encode(), password_hash.encode())

    def has_database_access(
        self, project: str, database: str, password: str, access_level: str = "read"
    ) -> bool:
        """Check if password grants access to database."""
        if self.verify_database_password(project, database, password, access_level):
            return True
        # Write access also grants read access
        if access_level == "read":
            return self.verify_database_password(project, database, password, "write")
        return False
