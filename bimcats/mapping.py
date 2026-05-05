from __future__ import annotations

import re
import sqlite3

from .repository import list_mapping_rules


TOKEN_SPLIT_RE = re.compile(r"[-_]+")


def extract_tokens(full_code: str) -> set[str]:
    return {
        token.strip().upper()
        for token in TOKEN_SPLIT_RE.split(full_code)
        if token.strip() and token.strip().upper() != "XX"
    }


def normalize_snippets(snippets: str | None) -> tuple[str, ...]:
    if not snippets:
        return ()
    return tuple(part.strip().upper() for part in snippets.split(",") if part.strip())


def snippet_in_token(snippet: str, token: str) -> bool:
    """Hierarchical containment: a snippet matches a token when the token is the
    snippet itself or any of its descendants. Path codes concatenate ancestor
    codes (e.g. RO -> RORA, ME -> MEAL -> MEALAS). Because every level in
    BIMCats uses 2-letter local codes, a descendant token always starts with
    the ancestor's full path code on a 2-char boundary.
    """
    if not snippet or not token:
        return False
    if token == snippet:
        return True
    # Only allow prefix-based descent on even (2-char) boundaries to avoid
    # matching across unrelated path codes (e.g. snippet "ME" against token
    # "MEALAS" is valid; snippet "MEA" would not be a real path code at all,
    # but if produced it must still align to a 2-char boundary to match).
    if len(token) > len(snippet) and len(snippet) % 2 == 0 and token.startswith(snippet):
        return True
    return False


def snippet_matches_tokens(snippet: str, tokens: set[str]) -> bool:
    return any(snippet_in_token(snippet, token) for token in tokens)


def rule_matches(full_code: str, snippets: tuple[str, ...]) -> bool:
    tokens = extract_tokens(full_code)
    return all(snippet_matches_tokens(snippet.upper(), tokens) for snippet in snippets)


def matching_external_classes(conn: sqlite3.Connection, full_code: str) -> list[dict[str, str]]:
    matches: list[dict[str, str]] = []
    for rule in list_mapping_rules(conn, active_only=True):
        snippets = normalize_snippets(rule["snippets"])
        if rule_matches(full_code, snippets):
            matches.append(
                {
                    "system": rule["system_name"],
                    "system_slug": rule["system_slug"],
                    "external_code": rule["external_code"],
                    "external_name": rule["external_name"],
                    "snippets": ", ".join(snippets),
                }
            )
    return matches


def cross_links(conn: sqlite3.Connection, rule_id: int) -> list[dict[str, str]]:
    rules = list_mapping_rules(conn, active_only=True)
    origin = next((rule for rule in rules if int(rule["id"]) == rule_id), None)
    if origin is None:
        return []
    origin_snippets = set(normalize_snippets(origin["snippets"]))
    links: list[dict[str, str]] = []
    for rule in rules:
        if int(rule["id"]) == rule_id:
            continue
        snippets = set(normalize_snippets(rule["snippets"]))
        shared = sorted(origin_snippets & snippets)
        if shared:
            links.append(
                {
                    "system": rule["system_name"],
                    "external_code": rule["external_code"],
                    "external_name": rule["external_name"],
                    "shared_snippets": ", ".join(shared),
                }
            )
    return links


def nearest_matches(
    conn: sqlite3.Connection, full_code: str, limit: int = 5
) -> list[dict[str, str | int]]:
    tokens = extract_tokens(full_code)
    ranked: list[dict[str, str | int]] = []
    for rule in list_mapping_rules(conn, active_only=True):
        snippets = set(normalize_snippets(rule["snippets"]))
        # Count snippets that match hierarchically (parent snippet matches a
        # descendant token), aligning overlap with rule_matches semantics.
        overlap = sum(1 for snippet in snippets if snippet_matches_tokens(snippet, tokens))
        if overlap == 0:
            continue
        ranked.append(
                {
                    "system": rule["system_name"],
                    "system_slug": rule["system_slug"],
                    "external_code": rule["external_code"],
                    "external_name": rule["external_name"],
                    "overlap": overlap,
                "snippets": ", ".join(sorted(snippets)),
            }
        )
    return sorted(ranked, key=lambda item: (-int(item["overlap"]), str(item["system"])))[:limit]
