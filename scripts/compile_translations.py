#!/usr/bin/env python3
"""Compile PO files to MO files."""

import os
import sys
from pathlib import Path

def compile_po_files(locales_dir: Path) -> None:
    """Compile all PO files in the locales directory to MO files."""
    try:
        from babel.messages.mofile import write_mo
        from babel.messages.pofile import read_po
    except ImportError:
        print("Warning: babel not installed. PO files will be compiled at runtime.")
        print("Install babel: pip install babel")
        return

    for lang_dir in locales_dir.iterdir():
        if lang_dir.is_dir():
            po_file = lang_dir / "messages.po"
            if po_file.exists():
                mo_dir = lang_dir / "LC_MESSAGES"
                mo_path = mo_dir / "messages.mo"

                mo_dir.mkdir(parents=True, exist_ok=True)

                with open(po_file, "rb") as f:
                    catalog = read_po(f)

                with open(mo_path, "wb") as f:
                    write_mo(f, catalog)

                print(f"Compiled {po_file} -> {mo_path}")


if __name__ == "__main__":
    locales_dir = Path(__file__).parent.parent / "locales"
    compile_po_files(locales_dir)
