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

"""Shared context for all pages — dependencies and theme constants."""

from webduck.auth.manager import AuthManager, ProjectAuth
from webduck.config import WebDuckConfig
from webduck.storage.engine import StorageEngine

# Set by setup_app() via init_context()
config: WebDuckConfig | None = None
storage: StorageEngine | None = None
auth: AuthManager | None = None
project_auth: ProjectAuth | None = None
version: str = ""
icon: str = ""
max_upload_mb: int = 5

AUTUMO_URL = "https://autumo.ch"
DOCS_URL = "https://webduck.autumo.ch"

# Theme colors
YELLOW = "#FFD54F"
YELLOW_LIGHT = "#FFE082"
YELLOW_DARK = "#FFC107"
YELLOW_DARKER = "#806002"
TEXT_SOFT = "#E0E0E0"
TEXT_DIM = "#999999"
TEXT_PLACEHOLDER = "#666666"
BG_DARK = "#121212"
BG_CARD = "#1E1E1E"
BORDER = "#333333"
BORDER_BTN = "#2a2a2a"
NAV_COLOR = "#BBBBBB"

# DB browsing
TREE_WIDTH = "20%"
BROWSE_PAGE_SIZE = 100


def init_context(
    cfg: WebDuckConfig,
    store: StorageEngine,
    auth_mgr: AuthManager,
    proj_auth: ProjectAuth,
) -> None:
    """Initialize shared context. Called once from setup_app()."""
    global config, storage, auth, project_auth, version, icon, max_upload_mb
    config = cfg
    storage = store
    auth = auth_mgr
    project_auth = proj_auth
    version = cfg.version
    icon = cfg.icon
    max_upload_mb = cfg.server.max_upload_mb
