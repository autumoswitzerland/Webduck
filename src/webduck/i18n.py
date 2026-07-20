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
#  WebDuck — Internationalization
#  ---------------------------------------------------------------------------
#  Internationalization support using Gettext PO/MO files.
#
#  Provides get_translator() to obtain a translation function for the
#  current user language, plus helpers for supported languages and
#  language display names.
#
#  Project:   WebDuck
#  Author:    autumo GmbH
#  Version:   0.1.0
#  Date:      2026-07-20
# =============================================================================

"""WebDuck i18n module - internationalization support."""

import gettext
from collections.abc import Callable
from pathlib import Path

# Default language
DEFAULT_LANGUAGE = "en"

# Supported languages
SUPPORTED_LANGUAGES = ["en", "de", "fr"]

# Locales directory
LOCALES_DIR = Path(__file__).parent.parent.parent / "locales"


def _ensure_mo_files() -> None:
    """Compile PO files to MO files if they don't exist."""
    for lang in SUPPORTED_LANGUAGES:
        lang_dir = LOCALES_DIR / lang
        po_file = lang_dir / "messages.po"
        lc_messages_dir = lang_dir / "LC_MESSAGES"
        mo_file = lc_messages_dir / "messages.mo"

        if not mo_file.exists() and po_file.exists():
            try:
                from babel.messages.mofile import write_mo
                from babel.messages.pofile import read_po

                lc_messages_dir.mkdir(parents=True, exist_ok=True)

                with open(po_file, "rb") as f:
                    catalog = read_po(f)

                with open(mo_file, "wb") as f:
                    write_mo(f, catalog)
            except ImportError:
                # babel not installed, skip compilation
                pass


def get_translator(language: str | None = None) -> Callable[[str], str]:
    """Get a translation function for the specified language.

    Args:
        language: Language code (e.g., 'en', 'de', 'fr'). If None, uses default.

    Returns:
        Translation function that maps strings to translations.
    """
    if language is None:
        language = DEFAULT_LANGUAGE

    if language not in SUPPORTED_LANGUAGES:
        language = DEFAULT_LANGUAGE

    # Ensure MO files exist
    _ensure_mo_files()

    try:
        translation = gettext.translation(
            "messages",
            LOCALES_DIR,
            languages=[language],
        )
    except FileNotFoundError:
        # Fallback to English if translation file not found
        translation = gettext.NullTranslations()

    return translation.gettext


def get_supported_languages() -> list[str]:
    """Get list of supported languages."""
    return SUPPORTED_LANGUAGES.copy()


def get_language_name(code: str) -> str:
    """Get human-readable language name from code."""
    names = {
        "en": "English",
        "de": "Deutsch",
        "fr": "Français",
    }
    return names.get(code, code)
