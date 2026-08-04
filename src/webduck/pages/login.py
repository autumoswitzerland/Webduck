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

"""Login page.

Handles browser language auto-detection via the Accept-Language header,
JWT-based session creation, and a language selector that persists the
user's choice across sessions.
"""

from fastapi import Request
from nicegui import app as nicegui_app
from nicegui import ui

from webduck.pages import context as ctx
from webduck.pages.context import BG_CARD, YELLOW
from webduck.pages.ui_helpers import apply_dark_theme


def register():
    """Register the ``/login`` page route with NiceGUI."""
    from webduck.i18n import (
        get_language_name,
        get_supported_languages,
        get_translator,
    )

    @ui.page("/login")
    def login_page(request: Request):
        # ---------------------------------------------------------------
        # Language detection: Accept-Language header → saved preference → "en"
        # The first two characters of the header give us the ISO 639-1 code.
        # ---------------------------------------------------------------
        browser_lang = request.headers.get(
            "accept-language", "en"
        )[:2]
        saved_lang = nicegui_app.storage.user.get(
            "language", browser_lang
        )
        # Fall back to English if the stored language is no longer supported.
        if saved_lang not in get_supported_languages():
            saved_lang = "en"
        nicegui_app.storage.user["language"] = saved_lang

        _ = get_translator(saved_lang)
        apply_dark_theme()
        ui.page_title(f"WebDuck {ctx.version} — Login")

        with ui.column().classes("fixed-center items-center gap-6"):

            # -- Login card: icon + version title, credential fields, button
            with ui.card().style(
                f"background: {BG_CARD}; padding: 20px 24px 20px 24px;"
            ):
                # -- Branding row: optional icon + "WebDuck vX.Y.Z"
                with ui.row().classes("items-center gap-2"):
                    if ctx.icon:
                        ui.html(
                            f'<img src="/static/{ctx.icon}" alt="icon" '
                            f'style="height:36px; vertical-align:middle;">'
                        )
                    ui.label(f"WebDuck {ctx.version}").classes(
                        "text-h4 text-bold"
                    ).style(f"color: {YELLOW}")

                ui.space().classes("h-3")

                username = ui.input(_("username")).classes("w-full")
                password = ui.input(
                    _("password"), password=True
                ).classes("w-full")

                def handle_login():
                    """Verify credentials, create JWT, store in session, and redirect.

                    On failure a warning is logged and the user sees a
                    negative notification.  Both bad credentials and
                    unexpected errors produce the same user-facing message
                    to avoid leaking system details.
                    """
                    try:
                        if ctx.auth.verify_user(username.value, password.value):
                            token = ctx.auth.create_jwt_token(username.value)
                            nicegui_app.storage.user["token"] = token
                            nicegui_app.storage.user["username"] = (
                                username.value
                            )
                            ui.navigate.to("/")
                        else:
                            from webduck.logging import log_warning
                            log_warning(f"Failed login attempt for user '{username.value}'")
                            ui.notify(
                                _("invalid_credentials"), type="negative"
                            )
                    except Exception as e:
                        from webduck.logging import log_error
                        log_error(f"Login error: {e}")
                        ui.notify(
                            _("invalid_credentials"), type="negative"
                        )

                # Allow pressing Enter anywhere in the form to submit.
                ui.on("keydown.enter", handle_login)

                ui.space().classes("h-3")

                ui.button(
                    _("login_button"), on_click=handle_login
                ).classes("w-full")

                ui.space().classes("h-3")

                # -- Language selector: changes language and reloads the page
                #    to re-render all UI strings in the chosen locale.
                lang_options = {
                    code: get_language_name(code)
                    for code in get_supported_languages()
                }

                ui.select(
                    lang_options,
                    value=saved_lang,
                    on_change=lambda e: (
                        nicegui_app.storage.user.update(
                            {"language": e.value}
                        ),
                        ui.navigate.reload(),
                    ),
                ).classes("w-full q-mt-sm").props(
                    "outlined dense"
                )
