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
#  WebDuck — CLI Entry Point
#  ---------------------------------------------------------------------------
#  Command-line interface entry point. Delegates to main.main().
#
#  Usage:
#    webduck init     — Initialize WebDuck (create admin user)
#    webduck start    — Start the WebDuck server
#    webduck status   — Show WebDuck status
#
#  Project:   WebDuck
#  Author:    autumo GmbH
#  Version:   0.1.0
#  Date:      2026-07-20
# =============================================================================

"""WebDuck CLI entry point."""

from webduck.main import main

if __name__ == "__main__":
    main()
