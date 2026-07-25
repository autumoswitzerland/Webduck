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
#  Version:   1.0.0
#  Date:      2026-07-20
# =============================================================================

"""WebDuck authentication module - JWT and bcrypt."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import bcrypt
import jwt


class AuthManager:
    """Authentication manager for admin users.

    Manages admin user credentials stored as bcrypt hashes in a JSON file,
    and issues/verifies JWT tokens for API session authentication.
    """

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
        """Create a new admin user.

        Bcrypt automatically generates a random salt via gensalt() and
        embeds it in the resulting hash string (format: $2b$...).
        This means we never store the salt separately — it is self-contained
        in the hash, which is a standard bcrypt convention.
        """
        if username in self._users:
            return False

        # bcrypt.hashpw() accepts bytes; we encode the password to UTF-8.
        # gensalt() with default rounds (12) provides a good balance of
        # security and performance for interactive login.
        password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        self._users[username] = {
            "password_hash": password_hash,
            "created_at": datetime.now(UTC).isoformat(),
        }
        self._save_users()
        return True

    def verify_user(self, username: str, password: str) -> bool:
        """Verify user credentials.

        Uses constant-time comparison internally via bcrypt.checkpw(),
        which prevents timing-based side-channel attacks.
        """
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
        """Create a JWT token.

        Token payload claims:
          - "sub" (subject): The authenticated username. This is the standard
            claim for identifying the principal — verified callers are
            retrieved via payload["sub"] throughout the API.
          - "iat" (issued-at): Timestamp of token creation. Enables auditing
            and token age checks if needed in the future.
          - "exp" (expiration): Standard claim enforced by PyJWT — tokens
            past this timestamp are rejected automatically by jwt.decode().
            Default 60 minutes balances security vs. user convenience for
            an internal tool.

        Uses HS256 (HMAC-SHA256) which is a symmetric signing algorithm
        appropriate for single-server deployments where the same process
        both creates and verifies tokens. No public/private key overhead.
        """
        payload = {
            "sub": username,
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(minutes=expire_minutes),
        }
        return jwt.encode(payload, self.jwt_secret, algorithm=self.jwt_algorithm)

    def verify_jwt_token(self, token: str) -> str | None:
        """Verify JWT token and return username.

        Returns the "sub" claim (username) on success, or None if the token
        is expired, tampered, or malformed. The broad except clause is
        intentional — PyJWT raises specific InvalidTokenError subclasses
        for all failure modes (expired, invalid signature, malformed), and
        we treat all of them uniformly as auth failure.
        """
        try:
            payload = jwt.decode(token, self.jwt_secret, algorithms=[self.jwt_algorithm])
            return payload.get("sub")
        except jwt.InvalidTokenError:
            return None


class ProjectAuth:
    """Project-level authentication for database access.

    Provides optional per-database password protection within projects.
    Unlike AdminManager (which always requires credentials), ProjectAuth
    supports an "open access" model: if no password has been set for a
    database, all requests are granted access. This is useful for local/
    development deployments where frictionless access is preferred.

    Security model:
      - Passwords are bcrypt-hashed, same as admin users.
      - Separate read and write password hashes allow read-only sharing.
      - Write access implicitly grants read access (checked in
        has_database_access).
      - Config is stored per-project in <data_dir>/<project>/.project.json.
    """

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
        """Set password for database access.

        Stores a bcrypt hash keyed by access_level (e.g. "read_password_hash"
        or "write_password_hash"). This allows independent passwords for
        read-only vs. read-write access to the same database.
        """
        config_path = self._get_project_config_path(project)
        config = self.get_project_config(project)

        if "databases" not in config:
            config["databases"] = {}
        if database not in config["databases"]:
            config["databases"][database] = {}

        # Same bcrypt approach as admin passwords — self-contained salt.
        password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        config["databases"][database][f"{access_level}_password_hash"] = password_hash

        # Ensure the project directory exists before writing config.
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)
        return True

    def verify_database_password(
        self, project: str, database: str, password: str, access_level: str = "read"
    ) -> bool:
        """Verify database password. No password set = open access.

        The open-access fallback (returning True when no password is set)
        means this function only rejects requests when a password EXISTS
        but doesn't match. This is intentional for local-first usage —
        users can protect databases when needed but aren't forced to.
        """
        config = self.get_project_config(project)
        db_config = config.get("databases", {}).get(database, {})
        password_hash = db_config.get(f"{access_level}_password_hash")

        if not password_hash:
            # No hash stored for this access level — check if ANY password
            # is set. If none at all, grant open access. If only a different
            # level's password exists, deny (e.g. write-only configured but
            # no read password = no read access).
            if not self.has_database_password(project, database):
                return True
            return False

        return bcrypt.checkpw(password.encode(), password_hash.encode())

    def has_database_access(
        self, project: str, database: str, password: str, access_level: str = "read"
    ) -> bool:
        """Check if password grants access to database.

        Access escalation logic: write passwords implicitly grant read
        access. This avoids needing two passwords when a user should
        have full access — a single write-level credential covers both.
        """
        if self.verify_database_password(project, database, password, access_level):
            return True
        # Write access also grants read access
        if access_level == "read":
            return self.verify_database_password(project, database, password, "write")
        return False

    def has_database_password(self, project: str, database: str) -> bool:
        """Check if a password is set for a database.

        Checks both read and write password hashes. Used to distinguish
        between "no password configured" (open access) and "password
        configured but wrong" (denied).
        """
        config = self.get_project_config(project)
        db_config = config.get("databases", {}).get(database, {})
        return bool(db_config.get("read_password_hash") or db_config.get("write_password_hash"))
