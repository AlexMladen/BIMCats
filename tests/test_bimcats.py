from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from bimcats.db import connect
from bimcats.mapping import (
    cross_links,
    extract_tokens,
    matching_external_classes,
    nearest_matches,
    rule_matches,
)
from bimcats.repository import create_tag, list_mapping_rules, list_tags, update_tag
from bimcats.seed import seed
from bimcats.validation import validate_taxonomy


class BIMCatsTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "test.sqlite"
        self.conn = connect(self.db_path)
        warnings = seed(self.conn)
        self.assertEqual(warnings, [])

    def tearDown(self) -> None:
        self.conn.close()
        self.tmp.cleanup()

    def test_seed_contains_expected_hierarchy_paths(self) -> None:
        path_codes = {row["path_code"] for row in list_tags(self.conn)}
        self.assertIn("RORA", path_codes)
        self.assertIn("MEALAS", path_codes)
        self.assertIn("ENIT", path_codes)
        self.assertIn("INMW", path_codes)

    def test_validation_accepts_seed_data(self) -> None:
        self.assertEqual(validate_taxonomy(self.conn), [])

    def test_sibling_code_collision_is_rejected(self) -> None:
        with self.assertRaises(sqlite3.IntegrityError):
            create_tag(self.conn, "element", "RA", "Duplicate roof accessory", "RO")

    def test_parent_code_change_with_children_is_rejected(self) -> None:
        roof = next(row for row in list_tags(self.conn, "element") if row["path_code"] == "RO")
        with self.assertRaises(ValueError):
            update_tag(self.conn, int(roof["id"]), "RX", "Roofs", "", "active")

    def test_extract_tokens_ignores_placeholders(self) -> None:
        self.assertEqual(
            extract_tokens("A_S-RORA-XX-MEALAS_MEALAP"),
            {"A", "S", "RORA", "MEALAS", "MEALAP"},
        )

    def test_rule_matching_supports_and_snippets(self) -> None:
        self.assertTrue(rule_matches("S-ROSC-ENIT-INMW", ("ROSC", "ENIT")))
        self.assertFalse(rule_matches("S-ROSC-ENSE-INMW", ("ROSC", "ENIT")))

    def test_matching_external_classes_uses_containment(self) -> None:
        matches = matching_external_classes(self.conn, "S-RORA-XX-MEALAS_MEALAP")
        codes = {(row["system_slug"], row["external_code"]) for row in matches}
        self.assertIn(("talo-2000", "1262"), codes)

    def test_nearest_matches_rank_by_overlap(self) -> None:
        matches = nearest_matches(self.conn, "S-ROSC-ENIT-INMW")
        self.assertGreaterEqual(matches[0]["overlap"], 2)

    def test_cross_links_use_shared_bimcats_snippets(self) -> None:
        rule = next(
            row
            for row in list_mapping_rules(self.conn, active_only=True)
            if row["system_slug"] == "talo-2000" and row["external_code"] == "1241"
        )
        links = cross_links(self.conn, int(rule["id"]))
        codes = {(row["system"], row["external_code"]) for row in links}
        self.assertIn(("Uniclass", "EF_25_10_25"), codes)


if __name__ == "__main__":
    unittest.main()
