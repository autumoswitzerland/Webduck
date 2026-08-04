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
#  WebDuck — Internationalization
#  ---------------------------------------------------------------------------
#  Internationalization support using Gettext PO/MO files.
#
#  Provides get_translator() to obtain a translation function for the
#  current user language, plus helpers for supported languages and
#  language display names.
#
#  MO compilation strategy:
#    Translators edit human-readable ``.po`` files.  At runtime the module
#    compiles them to binary ``.mo`` files on demand (via Babel) so that
#    deployments never ship a stale translation.  The check is simple:
#    if the ``.mo`` file is missing or older than its source ``.po``,
#    it is recompiled.  If Babel is not installed the compilation is
#    silently skipped — the server still works, it just won't pick up
#    new translations until the MO files are generated externally.
#
#  Accept-Language parsing:
#    The browser's ``Accept-Language`` header is parsed by NiceGUI's
#    session storage mechanism.  The login page detects the preferred
#    language via ``nicegui.app.storage.user["language"]`` and stores
#    the user's choice.  ``get_user_translator()`` reads that session
#    value and delegates to ``get_translator()``.
#
#  Project:   WebDuck
#  Author:    autumo GmbH
#  Date:      2026-07-20
# =============================================================================

"""WebDuck i18n module - internationalization support.

All UI-facing strings go through ``get_user_translator()`` which returns a
callable ``_`` suitable for use in page modules::

    _ = get_user_translator()
    ui.label(_("Welcome to WebDuck"))
"""

import gettext
from collections.abc import Callable
from pathlib import Path

# Default language — used as fallback when no session language is set or
# when an unsupported language code is encountered.
DEFAULT_LANGUAGE = "en"

# Languages with PO files under ``locales/<lang>/messages.po``.
SUPPORTED_LANGUAGES = ["en", "de", "fr"]

# Locales directory — inside the package (src/webduck/locales/).
# Layout:  locales/en/LC_MESSAGES/messages.mo
#          locales/de/messages.po
#          locales/de/LC_MESSAGES/messages.mo
LOCALES_DIR = Path(__file__).parent / "locales"


def _ensure_mo_files() -> None:
    """Compile PO files to MO files if outdated or missing.

    For each supported language:
      1. Check that ``locales/<lang>/messages.po`` exists.
      2. Compare its modification time against ``locales/<lang>/LC_MESSAGES/messages.mo``.
      3. If the MO is missing or stale, use Babel to compile a fresh MO.

    Babel is an optional dependency — if it's not installed, the
    ``ImportError`` is caught and silently ignored.  In that case the
    pre-existing MO files (or ``NullTranslations`` fallback) are used.
    """
    for lang in SUPPORTED_LANGUAGES:
        lang_dir = LOCALES_DIR / lang
        po_file = lang_dir / "messages.po"
        lc_messages_dir = lang_dir / "LC_MESSAGES"
        mo_file = lc_messages_dir / "messages.mo"

        if not po_file.exists():
            continue

        # Compile only if MO is missing or older than the PO source
        needs_compile = (
            not mo_file.exists()
            or mo_file.stat().st_mtime < po_file.stat().st_mtime
        )
        if not needs_compile:
            continue

        try:
            # Babel handles PO→MO compilation — read_po() parses the
            # human-readable PO format, write_mo() emits the binary MO.
            from babel.messages.mofile import write_mo
            from babel.messages.pofile import read_po

            lc_messages_dir.mkdir(parents=True, exist_ok=True)

            with open(po_file, "rb") as f:
                catalog = read_po(f)

            with open(mo_file, "wb") as f:
                write_mo(f, catalog)

            print(f"[i18n] Compiled {po_file} -> {mo_file}")
        except ImportError:
            # Babel not installed — skip compilation, rely on existing MOs
            pass


def get_translator(language: str | None = None) -> Callable[[str], str]:
    """Get a translation function for the specified language.

    The returned callable maps source strings to their translations.
    If the language is unsupported or its MO file is missing, an
    identity function (``NullTranslations``) is returned so that
    ``_("English string")`` always works regardless of locale state.

    Args:
        language: Language code (e.g., ``'en'``, ``'de'``, ``'fr'``).
                  If ``None``, ``DEFAULT_LANGUAGE`` is used.

    Returns:
        A callable ``gettext``-style translation function.
    """
    if language is None:
        language = DEFAULT_LANGUAGE

    if language not in SUPPORTED_LANGUAGES:
        language = DEFAULT_LANGUAGE

    # Ensure MO files are up-to-date before loading them
    _ensure_mo_files()

    try:
        translation = gettext.translation(
            "messages",
            LOCALES_DIR,
            languages=[language],
        )
    except FileNotFoundError:
        # No translation file found — fall back to English identity
        translation = gettext.NullTranslations()

    return translation.gettext


def get_user_translator() -> Callable[[str], str]:
    """Get translator using the current user's language from session storage.

    Reads the ``"language"`` key from NiceGUI's per-user session storage
    (persisted in a signed cookie).  Falls back to ``DEFAULT_LANGUAGE``
    on any error (e.g. no session, corrupted cookie, server-side render).
    """
    try:
        from nicegui import app as nicegui_app
        lang = nicegui_app.storage.user.get("language", DEFAULT_LANGUAGE)
    except Exception:
        lang = DEFAULT_LANGUAGE
    return get_translator(lang)


def get_supported_languages() -> list[str]:
    """Get list of supported languages.

    Returns a copy to prevent accidental mutation of the module constant.
    """
    return SUPPORTED_LANGUAGES.copy()


def get_language_name(code: str) -> str:
    """Get human-readable language name from code.

    Maps ISO 639-1 codes to their native names for display in the
    language dropdown on the login page.  Returns the raw code if
    the language is not in the lookup table.
    """
    names = {
        "en": "English",
        "de": "Deutsch",
        "fr": "Français",
    }
    return names.get(code, code)
