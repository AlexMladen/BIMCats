from __future__ import annotations

import sqlite3
from pathlib import Path

from .db import DEFAULT_DB_PATH, connect, init_schema
from .repository import (
    MappingInput,
    create_mapping_rule,
    create_tag,
    list_mapping_rules,
    list_tags,
    upsert_classification_system,
    upsert_hierarchy,
)
from .validation import validate_taxonomy


HIERARCHIES = (
    ("discipline", "Discipline", 1),
    ("element", "Element", 2),
    ("function", "Function", 3),
    ("material", "Material", 4),
)

SYSTEMS = (
    (
        "bimcats",
        "BIMCats",
        "Internal harmonized classification model based on the thesis prototype.",
    ),
    ("talo-2000", "Talo 2000", "External mapping examples from Appendix 5."),
    ("uniclass", "Uniclass", "External mapping examples from Appendix 5."),
)

TAGS = (
    # Discipline
    ("discipline", None, "A", "Architectural", ""),
    ("discipline", None, "S", "Structural", ""),
    ("discipline", None, "M", "MEP", ""),
    # Element hierarchy
    ("element", None, "SU", "Substructure", ""),
    ("element", "SU", "FS", "Foundation systems", ""),
    ("element", "SU", "FE", "Foundation elements and accessories", ""),
    ("element", "SU", "SX", "Special substructure", ""),
    ("element", None, "ST", "Superstructure", ""),
    ("element", "ST", "BJ", "Beams and joists", ""),
    ("element", "ST", "CO", "Columns", ""),
    ("element", "ST", "SX", "Special superstructure", ""),
    ("element", None, "FL", "Floors", ""),
    ("element", "FL", "FS", "Floor systems", ""),
    ("element", "FL", "FF", "Floor elements and accessories", ""),
    ("element", "FL", "SX", "Special floors", ""),
    ("element", None, "WB", "Walls and barriers", ""),
    ("element", "WB", "FC", "Facade systems and claddings", ""),
    ("element", "WB", "EW", "External walls", ""),
    ("element", "WB", "IW", "Internal walls", ""),
    ("element", "WB", "PW", "Partition walls", ""),
    ("element", "WB", "BW", "Balcony walls", ""),
    ("element", "WB", "RA", "Railings", ""),
    ("element", "WB", "WA", "Wall elements and accessories", ""),
    ("element", "WB", "SX", "Special walls", ""),
    ("element", None, "RO", "Roofs", ""),
    ("element", "RO", "RA", "Roof accessories", ""),
    ("element", "RO", "SC", "Roof systems and claddings", ""),
    ("element", "RO", "SX", "Special roofs", ""),
    ("element", None, "SF", "Sanitary fittings and accessories", ""),
    ("element", "SF", "BA", "Baths", ""),
    ("element", "SF", "SE", "Shower enclosures", ""),
    ("element", "SF", "SX", "Special sanitary", ""),
    ("element", None, "FF", "Fittings, furnishing and equipment", ""),
    ("element", "FF", "BE", "Beds", ""),
    ("element", "FF", "CS", "Chairs, seats and benches", ""),
    ("element", "FF", "BB", "Bins and buckets", ""),
    ("element", "FF", "SX", "Special equipment", ""),
    # Function hierarchy
    ("function", None, "ST", "Structural", ""),
    ("function", "ST", "AN", "Anchor", ""),
    ("function", "ST", "FO", "Foot", ""),
    ("function", "ST", "PR", "Prefabricated reinforcement", ""),
    ("function", "ST", "RC", "Reinforcement couplers", ""),
    ("function", "ST", "RS", "Reinforcement starters", ""),
    ("function", "ST", "RA", "Reinforcement ancillaries", ""),
    ("function", "ST", "BA", "Balcony connectors", ""),
    ("function", "ST", "FR", "Frame", "Normalized from thesis label 'Fr'."),
    ("function", "ST", "BB", "Building blocks", ""),
    ("function", "ST", "SC", "Slabs", ""),
    ("function", "ST", "SX", "Special structural", ""),
    ("function", None, "EN", "Envelope", ""),
    ("function", "EN", "RS", "Rainwater systems", ""),
    ("function", "EN", "WP", "Waterproofing", ""),
    ("function", "EN", "SE", "Sealing", ""),
    ("function", "EN", "IT", "Insulation thermal", ""),
    ("function", "EN", "IA", "Insulation acoustic - airborne", ""),
    ("function", "EN", "II", "Insulation acoustic - impact", ""),
    ("function", "EN", "SX", "Special envelope", ""),
    ("function", None, "FS", "Finishing", ""),
    ("function", "FS", "PA", "Paint", ""),
    ("function", "FS", "CO", "Coating", ""),
    ("function", "FS", "PL", "Plaster", ""),
    ("function", "FS", "CL", "Cladding", ""),
    ("function", "FS", "SX", "Special finishing", ""),
    ("function", None, "OT", "Other", ""),
    ("function", "OT", "SS", "Safety systems", ""),
    ("function", "OT", "SX", "Special", ""),
    ("function", None, "FF", "Equipment", ""),
    ("function", "FF", "ME", "Medical", ""),
    ("function", "FF", "OF", "Office", ""),
    ("function", "FF", "SP", "Sports", ""),
    ("function", "FF", "SX", "Special equipment", ""),
    ("function", None, "VA", "Ventilation", ""),
    ("function", "VA", "FE", "Fume extraction", ""),
    ("function", "VA", "GV", "General space ventilation", ""),
    ("function", "VA", "SM", "Smoke extraction", ""),
    ("function", "VA", "SX", "Special ventilation", ""),
    ("function", None, "AC", "Air conditioning", ""),
    ("function", "AC", "CA", "Central air conditioning", ""),
    ("function", "AC", "CE", "Controlled environments", ""),
    ("function", "AC", "LA", "Local air conditioning", ""),
    ("function", "AC", "SX", "Special air conditioning", ""),
    ("function", None, "SH", "Space heating and cooling", ""),
    ("function", "SH", "CH", "Combined heating, cooling and power", ""),
    ("function", "SH", "CO", "Cooling", ""),
    (
        "function",
        "SH",
        "HE",
        "Heating",
        "Appendix 5 lists this as CH, which collides with its sibling. BIMCats uses HE to preserve sibling-code uniqueness.",
    ),
    ("function", "SH", "SX", "Special heating/cooling", ""),
    ("function", None, "EL", "Electrical power and lighting", ""),
    ("function", "EL", "EL", "External lighting", ""),
    ("function", "EL", "GL", "General space lighting", ""),
    ("function", "EL", "FP", "Fossil fuel power generation", ""),
    ("function", "EL", "RP", "Renewable power generation", ""),
    ("function", "EL", "CM", "Cable management", ""),
    ("function", "EL", "HV", "High-voltage electricity distribution", ""),
    ("function", "EL", "LV", "Low-voltage electricity distribution", ""),
    ("function", "EL", "SX", "Special electrical", ""),
    # Material hierarchy
    ("material", None, "WO", "Wood", ""),
    ("material", "WO", "SW", "Solid wood", ""),
    ("material", "WOSW", "ST", "Structural timber", ""),
    ("material", "WOSWST", "SS", "Solid structural timber", ""),
    ("material", "WOSWST", "GL", "Glue-laminated timber", ""),
    ("material", "WOSWST", "CL", "Cross-laminated timber", ""),
    ("material", "WOSWST", "GB", "Glue-laminated timber board", ""),
    ("material", "WOSW", "OS", "Oriented strand board", ""),
    ("material", "WOSW", "LV", "Laminated veneer lumber", ""),
    ("material", "WOSW", "PB", "Plywood board", ""),
    ("material", "WOSW", "VB", "Veneer board", ""),
    ("material", None, "ME", "Metals", ""),
    ("material", "ME", "SI", "Steel and iron", ""),
    ("material", "MESI", "RB", "Steel reinforcing bar", ""),
    ("material", "MESI", "SP", "Structural steel profile", ""),
    ("material", "MESI", "SS", "Steel sheets", ""),
    ("material", "ME", "SS", "Stainless steel", ""),
    ("material", "MESS", "SH", "Stainless steel sheets", ""),
    ("material", "MESS", "SP", "Stainless steel profiles", ""),
    ("material", "ME", "AL", "Aluminium", ""),
    ("material", "MEAL", "AS", "Aluminium sheets", ""),
    ("material", "MEAL", "AP", "Aluminium profiles", ""),
    ("material", "MEAL", "CA", "Cast aluminium", ""),
    ("material", "MEAL", "AF", "Aluminium foil", ""),
    ("material", None, "MN", "Mineral building products", ""),
    ("material", "MN", "BB", "Bricks, blocks and elements", ""),
    ("material", "MNBB", "FB", "Fired brick", ""),
    ("material", "MNBB", "AC", "Aerated concrete", ""),
    ("material", "MNBB", "LC", "Light concrete", ""),
    ("material", "MNBB", "PC", "Precast concrete elements", ""),
    ("material", "MNBB", "TC", "Tiles and cladding panels", ""),
    ("material", "MNBB", "NC", "Natural cut stone", ""),
    ("material", "MNBB", "CT", "Ceramic roof tile", ""),
    ("material", "MNBB", "FC", "Fibre cement", ""),
    ("material", "MNBB", "GP", "Gypsum plasterboard", ""),
    ("material", None, "IN", "Insulation materials", ""),
    ("material", "IN", "MW", "Mineral wool", ""),
    ("material", "IN", "EP", "Expanded polystyrene", ""),
    ("material", "IN", "XP", "Extruded polystyrene", ""),
)

MAPPINGS = (
    MappingInput("talo-2000", "1212", "Enclosure walls, foundation columns, foundation beams", ("SUFS",)),
    MappingInput("talo-2000", "1211", "Footings", ("SUFE",)),
    MappingInput("talo-2000", "1213", "Special foundations", ("SUSX",)),
    MappingInput("talo-2000", "1241", "External walls", ("WBEW",)),
    MappingInput("talo-2000", "1241", "External walls", ("WBFC",)),
    MappingInput("talo-2000", "1262", "Roof substructures", ("ROSC", "ENWP")),
    MappingInput("talo-2000", "1262", "Roof substructures", ("ROSC", "ENSE")),
    MappingInput("talo-2000", "1262", "Roof substructures", ("ROSC", "ENIT")),
    MappingInput("talo-2000", "1262", "Roof substructures", ("RORA",)),
    MappingInput("talo-2000", "1263", "Roofings", ("ROSC",)),
    MappingInput("uniclass", "EF_20_05_30", "Foundations", ("SUFS",)),
    MappingInput("uniclass", "EF_25_10_25", "External walls", ("WBEW",)),
    MappingInput("uniclass", "Pr_25_57_06_53", "Mineral wool insulation", ("ENIT", "INMW")),
    MappingInput("uniclass", "Pr_20_29_03_86", "Structural anchors", ("STAN",)),
)

ATTRIBUTES = (
    ("Width", "m", "", ("XX",)),
    ("Length", "m", "", ("XX",)),
    ("Global Warming Potential (GWP100), A1-A3, EPD Total", "kg CO2-eq", "", ("XX",)),
    ("Reaction to fire", "", "A1...F", ("XX",)),
    ("Wind load resistance", "kN/m^2", "", ("WBFC",)),
    ("Thermal resistance", "m^2*K/W", "", ("ENIT", "WBFC", "WBEW", "WBBW", "ROSC", "FLFS")),
)


def seed(conn: sqlite3.Connection) -> list[str]:
    init_schema(conn)
    for slug, name, description in SYSTEMS:
        upsert_classification_system(conn, slug, name, description)
    for slug, name, axis_order in HIERARCHIES:
        upsert_hierarchy(conn, slug, name, axis_order)

    if not list_tags(conn):
        for hierarchy, parent_path, local_code, name, source_note in TAGS:
            create_tag(
                conn,
                hierarchy,
                local_code,
                name,
                parent_path_code=parent_path,
                source_note=source_note,
            )

    if not list_mapping_rules(conn):
        for mapping in MAPPINGS:
            create_mapping_rule(conn, mapping)

    if not conn.execute("SELECT id FROM attributes LIMIT 1").fetchone():
        for name, unit, value_range, snippets in ATTRIBUTES:
            cur = conn.execute(
                """
                INSERT INTO attributes (name, unit, value_range)
                VALUES (?, ?, ?)
                """,
                (name, unit, value_range),
            )
            attribute_id = int(cur.lastrowid)
            for index, snippet in enumerate(snippets):
                conn.execute(
                    """
                    INSERT INTO attribute_rules (attribute_id, snippet, position)
                    VALUES (?, ?, ?)
                    """,
                    (attribute_id, snippet, index),
                )

    conn.commit()
    return validate_taxonomy(conn)


def main(db_path: str | Path = DEFAULT_DB_PATH) -> None:
    with connect(db_path) as conn:
        warnings = seed(conn)
    print(f"Seeded BIMCats database at {db_path}")
    if warnings:
        print("Validation warnings:")
        for warning in warnings:
            print(f"- {warning}")
    else:
        print("Validation passed.")


if __name__ == "__main__":
    main()
