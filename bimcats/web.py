from __future__ import annotations

import html
import json
import mimetypes
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote_plus, urlparse

from .ai_mapping import create_ai_mapping_queue, process_ai_mapping_run_path
from .db import DEFAULT_DB_PATH, connect
from .external_import import import_talo2000_english_xml
from .mapping import matching_external_classes, nearest_matches
from .ollama_client import CHAT_MODEL, EMBEDDING_MODEL
from .repository import (
    MappingInput,
    archive_mapping_rule,
    archive_tag,
    create_mapping_rule,
    create_tag,
    ai_mapping_run_progress,
    external_class_summary,
    latest_ai_mapping_run,
    latest_ai_mapping_runs,
    list_classification_systems,
    list_hierarchies,
    list_mapping_rules,
    list_tags,
    update_mapping_rule,
    update_tag,
)
from .search import filter_mapping_rules, suggest_tags
from .seed import seed
from .validation import mapping_warnings, validate_taxonomy

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ASSET_PATHS = {
    "/assets/logo.png": PROJECT_ROOT / "logo.png",
    "/assets/logo-transparent.png": PROJECT_ROOT / "logo-transparent.png",
}


CSS = """
:root {
  color-scheme: light;
  --deep-green: #1F3B2E;
  --warm-yellow: #F2C230;
  --soft-yellow: #FFE08A;
  --off-white: #FAF7F1;
  --charcoal: #1A1A1A;
  --bg: #F8F5EF;
  --panel: #ffffff;
  --text: #1A1A1A;
  --muted: #5F675F;
  --line: #E6DED2;
  --accent: #1F3B2E;
  --accent-yellow: #F2C230;
  --accent-yellow-light: #FFE08A;
  --danger: #d4391e;
  --success-bg: #e8f5ec;
  --success-border: #b5e0c5;
  --success-text: #0d5c2e;
  --notice-bg: #FFF7E3;
  --notice-border: #F2D56C;
  --notice-text: #6C5511;
  --error-bg: #FFF0EE;
  --error-border: #F9B89C;
  --error-text: #912018;
  --code-bg: #EEF4F0;
  --code-border: #C8D8D0;
  --code-text: #1F3B2E;
  --sidebar-width: 188px;
  --radius-sm: 10px;
  --radius-md: 14px;
  --radius-lg: 18px;
  --ring: 0 0 0 3px rgba(31,59,46,0.12);
  --shadow-sm: 0 2px 8px rgba(31,59,46,0.08);
  --shadow-md: 0 10px 26px rgba(31,59,46,0.08);
}
*,
*::before,
*::after { box-sizing: border-box; }
body {
  margin: 0;
  font-family: "Inter", "Avenir Next", "Segoe UI", ui-sans-serif, sans-serif;
  color: var(--text);
  background: var(--bg);
  line-height: 1.45;
}
a {
  color: var(--accent);
  text-decoration: none;
}
a:hover { text-decoration: underline; }

/* Layout */
.layout { display: flex; min-height: 100vh; }
.shell {
  max-width: 1260px;
  margin: 0 auto;
  padding: 30px;
  width: 100%;
}

/* Sidebar */
.sidebar {
  width: var(--sidebar-width);
  background: #6B7177;
  color: white;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  padding: 22px 0;
  position: fixed;
  top: 0;
  left: 0;
  bottom: 0;
  overflow-y: auto;
}
.sidebar-brand {
  padding: 0 18px 20px;
  border-bottom: 1px solid rgba(255,255,255,0.18);
  margin-bottom: 12px;
}
.sidebar-logo {
  display: block;
  width: 100%;
  padding: 4px 8px 2px;
}
.sidebar-logo img {
  display: block;
  width: auto;
  max-width: 100%;
  max-height: 82px;
  margin: 0 auto;
  height: auto;
}
.sidebar-tagline {
  font-size: 11px;
  color: rgba(255,255,255,0.72);
  margin-top: 12px;
  letter-spacing: 0.5px;
  text-transform: uppercase;
  text-align: center;
  font-weight: 600;
}
.sidebar nav { display: flex; gap: 4px; flex-direction: column; padding: 0 12px; }
.sidebar nav a {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 999px;
  color: rgba(255,255,255,0.83);
  font-size: 14px;
  font-weight: 600;
  border: 1px solid transparent;
  transition: background 0.18s ease, color 0.18s ease, border-color 0.18s ease;
}
.sidebar nav a:hover {
  background: rgba(255,255,255,0.16);
  color: #fff;
  border-color: rgba(255,255,255,0.24);
  text-decoration: none;
}
.sidebar nav a.active {
  background: #fff;
  color: var(--deep-green);
  border-color: #fff;
  box-shadow: var(--shadow-sm);
}
.sidebar nav a svg { flex-shrink: 0; opacity: 0.8; }
.sidebar nav a.active svg { opacity: 1; }
.sidebar-footer {
  margin-top: auto;
  padding: 20px 24px 0;
  font-size: 11px;
  color: rgba(255,255,255,0.66);
  letter-spacing: 0.3px;
  text-align: center;
}
.main-content { margin-left: var(--sidebar-width); flex: 1; min-width: 0; }
.mobile-menu-toggle {
  display: none;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  position: sticky;
  top: 10px;
  z-index: 20;
}
.mobile-menu-toggle button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid #C7D7CF;
  background: #fff;
  color: var(--deep-green);
  border-radius: 10px;
  min-height: 40px;
  padding: 0;
  font: inherit;
  font-weight: 700;
  cursor: pointer;
  width: 42px;
}
.mobile-menu-toggle .hamburger {
  display: grid;
  gap: 4px;
  justify-items: center;
  align-items: center;
  width: 16px;
  line-height: 0;
}
.mobile-menu-toggle .hamburger span {
  display: block;
  width: 16px;
  height: 2px;
  border-radius: 2px;
  background: var(--deep-green);
}
.mobile-menu-toggle button:hover { background: #F8FCFA; }

/* Hero */
.hero { padding: 8px 0 20px; }
.hero h1 {
  margin: 0 0 10px;
  font-size: clamp(1.8rem, 2.6vw, 2.4rem);
  line-height: 1.12;
  letter-spacing: -0.03em;
  font-weight: 800;
  color: #14362A;
}
.hero p {
  margin: 0;
  color: var(--muted);
  max-width: 840px;
  font-size: 15px;
  line-height: 1.56;
}

/* Grid */
.grid { display: grid; grid-template-columns: repeat(12, 1fr); gap: 16px; }
.span-4 { grid-column: span 4; }
.span-5 { grid-column: span 5; }
.span-7 { grid-column: span 7; }
.span-12 { grid-column: span 12; }

/* Panel */
.panel {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: var(--radius-md);
  padding: 20px;
  box-shadow: var(--shadow-sm);
}
.panel h2, .panel h3 {
  margin: 0 0 14px;
  line-height: 1.2;
  letter-spacing: -0.02em;
  color: #193D2F;
}
.panel h2 { font-size: 18px; font-weight: 800; }
.panel h3 { font-size: 16px; font-weight: 700; }

/* Utility */
.muted { color: var(--muted); }
.stat {
  font-size: 34px;
  font-weight: 800;
  line-height: 1;
  margin-bottom: 6px;
  color: var(--deep-green);
}

/* Tree view */
.treeview { display: grid; gap: 8px; }
.tree-children {
  margin: 8px 0 0 18px;
  padding-left: 14px;
  border-left: 2px solid #EAD58B;
  display: grid;
  gap: 8px;
}
.tree-node {
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  background: #fff;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.tree-node[open] { border-color: #DCC897; box-shadow: 0 1px 0 rgba(31,59,46,0.03); }
.tree-node > summary {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 44px;
  padding: 9px 12px;
  cursor: pointer;
  list-style: none;
}
.tree-node > summary::-webkit-details-marker { display: none; }
.tree-node > summary::before {
  content: "▸";
  width: 16px;
  color: #6A756D;
  font-size: 12px;
  transition: transform 0.15s;
}
.tree-node[open] > summary::before { transform: rotate(90deg); }
.tree-leaf {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 40px;
  padding: 8px 12px;
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  background: #fff;
}
.node-title {
  min-width: 0;
  overflow-wrap: anywhere;
}
.node-meta {
  color: #6A756D;
  font-size: 12px;
  margin-left: auto;
  white-space: nowrap;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.admin-node-body {
  padding: 0 12px 14px 32px;
  display: grid;
  gap: 10px;
}

/* Forms */
.compact-form {
  display: grid;
  grid-template-columns: 110px minmax(160px, 1fr) minmax(160px, 1.3fr) auto;
  gap: 8px;
  align-items: end;
}
.child-form {
  display: grid;
  grid-template-columns: 110px minmax(160px, 1fr) auto;
  gap: 8px;
  align-items: end;
  padding: 12px;
  border-radius: var(--radius-sm);
  background: #FFFDF8;
  border: 1px dashed #DBCFAF;
}

/* Code badge */
.code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  background: var(--code-bg);
  border: 1px solid var(--code-border);
  color: var(--code-text);
  padding: 2px 7px;
  border-radius: 6px;
  white-space: nowrap;
  font-size: 13px;
  font-weight: 600;
}

/* Status badges */
.badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 10px;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 600;
}
.badge-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}
.badge.active { background: #e6f4ec; color: #0a7c42; }
.badge.active .badge-dot { background: #2ecc71; }
.badge.pending { background: #FFF3DC; color: #946200; }
.badge.pending .badge-dot { background: var(--warm-yellow); }
.badge.archived { background: #f0eeeb; color: #6b7280; }
.badge.archived .badge-dot { background: #9ca3af; }

/* Table */
table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  font-size: 14px;
}
th,
td {
  text-align: left;
  vertical-align: middle;
  padding: 11px 12px;
  border-bottom: 1px solid var(--line);
}
th {
  color: #214638;
  background: #F8F3E8;
  font-weight: 700;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}
tbody tr:hover { background: rgba(242,194,48,0.08); }

/* Form elements */
input, select, textarea {
  width: 100%;
  border: 1.5px solid #DCCDB7;
  border-radius: 10px;
  padding: 9px 11px;
  font: inherit;
  background: white;
  transition: border-color 0.15s, box-shadow 0.15s;
}
input:focus, select:focus, textarea:focus {
  outline: none;
  border-color: var(--deep-green);
  box-shadow: var(--ring);
}
input[type="checkbox"] { width: auto; }
label {
  display: block;
  font-size: 13px;
  color: #1F3B2E;
  margin-bottom: 5px;
  font-weight: 600;
}
.form-grid { display: grid; grid-template-columns: repeat(12, 1fr); gap: 12px; align-items: end; }
.field-2 { grid-column: span 2; }
.field-1 { grid-column: span 1; }
.field-3 { grid-column: span 3; }
.field-4 { grid-column: span 4; }
.field-5 { grid-column: span 5; }
.field-6 { grid-column: span 6; }
.field-8 { grid-column: span 8; }
.field-12 { grid-column: span 12; }

/* Buttons */
.button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: linear-gradient(180deg, #295442 0%, #1F3B2E 100%);
  color: white;
  border-radius: 10px;
  padding: 10px 16px;
  font: inherit;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  min-height: 40px;
  transition: transform 0.12s ease, box-shadow 0.15s ease, filter 0.15s ease;
  box-shadow: 0 4px 12px rgba(31,59,46,0.2);
}
.button:hover {
  filter: brightness(1.03);
  transform: translateY(-1px);
}
.button.primary-yellow {
  background: linear-gradient(180deg, #F5CB45 0%, #F2C230 100%);
  color: var(--charcoal);
  box-shadow: 0 4px 12px rgba(242,194,48,0.34);
}
.button.primary-yellow:hover {
  filter: brightness(1.02);
}
.button.secondary {
  background: white;
  color: var(--deep-green);
  border: 1.5px solid #C7D7CF;
  box-shadow: none;
}
.button.secondary:hover {
  border-color: var(--deep-green);
  background: #F8FCFA;
  box-shadow: none;
  transform: none;
}
.button.danger {
  border-color: var(--danger);
  background: var(--danger);
  color: white;
  box-shadow: 0 4px 12px rgba(212,57,30,0.24);
}
.button.danger:hover {
  filter: brightness(0.95);
}
.actions { display: flex; gap: 8px; flex-wrap: wrap; }
.chip-list { display: flex; flex-wrap: wrap; gap: 6px; }
.chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 9px;
  border-radius: 999px;
  background: #F8FBF9;
  border: 1px solid #CDDDD6;
  color: var(--deep-green);
  font-size: 13px;
}
.card-list { display: grid; gap: 12px; }
.mapping-card {
  border: 1px solid var(--line);
  border-radius: var(--radius-md);
  background: #fff;
  padding: 14px;
  box-shadow: var(--shadow-sm);
}
.mapping-card summary {
  cursor: pointer;
  list-style: none;
}
.mapping-card summary::-webkit-details-marker { display: none; }
.mapping-card-header {
  display: grid;
  grid-template-columns: minmax(140px, 0.8fr) minmax(220px, 1.6fr) auto;
  gap: 12px;
  align-items: center;
}
.mapping-card-body {
  display: grid;
  gap: 12px;
  padding-top: 14px;
  margin-top: 12px;
  border-top: 1px solid var(--line);
}
.suggestion-list { display: grid; gap: 8px; }
.suggestion-row {
  display: grid;
  grid-template-columns: auto 1fr auto;
  gap: 10px;
  align-items: center;
  padding: 9px 10px;
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  background: #FAF9F6;
}
.suggestion-row label { margin: 0; color: inherit; }
.suggestion-row input[type="checkbox"] { width: auto; }
.advanced-box {
  border: 1px dashed #D7CCB1;
  border-radius: var(--radius-sm);
  padding: 10px;
  background: #FFFDF8;
}
.advanced-box summary { cursor: pointer; color: var(--deep-green); font-weight: 700; }

/* Alert banners */
.notice {
  border: 1px solid var(--notice-border);
  background: var(--notice-bg);
  color: var(--notice-text);
  padding: 12px 16px;
  border-radius: 10px;
  margin-bottom: 18px;
  font-size: 14px;
}
.error {
  border: 1px solid var(--error-border);
  background: var(--error-bg);
  color: var(--error-text);
  padding: 12px 16px;
  border-radius: 10px;
  margin-bottom: 18px;
  font-size: 14px;
}
.success {
  border: 1px solid var(--success-border);
  background: var(--success-bg);
  color: var(--success-text);
  padding: 12px 16px;
  border-radius: 10px;
  margin-bottom: 18px;
  font-size: 14px;
}

/* Spacing */
.mt-16 { margin-top: 16px; }
.mt-24 { margin-top: 24px; }

/* Responsive */
@media (max-width: 900px) {
  .sidebar {
    display: flex;
    transform: translateX(-100%);
    transition: transform 0.2s ease;
    z-index: 30;
    width: min(82vw, 320px);
  }
  body.menu-open .sidebar { transform: translateX(0); }
  .main-content { margin-left: 0; }
  .mobile-menu-toggle { display: flex; }
  .grid, .form-grid, .compact-form, .child-form { grid-template-columns: 1fr; }
  .span-4, .span-5, .span-7, .span-12,
  .field-1, .field-2, .field-3, .field-4, .field-5, .field-6, .field-8, .field-12 {
    grid-column: span 1;
  }
  .shell { padding: 18px; }
  .tree-children { margin-left: 8px; padding-left: 10px; }
  .admin-node-body { padding-left: 10px; }
  .node-meta { display: none; }
  .mapping-card-header, .suggestion-row { grid-template-columns: 1fr; }
}
"""


def esc(value: object) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def split_snippets(value: str) -> tuple[str, ...]:
    return tuple(part.strip().upper() for part in value.split(",") if part.strip())


def optional_int(value: str | None) -> int | None:
    if value is None or not value.strip():
        return None
    parsed = int(value)
    if parsed < 1:
        raise ValueError("Limit must be empty or greater than zero")
    return parsed


def selected_snippets_from_form(form: dict[str, str]) -> tuple[str, ...]:
    raw = form.get("snippets", "").strip() or form.get("advanced_snippets", "").strip()
    return split_snippets(raw)


def system_options(systems: list[object], selected: str = "", include_all: bool = False) -> str:
    options = ["<option value=''>All systems</option>"] if include_all else []
    for system in systems:
        is_selected = "selected" if system["slug"] == selected else ""
        options.append(
            f"<option value='{esc(system['slug'])}' {is_selected}>{esc(system['name'])}</option>"
        )
    return "".join(options)


def status_badge(status: str) -> str:
    status_class = "archived" if status == "archived" else "active"
    return (
        f"<span class='badge {status_class}'>"
        "<span class='badge-dot'></span>"
        f"{esc(status)}"
        "</span>"
    )


def snippet_chips(snippets: str | None, tags_by_code: dict[str, object]) -> str:
    chips = []
    for snippet in split_snippets(snippets or ""):
        tag = tags_by_code.get(snippet)
        label = f"{snippet} - {tag['name']}" if tag else f"{snippet} - unknown tag"
        chips.append(f"<span class='chip'><span class='code'>{esc(snippet)}</span>{esc(label.split(' - ', 1)[1])}</span>")
    return f"<div class='chip-list'>{''.join(chips)}</div>" if chips else "<span class='muted'>No snippets</span>"


def render_tag_suggestions(
    suggestions: list[object],
    selected: tuple[str, ...] = (),
    input_name: str = "snippets",
) -> str:
    selected_set = set(selected)
    if not suggestions:
        return "<p class='muted'>No tag suggestions. Try a broader search term.</p>"
    rows = []
    for item in suggestions:
        checked = "checked" if item.path_code in selected_set else ""
        rows.append(
            "<div class='suggestion-row'>"
            f"<input type='checkbox' name='{esc(input_name)}' value='{esc(item.path_code)}' {checked}>"
            "<label>"
            f"<span class='code'>{esc(item.path_code)}</span> "
            f"{esc(item.name)}"
            f"<br><span class='muted'>{esc(item.hierarchy)}"
            f"{' / ' + esc(item.parent_name) if item.parent_name else ''} · {esc(item.reason)}</span>"
            "</label>"
            f"<span class='badge pending'><span class='badge-dot'></span>{esc(item.score)}</span>"
            "</div>"
        )
    return "<div class='suggestion-list'>" + "".join(rows) + "</div>"


def render_tag_picker(
    suggestions: list[object],
    selected: tuple[str, ...],
    tags_by_code: dict[str, object],
) -> str:
    selected_set = set(selected)
    rendered: set[str] = set()
    rows = []

    for snippet in selected:
        tag = tags_by_code.get(snippet)
        if not tag:
            continue
        rendered.add(snippet)
        rows.append(
            "<div class='suggestion-row'>"
            f"<input type='checkbox' name='snippets' value='{esc(snippet)}' checked>"
            "<label>"
            f"<span class='code'>{esc(snippet)}</span> {esc(tag['name'])}"
            f"<br><span class='muted'>{esc(tag['hierarchy_name'])} · currently selected</span>"
            "</label>"
            "<span class='badge active'><span class='badge-dot'></span>selected</span>"
            "</div>"
        )

    for item in suggestions:
        if item.path_code in rendered:
            continue
        checked = "checked" if item.path_code in selected_set else ""
        rows.append(
            "<div class='suggestion-row'>"
            f"<input type='checkbox' name='snippets' value='{esc(item.path_code)}' {checked}>"
            "<label>"
            f"<span class='code'>{esc(item.path_code)}</span> {esc(item.name)}"
            f"<br><span class='muted'>{esc(item.hierarchy)}"
            f"{' / ' + esc(item.parent_name) if item.parent_name else ''} · {esc(item.reason)}</span>"
            "</label>"
            f"<span class='badge pending'><span class='badge-dot'></span>{esc(item.score)}</span>"
            "</div>"
        )

    return "<div class='suggestion-list'>" + "".join(rows) + "</div>" if rows else "<p class='muted'>No suggestions yet.</p>"


def render_mapping_cards(
    rules: list[object],
    systems: list[object],
    tags_by_code: dict[str, object],
    default_suggestions: list[object],
) -> str:
    if not rules:
        return "<p class='muted'>No mapping rules match the current filters.</p>"
    system_selects = {
        system["slug"]: system_options(systems, system["slug"], include_all=False)
        for system in systems
    }
    cards = []
    for rule in rules:
        selected = split_snippets(rule["snippets"] or "")
        card_suggestions = default_suggestions or []
        picker = render_tag_picker(card_suggestions, selected, tags_by_code)
        cards.append(
            "<details class='mapping-card'>"
            "<summary>"
            "<div class='mapping-card-header'>"
            f"<div><strong>{esc(rule['system_name'])}</strong><br><span class='code'>{esc(rule['external_code'])}</span></div>"
            f"<div>{esc(rule['external_name'])}<br>{snippet_chips(rule['snippets'], tags_by_code)}</div>"
            f"<div>{status_badge(rule['status'])}</div>"
            "</div>"
            "</summary>"
            "<div class='mapping-card-body'>"
            f"<form method='post' action='/admin/mappings/update' class='form-grid'>"
            f"<input type='hidden' name='rule_id' value='{esc(rule['id'])}'>"
            f"<div class='field-3'><label>System</label><select name='system_slug' disabled>{system_selects.get(rule['system_slug'], '')}</select></div>"
            f"<div class='field-3'><label>External code</label><input name='external_code' value='{esc(rule['external_code'])}' required></div>"
            f"<div class='field-4'><label>External name</label><input name='external_name' value='{esc(rule['external_name'])}' required></div>"
            f"<div class='field-2'><label>Status</label><select name='status'><option value='active' {'selected' if rule['status'] == 'active' else ''}>active</option><option value='archived' {'selected' if rule['status'] == 'archived' else ''}>archived</option></select></div>"
            f"<div class='field-12'><label>BIMCats tag picker</label>{picker}</div>"
            "<div class='field-12'><details class='advanced-box'><summary>Advanced raw snippets</summary>"
            f"<div class='mt-16'><label>Comma-separated snippets</label><input name='advanced_snippets' value='{esc(rule['snippets'])}'></div>"
            "</details></div>"
            "<div class='field-12'><button class='button secondary' type='submit'>Save mapping</button></div>"
            "</form>"
            "<div class='actions'>"
            f"<form method='post' action='/admin/mappings/archive'><input type='hidden' name='rule_id' value='{esc(rule['id'])}'><button class='button danger' type='submit'>Archive</button></form>"
            "</div>"
            "</div>"
            "</details>"
        )
    return "<div class='card-list'>" + "".join(cards) + "</div>"


def render_mapping_rows(rules: list[object], tags_by_code: dict[str, object]) -> str:
    if not rules:
        return "<tr><td colspan='4' class='muted'>No mapping rules found.</td></tr>"
    return "".join(
        "<tr>"
        f"<td>{esc(row['system_name'])}</td>"
        f"<td><span class='code'>{esc(row['external_code'])}</span></td>"
        f"<td>{esc(row['external_name'])}</td>"
        f"<td>{snippet_chips(row['snippets'], tags_by_code)}</td>"
        "</tr>"
        for row in rules
    )


def render_external_class_summary(rows: list[object]) -> str:
    if not rows:
        return "<p class='muted'>No external classes imported yet.</p>"
    body = "".join(
        "<tr>"
        f"<td>{esc(row['system_name'])}</td>"
        f"<td>{esc(row['total'] or 0)}</td>"
        f"<td>{esc(row['mapped'] or 0)}</td>"
        f"<td>{esc(row['unmapped'] or 0)}</td>"
        "</tr>"
        for row in rows
    )
    return (
        "<table><thead><tr><th>System</th><th>Imported</th><th>Mapped</th>"
        f"<th>Unmapped</th></tr></thead><tbody>{body}</tbody></table>"
    )


def render_ai_run_summary(rows: list[object]) -> str:
    if not rows:
        return "<p class='muted'>No AI mapping runs yet.</p>"
    body = "".join(
        "<tr>"
        f"<td><span class='code'>{esc(row['id'])}</span></td>"
        f"<td>{esc(row['action_type'])}</td>"
        f"<td>{status_badge(row['status'])}</td>"
        f"<td>{esc(row['item_count'] or 0)}</td>"
        f"<td>{esc(row['saved_count'] or 0)}</td>"
        f"<td>{esc(row['failed_count'] or 0)}</td>"
        f"<td>{esc(row['message'])}<br><span class='muted'>{esc(row['started_at'])}"
        f"{' - ' + esc(row['finished_at']) if row['finished_at'] else ''}</span></td>"
        "</tr>"
        for row in rows
    )
    return (
        "<table><thead><tr><th>Run</th><th>Action</th><th>Status</th><th>Items</th>"
        f"<th>Saved</th><th>Failed</th><th>Message</th></tr></thead><tbody>{body}</tbody></table>"
    )


def _suggestion_text(item: dict[str, object]) -> str:
    """Render the nearest-match suggestion stored on a failed run item, if any.
    Returns a comma-separated list of candidate path codes, or an empty string.
    """
    raw = item.get("output_json") or ""
    if not raw:
        return ""
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return ""
    suggestions = parsed.get("nearest_match_suggestion") if isinstance(parsed, dict) else None
    if not isinstance(suggestions, list):
        return ""
    codes = [str(entry.get("path_code", "")) for entry in suggestions if isinstance(entry, dict)]
    return ", ".join(code for code in codes if code)


def render_ai_progress_snapshot(progress: dict[str, object] | None) -> str:
    if not progress:
        return "<p class='muted'>No AI mapping run has been started yet.</p>"
    run = progress["run"]
    counts = progress["counts"]
    latest_items = progress["latest_items"]
    total = int(run["total_items"] or 0)
    processed = int(run["processed_items"] or 0)
    candidates_ready = int(progress["candidates_ready"] or 0)
    latest_rows = "".join(
        "<tr>"
        f"<td><span class='code'>{esc(item['external_code'])}</span></td>"
        f"<td>{esc(item['external_name'])}</td>"
        f"<td>{esc(item['status'])}</td>"
        f"<td>{esc(item['error'])}</td>"
        f"<td><span class='code'>{esc(_suggestion_text(item))}</span></td>"
        "</tr>"
        for item in latest_items
    ) or "<tr><td colspan='5' class='muted'>No item updates yet.</td></tr>"
    return f"""
      <div class="grid">
        <div class="span-4"><div class="stat">{esc(processed)}/{esc(total)}</div><div class="muted">Processed in current phase</div></div>
        <div class="span-4"><div class="stat">{esc(candidates_ready)}</div><div class="muted">Candidate sets ready</div></div>
        <div class="span-4"><div class="stat">{esc(counts.get('saved', 0) + counts.get('reviewed', 0))}</div><div class="muted">Mapped or reviewed</div></div>
        <div class="span-12">
          <p><strong>Run {esc(run['id'])}</strong> · {esc(run['action_type'])} · {status_badge(run['status'])} · phase: <span class="code">{esc(run['phase'])}</span></p>
          <p class="muted">{esc(run['message'])}</p>
          <p>Current: <span class="code">{esc(run['current_external_code'])}</span> {esc(run['current_external_name'])}</p>
        </div>
        <div class="span-12">
          <table><thead><tr><th>Code</th><th>Name</th><th>Status</th><th>Error</th><th>Suggestion</th></tr></thead><tbody>{latest_rows}</tbody></table>
        </div>
      </div>
    """


def grouped_tree(tags: list[object]) -> dict[int | None, list[object]]:
    groups: dict[int | None, list[object]] = {}
    for tag in tags:
        groups.setdefault(tag["parent_id"], []).append(tag)
    return groups


def active_tags(tags: list[object]) -> list[object]:
    return [tag for tag in tags if tag["status"] == "active"]


def render_browse_tree(groups: dict[int | None, list[object]], parent_id: int | None = None) -> str:
    rows = groups.get(parent_id, [])
    if not rows:
        return ""
    items: list[str] = []
    for row in rows:
        children = render_browse_tree(groups, int(row["id"]))
        label = (
            f"<span class='code'>{esc(row['path_code'])}</span>"
            f"<span class='node-title'>{esc(row['name'])}</span>"
        )
        if children:
            items.append(
                "<details class='tree-node'>"
                f"<summary>{label}<span class='node-meta'>children</span></summary>"
                f"<div class='tree-children'>{children}</div>"
                "</details>"
            )
        else:
            items.append(f"<div class='tree-leaf'>{label}</div>")
    return "".join(items)


def render_admin_tree(
    groups: dict[int | None, list[object]],
    hierarchy_slug: str,
    parent_id: int | None = None,
) -> str:
    rows = groups.get(parent_id, [])
    if not rows:
        return ""
    items: list[str] = []
    for row in rows:
        children = render_admin_tree(groups, hierarchy_slug, int(row["id"]))
        children_html = f"<div class='tree-children'>{children}</div>" if children else ""
        items.append(
            "<details class='tree-node'>"
            "<summary>"
            f"<span class='code'>{esc(row['path_code'])}</span>"
            f"<span class='node-title'>{esc(row['name'])}</span>"
            "<span class='node-meta'>edit</span>"
            "</summary>"
            "<div class='admin-node-body'>"
            f"<form method='post' action='/admin/tags/update' class='compact-form'>"
            f"<input type='hidden' name='tag_id' value='{esc(row['id'])}'>"
            "<input type='hidden' name='status' value='active'>"
            f"<div><label>Local code</label><input name='local_code' value='{esc(row['local_code'])}' required></div>"
            f"<div><label>Name</label><input name='name' value='{esc(row['name'])}' required></div>"
            f"<div><label>Description</label><input name='description' value='{esc(row['description'])}'></div>"
            "<button class='button secondary' type='submit'>Save</button>"
            "</form>"
            "<div class='actions'>"
            f"<form method='post' action='/admin/tags/archive'><input type='hidden' name='tag_id' value='{esc(row['id'])}'><button class='button danger' type='submit'>Archive</button></form>"
            "</div>"
            f"<form method='post' action='/admin/tags/create' class='child-form'>"
            f"<input type='hidden' name='hierarchy_slug' value='{esc(hierarchy_slug)}'>"
            f"<input type='hidden' name='parent_path_code' value='{esc(row['path_code'])}'>"
            f"<div><label>Child code</label><input name='local_code' required></div>"
            f"<div><label>Child name</label><input name='name' required></div>"
            "<input type='hidden' name='description' value=''>"
            "<button class='button' type='submit'>Add child</button>"
            "</form>"
            f"{children_html}"
            "</div>"
            "</details>"
        )
    return "".join(items)


def render_root_add_form(hierarchy: object) -> str:
    return (
        f"<form method='post' action='/admin/tags/create' class='child-form'>"
        f"<input type='hidden' name='hierarchy_slug' value='{esc(hierarchy['slug'])}'>"
        "<input type='hidden' name='parent_path_code' value=''>"
        f"<div><label>Root code</label><input name='local_code' required></div>"
        f"<div><label>Root tag in {esc(hierarchy['name'])}</label><input name='name' required></div>"
        "<input type='hidden' name='description' value=''>"
        "<button class='button' type='submit'>Add root tag</button>"
        "</form>"
    )


def _nav_icons():
    folder = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>'
    link = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>'
    tags = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z"/><line x1="7" y1="7" x2="7.01" y2="7"/></svg>'
    map = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="1 6 1 22 8 18 16 22 23 18 23 2 16 6 8 2 1 6"/><line x1="8" y1="2" x2="8" y2="18"/><line x1="16" y1="6" x2="16" y2="22"/></svg>'
    api = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>'
    return {"browse": folder, "mappings": link, "admintags": tags, "adminmappings": map, "apisummary": api}


def nav_link(href: str, label: str, icon: str, active_nav: str, nav_key: str) -> str:
    active_class = " active" if active_nav == nav_key else ""
    return f"<a class='{active_class.strip()}' href='{href}'><span>{icon}</span>{label}</a>"


def page(title: str, body: str, message: str = "", error: str = "", active_nav: str = "") -> bytes:
    message_html = f"<div class='success'>{esc(message)}</div>" if message else ""
    error_html = f"<div class='error'>{esc(error)}</div>" if error else ""
    icons = _nav_icons()
    html_doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(title)} - BIMCats</title>
  <style>{CSS}</style>
</head>
<body>
  <div class="layout">
    <aside class="sidebar">
      <div class="sidebar-brand">
        <div class="sidebar-logo">
          <img src="/assets/logo-transparent.png" alt="BIMCats logo">
        </div>
        <div class="sidebar-tagline">Classification Workbench</div>
      </div>
      <nav id="sidebar-nav">
        {nav_link("/", "Browse", icons["browse"], active_nav, "browse")}
        {nav_link("/mappings", "Mappings", icons["mappings"], active_nav, "mappings")}
        {nav_link("/admin/tags", "Taxonomy", icons["admintags"], active_nav, "admintags")}
        {nav_link("/admin/mappings", "Map Rules", icons["adminmappings"], active_nav, "adminmappings")}
        {nav_link("/api/summary", "API", icons["apisummary"], active_nav, "apisummary")}
      </nav>
      <div class="sidebar-footer">Local &middot; Self-hosted</div>
    </aside>
    <div class="main-content">
      <main class="shell">
        <div class="mobile-menu-toggle">
          <button type="button" id="menu-toggle" aria-controls="sidebar-nav" aria-expanded="false" aria-label="Toggle navigation menu">
            <span class="hamburger" aria-hidden="true"><span></span><span></span><span></span></span>
          </button>
        </div>
        {message_html}
        {error_html}
        {body}
      </main>
    </div>
  </div>
  <script>
    (function () {{
      const btn = document.getElementById("menu-toggle");
      if (!btn) return;
      btn.addEventListener("click", function () {{
        const open = document.body.classList.toggle("menu-open");
        btn.setAttribute("aria-expanded", open ? "true" : "false");
      }});
      document.addEventListener("click", function (event) {{
        if (!document.body.classList.contains("menu-open")) return;
        const sidebar = document.querySelector(".sidebar");
        if (!sidebar) return;
        if (sidebar.contains(event.target) || btn.contains(event.target)) return;
        document.body.classList.remove("menu-open");
        btn.setAttribute("aria-expanded", "false");
      }});
    }})();
  </script>
</body>
</html>"""
    return html_doc.encode("utf-8")


class BIMCatsHandler(BaseHTTPRequestHandler):
    db_path: Path = DEFAULT_DB_PATH

    def log_message(self, format: str, *args: object) -> None:
        print(f"{self.address_string()} - {format % args}")

    def send_html(self, body: bytes, status: HTTPStatus = HTTPStatus.OK) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, payload: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_binary(self, body: bytes, content_type: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def redirect(self, target: str) -> None:
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", target)
        self.end_headers()

    def start_ai_mapping_thread(self, run_id: int) -> None:
        thread = threading.Thread(
            target=process_ai_mapping_run_path,
            args=(run_id, self.db_path),
            daemon=True,
            name=f"ai-mapping-run-{run_id}",
        )
        thread.start()

    def read_form(self) -> dict[str, str]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8")
        parsed = parse_qs(raw)
        return {
            key: ",".join(values) if key == "snippets" else values[0]
            for key, values in parsed.items()
        }

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        query = {key: values[0] for key, values in parse_qs(parsed.query).items()}
        try:
            # Serve explicitly mapped static assets used by the app shell.
            if parsed.path in ASSET_PATHS:
                self.render_asset(parsed.path)
            elif parsed.path == "/":
                self.render_home(query)
            elif parsed.path == "/mappings":
                self.render_mappings(query)
            elif parsed.path == "/admin/tags":
                self.render_admin_tags(query)
            elif parsed.path == "/admin/mappings":
                self.render_admin_mappings(query)
            elif parsed.path == "/api/ai-mapping-progress":
                self.render_ai_mapping_progress(query)
            elif parsed.path == "/api/summary":
                self.render_api_summary()
            else:
                self.send_html(page("Not Found", "<h1>Not found</h1>"), HTTPStatus.NOT_FOUND)
        except Exception as exc:
            self.send_html(page("Error", "<h1>Request failed</h1>", error=str(exc)), HTTPStatus.INTERNAL_SERVER_ERROR)

    def render_asset(self, request_path: str) -> None:
        asset_path = ASSET_PATHS.get(request_path)
        if not asset_path or not asset_path.exists():
            self.send_binary(b"Not found", "text/plain; charset=utf-8", HTTPStatus.NOT_FOUND)
            return
        content_type, _ = mimetypes.guess_type(asset_path.name)
        self.send_binary(asset_path.read_bytes(), content_type or "application/octet-stream")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        form = self.read_form()
        try:
            with connect(self.db_path) as conn:
                if parsed.path == "/admin/tags/create":
                    create_tag(
                        conn,
                        form["hierarchy_slug"],
                        form["local_code"].strip().upper(),
                        form["name"].strip(),
                        parent_path_code=form.get("parent_path_code") or None,
                        description=form.get("description", "").strip(),
                    )
                    conn.commit()
                    self.redirect("/admin/tags?message=Tag+created")
                elif parsed.path == "/admin/tags/update":
                    update_tag(
                        conn,
                        int(form["tag_id"]),
                        form["local_code"].strip().upper(),
                        form["name"].strip(),
                        form.get("description", "").strip(),
                        form["status"],
                    )
                    conn.commit()
                    self.redirect("/admin/tags?message=Tag+updated")
                elif parsed.path == "/admin/tags/archive":
                    archive_tag(conn, int(form["tag_id"]))
                    conn.commit()
                    self.redirect("/admin/tags?message=Tag+archived")
                elif parsed.path == "/admin/mappings/create":
                    create_mapping_rule(
                        conn,
                        MappingInput(
                            form["system_slug"],
                            form["external_code"].strip(),
                            form["external_name"].strip(),
                            selected_snippets_from_form(form),
                        ),
                    )
                    conn.commit()
                    self.redirect("/admin/mappings?message=Mapping+created")
                elif parsed.path == "/admin/mappings/update":
                    update_mapping_rule(
                        conn,
                        int(form["rule_id"]),
                        form["external_code"].strip(),
                        form["external_name"].strip(),
                        selected_snippets_from_form(form),
                        form["status"],
                    )
                    conn.commit()
                    self.redirect("/admin/mappings?message=Mapping+updated")
                elif parsed.path == "/admin/mappings/archive":
                    archive_mapping_rule(conn, int(form["rule_id"]))
                    conn.commit()
                    self.redirect("/admin/mappings?message=Mapping+archived")
                elif parsed.path == "/admin/mappings/import-talo":
                    imported = import_talo2000_english_xml(conn)
                    conn.commit()
                    self.redirect(
                        f"/admin/mappings?message={quote_plus(f'Imported {imported} Talo 2000 classes')}"
                    )
                elif parsed.path == "/admin/mappings/ai/map-unmapped":
                    import_talo2000_english_xml(conn)
                    run_id, total = create_ai_mapping_queue(
                        conn,
                        "map_unmapped",
                        system_slug=form.get("system_slug", "talo-2000"),
                        limit=optional_int(form.get("limit")) or 5,
                    )
                    conn.commit()
                    self.start_ai_mapping_thread(run_id)
                    self.redirect(
                        f"/admin/mappings?message={quote_plus(f'Started AI mapping run {run_id} for {total} classes')}"
                    )
                elif parsed.path == "/admin/mappings/ai/review-all":
                    import_talo2000_english_xml(conn)
                    run_id, total = create_ai_mapping_queue(
                        conn,
                        "review_all",
                        system_slug=form.get("system_slug", "talo-2000"),
                        limit=optional_int(form.get("limit")) or 5,
                    )
                    conn.commit()
                    self.start_ai_mapping_thread(run_id)
                    self.redirect(
                        f"/admin/mappings?message={quote_plus(f'Started AI review run {run_id} for {total} classes')}"
                    )
                elif parsed.path == "/admin/mappings/ai/update-all":
                    import_talo2000_english_xml(conn)
                    run_id, total = create_ai_mapping_queue(
                        conn,
                        "update_all",
                        system_slug=form.get("system_slug", "talo-2000"),
                        limit=optional_int(form.get("limit")) or 5,
                    )
                    conn.commit()
                    self.start_ai_mapping_thread(run_id)
                    self.redirect(
                        f"/admin/mappings?message={quote_plus(f'Started AI update run {run_id} for {total} classes')}"
                    )
                else:
                    self.send_html(page("Not Found", "<h1>Not found</h1>", active_nav=""), HTTPStatus.NOT_FOUND)
        except Exception as exc:
            target = "/admin/mappings" if "mapping" in parsed.path else "/admin/tags"
            self.redirect(f"{target}?error={quote_plus(str(exc))}")

    def render_home(self, query: dict[str, str]) -> None:
        with connect(self.db_path) as conn:
            seed(conn)
            hierarchies = list_hierarchies(conn)
            tags = list_tags(conn)
            rules = list_mapping_rules(conn, active_only=True)
            warnings = validate_taxonomy(conn)

        cards = f"""
        <section class="hero">
          <h1>Global classification library</h1>
          <p>Browse the BIMCats seed taxonomy from the thesis prototype. Codes are generated from hierarchy paths, not isolated labels.</p>
        </section>
        <section class="grid">
          <div class="panel span-4"><div class="stat">{len(hierarchies)}</div><div class="muted">Hierarchies</div></div>
          <div class="panel span-4"><div class="stat">{len(tags)}</div><div class="muted">Tags</div></div>
          <div class="panel span-4"><div class="stat">{len(rules)}</div><div class="muted">Active mapping rules</div></div>
        </section>
        """
        warning_html = ""
        if warnings:
            warning_html = "<div class='notice'><strong>Validation warnings</strong><br>" + "<br>".join(esc(w) for w in warnings) + "</div>"

        sections = []
        for hierarchy in hierarchies:
            h_tags = active_tags([tag for tag in tags if tag["hierarchy_slug"] == hierarchy["slug"]])
            tree = render_browse_tree(grouped_tree(h_tags))
            sections.append(
                "<section class='panel span-12'>"
                f"<h2>{esc(hierarchy['name'])}</h2>"
                f"<div class='treeview'>{tree or '<p class=\"muted\">No active tags.</p>'}</div>"
                "</section>"
            )
        body = cards + warning_html + "<section class='grid mt-24'>" + "".join(sections) + "</section>"
        self.send_html(page("Browse", body, query.get("message", ""), query.get("error", ""), active_nav="browse"))

    def render_mappings(self, query: dict[str, str]) -> None:
        search_text = query.get("q", "").strip()
        system_slug = query.get("system", "").strip()
        full_code = query.get("code", "").strip()
        with connect(self.db_path) as conn:
            seed(conn)
            systems = [row for row in list_classification_systems(conn) if row["slug"] != "bimcats"]
            tags = active_tags(list_tags(conn))
            tags_by_code = {row["path_code"]: row for row in tags}
            tag_suggestions = suggest_tags(conn, search_text, limit=12) if search_text else []
            rules = filter_mapping_rules(conn, system_slug=system_slug, search_text=search_text)
            code_matches = matching_external_classes(conn, full_code) if full_code else []
            nearest = nearest_matches(conn, full_code) if full_code else []

        if system_slug:
            code_matches = [row for row in code_matches if row["system_slug"] == system_slug]
            nearest = [row for row in nearest if row["system_slug"] == system_slug]

        suggestion_rows = []
        for item in tag_suggestions:
            related = [
                rule for rule in rules
                if item.path_code in split_snippets(rule["snippets"] or "")
            ]
            suggestion_rows.append(
                "<tr>"
                f"<td><span class='code'>{esc(item.path_code)}</span></td>"
                f"<td>{esc(item.name)}<br><span class='muted'>{esc(item.hierarchy)}"
                f"{' / ' + esc(item.parent_name) if item.parent_name else ''}</span></td>"
                f"<td>{esc(item.reason)}</td>"
                f"<td>{len(related)}</td>"
                "</tr>"
            )
        suggestions_html = "".join(suggestion_rows) or "<tr><td colspan='4' class='muted'>Search plain English to see BIMCats tag suggestions.</td></tr>"

        rows = "".join(
            f"<tr><td>{esc(row['system'])}</td><td><span class='code'>{esc(row['external_code'])}</span></td>"
            f"<td>{esc(row['external_name'])}</td><td>{esc(row['snippets'])}</td></tr>"
            for row in code_matches
        ) or "<tr><td colspan='4' class='muted'>No exact containment matches. Use Advanced to test a full BIMCats code.</td></tr>"
        nearest_rows = "".join(
            f"<tr><td>{esc(row['system'])}</td><td><span class='code'>{esc(row['external_code'])}</span></td>"
            f"<td>{esc(row['external_name'])}</td><td>{esc(row['overlap'])}</td><td>{esc(row['snippets'])}</td></tr>"
            for row in nearest
        ) or "<tr><td colspan='5' class='muted'>No nearest matches.</td></tr>"
        all_rows = render_mapping_rows(rules, tags_by_code)
        body = f"""
        <section class="hero">
          <h1>Mapping search</h1>
          <p>Search with plain English to find BIMCats tags and related external classification mappings.</p>
        </section>
        <section class="panel">
          <form method="get" action="/mappings" class="form-grid">
            <div class="field-8">
              <label for="q">Search tags and mappings</label>
              <input id="q" name="q" value="{esc(search_text)}" placeholder="roofs, roof accessories, mineral wool insulation">
            </div>
            <div class="field-3">
              <label for="system">Target system</label>
              <select id="system" name="system">{system_options(systems, system_slug, include_all=True)}</select>
            </div>
            <div class="field-1"><button class="button" type="submit">Search</button></div>
            <div class="field-12">
              <details class="advanced-box">
                <summary>Advanced BIMCats code check</summary>
                <div class="form-grid mt-16">
                  <div class="field-8">
                    <label for="code">BIMCats full code</label>
                    <input id="code" name="code" value="{esc(full_code)}" placeholder="S-ROSC-ENIT-INMW">
                  </div>
                  <div class="field-4"><button class="button secondary" type="submit">Check code</button></div>
                </div>
              </details>
            </div>
          </form>
        </section>
        <section class="grid mt-16">
          <div class="panel span-12">
            <h2>BIMCats tag suggestions</h2>
            <table><thead><tr><th>Tag</th><th>Name</th><th>Why</th><th>Related rules</th></tr></thead><tbody>{suggestions_html}</tbody></table>
          </div>
          <div class="panel span-12">
            <h2>Matching mapping rules</h2>
            <table><thead><tr><th>System</th><th>Code</th><th>Name</th><th>BIMCats tags</th></tr></thead><tbody>{all_rows}</tbody></table>
          </div>
          <div class="panel span-12">
            <h2>Exact containment matches</h2>
            <table><thead><tr><th>System</th><th>Code</th><th>Name</th><th>Required snippets</th></tr></thead><tbody>{rows}</tbody></table>
          </div>
          <div class="panel span-12">
            <h2>Nearest code matches</h2>
            <table><thead><tr><th>System</th><th>Code</th><th>Name</th><th>Overlap</th><th>Snippets</th></tr></thead><tbody>{nearest_rows}</tbody></table>
          </div>
        </section>
        """
        self.send_html(page("Mappings", body, query.get("message", ""), query.get("error", ""), active_nav="mappings"))

    def render_admin_tags(self, query: dict[str, str]) -> None:
        with connect(self.db_path) as conn:
            seed(conn)
            hierarchies = list_hierarchies(conn)
            tags = list_tags(conn)
            warnings = validate_taxonomy(conn)

        warning_html = ""
        if warnings:
            warning_html = "<div class='notice'>" + "<br>".join(esc(w) for w in warnings) + "</div>"

        sections = []
        for hierarchy in hierarchies:
            h_tags = active_tags([tag for tag in tags if tag["hierarchy_slug"] == hierarchy["slug"]])
            tree = render_admin_tree(grouped_tree(h_tags), hierarchy["slug"])
            sections.append(
                "<section class='panel span-12'>"
                f"<h2>{esc(hierarchy['name'])}</h2>"
                f"{render_root_add_form(hierarchy)}"
                f"<div class='treeview' style='margin-top:12px'>{tree or '<p class=\"muted\">No active tags.</p>'}</div>"
                "</section>"
            )

        body = f"""
        <section class="hero">
          <h1>Admin taxonomy</h1>
          <p>Expand a node to edit it directly or add a child under it. Archived tags are hidden from this tree.</p>
        </section>
        {warning_html}
        <section class="grid">{''.join(sections)}</section>
        """
        self.send_html(page("Admin Taxonomy", body, query.get("message", ""), query.get("error", ""), active_nav="admintags"))

    def render_admin_mappings(self, query: dict[str, str]) -> None:
        search_text = query.get("q", "").strip()
        system_slug = query.get("system", "").strip()
        show_archived = query.get("show_archived", "") == "1"
        with connect(self.db_path) as conn:
            seed(conn)
            systems = [row for row in list_classification_systems(conn) if row["slug"] != "bimcats"]
            tags = active_tags(list_tags(conn))
            tags_by_code = {row["path_code"]: row for row in tags}
            rules = filter_mapping_rules(
                conn,
                system_slug=system_slug,
                search_text=search_text,
                show_archived=show_archived,
            )
            suggestions = suggest_tags(conn, search_text, limit=10) if search_text else []
            warnings = mapping_warnings(conn)
            external_summary = external_class_summary(conn)
            ai_runs = latest_ai_mapping_runs(conn)
            latest_run = latest_ai_mapping_run(conn)
            ai_progress = ai_mapping_run_progress(conn, int(latest_run["id"])) if latest_run else None

        warning_html = ""
        if warnings:
            warning_html = "<div class='notice'>" + "<br>".join(esc(w) for w in warnings) + "</div>"
        show_archived_checked = "checked" if show_archived else ""
        create_picker = render_tag_picker(suggestions, (), tags_by_code)
        mapping_cards = render_mapping_cards(rules, systems, tags_by_code, suggestions)
        ai_system_options = system_options(systems, system_slug or "talo-2000")
        body = f"""
        <section class="hero">
          <h1>Admin mappings</h1>
          <p>Maintain external classification mappings by selecting readable BIMCats tags. Selected tags are saved as AND-rule snippets.</p>
        </section>
        {warning_html}
        <section class="panel">
          <h2>Find and create mapping rules</h2>
          <form method="get" action="/admin/mappings" class="form-grid">
            <div class="field-6"><label for="admin-q">Search mappings and tag suggestions</label><input id="admin-q" name="q" value="{esc(search_text)}" placeholder="roof accessories, mineral wool, external walls"></div>
            <div class="field-3"><label for="admin-system">Target system</label><select id="admin-system" name="system">{system_options(systems, system_slug, include_all=True)}</select></div>
            <div class="field-2"><label><input type="checkbox" name="show_archived" value="1" {show_archived_checked}> Show archived</label></div>
            <div class="field-1"><button class="button" type="submit">Filter</button></div>
          </form>
        </section>
        <section class="panel mt-16">
          <h2>Add mapping rule</h2>
          <form method="post" action="/admin/mappings/create" class="form-grid">
            <div class="field-3"><label>System</label><select name="system_slug">{system_options(systems)}</select></div>
            <div class="field-3"><label>External code</label><input name="external_code" required></div>
            <div class="field-4"><label>External name</label><input name="external_name" required></div>
            <div class="field-12"><label>BIMCats tag suggestions</label>{create_picker}</div>
            <div class="field-12"><details class="advanced-box"><summary>Advanced raw snippets</summary><div class="mt-16"><label>Comma-separated snippets</label><input name="advanced_snippets" placeholder="ROSC,ENIT"></div></details></div>
            <div class="field-12"><button class="button" type="submit">Create mapping</button></div>
          </form>
        </section>
        <section class="panel mt-16">
          <h2>Mapping rules</h2>
          {mapping_cards}
        </section>
        <section class="panel mt-16">
          <h2>Local AI mapping</h2>
          <p class="muted">Runs use local Ollama only. AI results are auto-saved only after every returned snippet is validated against active BIMCats tags.</p>
          <div class="grid">
            <div class="span-12">{render_external_class_summary(external_summary)}</div>
            <div class="span-12">
              <form method="post" action="/admin/mappings/import-talo" class="actions" onsubmit="this.querySelector('button').textContent='Importing...';">
                <button class="button secondary" type="submit">Import Talo 2000 XML</button>
              </form>
            </div>
            <div class="span-12">
              <form method="post" action="/admin/mappings/ai/map-unmapped" class="form-grid" onsubmit="this.querySelector('button').textContent='Running...';">
                <input type="hidden" name="system_slug" value="talo-2000">
                <div class="field-4"><label>AI action</label><input value="Map unmapped classifications" disabled></div>
                <div class="field-3"><label>Embedding model</label><input value="{esc(EMBEDDING_MODEL)}" disabled></div>
                <div class="field-3"><label>Class limit</label><input name="limit" value="5"></div>
                <div class="field-2"><button class="button" type="submit">Start</button></div>
              </form>
            </div>
            <div class="span-12">
              <form method="post" action="/admin/mappings/ai/review-all" class="form-grid" onsubmit="this.querySelector('button').textContent='Running...';">
                <input type="hidden" name="system_slug" value="talo-2000">
                <div class="field-4"><label>AI action</label><input value="Review all mappings" disabled></div>
                <div class="field-3"><label>Chat model</label><input value="{esc(CHAT_MODEL)}" disabled></div>
                <div class="field-3"><label>Class limit</label><input name="limit" value="5"></div>
                <div class="field-2"><button class="button secondary" type="submit">Review</button></div>
              </form>
            </div>
            <div class="span-12">
              <form method="post" action="/admin/mappings/ai/update-all" class="form-grid" onsubmit="this.querySelector('button').textContent='Running...';">
                <input type="hidden" name="system_slug" value="talo-2000">
                <div class="field-4"><label>AI action</label><input value="Update all mappings" disabled></div>
                <div class="field-3"><label>Target system</label><select disabled>{ai_system_options}</select></div>
                <div class="field-3"><label>Class limit</label><input name="limit" value="5"></div>
                <div class="field-2"><button class="button danger" type="submit">Update</button></div>
              </form>
            </div>
          </div>
        </section>
        <section class="panel mt-16">
          <h2>AI mapping progress</h2>
          <div id="ai-progress" data-run-id="{esc(ai_progress['run']['id']) if ai_progress else ''}">
            {render_ai_progress_snapshot(ai_progress)}
          </div>
        </section>
        <section class="panel mt-16">
          <h2>Latest AI runs</h2>
          {render_ai_run_summary(ai_runs)}
        </section>
        <script>
          const progressNode = document.getElementById("ai-progress");
          const runId = progressNode ? progressNode.dataset.runId : "";
          function text(value) {{
            return value === null || value === undefined ? "" : String(value).replace(/[&<>"']/g, (char) => ({{
              "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
            }}[char]));
          }}
          function suggestionFromOutput(raw) {{
            if (!raw) return "";
            try {{
              const parsed = JSON.parse(raw);
              const list = parsed && parsed.nearest_match_suggestion;
              if (!Array.isArray(list)) return "";
              return list.map((entry) => entry && entry.path_code ? entry.path_code : "").filter(Boolean).join(", ");
            }} catch (err) {{
              return "";
            }}
          }}
          function renderProgress(data) {{
            if (!progressNode || !data.run) return;
            const run = data.run;
            const counts = data.counts || {{}};
            const latest = data.latest_items || [];
            const rows = latest.map((item) => `
              <tr><td><span class="code">${{text(item.external_code)}}</span></td><td>${{text(item.external_name)}}</td><td>${{text(item.status)}}</td><td>${{text(item.error)}}</td><td><span class="code">${{text(suggestionFromOutput(item.output_json))}}</span></td></tr>
            `).join("") || "<tr><td colspan='5' class='muted'>No item updates yet.</td></tr>";
            progressNode.innerHTML = `
              <div class="grid">
                <div class="span-4"><div class="stat">${{text(run.processed_items)}}/${{text(run.total_items)}}</div><div class="muted">Processed in current phase</div></div>
                <div class="span-4"><div class="stat">${{text(data.candidates_ready)}}</div><div class="muted">Candidate sets ready</div></div>
                <div class="span-4"><div class="stat">${{Number(counts.saved || 0) + Number(counts.reviewed || 0)}}</div><div class="muted">Mapped or reviewed</div></div>
                <div class="span-12">
                  <p><strong>Run ${{text(run.id)}}</strong> · ${{text(run.action_type)}} · ${{text(run.status)}} · phase: <span class="code">${{text(run.phase)}}</span></p>
                  <p class="muted">${{text(run.message)}}</p>
                  <p>Current: <span class="code">${{text(run.current_external_code)}}</span> ${{text(run.current_external_name)}}</p>
                </div>
                <div class="span-12"><table><thead><tr><th>Code</th><th>Name</th><th>Status</th><th>Error</th><th>Suggestion</th></tr></thead><tbody>${{rows}}</tbody></table></div>
              </div>
            `;
            if (run.status !== "running") window.clearInterval(window.aiProgressTimer);
          }}
          if (runId) {{
            window.aiProgressTimer = window.setInterval(() => {{
              fetch(`/api/ai-mapping-progress?run_id=${{encodeURIComponent(runId)}}`)
                .then((response) => response.ok ? response.json() : null)
                .then((data) => data && renderProgress(data))
                .catch(() => null);
            }}, 3000);
          }}
        </script>
        """
        self.send_html(page("Admin Mappings", body, query.get("message", ""), query.get("error", ""), active_nav="adminmappings"))

    def render_api_summary(self) -> None:
        with connect(self.db_path) as conn:
            seed(conn)
            self.send_json(
                {
                    "name": "BIMCats",
                    "hierarchies": [dict(row) for row in list_hierarchies(conn)],
                    "tag_count": len(list_tags(conn)),
                    "mapping_rule_count": len(list_mapping_rules(conn, active_only=True)),
                    "validation_warnings": validate_taxonomy(conn),
                    "mapping_warnings": mapping_warnings(conn),
                }
            )

    def render_ai_mapping_progress(self, query: dict[str, str]) -> None:
        with connect(self.db_path) as conn:
            seed(conn)
            run_id_raw = query.get("run_id", "").strip()
            if run_id_raw:
                run_id = int(run_id_raw)
            else:
                latest_run = latest_ai_mapping_run(conn)
                if latest_run is None:
                    self.send_json({"run": None, "counts": {}, "candidates_ready": 0, "latest_items": []})
                    return
                run_id = int(latest_run["id"])
            self.send_json(ai_mapping_run_progress(conn, run_id))


def run(host: str = "127.0.0.1", port: int = 8000, db_path: Path = DEFAULT_DB_PATH) -> None:
    with connect(db_path) as conn:
        seed(conn)
    BIMCatsHandler.db_path = db_path
    server = ThreadingHTTPServer((host, port), BIMCatsHandler)
    print(f"BIMCats running at http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run()
