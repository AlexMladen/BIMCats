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


@dataclass(frozen=True)
class ExternalClassInput:
    system_slug: str
    external_code: str
    external_name: str
    description: str = ""
    parent_external_code: str = ""
    availability: str = ""
    source_file: str = ""
    source_version: str = ""
    status: str = "active"


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


def find_mapping_rule_by_snippets(
    conn: sqlite3.Connection,
    mapping: MappingInput,
    active_only: bool = True,
) -> sqlite3.Row | None:
    system = conn.execute(
        "SELECT id FROM classification_systems WHERE slug = ?", (mapping.system_slug,)
    ).fetchone()
    if system is None:
        raise ValueError(f"Unknown classification system: {mapping.system_slug}")
    status_filter = "AND mr.status = 'active'" if active_only else ""
    expected = {snippet.strip().upper() for snippet in mapping.snippets if snippet.strip()}
    for row in conn.execute(
        f"""
        SELECT mr.*, GROUP_CONCAT(mrs.snippet, ',') AS snippets
        FROM mapping_rules mr
        LEFT JOIN mapping_rule_snippets mrs ON mrs.mapping_rule_id = mr.id
        WHERE mr.classification_system_id = ?
          AND mr.external_code = ?
          AND mr.external_name = ?
          {status_filter}
        GROUP BY mr.id
        """,
        (system["id"], mapping.external_code, mapping.external_name),
    ):
        existing = {
            part.strip().upper()
            for part in (row["snippets"] or "").split(",")
            if part.strip()
        }
        if existing == expected:
            return row
    return None


def create_mapping_rule_if_missing(conn: sqlite3.Connection, mapping: MappingInput) -> int:
    existing = find_mapping_rule_by_snippets(conn, mapping, active_only=True)
    if existing is not None:
        return int(existing["id"])
    return create_mapping_rule(conn, mapping)


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


def list_active_mapping_rules_for_external(
    conn: sqlite3.Connection,
    system_slug: str,
    external_code: str,
) -> list[sqlite3.Row]:
    """Return active mapping rules for one external class. Used by
    update-style flows that need to compare existing rules to newly proposed
    snippet sets before deciding what to archive.
    """
    return list(
        conn.execute(
            """
            SELECT mr.*, cs.slug AS system_slug, cs.name AS system_name,
                   GROUP_CONCAT(mrs.snippet, ',') AS snippets
            FROM mapping_rules mr
            JOIN classification_systems cs ON cs.id = mr.classification_system_id
            LEFT JOIN mapping_rule_snippets mrs ON mrs.mapping_rule_id = mr.id
            WHERE cs.slug = ?
              AND mr.external_code = ?
              AND mr.status = 'active'
            GROUP BY mr.id
            ORDER BY mr.id
            """,
            (system_slug, external_code),
        )
    )


def archive_active_mapping_rules_for_external(
    conn: sqlite3.Connection,
    system_slug: str,
    external_code: str,
) -> int:
    system = conn.execute(
        "SELECT id FROM classification_systems WHERE slug = ?", (system_slug,)
    ).fetchone()
    if system is None:
        raise ValueError(f"Unknown classification system: {system_slug}")
    cur = conn.execute(
        """
        UPDATE mapping_rules
        SET status = 'archived', updated_at = CURRENT_TIMESTAMP
        WHERE classification_system_id = ?
          AND external_code = ?
          AND status = 'active'
        """,
        (system["id"], external_code),
    )
    return int(cur.rowcount)


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


def upsert_external_class(conn: sqlite3.Connection, external_class: ExternalClassInput) -> int:
    system = conn.execute(
        "SELECT id FROM classification_systems WHERE slug = ?",
        (external_class.system_slug,),
    ).fetchone()
    if system is None:
        raise ValueError(f"Unknown classification system: {external_class.system_slug}")
    conn.execute(
        """
        INSERT INTO external_classes (
            classification_system_id, external_code, external_name, description,
            parent_external_code, availability, source_file, source_version, status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(classification_system_id, external_code) DO UPDATE SET
            external_name = excluded.external_name,
            description = excluded.description,
            parent_external_code = excluded.parent_external_code,
            availability = excluded.availability,
            source_file = excluded.source_file,
            source_version = excluded.source_version,
            status = excluded.status,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            system["id"],
            external_class.external_code,
            external_class.external_name,
            external_class.description,
            external_class.parent_external_code,
            external_class.availability,
            external_class.source_file,
            external_class.source_version,
            external_class.status,
        ),
    )
    row = conn.execute(
        """
        SELECT id
        FROM external_classes
        WHERE classification_system_id = ? AND external_code = ?
        """,
        (system["id"], external_class.external_code),
    ).fetchone()
    return int(row["id"])


def list_external_classes(
    conn: sqlite3.Connection,
    system_slug: str = "",
    mapping_status: str = "",
    active_only: bool = True,
    limit: int | None = None,
) -> list[sqlite3.Row]:
    clauses = []
    params: list[str | int] = []
    if system_slug:
        clauses.append("cs.slug = ?")
        params.append(system_slug)
    if mapping_status:
        clauses.append("ec.mapping_status = ?")
        params.append(mapping_status)
    if active_only:
        clauses.append("ec.status = 'active'")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    limit_sql = "LIMIT ?" if limit is not None else ""
    if limit is not None:
        params.append(limit)
    return list(
        conn.execute(
            f"""
            SELECT ec.*, cs.slug AS system_slug, cs.name AS system_name
            FROM external_classes ec
            JOIN classification_systems cs ON cs.id = ec.classification_system_id
            {where}
            ORDER BY cs.name, length(ec.external_code), ec.external_code
            {limit_sql}
            """,
            params,
        )
    )


def get_external_class(conn: sqlite3.Connection, external_class_id: int) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT ec.*, cs.slug AS system_slug, cs.name AS system_name
        FROM external_classes ec
        JOIN classification_systems cs ON cs.id = ec.classification_system_id
        WHERE ec.id = ?
        """,
        (external_class_id,),
    ).fetchone()


def refresh_external_mapping_status(
    conn: sqlite3.Connection,
    system_slug: str = "",
) -> None:
    system_clause = ""
    params: list[str] = []
    if system_slug:
        system_clause = "WHERE cs.slug = ?"
        params.append(system_slug)
    rows = conn.execute(
        f"""
        SELECT ec.id, ec.external_code, cs.id AS system_id
        FROM external_classes ec
        JOIN classification_systems cs ON cs.id = ec.classification_system_id
        {system_clause}
        """,
        params,
    ).fetchall()
    for row in rows:
        active_rule = conn.execute(
            """
            SELECT id FROM mapping_rules
            WHERE classification_system_id = ?
              AND external_code = ?
              AND status = 'active'
            LIMIT 1
            """,
            (row["system_id"], row["external_code"]),
        ).fetchone()
        conn.execute(
            """
            UPDATE external_classes
            SET mapping_status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            ("mapped" if active_rule else "unmapped", row["id"]),
        )


def external_class_summary(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            """
            SELECT cs.slug AS system_slug, cs.name AS system_name,
                   COUNT(ec.id) AS total,
                   SUM(CASE WHEN ec.mapping_status = 'mapped' THEN 1 ELSE 0 END) AS mapped,
                   SUM(CASE WHEN ec.mapping_status = 'unmapped' THEN 1 ELSE 0 END) AS unmapped
            FROM classification_systems cs
            LEFT JOIN external_classes ec ON ec.classification_system_id = cs.id
            WHERE cs.slug != 'bimcats'
            GROUP BY cs.id
            ORDER BY cs.name
            """
        )
    )


def create_ai_mapping_run(
    conn: sqlite3.Connection,
    action_type: str,
    embedding_model: str,
    chat_model: str,
    total_items: int = 0,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO ai_mapping_runs (
            action_type, embedding_model, chat_model, total_items, phase
        )
        VALUES (?, ?, ?, ?, 'queued')
        """,
        (action_type, embedding_model, chat_model, total_items),
    )
    return int(cur.lastrowid)


def update_ai_mapping_run_progress(
    conn: sqlite3.Connection,
    run_id: int,
    phase: str,
    processed_items: int | None = None,
    total_items: int | None = None,
    current_external_code: str = "",
    current_external_name: str = "",
    message: str = "",
) -> None:
    assignments = [
        "phase = ?",
        "current_external_code = ?",
        "current_external_name = ?",
        "updated_at = CURRENT_TIMESTAMP",
    ]
    params: list[str | int] = [phase, current_external_code, current_external_name]
    if processed_items is not None:
        assignments.append("processed_items = ?")
        params.append(processed_items)
    if total_items is not None:
        assignments.append("total_items = ?")
        params.append(total_items)
    if message:
        assignments.append("message = ?")
        params.append(message)
    params.append(run_id)
    conn.execute(
        f"UPDATE ai_mapping_runs SET {', '.join(assignments)} WHERE id = ?",
        params,
    )


def finish_ai_mapping_run(
    conn: sqlite3.Connection,
    run_id: int,
    status: str,
    message: str = "",
) -> None:
    conn.execute(
        """
        UPDATE ai_mapping_runs
        SET status = ?, phase = ?, message = ?, finished_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP, current_external_code = '',
            current_external_name = ''
        WHERE id = ?
        """,
        (status, status, message, run_id),
    )


def add_ai_mapping_run_item(
    conn: sqlite3.Connection,
    run_id: int,
    external_class_id: int | None,
    external_code: str,
    external_name: str,
    candidates_json: str,
    output_json: str,
    saved_rule_ids_json: str,
    status: str,
    error: str = "",
) -> int:
    cur = conn.execute(
        """
        INSERT INTO ai_mapping_run_items (
            run_id, external_class_id, external_code, external_name,
            candidates_json, output_json, saved_rule_ids_json, status, error,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        (
            run_id,
            external_class_id,
            external_code,
            external_name,
            candidates_json,
            output_json,
            saved_rule_ids_json,
            status,
            error,
        ),
    )
    return int(cur.lastrowid)


def create_ai_mapping_run_item(
    conn: sqlite3.Connection,
    run_id: int,
    external_class: sqlite3.Row,
) -> int:
    return add_ai_mapping_run_item(
        conn,
        run_id,
        int(external_class["id"]),
        external_class["external_code"],
        external_class["external_name"],
        "[]",
        "{}",
        "[]",
        "pending",
    )


def list_ai_mapping_run_items(
    conn: sqlite3.Connection,
    run_id: int,
) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            """
            SELECT i.*, ec.description, ec.parent_external_code, ec.availability,
                   cs.slug AS system_slug, cs.name AS system_name
            FROM ai_mapping_run_items i
            LEFT JOIN external_classes ec ON ec.id = i.external_class_id
            LEFT JOIN classification_systems cs ON cs.id = ec.classification_system_id
            WHERE i.run_id = ?
            ORDER BY i.id
            """,
            (run_id,),
        )
    )


def update_ai_mapping_run_item_candidates(
    conn: sqlite3.Connection,
    item_id: int,
    candidates_json: str,
) -> None:
    conn.execute(
        """
        UPDATE ai_mapping_run_items
        SET candidates_json = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (candidates_json, item_id),
    )


def update_ai_mapping_run_item_result(
    conn: sqlite3.Connection,
    item_id: int,
    status: str,
    output_json: str = "{}",
    saved_rule_ids_json: str = "[]",
    error: str = "",
) -> None:
    conn.execute(
        """
        UPDATE ai_mapping_run_items
        SET status = ?, output_json = ?, saved_rule_ids_json = ?, error = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (status, output_json, saved_rule_ids_json, error, item_id),
    )


def latest_ai_mapping_runs(
    conn: sqlite3.Connection,
    limit: int = 5,
) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            """
            SELECT r.*,
                   COUNT(i.id) AS item_count,
                   SUM(CASE WHEN i.status = 'saved' THEN 1 ELSE 0 END) AS saved_count,
                   SUM(CASE WHEN i.status = 'failed' THEN 1 ELSE 0 END) AS failed_count,
                   SUM(CASE WHEN i.status = 'reviewed' THEN 1 ELSE 0 END) AS reviewed_count
            FROM ai_mapping_runs r
            LEFT JOIN ai_mapping_run_items i ON i.run_id = r.id
            GROUP BY r.id
            ORDER BY r.id DESC
            LIMIT ?
            """,
            (limit,),
        )
    )


def latest_ai_mapping_run(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM ai_mapping_runs ORDER BY id DESC LIMIT 1"
    ).fetchone()


def ai_mapping_run_progress(conn: sqlite3.Connection, run_id: int) -> dict[str, object]:
    run = conn.execute(
        "SELECT * FROM ai_mapping_runs WHERE id = ?", (run_id,)
    ).fetchone()
    if run is None:
        raise ValueError(f"Unknown AI mapping run: {run_id}")
    counts = {
        row["status"]: int(row["c"])
        for row in conn.execute(
            """
            SELECT status, COUNT(*) AS c
            FROM ai_mapping_run_items
            WHERE run_id = ?
            GROUP BY status
            """,
            (run_id,),
        )
    }
    candidates_ready = conn.execute(
        """
        SELECT COUNT(*) AS c
        FROM ai_mapping_run_items
        WHERE run_id = ? AND candidates_json != '[]'
        """,
        (run_id,),
    ).fetchone()["c"]
    latest_items = [
        dict(row)
        for row in conn.execute(
            """
            SELECT external_code, external_name, status, error, saved_rule_ids_json,
                   output_json, updated_at
            FROM ai_mapping_run_items
            WHERE run_id = ?
            ORDER BY updated_at DESC, id DESC
            LIMIT 8
            """,
            (run_id,),
        )
    ]
    return {
        "run": dict(run),
        "counts": counts,
        "candidates_ready": int(candidates_ready),
        "latest_items": latest_items,
    }
