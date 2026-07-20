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
#  Version:   0.1.0
#  Date:      2026-07-20
# =============================================================================

"""WebDuck configuration module."""

from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class ServerConfig(BaseModel):
    """Server configuration."""

    host: str = "0.0.0.0"
    port: int = 8998
    data_dir: Path = Path("data")


class AuthConfig(BaseModel):
    """Authentication configuration."""

    jwt_secret: str = "CHANGE-ME-TO-A-SECRET-KEY-IN-PRODUCTION"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60


class LoggingConfig(BaseModel):
    """Logging configuration."""

    enabled: bool = False
    max_size_mb: int = 10
    max_files: int = 5
    query_log: bool = False


class WebDuckConfig(BaseModel):
    """Main WebDuck configuration."""

    version: str = "0.1.0"
    icon: str = "🦆"
    server: ServerConfig = Field(default_factory=ServerConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)


def load_config(config_path: Path | None = None) -> WebDuckConfig:
    """Load configuration from YAML file or return defaults."""
    if config_path and config_path.exists():
        with open(config_path) as f:
            data = yaml.safe_load(f)
        return WebDuckConfig(**data) if data else WebDuckConfig()
    return WebDuckConfig()


def save_config(config: WebDuckConfig, config_path: Path) -> None:
    """Save configuration to YAML file."""
    data = config.model_dump()
    # Convert Path objects to strings for YAML serialization
    if "server" in data and "data_dir" in data["server"]:
        data["server"]["data_dir"] = str(data["server"]["data_dir"])
    with open(config_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False)
