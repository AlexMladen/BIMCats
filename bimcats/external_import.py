from __future__ import annotations

import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path

from .repository import (
    ExternalClassInput,
    refresh_external_mapping_status,
    upsert_classification_system,
    upsert_external_class,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
TALO2000_ENG_XML = PROJECT_ROOT / "files" / "catsys" / "TALO2000_Building_Component_Classification_ENG.xml"


def text_of(node: ET.Element, child_name: str) -> str:
    child = node.find(child_name)
    return "" if child is None or child.text is None else child.text.strip()


def normalize_talo_code(value: str) -> str:
    return value.replace(".", "").strip()


def import_talo2000_english_xml(
    conn: sqlite3.Connection,
    xml_path: str | Path = TALO2000_ENG_XML,
) -> int:
    path = Path(xml_path)
    if not path.exists():
        raise FileNotFoundError(f"Talo 2000 XML not found: {path}")

    tree = ET.parse(path)
    root = tree.getroot()
    system = root.find("./Classification/System")
    if system is None:
        raise ValueError("Talo 2000 XML does not contain Classification/System")

    system_name = text_of(system, "Name") or "Talo 2000"
    description = text_of(system, "Description")
    source_version = text_of(system, "EditionVersion")
    upsert_classification_system(conn, "talo-2000", "Talo 2000", description or system_name)

    imported = 0

    def walk(item: ET.Element, parent_code: str = "") -> None:
        nonlocal imported
        item_id = text_of(item, "ID")
        name = text_of(item, "Name")
        if item_id and name:
            external_code = normalize_talo_code(item_id)
            upsert_external_class(
                conn,
                ExternalClassInput(
                    system_slug="talo-2000",
                    external_code=external_code,
                    external_name=name,
                    description=text_of(item, "Description"),
                    parent_external_code=parent_code,
                    availability=text_of(item, "Availability"),
                    source_file=str(path),
                    source_version=source_version,
                ),
            )
            imported += 1
            parent_code = external_code

        children = item.find("Children")
        if children is not None:
            for child in children.findall("Item"):
                walk(child, parent_code)

    items = system.find("Items")
    if items is None:
        raise ValueError("Talo 2000 XML does not contain System/Items")
    for item in items.findall("Item"):
        walk(item)

    refresh_external_mapping_status(conn, "talo-2000")
    return imported
