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

"""Shared context for all pages — dependencies and theme constants.

Module-level globals act as singletons wired once at startup by init_context().
Every page module imports this to access config, storage, auth, and theme colors.
"""

from webduck.auth.manager import AuthManager, ProjectAuth
from webduck.config import WebDuckConfig
from webduck.storage.engine import StorageEngine

# ---------------------------------------------------------------------------
# Shared service instances — all populated by init_context() during app startup.
# Pages import these directly (e.g. ``ctx.storage.list_projects()``).
# ---------------------------------------------------------------------------
config: WebDuckConfig | None = None
storage: StorageEngine | None = None
auth: AuthManager | None = None
project_auth: ProjectAuth | None = None
version: str = ""
icon: str = ""
max_upload_mb: int = 256

# External URLs displayed in the footer and navigation drawer.
AUTUMO_URL = "https://autumo.ch"
DOCS_URL = "https://webduck.autumo.ch"
DONATE_URL = "https://www.paypal.com/ncp/payment/NZ4CC6SVF9HN8"

# ---------------------------------------------------------------------------
# Theme colors — shared across all pages for a consistent dark-mode look.
# ---------------------------------------------------------------------------

# Yellow / amber accent scale (titles, highlights, active indicators)
YELLOW = "#FFD54F"
YELLOW_LIGHT = "#FFE082"
YELLOW_DARK = "#FFC107"
YELLOW_DARKER = "#806002"

# Text colors at different emphasis levels
TEXT_SOFT = "#E0E0E0"        # primary body text
TEXT_DIM = "#999999"         # secondary / muted text
TEXT_PLACEHOLDER = "#666666" # input placeholders

# Background colors
BG_DARK = "#121212"          # main page background
BG_CARD = "#1E1E1E"          # card / panel surfaces

# Border colors
BORDER = "#333333"           # general borders
BORDER_BTN = "#2a2a2a"       # button outlines

# Navigation drawer text / icon color
NAV_COLOR = "#BBBBBB"

# ---------------------------------------------------------------------------
# DB browsing constants
# ---------------------------------------------------------------------------
TREE_WIDTH = "20%"            # left panel width for the object tree
BROWSE_PAGE_SIZE = 100        # rows fetched per page during infinite scroll


def init_context(
    cfg: WebDuckConfig,
    store: StorageEngine,
    auth_mgr: AuthManager,
    proj_auth: ProjectAuth,
) -> None:
    """Initialize shared context.  Called once from setup_app().

    Copies configuration and service references into module-level globals
    so every page module can access them via ``from webduck.pages import context``.
    """
    global config, storage, auth, project_auth, version, icon, max_upload_mb
    config = cfg
    storage = store
    auth = auth_mgr
    project_auth = proj_auth
    version = cfg.version
    icon = cfg.icon
    max_upload_mb = cfg.server.max_upload_mb
