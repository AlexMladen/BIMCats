from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .db import DEFAULT_DB_PATH, connect
from .ollama_client import CHAT_MODEL, EMBEDDING_MODEL, OllamaClient, OllamaError
from .mapping import normalize_snippets
from .repository import (
    MappingInput,
    archive_mapping_rule,
    create_ai_mapping_run,
    create_ai_mapping_run_item,
    create_mapping_rule_if_missing,
    finish_ai_mapping_run,
    list_active_mapping_rules_for_external,
    list_ai_mapping_run_items,
    list_external_classes,
    list_tags,
    refresh_external_mapping_status,
    update_ai_mapping_run_item_candidates,
    update_ai_mapping_run_item_result,
    update_ai_mapping_run_progress,
)
from .search import suggest_tags


class MappingAIClient(Protocol):
    def embed(self, model: str, texts: list[str]) -> list[list[float]]:
        ...

    def chat_json(self, model: str, system: str, user: str) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class CandidateTag:
    path_code: str
    name: str
    hierarchy: str
    parent_name: str
    score: float
    reason: str

    def as_prompt_dict(self) -> dict[str, str | float]:
        return {
            "path_code": self.path_code,
            "name": self.name,
            "hierarchy": self.hierarchy,
            "parent_name": self.parent_name,
            "score": round(self.score, 4),
            "reason": self.reason,
        }


def candidate_from_dict(value: dict[str, Any]) -> CandidateTag:
    return CandidateTag(
        path_code=str(value.get("path_code", "")).upper(),
        name=str(value.get("name", "")),
        hierarchy=str(value.get("hierarchy", "")),
        parent_name=str(value.get("parent_name", "")),
        score=float(value.get("score", 0)),
        reason=str(value.get("reason", "")),
    )


def candidates_json(candidates: list[CandidateTag]) -> str:
    return json.dumps([candidate.as_prompt_dict() for candidate in candidates])


def candidates_from_json(value: str) -> list[CandidateTag]:
    try:
        raw = json.loads(value or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(raw, list):
        return []
    return [candidate_from_dict(item) for item in raw if isinstance(item, dict)]


def external_class_text(row: sqlite3.Row) -> str:
    return " ".join(
        part
        for part in (
            row["system_name"],
            row["external_code"],
            row["external_name"],
            row["description"] or "",
            row["parent_external_code"] or "",
            row["availability"] or "",
        )
        if part
    )


def ancestor_chain_names(
    tag_row: sqlite3.Row,
    tags_by_path: dict[str, sqlite3.Row],
) -> list[str]:
    """Walk parent_path_code links to return ancestor names from root to direct
    parent. Used to give the embedding model the full hierarchical context for
    tags whose own name is short or generic (e.g. "Anchor", "Foot").
    """
    names: list[str] = []
    current_parent = tag_row["parent_path_code"]
    visited: set[str] = set()
    while current_parent and current_parent not in visited:
        visited.add(current_parent)
        parent = tags_by_path.get(current_parent)
        if parent is None:
            break
        names.append(parent["name"])
        current_parent = parent["parent_path_code"]
    return list(reversed(names))


def tag_text(row: sqlite3.Row, tags_by_path: dict[str, sqlite3.Row] | None = None) -> str:
    """Build the embedding text for a tag. When tags_by_path is provided the
    full ancestor chain (root -> parent) is included so short tag names still
    carry hierarchical meaning into the embedding space.
    """
    chain = ancestor_chain_names(row, tags_by_path) if tags_by_path else []
    return " ".join(
        part
        for part in (
            row["path_code"],
            row["local_code"],
            row["name"],
            row["description"],
            row["hierarchy_name"],
            *chain,
            row["parent_path_code"] or "",
            row["parent_name"] or "",
        )
        if part
    )


def build_tags_by_path(tags: list[sqlite3.Row]) -> dict[str, sqlite3.Row]:
    return {row["path_code"]: row for row in tags}


def cosine(a: list[float], b: list[float]) -> float:
    numerator = sum(left * right for left, right in zip(a, b))
    left_norm = math.sqrt(sum(value * value for value in a))
    right_norm = math.sqrt(sum(value * value for value in b))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


# Per-hierarchy quota for candidate retrieval. Ensures the chat model can
# build multi-axis AND rules (e.g. (ROSC, ENIT)) by guaranteeing a minimum
# slice of candidates from each hierarchy before the global cap is applied.
PER_HIERARCHY_QUOTA = 4
DEFAULT_CANDIDATE_LIMIT = 12


def diversify_by_hierarchy(
    candidates: list[CandidateTag],
    limit: int,
    per_hierarchy_quota: int = PER_HIERARCHY_QUOTA,
) -> list[CandidateTag]:
    """Pick candidates so each hierarchy contributes up to per_hierarchy_quota
    items first (in score order), then fill the remaining limit with the next
    best by score. Input must already be sorted by score (descending).
    """
    selected: list[CandidateTag] = []
    seen: set[tuple[str, str]] = set()
    counts: dict[str, int] = {}
    for candidate in candidates:
        if counts.get(candidate.hierarchy, 0) >= per_hierarchy_quota:
            continue
        selected.append(candidate)
        seen.add((candidate.hierarchy, candidate.path_code))
        counts[candidate.hierarchy] = counts.get(candidate.hierarchy, 0) + 1
        if len(selected) >= limit:
            return selected
    for candidate in candidates:
        if len(selected) >= limit:
            break
        key = (candidate.hierarchy, candidate.path_code)
        if key in seen:
            continue
        selected.append(candidate)
        seen.add(key)
    return selected


def deterministic_candidates(
    conn: sqlite3.Connection,
    external_row: sqlite3.Row,
    limit: int = DEFAULT_CANDIDATE_LIMIT,
) -> list[CandidateTag]:
    # Ask the deterministic search for a wider pool so the diversifier has
    # enough material to satisfy each hierarchy's quota.
    query = f"{external_row['external_name']} {external_row['description'] or ''}".strip()
    pool = [
        CandidateTag(
            path_code=item.path_code,
            name=item.name,
            hierarchy=item.hierarchy,
            parent_name=item.parent_name,
            score=float(item.score),
            reason=f"deterministic fallback: {item.reason}",
        )
        for item in suggest_tags(conn, query, limit=max(limit * 4, limit))
    ]
    return diversify_by_hierarchy(pool, limit=limit)


def rank_semantic_candidates(
    tag_rows: list[sqlite3.Row],
    tag_vectors: list[list[float]],
    external_vector: list[float],
    limit: int = DEFAULT_CANDIDATE_LIMIT,
) -> list[CandidateTag]:
    ranked: list[CandidateTag] = []
    for row, vector in zip(tag_rows, tag_vectors):
        ranked.append(
            CandidateTag(
                path_code=row["path_code"],
                name=row["name"],
                hierarchy=row["hierarchy_name"],
                parent_name=row["parent_name"] or "",
                score=cosine(external_vector, vector),
                reason="semantic similarity",
            )
        )
    ranked.sort(key=lambda item: (-item.score, item.hierarchy, item.path_code))
    # Diversify so AND rules across Element/Function/Material/Discipline are
    # reachable even when one hierarchy dominates raw cosine similarity.
    return diversify_by_hierarchy(ranked, limit=limit)


def semantic_candidates(
    conn: sqlite3.Connection,
    external_row: sqlite3.Row,
    client: MappingAIClient,
    embedding_model: str = EMBEDDING_MODEL,
    limit: int = DEFAULT_CANDIDATE_LIMIT,
) -> list[CandidateTag]:
    tags = [row for row in list_tags(conn) if row["status"] == "active"]
    tags_by_path = build_tags_by_path(tags)
    texts = [
        external_class_text(external_row),
        *[tag_text(row, tags_by_path) for row in tags],
    ]
    try:
        vectors = client.embed(embedding_model, texts)
    except Exception:
        return deterministic_candidates(conn, external_row, limit=limit)
    if len(vectors) != len(texts):
        return deterministic_candidates(conn, external_row, limit=limit)
    return rank_semantic_candidates(tags, vectors[1:], vectors[0], limit=limit)


# Default confidence threshold for save-mode actions. Items whose minimum
# alternative confidence falls below this are downgraded to reviewed and not
# saved as mapping rules. The model is already prompted to return confidence.
DEFAULT_CONFIDENCE_THRESHOLD = 0.5


def _coerce_confidence(value: Any) -> float | None:
    """Best-effort parse of a confidence value from the model. Returns None
    when no usable confidence is present, so callers can decide how to treat
    missing confidences.
    """
    if value is None:
        return None
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    if score < 0:
        return 0.0
    if score > 1:
        # Tolerate models returning percentages (0-100) by rescaling to 0-1.
        return min(score / 100.0, 1.0)
    return score


def normalize_ai_alternatives(
    payload: dict[str, Any],
    valid_codes: set[str],
    candidate_codes: set[str],
) -> tuple[tuple[tuple[str, ...], float | None], ...]:
    """Validate and normalize the AI output.

    Returns a tuple of (snippets, confidence) pairs. Each snippet must be both
    an active BIMCats path_code and inside the candidate set shown to the
    model. Confidence is parsed best-effort; missing values yield None so the
    caller can apply its own gating policy.
    """
    raw_alternatives = payload.get("alternatives")
    if raw_alternatives is None and "snippets" in payload:
        raw_alternatives = [{"snippets": payload["snippets"], "confidence": payload.get("confidence")}]
    if not isinstance(raw_alternatives, list):
        raise ValueError("AI output must contain an alternatives list")

    alternatives: list[tuple[tuple[str, ...], float | None]] = []
    seen: set[tuple[str, ...]] = set()
    for item in raw_alternatives:
        if not isinstance(item, dict):
            continue
        snippets = item.get("snippets", [])
        if not isinstance(snippets, list):
            continue
        normalized: list[str] = []
        for snippet in snippets:
            code = str(snippet).strip().upper()
            if not code:
                continue
            if code not in valid_codes:
                raise ValueError(f"AI returned unknown BIMCats snippet: {code}")
            if code not in candidate_codes:
                raise ValueError(f"AI returned a snippet outside the candidate set: {code}")
            if code not in normalized:
                normalized.append(code)
        alternative = tuple(normalized)
        if alternative and alternative not in seen:
            seen.add(alternative)
            confidence = _coerce_confidence(item.get("confidence"))
            alternatives.append((alternative, confidence))
    if not alternatives:
        raise ValueError("AI did not return any valid mapping alternatives")
    return tuple(alternatives)


def mapping_prompt(external_row: sqlite3.Row, candidates: list[CandidateTag]) -> tuple[str, str]:
    system = (
        "You map external construction classification classes to BIMCats tag snippets. "
        "Return strict JSON only. Use only candidate path_code values. "
        "One alternative means all snippets in that alternative are required together as an AND rule. "
        "Multiple alternatives mean OR mapping rules for the same external class. "
        "Do not invent codes. Prefer the smallest precise snippet set."
    )
    user = json.dumps(
        {
            "external_class": {
                "system": external_row["system_name"],
                "code": external_row["external_code"],
                "name": external_row["external_name"],
                "description": external_row["description"] or "",
                "parent_external_code": external_row["parent_external_code"] or "",
                "availability": external_row["availability"] or "",
            },
            "candidate_bimcats_tags": [candidate.as_prompt_dict() for candidate in candidates],
            "required_output": {
                "alternatives": [
                    {
                        "snippets": ["EXAMPLE_PATH_CODE"],
                        "confidence": 0.0,
                        "reason": "short reason",
                    }
                ]
            },
        },
        ensure_ascii=True,
    )
    return system, user


def create_ai_mapping_queue(
    conn: sqlite3.Connection,
    action_type: str,
    system_slug: str = "talo-2000",
    limit: int | None = None,
    embedding_model: str = EMBEDDING_MODEL,
    chat_model: str = CHAT_MODEL,
) -> tuple[int, int]:
    if action_type not in {"map_unmapped", "review_all", "update_all"}:
        raise ValueError(f"Unknown AI mapping action: {action_type}")
    mapping_status = "unmapped" if action_type == "map_unmapped" else ""
    classes = list_external_classes(
        conn,
        system_slug=system_slug,
        mapping_status=mapping_status,
        active_only=True,
        limit=limit,
    )
    run_id = create_ai_mapping_run(
        conn,
        action_type,
        embedding_model,
        chat_model,
        total_items=len(classes),
    )
    for external_class in classes:
        create_ai_mapping_run_item(conn, run_id, external_class)
    if not classes:
        finish_ai_mapping_run(conn, run_id, "completed", "No external classes matched this action.")
    return run_id, len(classes)


def prepare_run_candidates(
    conn: sqlite3.Connection,
    run_id: int,
    client: MappingAIClient,
    embedding_model: str,
    limit: int = 12,
) -> None:
    items = list_ai_mapping_run_items(conn, run_id)
    if not items:
        return

    tags = [row for row in list_tags(conn) if row["status"] == "active"]
    tags_by_path = build_tags_by_path(tags)
    try:
        tag_vectors = client.embed(
            embedding_model, [tag_text(row, tags_by_path) for row in tags]
        )
        external_vectors = client.embed(embedding_model, [external_class_text(row) for row in items])
    except Exception:
        tag_vectors = []
        external_vectors = []

    total = len(items)
    for index, item in enumerate(items, start=1):
        update_ai_mapping_run_progress(
            conn,
            run_id,
            "embedding",
            processed_items=index - 1,
            total_items=total,
            current_external_code=item["external_code"],
            current_external_name=item["external_name"],
            message=f"Preparing candidates {index}/{total}",
        )
        if tag_vectors and external_vectors and len(external_vectors) == total:
            candidates = rank_semantic_candidates(tags, tag_vectors, external_vectors[index - 1], limit=limit)
        else:
            candidates = deterministic_candidates(conn, item, limit=limit)
        update_ai_mapping_run_item_candidates(conn, int(item["id"]), candidates_json(candidates))
        update_ai_mapping_run_progress(
            conn,
            run_id,
            "embedding",
            processed_items=index,
            total_items=total,
            current_external_code=item["external_code"],
            current_external_name=item["external_name"],
            message=f"Prepared candidates {index}/{total}",
        )
        conn.commit()


def _annotate_output_with_threshold(
    output: dict[str, Any],
    alternatives: tuple[tuple[tuple[str, ...], float | None], ...],
    threshold: float,
    decision: str,
) -> dict[str, Any]:
    """Stamp the model output with the applied threshold and the resulting
    decision so audit logs explain why an item was saved or downgraded.
    """
    output = dict(output)
    output["confidence_threshold"] = threshold
    output["confidence_decision"] = decision
    output["confidences"] = [
        {"snippets": list(snippets), "confidence": confidence}
        for snippets, confidence in alternatives
    ]
    return output


def apply_mapping_for_item(
    conn: sqlite3.Connection,
    run_id: int,
    item: sqlite3.Row,
    client: MappingAIClient,
    chat_model: str,
    save: bool,
    replace_existing: bool,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
) -> int:
    candidates = candidates_from_json(item["candidates_json"])
    if not candidates:
        update_ai_mapping_run_item_result(
            conn,
            int(item["id"]),
            "failed",
            error="No BIMCats candidates found",
        )
        return 0

    output: dict[str, Any] = {}
    saved_rule_ids: list[int] = []
    try:
        system_prompt, user_prompt = mapping_prompt(item, candidates)
        output = client.chat_json(chat_model, system_prompt, user_prompt)
        valid_codes = {
            row["path_code"].upper()
            for row in list_tags(conn)
            if row["status"] == "active"
        }
        candidate_codes = {candidate.path_code for candidate in candidates}
        alternatives = normalize_ai_alternatives(output, valid_codes, candidate_codes)

        # Confidence gating: when saving is requested, every alternative must
        # meet the threshold. A missing confidence is treated as 0 to fail
        # closed and force human review. Review-only runs ignore the gate.
        confidences = [confidence for _, confidence in alternatives]
        below_threshold = save and any(
            (confidence or 0.0) < confidence_threshold for confidence in confidences
        )
        decision = "reviewed" if (not save or below_threshold) else "saved"
        if save and below_threshold:
            output = _annotate_output_with_threshold(
                output, alternatives, confidence_threshold, decision
            )
        else:
            output = _annotate_output_with_threshold(
                output, alternatives, confidence_threshold, decision
            )

        effective_save = save and not below_threshold
        if effective_save and replace_existing:
            # Divergence-aware update: archive only the rules whose snippet
            # set is no longer in the new alternative set, leaving stable
            # rules untouched. This avoids audit churn when an update_all
            # regenerates an identical mapping.
            new_sets = {frozenset(snippets) for snippets, _ in alternatives}
            existing_rules = list_active_mapping_rules_for_external(
                conn,
                item["system_slug"],
                item["external_code"],
            )
            for rule in existing_rules:
                existing_set = frozenset(normalize_snippets(rule["snippets"]))
                if existing_set not in new_sets:
                    archive_mapping_rule(conn, int(rule["id"]))
        if effective_save:
            for snippets, _ in alternatives:
                saved_rule_ids.append(
                    create_mapping_rule_if_missing(
                        conn,
                        MappingInput(
                            system_slug=item["system_slug"],
                            external_code=item["external_code"],
                            external_name=item["external_name"],
                            snippets=snippets,
                            source_note=f"AI Ollama mapping run {run_id}",
                        ),
                    )
                )
            refresh_external_mapping_status(conn, item["system_slug"])
        update_ai_mapping_run_item_result(
            conn,
            int(item["id"]),
            decision,
            output_json=json.dumps(output),
            saved_rule_ids_json=json.dumps(saved_rule_ids),
        )
        return len(saved_rule_ids)
    except Exception as exc:
        # Nearest-match fallback: when validation rejects every alternative or
        # the chat call fails outright, persist the strongest deterministic
        # candidates as a human-reviewable suggestion. The thesis calls for a
        # "nearest match by code overlap" when no exact match is available.
        suggestion = [candidate.as_prompt_dict() for candidate in candidates[:5]]
        annotated = dict(output) if isinstance(output, dict) else {}
        annotated["nearest_match_suggestion"] = suggestion
        update_ai_mapping_run_item_result(
            conn,
            int(item["id"]),
            "failed",
            output_json=json.dumps(annotated),
            saved_rule_ids_json=json.dumps(saved_rule_ids),
            error=str(exc),
        )
        return 0


def process_ai_mapping_run(
    conn: sqlite3.Connection,
    run_id: int,
    client: MappingAIClient | None = None,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
) -> tuple[int, str]:
    run = conn.execute("SELECT * FROM ai_mapping_runs WHERE id = ?", (run_id,)).fetchone()
    if run is None:
        raise ValueError(f"Unknown AI mapping run: {run_id}")
    if run["status"] != "running":
        return run_id, run["message"]

    client = client or OllamaClient(timeout=240)
    if isinstance(client, OllamaClient) and not client.is_available():
        raise OllamaError("Ollama is not available at http://127.0.0.1:11434")

    save = run["action_type"] != "review_all"
    replace_existing = run["action_type"] == "update_all"
    saved_count = 0
    items = list_ai_mapping_run_items(conn, run_id)

    if not items:
        finish_ai_mapping_run(conn, run_id, "completed", "No external classes matched this action.")
        conn.commit()
        return run_id, "No external classes matched this action."

    try:
        update_ai_mapping_run_progress(conn, run_id, "embedding", total_items=len(items), message="Embedding candidates")
        conn.commit()
        prepare_run_candidates(conn, run_id, client, run["embedding_model"])
        if isinstance(client, OllamaClient):
            client.stop_model(run["embedding_model"])

        update_ai_mapping_run_progress(
            conn,
            run_id,
            "mapping",
            processed_items=0,
            total_items=len(items),
            message="Running mapping decisions",
        )
        conn.commit()
        for index, item in enumerate(list_ai_mapping_run_items(conn, run_id), start=1):
            update_ai_mapping_run_progress(
                conn,
                run_id,
                "mapping",
                processed_items=index - 1,
                total_items=len(items),
                current_external_code=item["external_code"],
                current_external_name=item["external_name"],
                message=f"Mapping {index}/{len(items)}",
            )
            conn.commit()
            saved_count += apply_mapping_for_item(
                conn,
                run_id,
                item,
                client,
                run["chat_model"],
                save=save,
                replace_existing=replace_existing,
                confidence_threshold=confidence_threshold,
            )
            update_ai_mapping_run_progress(
                conn,
                run_id,
                "mapping",
                processed_items=index,
                total_items=len(items),
                current_external_code=item["external_code"],
                current_external_name=item["external_name"],
                message=f"Mapped {index}/{len(items)}",
            )
            conn.commit()

        item_word = "class" if len(items) == 1 else "classes"
        if save:
            message = f"Processed {len(items)} {item_word}; saved {saved_count} mapping rules."
        else:
            message = f"Reviewed {len(items)} {item_word}; no mapping rules were changed."
        finish_ai_mapping_run(conn, run_id, "completed", message)
        conn.commit()
        return run_id, message
    except Exception as exc:
        finish_ai_mapping_run(conn, run_id, "failed", str(exc))
        conn.commit()
        raise


def process_ai_mapping_run_path(
    run_id: int,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> None:
    with connect(db_path) as conn:
        process_ai_mapping_run(conn, run_id)


def run_ai_mapping_action(
    conn: sqlite3.Connection,
    action_type: str,
    system_slug: str = "talo-2000",
    limit: int | None = None,
    client: MappingAIClient | None = None,
    embedding_model: str = EMBEDDING_MODEL,
    chat_model: str = CHAT_MODEL,
) -> tuple[int, str]:
    run_id, total = create_ai_mapping_queue(
        conn,
        action_type,
        system_slug=system_slug,
        limit=limit,
        embedding_model=embedding_model,
        chat_model=chat_model,
    )
    conn.commit()
    if total:
        return process_ai_mapping_run(conn, run_id, client=client)
    return run_id, "No external classes matched this action."


def map_external_class(
    conn: sqlite3.Connection,
    external_row: sqlite3.Row,
    run_id: int,
    client: MappingAIClient,
    embedding_model: str = EMBEDDING_MODEL,
    chat_model: str = CHAT_MODEL,
    save: bool = True,
    replace_existing: bool = False,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
) -> int:
    candidates = semantic_candidates(conn, external_row, client, embedding_model=embedding_model)
    item_id = create_ai_mapping_run_item(conn, run_id, external_row)
    update_ai_mapping_run_item_candidates(conn, item_id, candidates_json(candidates))
    item = next(row for row in list_ai_mapping_run_items(conn, run_id) if int(row["id"]) == item_id)
    return apply_mapping_for_item(
        conn,
        run_id,
        item,
        client,
        chat_model,
        save=save,
        replace_existing=replace_existing,
        confidence_threshold=confidence_threshold,
    )
