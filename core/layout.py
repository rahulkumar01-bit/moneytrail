"""
layout.py
---------
Given the extracted `data` dict, compute x/y positions for every account
node, arranged in columns by layer (depth) with a barycenter ordering pass
to reduce line crossings. Used by the HTML (fixed box height) generator.
"""

from collections import defaultdict

BOX_W, BOX_H = 190, 54
COL_W, ROW_H = 260 * 3, 78  # 3x column pitch per readability request


def compute_simple_layout(data):
    """Fixed-height box layout (used by the interactive HTML output)."""
    nodes = {n["id"]: n for n in data["nodes"]}
    edges = data["edges"]

    by_depth = defaultdict(list)
    for n in data["nodes"]:
        by_depth[n["depth"]].append(n["id"])

    incoming = defaultdict(list)
    for e in edges:
        incoming[e["dst"]].append(e["src"])

    pos = {}
    max_depth = max(by_depth.keys())

    by_depth[0] = sorted(by_depth.get(0, []))
    for i, nid in enumerate(by_depth[0]):
        pos[nid] = (0, i)

    for d in range(1, max_depth + 1):
        lst = by_depth.get(d, [])

        def barycenter(nid):
            preds = [p for p in incoming.get(nid, []) if p in pos]
            if not preds:
                return 999999
            ys = [pos[p][1] for p in preds]
            return sum(ys) / len(ys)

        lst.sort(key=barycenter)
        for i, nid in enumerate(lst):
            pos[nid] = (d, i)

    col_counts = {d: len(v) for d, v in by_depth.items()}
    max_count = max(col_counts.values())

    out_nodes = []
    for n in data["nodes"]:
        d, i = pos[n["id"]]
        cnt = col_counts[d]
        x = 60 + d * COL_W
        total_h = cnt * ROW_H
        y_offset = (max_count * ROW_H - total_h) / 2
        y = 60 + y_offset + i * ROW_H
        display_acct = n.get("display_account", n["id"])
        short = display_acct[-4:] if display_acct else "----"
        out_nodes.append({**n, "x": x, "y": y, "short": short})

    canvas_w = 60 + (max_depth + 1) * COL_W + 100
    canvas_h = 60 + max_count * ROW_H + 60

    return {
        "nodes": out_nodes,
        "edges": edges,
        "canvas_w": canvas_w,
        "canvas_h": canvas_h,
    }
