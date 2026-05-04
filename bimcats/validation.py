from __future__ import annotations

import sqlite3


def validate_taxonomy(conn: sqlite3.Connection) -> list[str]:
    warnings: list[str] = []

    sibling_duplicates = conn.execute(
        """
        SELECT h.slug AS hierarchy_slug, COALESCE(p.path_code, '<root>') AS parent_path,
               t.local_code, COUNT(*) AS count
        FROM tags t
        JOIN hierarchies h ON h.id = t.hierarchy_id
        LEFT JOIN tags p ON p.id = t.parent_id
        GROUP BY h.slug, t.parent_id, t.local_code
        HAVING COUNT(*) > 1
        """
    ).fetchall()
    for row in sibling_duplicates:
        warnings.append(
            "Duplicate sibling code "
            f"{row['local_code']} under {row['hierarchy_slug']}:{row['parent_path']}"
        )

    path_duplicates = conn.execute(
        """
        SELECT h.slug AS hierarchy_slug, t.path_code, COUNT(*) AS count
        FROM tags t
        JOIN hierarchies h ON h.id = t.hierarchy_id
        GROUP BY h.slug, t.path_code
        HAVING COUNT(*) > 1
        """
    ).fetchall()
    for row in path_duplicates:
        warnings.append(
            f"Duplicate generated path code {row['path_code']} in {row['hierarchy_slug']}"
        )

    missing_snippets = conn.execute(
        """
        SELECT DISTINCT mrs.snippet
        FROM mapping_rule_snippets mrs
        LEFT JOIN tags t ON t.path_code = mrs.snippet
        WHERE t.id IS NULL
        """
    ).fetchall()
    for row in missing_snippets:
        warnings.append(f"Mapping references unknown BIMCats snippet {row['snippet']}")

    return warnings


def mapping_warnings(conn: sqlite3.Connection) -> list[str]:
    warnings: list[str] = []
    overlapping = conn.execute(
        """
        SELECT mrs.snippet, COUNT(DISTINCT mr.external_code) AS external_count
        FROM mapping_rule_snippets mrs
        JOIN mapping_rules mr ON mr.id = mrs.mapping_rule_id
        WHERE mr.status = 'active'
        GROUP BY mrs.snippet
        HAVING COUNT(DISTINCT mr.external_code) > 1
        ORDER BY external_count DESC, mrs.snippet
        """
    ).fetchall()
    for row in overlapping:
        warnings.append(
            f"Snippet {row['snippet']} maps to {row['external_count']} active external codes"
        )
    return warnings
