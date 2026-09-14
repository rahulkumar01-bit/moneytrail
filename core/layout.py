"""
layout.py
---------
Given the extracted `data` dict, compute x/y positions for every account
node, arranged in columns by layer (depth) with a barycenter ordering pass
to reduce line crossings. Used by the HTML (fixed box height) generator.

Nodes flagged `unreferenced` (accounts that showed up only in a footnote
sheet like "Others Less Then 500" with no real edge anywhere in the money
trail) are deliberately excluded from that column layout and placed in a
separate grid below the main diagram instead -- mixing them into Layer 0
would visually claim they're part of the traced flow, which they aren't.
"""

from collections import defaultdict
import math

BOX_W, BOX_H = 190, 54
COL_W, ROW_H = 260 * 3, 78  # 3x column pitch per readability request
UNREF_PER_ROW = 4
UNREF_GAP_X, UNREF_GAP_Y = 20, 20
UNREF_SECTION_TOP_MARGIN = 70  # room for the section header label


def compute_simple_layout(data):
    """Fixed-height box layout (used by the interactive HTML output)."""
    flow_nodes = [n for n in data["nodes"] if not n.get("unreferenced")]
    unref_nodes = [n for n in data["nodes"] if n.get("unreferenced")]

    nodes = {n["id"]: n for n in flow_nodes}
    edges = data["edges"]

    by_depth = defaultdict(list)
    for n in flow_nodes:
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
    for n in flow_nodes:
        d, i = pos[n["id"]]
        cnt = col_counts[d]
        x = 60 + d * COL_W
        total_h = cnt * ROW_H
        y_offset = (max_count * ROW_H - total_h) / 2
        y = 60 + y_offset + i * ROW_H
        display_acct = n.get("display_account", n["id"])
        short = display_acct[-4:] if display_acct else "----"
        out_nodes.append({**n, "x": x, "y": y, "short": short})

    main_canvas_w = 60 + (max_depth + 1) * COL_W + 100
    main_canvas_h = 60 + max_count * ROW_H + 60

    canvas_w, canvas_h = main_canvas_w, main_canvas_h
    unref_section_y = None

    if unref_nodes:
        unref_rows = math.ceil(len(unref_nodes) / UNREF_PER_ROW)
        row_width = UNREF_PER_ROW * (BOX_W + UNREF_GAP_X) - UNREF_GAP_X
        # right-align the grid within the main diagram's width (at least),
        # widening the canvas if there are more unreferenced accounts than
        # the main diagram is wide
        canvas_w = max(main_canvas_w, 60 + row_width + 60)
        unref_section_y = main_canvas_h + 30
        section_right_edge = canvas_w - 60
        for idx, n in enumerate(unref_nodes):
            row, col = divmod(idx, UNREF_PER_ROW)
            cols_in_this_row = min(UNREF_PER_ROW, len(unref_nodes) - row * UNREF_PER_ROW)
            row_start_x = section_right_edge - (cols_in_this_row * (BOX_W + UNREF_GAP_X) - UNREF_GAP_X)
            x = row_start_x + col * (BOX_W + UNREF_GAP_X)
            y = unref_section_y + UNREF_SECTION_TOP_MARGIN + row * (ROW_H)
            display_acct = n.get("display_account", n["id"])
            short = display_acct[-4:] if display_acct else "----"
            out_nodes.append({**n, "x": x, "y": y, "short": short})
        canvas_h = unref_section_y + UNREF_SECTION_TOP_MARGIN + unref_rows * ROW_H + 40

    return {
        "nodes": out_nodes,
        "edges": edges,
        "canvas_w": canvas_w,
        "canvas_h": canvas_h,
        "unref_section_y": unref_section_y,
    }
