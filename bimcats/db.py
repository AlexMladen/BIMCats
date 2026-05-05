from __future__ import annotations

import sqlite3
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = ROOT_DIR / "data" / "bimcats.sqlite"


def connect(db_path: str | Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS classification_systems (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS hierarchies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            axis_order INTEGER NOT NULL UNIQUE
        );

        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hierarchy_id INTEGER NOT NULL REFERENCES hierarchies(id) ON DELETE CASCADE,
            parent_id INTEGER REFERENCES tags(id) ON DELETE CASCADE,
            local_code TEXT NOT NULL,
            path_code TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived')),
            source_note TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (hierarchy_id, parent_id, local_code),
            UNIQUE (hierarchy_id, path_code)
        );

        CREATE INDEX IF NOT EXISTS idx_tags_hierarchy_parent ON tags(hierarchy_id, parent_id);
        CREATE INDEX IF NOT EXISTS idx_tags_status ON tags(status);

        CREATE TABLE IF NOT EXISTS mapping_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            classification_system_id INTEGER NOT NULL
                REFERENCES classification_systems(id) ON DELETE CASCADE,
            external_code TEXT NOT NULL,
            external_name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived')),
            source_note TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_mapping_rules_system
            ON mapping_rules(classification_system_id, external_code);

        CREATE TABLE IF NOT EXISTS mapping_rule_snippets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mapping_rule_id INTEGER NOT NULL REFERENCES mapping_rules(id) ON DELETE CASCADE,
            snippet TEXT NOT NULL,
            position INTEGER NOT NULL,
            UNIQUE (mapping_rule_id, snippet)
        );

        CREATE TABLE IF NOT EXISTS attributes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            unit TEXT NOT NULL DEFAULT '',
            value_range TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived'))
        );

        CREATE TABLE IF NOT EXISTS attribute_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            attribute_id INTEGER NOT NULL REFERENCES attributes(id) ON DELETE CASCADE,
            snippet TEXT NOT NULL,
            position INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS aliases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
            language TEXT NOT NULL DEFAULT 'en',
            alias TEXT NOT NULL,
            UNIQUE (tag_id, language, alias)
        );

        CREATE TABLE IF NOT EXISTS external_classes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            classification_system_id INTEGER NOT NULL
                REFERENCES classification_systems(id) ON DELETE CASCADE,
            external_code TEXT NOT NULL,
            external_name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            parent_external_code TEXT NOT NULL DEFAULT '',
            availability TEXT NOT NULL DEFAULT '',
            source_file TEXT NOT NULL DEFAULT '',
            source_version TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived')),
            mapping_status TEXT NOT NULL DEFAULT 'unmapped'
                CHECK (mapping_status IN ('unmapped', 'mapped')),
            imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (classification_system_id, external_code)
        );

        CREATE INDEX IF NOT EXISTS idx_external_classes_system_status
            ON external_classes(classification_system_id, status, mapping_status);

        CREATE TABLE IF NOT EXISTS ai_mapping_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action_type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'running'
                CHECK (status IN ('running', 'completed', 'failed')),
            phase TEXT NOT NULL DEFAULT 'queued',
            total_items INTEGER NOT NULL DEFAULT 0,
            processed_items INTEGER NOT NULL DEFAULT 0,
            current_external_code TEXT NOT NULL DEFAULT '',
            current_external_name TEXT NOT NULL DEFAULT '',
            embedding_model TEXT NOT NULL DEFAULT '',
            chat_model TEXT NOT NULL DEFAULT '',
            started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            finished_at TEXT,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            message TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS ai_mapping_run_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL REFERENCES ai_mapping_runs(id) ON DELETE CASCADE,
            external_class_id INTEGER REFERENCES external_classes(id) ON DELETE SET NULL,
            external_code TEXT NOT NULL,
            external_name TEXT NOT NULL,
            candidates_json TEXT NOT NULL DEFAULT '[]',
            output_json TEXT NOT NULL DEFAULT '{}',
            saved_rule_ids_json TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'saved', 'reviewed', 'skipped', 'failed')),
            error TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    ensure_column(conn, "ai_mapping_runs", "phase", "phase TEXT NOT NULL DEFAULT 'queued'")
    ensure_column(conn, "ai_mapping_runs", "total_items", "total_items INTEGER NOT NULL DEFAULT 0")
    ensure_column(conn, "ai_mapping_runs", "processed_items", "processed_items INTEGER NOT NULL DEFAULT 0")
    ensure_column(conn, "ai_mapping_runs", "current_external_code", "current_external_code TEXT NOT NULL DEFAULT ''")
    ensure_column(conn, "ai_mapping_runs", "current_external_name", "current_external_name TEXT NOT NULL DEFAULT ''")
    ensure_column(conn, "ai_mapping_runs", "updated_at", "updated_at TEXT NOT NULL DEFAULT ''")
    ensure_column(conn, "ai_mapping_run_items", "updated_at", "updated_at TEXT NOT NULL DEFAULT ''")
    conn.commit()


def ensure_column(
    conn: sqlite3.Connection,
    table: str,
    column: str,
    column_sql: str,
) -> None:
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column_sql}")
