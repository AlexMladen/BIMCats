from __future__ import annotations

import html
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote_plus, urlparse

from .db import DEFAULT_DB_PATH, connect
from .mapping import cross_links, matching_external_classes, nearest_matches
from .repository import (
    MappingInput,
    archive_mapping_rule,
    archive_tag,
    create_mapping_rule,
    create_tag,
    list_classification_systems,
    list_hierarchies,
    list_mapping_rules,
    list_tags,
    update_mapping_rule,
    update_tag,
)
from .seed import seed
from .validation import mapping_warnings, validate_taxonomy


CSS = """
:root {
  color-scheme: light;
  --bg: #f6f7f9;
  --panel: #ffffff;
  --text: #20242a;
  --muted: #667085;
  --line: #d9dee7;
  --accent: #0f766e;
  --accent-dark: #115e59;
  --danger: #b42318;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  color: var(--text);
  background: var(--bg);
}
a { color: var(--accent-dark); text-decoration: none; }
a:hover { text-decoration: underline; }
.shell { max-width: 1220px; margin: 0 auto; padding: 24px; }
.topbar {
  background: #10201e;
  color: white;
  border-bottom: 1px solid #0a1413;
}
.topbar .shell {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  padding-top: 14px;
  padding-bottom: 14px;
}
.brand { font-weight: 750; font-size: 20px; letter-spacing: 0; }
.nav { display: flex; gap: 14px; flex-wrap: wrap; }
.nav a { color: #d7fffb; font-size: 14px; }
.hero {
  padding: 22px 0 12px;
}
.hero h1 { margin: 0 0 8px; font-size: 30px; line-height: 1.15; letter-spacing: 0; }
.hero p { margin: 0; color: var(--muted); max-width: 820px; }
.grid { display: grid; grid-template-columns: repeat(12, 1fr); gap: 16px; }
.panel {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 16px;
}
.span-4 { grid-column: span 4; }
.span-5 { grid-column: span 5; }
.span-7 { grid-column: span 7; }
.span-12 { grid-column: span 12; }
.panel h2, .panel h3 { margin: 0 0 12px; line-height: 1.2; letter-spacing: 0; }
.panel h2 { font-size: 20px; }
.panel h3 { font-size: 16px; }
.muted { color: var(--muted); }
.stat { font-size: 32px; font-weight: 760; line-height: 1; margin-bottom: 6px; }
.treeview { display: grid; gap: 7px; }
.tree-children {
  margin: 8px 0 0 18px;
  padding-left: 14px;
  border-left: 1px solid var(--line);
  display: grid;
  gap: 7px;
}
.tree-node {
  border: 1px solid #e4e8f0;
  border-radius: 7px;
  background: #fbfcfe;
}
.tree-node[open] { background: #ffffff; }
.tree-node > summary {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 38px;
  padding: 7px 9px;
  cursor: pointer;
  list-style: none;
}
.tree-node > summary::-webkit-details-marker { display: none; }
.tree-node > summary::before {
  content: ">";
  width: 14px;
  color: var(--muted);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}
.tree-node[open] > summary::before { transform: rotate(90deg); }
.tree-leaf {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 36px;
  padding: 7px 9px;
  border: 1px solid #e4e8f0;
  border-radius: 7px;
  background: #fbfcfe;
}
.node-title {
  min-width: 0;
  overflow-wrap: anywhere;
}
.node-meta {
  color: var(--muted);
  font-size: 12px;
  margin-left: auto;
  white-space: nowrap;
}
.admin-node-body {
  padding: 0 9px 10px 31px;
  display: grid;
  gap: 10px;
}
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
  padding: 10px;
  border-radius: 7px;
  background: #f8fafc;
  border: 1px dashed #cbd5e1;
}
.code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  background: #eef6f5;
  border: 1px solid #c8e5e1;
  color: #115e59;
  padding: 2px 5px;
  border-radius: 5px;
  white-space: nowrap;
}
table { width: 100%; border-collapse: collapse; font-size: 14px; }
th, td { text-align: left; vertical-align: top; padding: 8px; border-bottom: 1px solid var(--line); }
th { color: #344054; background: #f8fafc; }
input, select, textarea {
  width: 100%;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  padding: 8px;
  font: inherit;
  background: white;
}
label { display: block; font-size: 13px; color: #344054; margin-bottom: 5px; }
.form-grid { display: grid; grid-template-columns: repeat(12, 1fr); gap: 12px; align-items: end; }
.field-2 { grid-column: span 2; }
.field-3 { grid-column: span 3; }
.field-4 { grid-column: span 4; }
.field-5 { grid-column: span 5; }
.field-6 { grid-column: span 6; }
.field-8 { grid-column: span 8; }
.field-12 { grid-column: span 12; }
.button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--accent);
  background: var(--accent);
  color: white;
  border-radius: 6px;
  padding: 8px 11px;
  font: inherit;
  cursor: pointer;
  min-height: 36px;
}
.button.secondary { background: white; color: var(--accent-dark); }
.button.danger { border-color: var(--danger); background: var(--danger); }
.actions { display: flex; gap: 8px; flex-wrap: wrap; }
.notice {
  border: 1px solid #fedf89;
  background: #fffaeb;
  color: #7a2e0e;
  padding: 10px 12px;
  border-radius: 8px;
  margin-bottom: 14px;
}
.error {
  border: 1px solid #fecdca;
  background: #fffbfa;
  color: #912018;
  padding: 10px 12px;
  border-radius: 8px;
  margin-bottom: 14px;
}
.success {
  border: 1px solid #abefc6;
  background: #ecfdf3;
  color: #085d3a;
  padding: 10px 12px;
  border-radius: 8px;
  margin-bottom: 14px;
}
@media (max-width: 820px) {
  .grid, .form-grid, .compact-form, .child-form { grid-template-columns: 1fr; }
  .span-4, .span-5, .span-7, .span-12,
  .field-2, .field-3, .field-4, .field-5, .field-6, .field-8, .field-12 {
    grid-column: span 1;
  }
  .topbar .shell { align-items: flex-start; flex-direction: column; }
  .shell { padding: 18px; }
  .tree-children { margin-left: 8px; padding-left: 10px; }
  .admin-node-body { padding-left: 10px; }
  .node-meta { display: none; }
}
"""


def esc(value: object) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def split_snippets(value: str) -> tuple[str, ...]:
    return tuple(part.strip().upper() for part in value.split(",") if part.strip())


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


def page(title: str, body: str, message: str = "", error: str = "") -> bytes:
    message_html = f"<div class='success'>{esc(message)}</div>" if message else ""
    error_html = f"<div class='error'>{esc(error)}</div>" if error else ""
    html_doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(title)} - BIMCats</title>
  <style>{CSS}</style>
</head>
<body>
  <header class="topbar">
    <div class="shell">
      <div class="brand">BIMCats</div>
      <nav class="nav">
        <a href="/">Browse</a>
        <a href="/mappings">Mappings</a>
        <a href="/admin/tags">Admin: Taxonomy</a>
        <a href="/admin/mappings">Admin: Mappings</a>
        <a href="/api/summary">API Summary</a>
      </nav>
    </div>
  </header>
  <main class="shell">
    {message_html}
    {error_html}
    {body}
  </main>
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

    def redirect(self, target: str) -> None:
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", target)
        self.end_headers()

    def read_form(self) -> dict[str, str]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8")
        return {key: values[0] for key, values in parse_qs(raw).items()}

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        query = {key: values[0] for key, values in parse_qs(parsed.query).items()}
        try:
            if parsed.path == "/":
                self.render_home(query)
            elif parsed.path == "/mappings":
                self.render_mappings(query)
            elif parsed.path == "/admin/tags":
                self.render_admin_tags(query)
            elif parsed.path == "/admin/mappings":
                self.render_admin_mappings(query)
            elif parsed.path == "/api/summary":
                self.render_api_summary()
            else:
                self.send_html(page("Not Found", "<h1>Not found</h1>"), HTTPStatus.NOT_FOUND)
        except Exception as exc:
            self.send_html(page("Error", "<h1>Request failed</h1>", error=str(exc)), HTTPStatus.INTERNAL_SERVER_ERROR)

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
                            split_snippets(form["snippets"]),
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
                        split_snippets(form["snippets"]),
                        form["status"],
                    )
                    conn.commit()
                    self.redirect("/admin/mappings?message=Mapping+updated")
                elif parsed.path == "/admin/mappings/archive":
                    archive_mapping_rule(conn, int(form["rule_id"]))
                    conn.commit()
                    self.redirect("/admin/mappings?message=Mapping+archived")
                else:
                    self.send_html(page("Not Found", "<h1>Not found</h1>"), HTTPStatus.NOT_FOUND)
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
        body = cards + warning_html + "<section class='grid'>" + "".join(sections) + "</section>"
        self.send_html(page("Browse", body, query.get("message", ""), query.get("error", "")))

    def render_mappings(self, query: dict[str, str]) -> None:
        full_code = query.get("code", "S-RORA-XX-MEALAS_MEALAP")
        with connect(self.db_path) as conn:
            seed(conn)
            matches = matching_external_classes(conn, full_code)
            nearest = nearest_matches(conn, full_code)
            rules = list_mapping_rules(conn, active_only=True)

        rows = "".join(
            f"<tr><td>{esc(row['system'])}</td><td><span class='code'>{esc(row['external_code'])}</span></td>"
            f"<td>{esc(row['external_name'])}</td><td>{esc(row['snippets'])}</td></tr>"
            for row in matches
        ) or "<tr><td colspan='4' class='muted'>No exact containment matches.</td></tr>"
        nearest_rows = "".join(
            f"<tr><td>{esc(row['system'])}</td><td><span class='code'>{esc(row['external_code'])}</span></td>"
            f"<td>{esc(row['external_name'])}</td><td>{esc(row['overlap'])}</td><td>{esc(row['snippets'])}</td></tr>"
            for row in nearest
        ) or "<tr><td colspan='5' class='muted'>No nearest matches.</td></tr>"
        all_rows = "".join(
            f"<tr><td>{esc(row['system_name'])}</td><td><span class='code'>{esc(row['external_code'])}</span></td>"
            f"<td>{esc(row['external_name'])}</td><td>{esc(row['snippets'])}</td></tr>"
            for row in rules
        )
        body = f"""
        <section class="hero">
          <h1>Mapping engine</h1>
          <p>Test thesis containment rules against a generated BIMCats code.</p>
        </section>
        <section class="panel">
          <form method="get" action="/mappings" class="form-grid">
            <div class="field-8">
              <label for="code">BIMCats full code</label>
              <input id="code" name="code" value="{esc(full_code)}">
            </div>
            <div class="field-4"><button class="button" type="submit">Check mappings</button></div>
          </form>
        </section>
        <section class="grid" style="margin-top:16px">
          <div class="panel span-12">
            <h2>Exact containment matches</h2>
            <table><thead><tr><th>System</th><th>Code</th><th>Name</th><th>Required snippets</th></tr></thead><tbody>{rows}</tbody></table>
          </div>
          <div class="panel span-12">
            <h2>Nearest matches</h2>
            <table><thead><tr><th>System</th><th>Code</th><th>Name</th><th>Overlap</th><th>Snippets</th></tr></thead><tbody>{nearest_rows}</tbody></table>
          </div>
          <div class="panel span-12">
            <h2>Active mapping rules</h2>
            <table><thead><tr><th>System</th><th>Code</th><th>Name</th><th>Snippets</th></tr></thead><tbody>{all_rows}</tbody></table>
          </div>
        </section>
        """
        self.send_html(page("Mappings", body, query.get("message", ""), query.get("error", "")))

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
        self.send_html(page("Admin Taxonomy", body, query.get("message", ""), query.get("error", "")))

    def render_admin_mappings(self, query: dict[str, str]) -> None:
        with connect(self.db_path) as conn:
            seed(conn)
            systems = [row for row in list_classification_systems(conn) if row["slug"] != "bimcats"]
            rules = list_mapping_rules(conn)
            warnings = mapping_warnings(conn)
            cross_link_rows = cross_links(conn, int(rules[0]["id"])) if rules else []

        system_options = "".join(
            f"<option value='{esc(row['slug'])}'>{esc(row['name'])}</option>" for row in systems
        )
        warning_html = ""
        if warnings:
            warning_html = "<div class='notice'>" + "<br>".join(esc(w) for w in warnings) + "</div>"
        cross_html = "".join(
            f"<tr><td>{esc(row['system'])}</td><td>{esc(row['external_code'])}</td><td>{esc(row['external_name'])}</td><td>{esc(row['shared_snippets'])}</td></tr>"
            for row in cross_link_rows
        ) or "<tr><td colspan='4' class='muted'>No cross-links.</td></tr>"
        rows = []
        for row in rules:
            rows.append(
                "<tr><form method='post' action='/admin/mappings/update'>"
                f"<td><input type='hidden' name='rule_id' value='{esc(row['id'])}'>{esc(row['system_name'])}</td>"
                f"<td><input name='external_code' value='{esc(row['external_code'])}'></td>"
                f"<td><input name='external_name' value='{esc(row['external_name'])}'></td>"
                f"<td><input name='snippets' value='{esc(row['snippets'])}'></td>"
                f"<td><select name='status'><option value='active' {'selected' if row['status'] == 'active' else ''}>active</option><option value='archived' {'selected' if row['status'] == 'archived' else ''}>archived</option></select></td>"
                "<td class='actions'><button class='button secondary' type='submit'>Save</button></form>"
                f"<form method='post' action='/admin/mappings/archive'><input type='hidden' name='rule_id' value='{esc(row['id'])}'><button class='button danger' type='submit'>Archive</button></form></td>"
                "</tr>"
            )
        body = f"""
        <section class="hero">
          <h1>Admin mappings</h1>
          <p>Maintain external classification mappings. Comma-separated snippets represent logical AND containment rules.</p>
        </section>
        {warning_html}
        <section class="panel">
          <h2>Add mapping rule</h2>
          <form method="post" action="/admin/mappings/create" class="form-grid">
            <div class="field-3"><label>System</label><select name="system_slug">{system_options}</select></div>
            <div class="field-3"><label>External code</label><input name="external_code" required></div>
            <div class="field-4"><label>External name</label><input name="external_name" required></div>
            <div class="field-2"><label>BIMCats snippets</label><input name="snippets" placeholder="ROSC,ENIT" required></div>
            <div class="field-12"><button class="button" type="submit">Create mapping</button></div>
          </form>
        </section>
        <section class="panel" style="margin-top:16px">
          <h2>Edit mapping rules</h2>
          <table><thead><tr><th>System</th><th>Code</th><th>Name</th><th>Snippets</th><th>Status</th><th>Actions</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
        </section>
        <section class="panel" style="margin-top:16px">
          <h2>Cross-link sample</h2>
          <p class="muted">Shown for the first active rule, based on shared BIMCats snippets.</p>
          <table><thead><tr><th>System</th><th>Code</th><th>Name</th><th>Shared snippets</th></tr></thead><tbody>{cross_html}</tbody></table>
        </section>
        """
        self.send_html(page("Admin Mappings", body, query.get("message", ""), query.get("error", "")))

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


def run(host: str = "127.0.0.1", port: int = 8000, db_path: Path = DEFAULT_DB_PATH) -> None:
    with connect(db_path) as conn:
        seed(conn)
    BIMCatsHandler.db_path = db_path
    server = ThreadingHTTPServer((host, port), BIMCatsHandler)
    print(f"BIMCats running at http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run()
