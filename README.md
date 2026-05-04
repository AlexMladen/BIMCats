# BIMCats

BIMCats is a local self-hosted classification workbench for construction product libraries and BIM object libraries.

> **Author:** Aleksandar Mladenov. This project is an implementation of the classification system prototype described in the author's master's thesis at Aalto University. See [Thesis](#thesis) below.

The first version implements the classification engine from the thesis prototype: a global taxonomy library, generated hierarchy-path codes, editable external mapping rules, and a small frontend for browsing and administration.

## MVP Scope

- Global classification library only.
- English-only taxonomy data.
- No login for the local self-hosted instance.
- Admin editing for taxonomy tags and mapping rules.
- Seed data from thesis Appendix 5.
- Talo 2000 and Uniclass mapping examples from thesis Appendix 5.
- BIM integration and product catalog records are future work.

## Technical Foundation

BIMCats currently uses only the Python standard library:

- Python HTTP server for the local frontend.
- SQLite through Python's built-in `sqlite3` module.
- `unittest` for focused backend tests.

The database file is created at `data/bimcats.sqlite`.

## Run Locally

```bash
python3 -m bimcats.seed
python3 -m bimcats.web
```

Then open:

```text
http://127.0.0.1:8000
```

## Run Tests

```bash
python3 -m unittest discover -s tests -v
```

## Main Screens

- `/` - browse the global taxonomy library in collapsed expandable trees.
- `/mappings` - test BIMCats codes against external mapping rules.
- `/admin/tags` - edit taxonomy in active-only treeviews and add children directly under tags.
- `/admin/mappings` - add, edit, and archive mapping rules.
- `/api/summary` - JSON summary for quick inspection.

## Data Model Notes

Tags use local codes inside a hierarchy, but BIMCats stores generated hierarchy path codes as structured data. For example, `RA` under `RO` becomes `RORA`.

Uniqueness is enforced at the sibling and hierarchy-path level. This matches the thesis principle that the meaningful code is the hierarchy of tags, not a plain isolated tag label.

## Agentic Maintenance

The module `bimcats.agentic` exposes an advisory maintenance report. Agents can use it to review taxonomy and mapping quality, but edits should remain admin-approved.

## Thesis

This software implements the classification system prototype from the author's master's thesis at Aalto University:

Mladenov, A. (2025). *A harmonized classification system for construction products and elements: The designers' perspective*. Master's thesis, Aalto University School of Engineering. https://aaltodoc.aalto.fi/items/d39d4882-66c3-4f85-af37-4643ac9301b1
