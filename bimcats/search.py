from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass

from .mapping import normalize_snippets, snippet_in_token
from .repository import list_mapping_rules, list_tags


WORD_RE = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class TagSuggestion:
    path_code: str
    name: str
    hierarchy: str
    hierarchy_slug: str
    parent_name: str
    score: int
    reason: str


def normalize_word(word: str) -> str:
    word = word.lower().strip()
    if len(word) > 4 and word.endswith("ies"):
        return f"{word[:-3]}y"
    if len(word) > 3 and word.endswith("s"):
        return word[:-1]
    return word


def tokenize(value: str) -> set[str]:
    return {normalize_word(match.group(0)) for match in WORD_RE.finditer(value.lower())}


def context_text(tag: sqlite3.Row) -> str:
    parts = [
        tag["path_code"],
        tag["local_code"],
        tag["name"],
        tag["hierarchy_name"],
        tag["parent_name"] or "",
        tag["parent_path_code"] or "",
    ]
    return " ".join(part for part in parts if part)


def suggest_tags(
    conn: sqlite3.Connection,
    query: str,
    limit: int = 12,
    active_only: bool = True,
) -> list[TagSuggestion]:
    query = query.strip()
    if not query:
        return []
    query_lower = query.lower()
    query_tokens = tokenize(query)
    suggestions: list[TagSuggestion] = []

    for tag in list_tags(conn):
        if active_only and tag["status"] != "active":
            continue

        path_code = tag["path_code"].upper()
        name = tag["name"]
        name_lower = name.lower()
        context = context_text(tag)
        context_lower = context.lower()
        context_tokens = tokenize(context)
        overlap = query_tokens & context_tokens
        score = 0
        reasons: list[str] = []

        if query.upper() == path_code:
            score += 120
            reasons.append("exact code")
        elif path_code.startswith(query.upper()) and len(query) >= 2:
            score += 50
            reasons.append("code prefix")

        if query_lower == name_lower:
            score += 100
            reasons.append("exact name")
        elif query_lower in name_lower:
            score += 55
            reasons.append("name contains query")
        elif query_lower in context_lower:
            score += 25
            reasons.append("context contains query")

        if overlap:
            score += 20 * len(overlap)
            reasons.append(f"{len(overlap)} shared word{'s' if len(overlap) != 1 else ''}")

        if not score:
            continue

        suggestions.append(
            TagSuggestion(
                path_code=path_code,
                name=name,
                hierarchy=tag["hierarchy_name"],
                hierarchy_slug=tag["hierarchy_slug"],
                parent_name=tag["parent_name"] or "",
                score=score,
                reason=", ".join(reasons),
            )
        )

    return sorted(
        suggestions,
        key=lambda item: (-item.score, item.hierarchy, len(item.path_code), item.path_code),
    )[:limit]


def filter_mapping_rules(
    conn: sqlite3.Connection,
    system_slug: str = "",
    search_text: str = "",
    show_archived: bool = False,
) -> list[sqlite3.Row]:
    query = search_text.strip().lower()
    query_tokens = tokenize(query)
    rows: list[sqlite3.Row] = []

    for rule in list_mapping_rules(conn, active_only=False):
        if rule["system_slug"] == "bimcats":
            continue
        if system_slug and rule["system_slug"] != system_slug:
            continue
        if not show_archived and rule["status"] == "archived":
            continue

        snippets = " ".join(normalize_snippets(rule["snippets"]))
        haystack = " ".join(
            [
                rule["system_name"],
                rule["system_slug"],
                rule["external_code"],
                rule["external_name"],
                snippets,
            ]
        ).lower()

        if query:
            haystack_tokens = tokenize(haystack)
            if query not in haystack and not (query_tokens & haystack_tokens):
                continue
        rows.append(rule)

    return rows


def related_rules_for_tag(
    conn: sqlite3.Connection,
    tag_path_code: str,
    system_slug: str = "",
    show_archived: bool = False,
) -> list[sqlite3.Row]:
    """Return rules whose snippet is the tag itself or any ancestor of it,
    so a leaf-tag query also surfaces rules keyed by parent path codes.
    """
    tag_path_code = tag_path_code.upper()
    rows: list[sqlite3.Row] = []
    for rule in filter_mapping_rules(conn, system_slug=system_slug, show_archived=show_archived):
        snippets = set(normalize_snippets(rule["snippets"]))
        if any(snippet_in_token(snippet, tag_path_code) for snippet in snippets):
            rows.append(rule)
    return rows

