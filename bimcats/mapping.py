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


def rule_matches(full_code: str, snippets: tuple[str, ...]) -> bool:
    tokens = extract_tokens(full_code)
    return all(snippet.upper() in tokens for snippet in snippets)


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
        overlap = len(tokens & snippets)
        if overlap == 0:
            continue
        ranked.append(
            {
                "system": rule["system_name"],
                "external_code": rule["external_code"],
                "external_name": rule["external_name"],
                "overlap": overlap,
                "snippets": ", ".join(sorted(snippets)),
            }
        )
    return sorted(ranked, key=lambda item: (-int(item["overlap"]), str(item["system"])))[:limit]
