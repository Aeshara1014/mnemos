"""Monochrome SVG rendering for identity-graph snapshots.

Pure presentation, extracted from simple_runtime: these functions take the
snapshot dict that MnemosRuntime.identity_graph() builds and turn it into a
portable artifact. No store access, no scope logic.
"""

from __future__ import annotations

import html
from typing import Any


def _escape(value: Any) -> str:
    return html.escape(str(value), quote=True)


def short_label(value: str, limit: int) -> str:
    clean = " ".join(value.split())
    if len(clean) <= limit:
        return clean
    return clean[: max(1, limit - 1)].rstrip() + "..."


def build_timeline(entries: list[dict[str, Any]], engrams: list[Any]) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, int]] = {}
    for entry in entries:
        day = str(entry.get("created_at") or "")[:10] or "unknown"
        bucket = buckets.setdefault(day, {"continuity": 0, "memories": 0})
        bucket["continuity"] += 1
    for engram in engrams:
        day = str(getattr(engram, "created_at", "") or "")[:10] or "unknown"
        bucket = buckets.setdefault(day, {"continuity": 0, "memories": 0})
        bucket["memories"] += 1
    return [
        {"date": day, **counts}
        for day, counts in sorted(buckets.items())
        if day != "unknown"
    ]


def render_identity_svg(snapshot: dict[str, Any]) -> str:
    width = 1280
    height = 800
    palette = {
        "bg": "#0e0e11",
        "surface": "#151518",
        "raised": "#1a1a1e",
        "rule": "rgba(220,219,216,0.10)",
        "rule_strong": "rgba(220,219,216,0.20)",
        "line": "rgba(220,219,216,0.34)",
        "text": "#F4F3F0",
        "body": "rgba(210,208,204,0.70)",
        "muted": "rgba(161,159,155,0.48)",
        "ghost": "rgba(132,130,126,0.16)",
        "node": "rgba(244,243,240,0.88)",
        "node_soft": "rgba(244,243,240,0.12)",
        "node_mid": "rgba(244,243,240,0.28)",
    }
    graph_x = 318
    graph_y = 150
    graph_w = 892
    graph_h = 482
    center_x = graph_x + graph_w * 0.44
    center_y = graph_y + graph_h * 0.44
    nodes = snapshot["nodes"]
    domain_nodes = [node for node in nodes if node["kind"] == "domain"]
    continuity_nodes = [node for node in nodes if node["kind"] == "continuity"]
    memory_nodes = [node for node in nodes if node["kind"] == "memory"]

    positions: dict[str, tuple[float, float]] = {
        f"agent:{snapshot['scope']['agent_id']}": (center_x, center_y)
    }

    if domain_nodes:
        for index, node in enumerate(domain_nodes):
            step = graph_h * 0.54 / max(1, len(domain_nodes) - 1)
            positions[node["id"]] = (graph_x + 144, graph_y + 116 + index * step)

    if continuity_nodes:
        for index, node in enumerate(continuity_nodes):
            row = index % 8
            col = index // 8
            positions[node["id"]] = (
                graph_x + graph_w - 250 + col * 96,
                graph_y + 78 + row * 44,
            )

    timeline = snapshot.get("timeline", [])
    if memory_nodes:
        start_x = graph_x + 72
        step = (graph_w - 144) / max(1, len(memory_nodes) - 1)
        for index, node in enumerate(memory_nodes):
            positions[node["id"]] = (start_x + index * step, graph_y + graph_h - 62)

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
        "<title id=\"title\">Mnemos Identity Graph</title>",
        "<desc id=\"desc\">A scoped monochrome snapshot of an agent identity graph, continuity anchors, memory traces, and formation over time.</desc>",
        "<defs>",
        "<pattern id=\"grid\" width=\"32\" height=\"32\" patternUnits=\"userSpaceOnUse\"><path d=\"M 32 0 L 0 0 0 32\" fill=\"none\" stroke=\"rgba(220,219,216,0.035)\" stroke-width=\"1\"/></pattern>",
        "<filter id=\"shadow\"><feDropShadow dx=\"0\" dy=\"10\" stdDeviation=\"18\" flood-color=\"#000\" flood-opacity=\"0.32\"/></filter>",
        "<filter id=\"fine-glow\"><feDropShadow dx=\"0\" dy=\"0\" stdDeviation=\"5\" flood-color=\"#F4F3F0\" flood-opacity=\"0.13\"/></filter>",
        "</defs>",
        f'<rect width="{width}" height="{height}" fill="{palette["bg"]}"/>',
        '<rect width="1280" height="800" fill="url(#grid)" opacity="0.9"/>',
        f'<rect x="38" y="34" width="{width - 76}" height="{height - 68}" rx="6" fill="none" stroke="{palette["rule"]}"/>',
        f'<text x="58" y="70" fill="{palette["muted"]}" font-family="JetBrains Mono, SF Mono, Menlo, monospace" font-size="11" letter-spacing="0">MNEMOS.IDENTITY_GRAPH / SCOPED TOPOLOGY</text>',
        f'<text x="58" y="104" fill="{palette["text"]}" font-family="Inter, Arial, sans-serif" font-size="29" font-weight="620">Mnemos Identity Graph</text>',
        f'<text x="58" y="132" fill="{palette["body"]}" font-family="Inter, Arial, sans-serif" font-size="13">{_escape(snapshot["summary"])}</text>',
        f'<text x="1032" y="70" fill="{palette["muted"]}" font-family="JetBrains Mono, SF Mono, Menlo, monospace" font-size="10" text-anchor="end">schema=v{_escape(snapshot.get("version", 1))}</text>',
        f'<text x="1178" y="70" fill="{palette["muted"]}" font-family="JetBrains Mono, SF Mono, Menlo, monospace" font-size="10" text-anchor="end">nodes={len(nodes):02d} / edges={len(snapshot["edges"]):02d}</text>',
        f'<rect x="58" y="150" width="220" height="220" rx="6" fill="{palette["surface"]}" stroke="{palette["rule"]}" filter="url(#shadow)"/>',
        f'<text x="78" y="184" fill="{palette["muted"]}" font-family="JetBrains Mono, SF Mono, Menlo, monospace" font-size="10">SCOPE</text>',
        f'<text x="78" y="218" fill="{palette["text"]}" font-family="Inter, Arial, sans-serif" font-size="20" font-weight="540">{_escape(snapshot["scope"]["agent_id"])}</text>',
        f'<text x="78" y="250" fill="{palette["body"]}" font-family="JetBrains Mono, SF Mono, Menlo, monospace" font-size="11">person  {_escape(snapshot["scope"]["person_id"])}</text>',
        f'<text x="78" y="276" fill="{palette["body"]}" font-family="JetBrains Mono, SF Mono, Menlo, monospace" font-size="11">project {_escape(snapshot["scope"]["project_scope"])}</text>',
        f'<line x1="78" y1="306" x2="258" y2="306" stroke="{palette["rule"]}"/>',
        f'<text x="78" y="336" fill="{palette["muted"]}" font-family="Inter, Arial, sans-serif" font-size="12">portable SVG plus structured graph data</text>',
        f'<rect x="58" y="394" width="220" height="238" rx="6" fill="{palette["surface"]}" stroke="{palette["rule"]}" filter="url(#shadow)"/>',
        f'<text x="78" y="426" fill="{palette["muted"]}" font-family="JetBrains Mono, SF Mono, Menlo, monospace" font-size="10">MEASURES</text>',
        f'<rect x="{graph_x}" y="{graph_y}" width="{graph_w}" height="{graph_h}" rx="6" fill="{palette["surface"]}" stroke="{palette["rule_strong"]}" filter="url(#shadow)"/>',
        f'<rect x="{graph_x + 1}" y="{graph_y + 1}" width="{graph_w - 2}" height="{graph_h - 2}" rx="5" fill="url(#grid)" opacity="0.55"/>',
        f'<text x="{graph_x + 22}" y="{graph_y + 34}" fill="{palette["muted"]}" font-family="JetBrains Mono, SF Mono, Menlo, monospace" font-size="10">TOPOLOGY FIELD</text>',
        f'<text x="{graph_x + graph_w - 22}" y="{graph_y + 34}" fill="{palette["muted"]}" font-family="JetBrains Mono, SF Mono, Menlo, monospace" font-size="10" text-anchor="end">formation live / monochrome</text>',
    ]

    stats = snapshot.get("stats", {})
    stat_rows = [
        ("active memories", stats.get("active_memories", 0)),
        ("continuity notes", stats.get("continuity_notes", 0)),
        ("connections", stats.get("connections", 0)),
        ("archived", stats.get("archived", 0)),
    ]
    for index, (label, value) in enumerate(stat_rows):
        y = 464 + index * 38
        lines.append(f'<text x="78" y="{y}" fill="{palette["text"]}" font-family="JetBrains Mono, SF Mono, Menlo, monospace" font-size="22" font-weight="540">{_escape(value)}</text>')
        lines.append(f'<text x="132" y="{y}" fill="{palette["muted"]}" font-family="Inter, Arial, sans-serif" font-size="12">{_escape(label)}</text>')

    if domain_nodes:
        lines.append(f'<text x="78" y="650" fill="{palette["muted"]}" font-family="JetBrains Mono, SF Mono, Menlo, monospace" font-size="10">DOMAIN INDEX</text>')
        for index, node in enumerate(domain_nodes[:5]):
            y = 678 + index * 20
            weight = int(node.get("weight", 0))
            lines.append(f'<text x="78" y="{y}" fill="{palette["body"]}" font-family="JetBrains Mono, SF Mono, Menlo, monospace" font-size="10">{_escape(short_label(node["label"], 15))}</text>')
            lines.append(f'<text x="250" y="{y}" fill="{palette["muted"]}" font-family="JetBrains Mono, SF Mono, Menlo, monospace" font-size="10" text-anchor="end">{weight:02d}</text>')

    for edge in snapshot["edges"]:
        source = positions.get(edge["source"])
        target = positions.get(edge["target"])
        if not source or not target:
            continue
        opacity = min(max(float(edge.get("strength", 0.45)), 0.18), 0.85)
        dash = {
            "contains": "",
            "anchors": "5 8",
            "encodes": "2 7",
        }.get(str(edge.get("relation")), "")
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        lines.append(
            f'<line x1="{source[0]:.1f}" y1="{source[1]:.1f}" x2="{target[0]:.1f}" y2="{target[1]:.1f}" '
            f'stroke="{palette["line"]}" stroke-width="{0.8 + opacity * 1.8:.2f}" opacity="{opacity:.2f}"{dash_attr}/>'
        )

    def draw_node(node: dict[str, Any]) -> None:
        x, y = positions[node["id"]]
        kind = node["kind"]
        if kind == "agent":
            radius = 58
        elif kind == "domain":
            radius = 24 + min(float(node.get("weight", 1)), 6) * 2
        elif kind == "continuity":
            radius = 10 + min(float(node.get("salience", 0.45)), 1.0) * 9
        else:
            radius = 8 + min(float(node.get("accessibility", 0.45)), 1.0) * 8
        label = _escape(node["label"])
        if kind == "agent":
            lines.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="76" fill="{palette["node_soft"]}" stroke="{palette["ghost"]}"/>')
            lines.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius}" fill="{palette["raised"]}" stroke="{palette["node"]}" stroke-width="1.4" filter="url(#fine-glow)"/>')
            lines.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="7" fill="{palette["node"]}"/>')
            lines.append(
                f'<text x="{x:.1f}" y="{y - 10:.1f}" fill="{palette["text"]}" font-family="Inter, Arial, sans-serif" '
                f'font-size="15" font-weight="540" text-anchor="middle">{label}</text>'
            )
            lines.append(
                f'<text x="{x:.1f}" y="{y + 18:.1f}" fill="{palette["muted"]}" font-family="JetBrains Mono, SF Mono, Menlo, monospace" '
                'font-size="10" text-anchor="middle">agent core</text>'
            )
        elif kind == "domain":
            lines.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius}" fill="{palette["node_soft"]}" stroke="{palette["node_mid"]}" stroke-width="1.2"/>')
            lines.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.4" fill="{palette["node"]}"/>')
            lines.append(
                f'<text x="{x - radius - 12:.1f}" y="{y + 4:.1f}" fill="{palette["body"]}" font-family="JetBrains Mono, SF Mono, Menlo, monospace" '
                f'font-size="10" text-anchor="end">{label}</text>'
            )
        elif kind == "continuity":
            lines.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius}" fill="{palette["node_soft"]}" stroke="{palette["node_mid"]}" stroke-width="1"/>')
            lines.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.8" fill="{palette["node"]}"/>')
            lines.append(
                f'<text x="{x + radius + 12:.1f}" y="{y - 2:.1f}" fill="{palette["body"]}" font-family="Inter, Arial, sans-serif" '
                f'font-size="10">{_escape(short_label(node["label"], 34))}</text>'
            )
            lines.append(
                f'<text x="{x + radius + 12:.1f}" y="{y + 13:.1f}" fill="{palette["muted"]}" font-family="JetBrains Mono, SF Mono, Menlo, monospace" '
                f'font-size="8">salience {float(node.get("salience", 0.0)):.2f}</text>'
            )
        else:
            lines.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius}" fill="{palette["node_soft"]}" stroke="{palette["node_mid"]}" stroke-width="1"/>')
            lines.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.6" fill="{palette["node"]}"/>')
            lines.append(
                f'<text x="{x:.1f}" y="{y + 31:.1f}" fill="{palette["muted"]}" font-family="Inter, Arial, sans-serif" '
                f'font-size="9" text-anchor="middle">{_escape(short_label(node["label"], 18))}</text>'
            )

    for node in domain_nodes:
        draw_node(node)
    for node in continuity_nodes:
        draw_node(node)
    for node in memory_nodes:
        draw_node(node)
    draw_node(nodes[0])

    if timeline:
        lines.append(f'<rect x="{graph_x}" y="662" width="{graph_w}" height="70" rx="6" fill="{palette["surface"]}" stroke="{palette["rule"]}"/>')
        lines.append(f'<text x="{graph_x + 22}" y="688" fill="{palette["muted"]}" font-family="JetBrains Mono, SF Mono, Menlo, monospace" font-size="10">FORMATION OVER TIME</text>')
        max_total = max(1, max(item["continuity"] + item["memories"] for item in timeline))
        start_x = graph_x + 180
        bar_w = min(34, 520 / max(1, len(timeline)))
        for index, item in enumerate(timeline[-16:]):
            total = item["continuity"] + item["memories"]
            h = 8 + (total / max_total) * 35
            x = start_x + index * (bar_w + 8)
            y = 717 - h
            lines.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{h:.1f}" rx="2" fill="{palette["node"]}" opacity="0.66"/>')
            lines.append(f'<text x="{x + bar_w / 2:.1f}" y="724" fill="{palette["muted"]}" font-family="JetBrains Mono, SF Mono, Menlo, monospace" font-size="8" text-anchor="middle">{_escape(item["date"][-5:])}</text>')
    else:
        lines.append(f'<rect x="{graph_x}" y="662" width="{graph_w}" height="70" rx="6" fill="{palette["surface"]}" stroke="{palette["rule"]}"/>')
        lines.append(f'<text x="{graph_x + 22}" y="702" fill="{palette["muted"]}" font-family="JetBrains Mono, SF Mono, Menlo, monospace" font-size="10">FORMATION OVER TIME / no dated events yet</text>')

    lines.append("</svg>")
    return "\n".join(lines)
