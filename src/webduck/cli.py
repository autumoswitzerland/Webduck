# ------------------------------------------------------------------------------
# Copyright (c) 2026 autumo GmbH. All rights reserved.
#
# Licensed under the GNU Affero General Public License v3.0 (AGPLv3).
# See LICENSE file in the project root for full license information.
#
# This file is part of WebDuck. WebDuck is free software: you can redistribute
# it and/or modify it under the terms of the GNU Affero General Public License
# as published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
# ------------------------------------------------------------------------------

# =============================================================================
#  WebDuck — CLI Entry Point
#  ---------------------------------------------------------------------------
#  Command-line interface entry point. Delegates to main.main().
#
#  This module exists solely to provide a thin wrapper around ``main()``
#  so that the ``[project.scripts]`` entry in ``pyproject.toml`` can
#  point to ``webduck.cli:main`` without importing the heavier ``main``
#  module at tab-completion time (Click can lazily load subcommands).
#
#  Usage (after ``pip install webduck``):
#    webduck init     — Initialize WebDuck (create admin user)
#    webduck start    — Start the WebDuck server
#    webduck status   — Show WebDuck status
#
#  Project:   WebDuck
#  Author:    autumo GmbH
#  Date:      2026-07-20
# =============================================================================

"""WebDuck CLI entry point.

This module is referenced by the ``webduck`` console script in
``pyproject.toml``::

    [project.scripts]
    webduck = "webduck.cli:main"

Running ``webduck --help`` triggers this module which imports and calls
``main()`` from ``webduck.main``, where the actual Click command group
lives.
"""

from webduck.main import main

if __name__ == "__main__":
    main()
