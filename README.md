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
- Talo 2000 English XML import for staging external classes.
- Local Ollama AI mapping actions for imported external classifications.
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
- `/mappings` - search BIMCats tags and external mapping rules with plain English.
- `/admin/tags` - edit taxonomy in active-only treeviews and add children directly under tags.
- `/admin/mappings` - manage mapping rules, import Talo 2000 XML, and start local AI mapping actions.
- `/api/summary` - JSON summary for quick inspection.

## Data Model Notes

Tags use local codes inside a hierarchy, but BIMCats stores generated hierarchy path codes as structured data. For example, `RA` under `RO` becomes `RORA`.

Uniqueness is enforced at the sibling and hierarchy-path level. This matches the thesis principle that the meaningful code is the hierarchy of tags, not a plain isolated tag label.

## Agentic Maintenance

The module `bimcats.agentic` exposes an advisory maintenance report. Agents can use it to review taxonomy and mapping quality.

Local Ollama workflows are available from `/admin/mappings`:

- `Map unmapped classifications` imports/stages Talo 2000 classes if needed, maps currently unmapped rows, validates every returned BIMCats snippet, and saves valid mapping rules.
- `Review all mappings` runs the same AI review path but records results without changing mapping rules.
- `Update all mappings` regenerates mappings for staged classes by archiving active rules for each processed external class before saving valid AI output.

AI runs are queued and processed in the background. The admin screen polls `/api/ai-mapping-progress` and shows the current phase, current external class, candidate count, saved/reviewed count, latest errors, and recent item updates.

The mapping pipeline is intentionally two-phase:

1. `embeddinggemma` embeds BIMCats tags (using the full ancestor-chain context per tag) and the selected external classes, then stores candidate BIMCats tags per class.
2. BIMCats asks Ollama to stop the embedding model.
3. `qwen3.6:27b-32k` receives only the stored candidate tags for each class and returns validated mapping alternatives.

Candidate retrieval applies a per-hierarchy quota (default `4` per Element/Function/Material/Discipline) before filling the global cap, so the chat model can construct multi-axis AND rules such as `(ROSC, ENIT)`.

Snippet matching is hierarchical: a rule keyed by an ancestor `path_code` (e.g. `RO`) matches any descendant token (e.g. `RORA`, `ROSC`) on a 2-character boundary. This implements the thesis principle that "with the presence of multiple deeper tags mapped, the parent tag is considered the closest match."

A confidence threshold (default `0.5`) gates `Map unmapped classifications` and `Update all mappings`. Items whose alternatives fall below the threshold are downgraded to `reviewed` and not auto-saved. `Update all mappings` is divergence-aware: rules whose snippet sets match the new AI output are kept active untouched.

When the AI returns no valid alternatives, the run item records a `nearest_match_suggestion` (top deterministic candidates) so a human can review without restarting the pipeline.

The admin UI defaults each AI action to `5` classes. Increase the limit only after checking quality and runtime.

Required local Ollama models:

```bash
ollama pull embeddinggemma
ollama pull qwen3.6:27b-32k
```

AI mappings are auto-saved only after validation against active BIMCats `path_code` values. The run log records action type, phase, models, candidates, model output, saved rule IDs, errors, and timestamps. Semantic correctness is still not guaranteed; the validation prevents invented snippets, not bad judgment.

## Thesis

This software implements the classification system prototype from the author's master's thesis at Aalto University:

Mladenov, A. (2025). *A harmonized classification system for construction products and elements: The designers' perspective*. Master's thesis, Aalto University School of Engineering. https://aaltodoc.aalto.fi/items/d39d4882-66c3-4f85-af37-4643ac9301b1
