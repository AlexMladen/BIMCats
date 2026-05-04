from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class MappingInput:
    system_slug: str
    external_code: str
    external_name: str
    snippets: tuple[str, ...]
    source_note: str = ""


def upsert_classification_system(
    conn: sqlite3.Connection, slug: str, name: str, description: str = ""
) -> int:
    conn.execute(
        """
        INSERT INTO classification_systems (slug, name, description)
        VALUES (?, ?, ?)
        ON CONFLICT(slug) DO UPDATE SET
            name = excluded.name,
            description = excluded.description
        """,
        (slug, name, description),
    )
    row = conn.execute(
        "SELECT id FROM classification_systems WHERE slug = ?", (slug,)
    ).fetchone()
    return int(row["id"])


def upsert_hierarchy(
    conn: sqlite3.Connection, slug: str, name: str, axis_order: int
) -> int:
    conn.execute(
        """
        INSERT INTO hierarchies (slug, name, axis_order)
        VALUES (?, ?, ?)
        ON CONFLICT(slug) DO UPDATE SET
            name = excluded.name,
            axis_order = excluded.axis_order
        """,
        (slug, name, axis_order),
    )
    row = conn.execute("SELECT id FROM hierarchies WHERE slug = ?", (slug,)).fetchone()
    return int(row["id"])


def get_hierarchy_id(conn: sqlite3.Connection, slug: str) -> int:
    row = conn.execute("SELECT id FROM hierarchies WHERE slug = ?", (slug,)).fetchone()
    if row is None:
        raise ValueError(f"Unknown hierarchy: {slug}")
    return int(row["id"])


def get_tag_by_path(
    conn: sqlite3.Connection, path_code: str, hierarchy_id: int | None = None
) -> sqlite3.Row | None:
    if hierarchy_id is None:
        return conn.execute(
            "SELECT * FROM tags WHERE path_code = ? ORDER BY hierarchy_id LIMIT 1",
            (path_code,),
        ).fetchone()
    return conn.execute(
        "SELECT * FROM tags WHERE hierarchy_id = ? AND path_code = ?",
        (hierarchy_id, path_code),
    ).fetchone()


def build_path_code(conn: sqlite3.Connection, parent_id: int | None, local_code: str) -> str:
    if parent_id is None:
        return local_code
    parent = conn.execute("SELECT path_code FROM tags WHERE id = ?", (parent_id,)).fetchone()
    if parent is None:
        raise ValueError(f"Unknown parent tag id: {parent_id}")
    return f"{parent['path_code']}{local_code}"


def create_tag(
    conn: sqlite3.Connection,
    hierarchy_slug: str,
    local_code: str,
    name: str,
    parent_path_code: str | None = None,
    description: str = "",
    status: str = "active",
    source_note: str = "",
) -> int:
    hierarchy_id = get_hierarchy_id(conn, hierarchy_slug)
    parent_id = None
    if parent_path_code:
        parent = get_tag_by_path(conn, parent_path_code, hierarchy_id)
        if parent is None:
            raise ValueError(f"Unknown parent path code: {parent_path_code}")
        parent_id = int(parent["id"])
    path_code = build_path_code(conn, parent_id, local_code)
    cur = conn.execute(
        """
        INSERT INTO tags (
            hierarchy_id, parent_id, local_code, path_code, name,
            description, status, source_note
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            hierarchy_id,
            parent_id,
            local_code,
            path_code,
            name,
            description,
            status,
            source_note,
        ),
    )
    return int(cur.lastrowid)


def update_tag(
    conn: sqlite3.Connection,
    tag_id: int,
    local_code: str,
    name: str,
    description: str,
    status: str,
) -> None:
    row = conn.execute(
        "SELECT parent_id, local_code FROM tags WHERE id = ?", (tag_id,)
    ).fetchone()
    if row is None:
        raise ValueError(f"Unknown tag id: {tag_id}")
    if row["local_code"] != local_code:
        child = conn.execute("SELECT id FROM tags WHERE parent_id = ? LIMIT 1", (tag_id,)).fetchone()
        if child is not None:
            raise ValueError("Cannot change a tag code while it has child tags")
    path_code = build_path_code(conn, row["parent_id"], local_code)
    conn.execute(
        """
        UPDATE tags
        SET local_code = ?, path_code = ?, name = ?, description = ?,
            status = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (local_code, path_code, name, description, status, tag_id),
    )


def archive_tag(conn: sqlite3.Connection, tag_id: int) -> None:
    conn.execute(
        "UPDATE tags SET status = 'archived', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (tag_id,),
    )


def list_hierarchies(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(conn.execute("SELECT * FROM hierarchies ORDER BY axis_order"))


def list_tags(conn: sqlite3.Connection, hierarchy_slug: str | None = None) -> list[sqlite3.Row]:
    params: list[str] = []
    where = ""
    if hierarchy_slug:
        where = "WHERE h.slug = ?"
        params.append(hierarchy_slug)
    return list(
        conn.execute(
            f"""
            SELECT t.*, h.slug AS hierarchy_slug, h.name AS hierarchy_name,
                   p.path_code AS parent_path_code, p.name AS parent_name
            FROM tags t
            JOIN hierarchies h ON h.id = t.hierarchy_id
            LEFT JOIN tags p ON p.id = t.parent_id
            {where}
            ORDER BY h.axis_order, t.path_code
            """,
            params,
        )
    )


def create_mapping_rule(conn: sqlite3.Connection, mapping: MappingInput) -> int:
    system = conn.execute(
        "SELECT id FROM classification_systems WHERE slug = ?", (mapping.system_slug,)
    ).fetchone()
    if system is None:
        raise ValueError(f"Unknown classification system: {mapping.system_slug}")
    cur = conn.execute(
        """
        INSERT INTO mapping_rules (
            classification_system_id, external_code, external_name, source_note
        )
        VALUES (?, ?, ?, ?)
        """,
        (system["id"], mapping.external_code, mapping.external_name, mapping.source_note),
    )
    rule_id = int(cur.lastrowid)
    for index, snippet in enumerate(mapping.snippets):
        conn.execute(
            """
            INSERT INTO mapping_rule_snippets (mapping_rule_id, snippet, position)
            VALUES (?, ?, ?)
            """,
            (rule_id, snippet, index),
        )
    return rule_id


def update_mapping_rule(
    conn: sqlite3.Connection,
    rule_id: int,
    external_code: str,
    external_name: str,
    snippets: Iterable[str],
    status: str,
) -> None:
    conn.execute(
        """
        UPDATE mapping_rules
        SET external_code = ?, external_name = ?, status = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (external_code, external_name, status, rule_id),
    )
    conn.execute("DELETE FROM mapping_rule_snippets WHERE mapping_rule_id = ?", (rule_id,))
    for index, snippet in enumerate(snippets):
        conn.execute(
            """
            INSERT INTO mapping_rule_snippets (mapping_rule_id, snippet, position)
            VALUES (?, ?, ?)
            """,
            (rule_id, snippet.strip(), index),
        )


def archive_mapping_rule(conn: sqlite3.Connection, rule_id: int) -> None:
    conn.execute(
        """
        UPDATE mapping_rules
        SET status = 'archived', updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (rule_id,),
    )


def list_mapping_rules(conn: sqlite3.Connection, active_only: bool = False) -> list[sqlite3.Row]:
    where = "WHERE mr.status = 'active'" if active_only else ""
    return list(
        conn.execute(
            f"""
            SELECT mr.*, cs.slug AS system_slug, cs.name AS system_name,
                   GROUP_CONCAT(mrs.snippet, ',') AS snippets
            FROM mapping_rules mr
            JOIN classification_systems cs ON cs.id = mr.classification_system_id
            LEFT JOIN mapping_rule_snippets mrs ON mrs.mapping_rule_id = mr.id
            {where}
            GROUP BY mr.id
            ORDER BY cs.name, mr.external_code, mr.id
            """
        )
    )


def list_classification_systems(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(conn.execute("SELECT * FROM classification_systems ORDER BY name"))
