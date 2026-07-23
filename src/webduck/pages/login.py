# ------------------------------------------------------------------------------
# Copyright (c) 2026 autusto GmbH. All rights reserved.
#
# Licensed under the MIT License. See LICENSE file in the project root for
# full license information.
#
# NOTICE: This file is part of WebDuck. The above copyright notice and this
# permission notice shall be included in all copies or substantial portions
# of this software.
# ------------------------------------------------------------------------------

"""Login page."""

from fastapi import Request
from nicegui import app as nicegui_app
from nicegui import ui

from webduck.pages import context as ctx
from webduck.pages.context import BG_CARD, YELLOW
from webduck.pages.ui_helpers import apply_dark_theme


def register():
    from webduck.i18n import (
        get_language_name,
        get_supported_languages,
        get_translator,
    )

    @ui.page("/login")
    def login_page(request: Request):
        browser_lang = request.headers.get(
            "accept-language", "en"
        )[:2]
        saved_lang = nicegui_app.storage.user.get(
            "language", browser_lang
        )
        if saved_lang not in get_supported_languages():
            saved_lang = "en"
        nicegui_app.storage.user["language"] = saved_lang

        _ = get_translator(saved_lang)
        apply_dark_theme()
        ui.page_title(f"WebDuck {ctx.version} — Login")

        with ui.column().classes("fixed-center items-center gap-6"):

            with ui.card().style(
                f"background: {BG_CARD}; padding: 20px 24px 20px 24px;"
            ):
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

                ui.on("keydown.enter", handle_login)

                ui.space().classes("h-3")

                ui.button(
                    _("login_button"), on_click=handle_login
                ).classes("w-full")

                ui.space().classes("h-3")

                lang_options = {
                    code: get_language_name(code)
                    for code in get_supported_languages()
                }

                lang_select = ui.select(
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
