from __future__ import annotations

import sqlite3

from .validation import mapping_warnings, validate_taxonomy


def maintenance_report(conn: sqlite3.Connection) -> dict[str, list[str]]:
    """Return advisory checks that an agent can review before an admin accepts edits."""
    return {
        "taxonomy": validate_taxonomy(conn),
        "mappings": mapping_warnings(conn),
        "review_prompts": [
            "Check whether proposed tags duplicate existing meaning under another name.",
            "Check whether a mapping rule is broader than the BIMCats snippets imply.",
            "Check whether imported external codes need an AND rule instead of a single snippet.",
            "Check whether a changed code affects downstream examples or documentation.",
        ],
    }
