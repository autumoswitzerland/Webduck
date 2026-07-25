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
#  WebDuck — Configuration
#  ---------------------------------------------------------------------------
#  YAML configuration loading and saving with Pydantic models.
#
#  Defines data models for server, auth, and logging settings.
#  Provides load_config() and save_config() helpers.
#
#  Project:   WebDuck
#  Author:    autumo GmbH
#  Version:   1.0.0
#  Date:      2026-07-20
# =============================================================================

"""WebDuck configuration module.

Configuration is stored as a single YAML file (``webduck.yaml``) with sections
for server, auth, and logging.  Each section is backed by a Pydantic BaseModel
which provides validation and default values at load time.  Unknown keys are
silently ignored by Pydantic (``model_config`` uses the default strict=False).

Loading flow:
    1. ``load_config()`` reads the YAML file (or returns a fully-default config).
    2. YAML dict is unpacked directly into ``WebDuckConfig(**data)``; Pydantic
       fills in any missing keys with the model defaults.
    3. If the file doesn't exist, a fresh ``WebDuckConfig()`` with all defaults
       is returned so the server can start without a pre-existing config.

Saving flow:
    1. ``save_config()`` calls ``model_dump()`` to get a plain dict.
    2. ``Path`` objects are converted to strings (YAML can't serialise Path).
    3. ``yaml.dump()`` writes the file with ``default_flow_style=False`` for
       readable block-style output.
"""

from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class ServerConfig(BaseModel):
    """Server configuration.

    Attributes:
        host: Bind address.  ``0.0.0.0`` exposes on all interfaces (needed
              for Docker).  Use ``127.0.0.1`` for local-only access.
        port: TCP port the HTTP server listens on.  8998 avoids conflicts
              with common dev servers (3000, 5000, 8000, 8080).
        data_dir: Root directory for all DuckDB databases and metadata.
                  Created automatically on startup if it doesn't exist.
        max_upload_mb: Maximum allowed upload size in megabytes.  Keeps
                       accidental large uploads from consuming memory.
    """

    host: str = "0.0.0.0"
    port: int = 8998
    data_dir: Path = Path("data")
    max_upload_mb: int = 256


class AuthConfig(BaseModel):
    """Authentication configuration.

    Attributes:
        jwt_secret: Secret key used to sign JWT tokens.  The placeholder
                    value is detected during ``webduck init`` and replaced
                    with a cryptographically random 48-byte URL-safe token.
        jwt_algorithm: HMAC algorithm for JWT signing.  HS256 is the
                       standard choice; change only if integrating with an
                       external identity provider.
        jwt_expire_minutes: Token lifetime in minutes.  60 minutes balances
                            security with usability.
    """

    jwt_secret: str = "CHANGE-ME-TO-A-SECRET-KEY-IN-PRODUCTION"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60


class FileLoggingConfig(BaseModel):
    """File logging configuration.

    File logging uses Python's ``RotatingFileHandler`` — see ``logging.py``
    for the actual handler setup.

    Attributes:
        enabled: Master switch; when ``False`` no log file is created.
        level: Minimum severity that triggers a write (debug/info/warning/error).
        max_size_mb: A single log file grows until this size, then a new
                     file is started and the oldest backup is deleted.
        max_files: Number of rotated backup files to retain (e.g. 5 keeps
                   ``webduck.log`` through ``webduck.log.4``).
        query_log: When ``True``, every SQL execution is recorded at INFO
                   level — useful for auditing but noisy in production.
        log_dir: Directory for ``webduck.log``.  Falls back to ``"log"``
                 relative to the working directory when empty.
    """

    enabled: bool = False
    level: str = "debug"
    max_size_mb: int = 10
    max_files: int = 5
    query_log: bool = False
    log_dir: str = "log"


class ConsoleLoggingConfig(BaseModel):
    """Console logging configuration (uvicorn).

    Controls how uvicorn's built-in access/error logging behaves.
    These settings are passed directly to ``uvicorn.run()``.

    Attributes:
        enabled: When ``False`` (default), uvicorn runs with ``log_level``
                 set to ``"warning"`` and ``access_log=False``, keeping the
                 console clean.  Set to ``True`` for development.
        access_log: Toggles uvicorn's per-request access log lines.
        level: Uvicorn log level (debug/info/warning/error).
    """

    enabled: bool = False
    access_log: bool = False
    level: str = "warning"


class LoggingConfig(BaseModel):
    """Logging configuration — aggregates file and console settings."""

    file: FileLoggingConfig = Field(default_factory=FileLoggingConfig)
    console: ConsoleLoggingConfig = Field(default_factory=ConsoleLoggingConfig)


class WebDuckConfig(BaseModel):
    """Main WebDuck configuration — top-level model.

    This is the root model that ``load_config()`` returns and that the rest
    of the application consumes.  Every sub-section defaults to an empty
    factory so the server can start without any ``webduck.yaml`` file at all.
    """

    version: str = "1.0.0"
    icon: str = ""
    server: ServerConfig = Field(default_factory=ServerConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)


def load_config(config_path: Path | None = None) -> WebDuckConfig:
    """Load configuration from YAML file or return defaults.

    Args:
        config_path: Path to ``webduck.yaml``.  If ``None`` or the file does
                     not exist, a ``WebDuckConfig()`` with all defaults is
                     returned — the server never fails on a missing config.

    Returns:
        A fully-populated ``WebDuckConfig`` instance.
    """
    if config_path and config_path.exists():
        # safe_load prevents YAML deserialisation attacks (arbitrary objects)
        with open(config_path) as f:
            data = yaml.safe_load(f)
        # If the file is empty YAML returns None; treat that as defaults
        return WebDuckConfig(**data) if data else WebDuckConfig()
    return WebDuckConfig()


def save_config(config: WebDuckConfig, config_path: Path) -> None:
    """Save configuration to YAML file.

    Converts the Pydantic model to a plain dict, coerces ``Path`` values to
    strings (YAML doesn't natively support Python ``Path`` objects), and
    writes block-style YAML for human readability.
    """
    data = config.model_dump()
    # Convert Path objects to strings for YAML serialization
    if "server" in data and "data_dir" in data["server"]:
        data["server"]["data_dir"] = str(data["server"]["data_dir"])
    with open(config_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False)
