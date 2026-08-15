"""
pdf_gen.py
----------
Builds the single-sheet, card-style PDF money-trail poster (one big PDF
page, laid out left-to-right by layer, matching the approved sample
format).
"""

from pathlib import Path
import math

from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.pdfbase.pdfmetrics import stringWidth

BOX_W = 300
PAD = 12
LINE_H = 12.5
COL_GAP = 130 * 2  # 2x spacing per readability request
ROW_GAP = 22

FONT_LABEL = ("Helvetica-Bold", 8.3)
FONT_VAL = ("Helvetica", 8.3)
FONT_TITLE = ("Helvetica-Bold", 9.5)

FIELD_COLORS = {
    "Total Amount Withdrawn (ATM):": colors.HexColor("#b3610a"),
    "Total Amount Withdrawn (Cheque):": colors.HexColor("#6a3d9a"),
    "Total Amount On Hold:": colors.HexColor("#a51d1d"),
}
DEFAULT_FIELD_COLOR = colors.HexColor("#111111")


def _wrap_text(text, font, size, max_w):
    if not text:
        return []
    words = text.split()
    lines, cur = [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if stringWidth(test, font, size) <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _fmt_amt(v):
    if v is None:
        return "-"
    return "Rs. " + format(v, ",.2f")


def _bezier_split_mid(p0, p1, p2, p3):
    """Split cubic Bezier p0,p1,p2,p3 at t=0.5 (De Casteljau). Returns
    (q0, r0, s0, r1, q2, angle) where s0 is the point on the curve at its
    midpoint and angle is the curve's tangent direction there (in
    radians) -- r0, s0, r1 are colinear by construction, so r1-r0 gives
    the tangent."""
    def mid(a, b):
        return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    q0, q1, q2 = mid(p0, p1), mid(p1, p2), mid(p2, p3)
    r0, r1 = mid(q0, q1), mid(q1, q2)
    s0 = mid(r0, r1)
    angle = math.atan2(r1[1] - r0[1], r1[0] - r0[0])
    return q0, r0, s0, r1, q2, angle


def _draw_curve_with_mid_arrow(c, p0, p3, ctrl1, ctrl2, arrow_color, arrow_size=5.5):
    """Draws a cubic Bezier from p0 to p3 (via control points ctrl1,
    ctrl2), with a small arrowhead centered on the curve's midpoint,
    oriented along the curve's direction there."""
    q0, r0, s0, r1, q2, angle = _bezier_split_mid(p0, ctrl1, ctrl2, p3)
    path = c.beginPath()
    path.moveTo(*p0)
    path.curveTo(q0[0], q0[1], r0[0], r0[1], s0[0], s0[1])
    path.curveTo(r1[0], r1[1], q2[0], q2[1], p3[0], p3[1])
    c.drawPath(path, stroke=1, fill=0)

    c.saveState()
    c.translate(s0[0], s0[1])
    c.rotate(math.degrees(angle))
    c.setFillColor(arrow_color)
    arrow = c.beginPath()
    arrow.moveTo(arrow_size, 0)
    arrow.lineTo(-arrow_size * 0.6, arrow_size * 0.55)
    arrow.lineTo(-arrow_size * 0.6, -arrow_size * 0.55)
    arrow.close()
    c.drawPath(arrow, stroke=0, fill=1)
    c.restoreState()


def generate_pdf(data, out_path):
    edges = data["edges"]
    nodes = {n["id"]: n for n in data["nodes"]}
    atm_map = data.get("atm_totals", {})
    cheque_map = data.get("cheque_totals", {})
    hold_map = data.get("hold_totals", {})
    extra_map = data.get("extra_txns_by_node", {})

    incoming = {}
    for e in edges:
        incoming.setdefault(e["dst"], []).append(e)

    by_depth = {}
    for n in data["nodes"]:
        by_depth.setdefault(n["depth"], []).append(n["id"])

    def card_lines(node_id):
        n = nodes[node_id]
        txs = incoming.get(node_id, []) + extra_map.get(node_id, [])
        total = sum(t["amt"] for t in txs if t.get("amt")) if txs else 0
        display_account = n.get("display_account", node_id)
        title_text = "Victim's Account" if n["depth"] == 0 else f"Layer: {n['depth']}"
        lines = [
            ("title", title_text),
            ("field", "To Account Number:", display_account),
            ("field", "Bank Name:", n["bank"] or "Unknown"),
            ("field", "Total Amount:", _fmt_amt(total)),
        ]
        if atm_map.get(node_id):
            lines.append(("field", "Total Amount Withdrawn (ATM):", _fmt_amt(atm_map.get(node_id))))
        if cheque_map.get(node_id):
            lines.append(("field", "Total Amount Withdrawn (Cheque):", _fmt_amt(cheque_map.get(node_id))))
        if hold_map.get(node_id):
            lines.append(("field", "Total Amount On Hold:", _fmt_amt(hold_map.get(node_id))))
        lines.append(("field", "Total Recovered Amount:", "Rs. 0.00"))

        for i, t in enumerate(txs, 1):
            lines.append(("spacer", ""))
            lines.append(("subtitle", f"#{i} Transaction ID: {t.get('txn_id') or 'NA'}"))
            lines.append(("plain", f"Transaction Type: {t.get('type')}"))
            lines.append(("plain", f"Transaction Amount: {_fmt_amt(t.get('amt'))}"))
            lines.append(("plain", f"Disputed Amount: {_fmt_amt(t.get('disputed'))}"))
            lines.append(("plain", f"Transaction Date: {t.get('date') or 'NA'}"))
            # Remarks are shown only for entries sourced from the "Others
            # Less Then 500" / "Other" sheets, per request -- normal
            # Money-Transfer-to-derived transactions keep remarks hidden.
            if t.get("show_remarks") and t.get("remarks"):
                wrapped = _wrap_text("Remarks: " + t["remarks"], "Helvetica-Oblique", 7.6, BOX_W - 2 * PAD)
                for wline in wrapped[:4]:
                    lines.append(("remark", wline))
        if not txs:
            lines.append(("plain", "(No inbound transaction on record)"))
        return lines

    def card_height(lines):
        h = PAD * 2
        for kind, *_ in lines:
            if kind == "spacer":
                h += 6
            elif kind == "title":
                h += 16
            else:
                h += LINE_H
        return h

    card_cache = {}

    def get_card(nid):
        if nid not in card_cache:
            lines = card_lines(nid)
            card_cache[nid] = {"lines": lines, "h": card_height(lines)}
        return card_cache[nid]

    max_depth = max(by_depth.keys())
    col_x = {}
    x_cursor = 40
    for d in range(0, max_depth + 1):
        col_x[d] = x_cursor
        x_cursor += BOX_W + COL_GAP

    def predecessors(nid):
        return [e["src"] for e in edges if e["dst"] == nid]

    pos = {}
    col_order = {0: sorted(by_depth.get(0, []))}
    for d in range(1, max_depth + 1):
        col_order[d] = by_depth.get(d, [])

    # Root complaint card's footprint must be reserved BEFORE laying out
    # column 0, otherwise the origin-account cards (which used to start
    # at a fixed y regardless of the root card's actual height) overlap
    # it whenever the root card grows taller than that fixed offset.
    root_w, root_h = 340, 118
    root_x = 40
    root_y = 10
    ROOT_TO_COLUMNS_GAP = 40
    y_top_root = root_y + root_h + ROOT_TO_COLUMNS_GAP

    for d in range(0, max_depth + 1):
        lst = col_order[d]
        if d > 0:
            def bary(nid):
                preds = [p for p in predecessors(nid) if p in pos]
                if not preds:
                    return 999999
                ys = [pos[p][1] + get_card(p)["h"] / 2 for p in preds]
                return sum(ys) / len(ys)
            lst = sorted(lst, key=bary)
            col_order[d] = lst
        y = y_top_root
        for nid in lst:
            pos[nid] = (col_x[d], y)
            y += get_card(nid)["h"] + ROW_GAP

    canvas_w = x_cursor + 40
    canvas_h = max(pos[n][1] + get_card(n)["h"] for n in pos) + 80

    c = canvas.Canvas(str(out_path), pagesize=(canvas_w, canvas_h))

    def flip(y, h):
        return canvas_h - y - h

    # root complaint card
    c.setLineWidth(2.2)
    c.setStrokeColor(colors.HexColor("#111111"))
    c.setFillColor(colors.white)
    c.roundRect(root_x, flip(root_y, root_h), root_w, root_h, 10, stroke=1, fill=1)
    ty = flip(root_y, root_h) + root_h - 18
    c.setFillColor(colors.HexColor("#111111"))
    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(root_x + root_w / 2, ty, f"Acknowledgement / Complaint No. - {data.get('ack_no', 'N/A')}")
    ty -= 15
    c.setFont("Helvetica", 9)
    c.drawCentredString(root_x + root_w / 2, ty, f"Total Amount Moved Out (Layer 1) - {_fmt_amt(data.get('layer1_total'))}")
    ty -= 14
    c.drawCentredString(root_x + root_w / 2, ty, "Total Recovered Amount - Rs. 0.00")
    ty -= 14
    c.setFillColor(colors.HexColor("#b3610a"))
    c.drawCentredString(root_x + root_w / 2, ty, f"Total Amount Withdrawn (ATM) - {_fmt_amt(data.get('total_atm'))}")
    ty -= 14
    c.setFillColor(colors.HexColor("#6a3d9a"))
    c.drawCentredString(root_x + root_w / 2, ty, f"Total Amount Withdrawn (Cheque) - {_fmt_amt(data.get('total_cheque'))}")
    ty -= 14
    c.setFillColor(colors.HexColor("#a51d1d"))
    c.drawCentredString(root_x + root_w / 2, ty, f"Total Amount On Hold - {_fmt_amt(data.get('total_hold'))}")
    ty -= 14
    c.setFillColor(colors.HexColor("#666666"))
    c.setFont("Helvetica-Oblique", 7.5)
    c.drawCentredString(root_x + root_w / 2, ty, "(Victim name not present in this sheet)")

    first_col_ids = col_order.get(0, [])
    if first_col_ids:
        root_bottom_y = flip(root_y, root_h)
        c.setStrokeColor(colors.HexColor("#4a6fa5"))
        c.setLineWidth(1.8)
        c.line(root_x + root_w / 2, root_bottom_y, root_x + root_w / 2, root_bottom_y - 15)

    # connector edges - darker, thicker stroke so the flow paths are
    # easy to follow across a large, densely-connected diagram, with a
    # directional arrowhead at each curve's midpoint (kept off the
    # endpoints, which get crowded where many edges converge on one card)
    c.setStrokeColor(colors.HexColor("#4a6fa5"))
    c.setLineWidth(1.7)
    arrow_color = colors.HexColor("#2f4d75")
    for e in edges:
        s = pos.get(e["src"])
        t = pos.get(e["dst"])
        if not s or not t:
            continue
        s_h = get_card(e["src"])["h"]
        t_h = get_card(e["dst"])["h"]
        # Most edges flow left-to-right (source column <= destination
        # column). But a destination's column is fixed by the EARLIEST
        # layer it was ever credited in, so a few real edges flow from a
        # later layer back to an earlier one. For those, connect from the
        # source's left edge to the destination's right edge instead, so
        # the curve -- and its arrowhead -- reads correctly.
        forward = s[0] <= t[0]
        sx = s[0] + BOX_W if forward else s[0]
        tx = t[0] if forward else t[0] + BOX_W
        sy = flip(s[1], s_h) + s_h / 2
        ty2 = flip(t[1], t_h) + t_h / 2
        mx = (sx + tx) / 2
        _draw_curve_with_mid_arrow(c, (sx, sy), (tx, ty2), (mx, sy), (mx, ty2), arrow_color)

    for nid in first_col_ids:
        t = pos[nid]
        tx = t[0]
        ty2 = flip(t[1], get_card(nid)["h"]) + get_card(nid)["h"] / 2
        rx = root_x + root_w / 2
        ry = flip(root_y, root_h) - 15
        c.setStrokeColor(colors.HexColor("#2f4d75"))
        c.setLineWidth(1.8)
        my = (ry + ty2) / 2
        _draw_curve_with_mid_arrow(c, (rx, ry), (tx, ty2), (rx, my), (tx, my), colors.HexColor("#1c3252"))

    # column headers - positioned just above where each column's cards
    # actually start (y_top_root), not a fixed page-top offset. The old
    # fixed offset happened to land inside the root complaint card's own
    # area for column 0, so "Origin Accounts" overlapped its border.
    c.setFont("Helvetica-Bold", 11)
    c.setFillColor(colors.HexColor("#333333"))
    header_y = canvas_h - (y_top_root - 25)
    for d in range(0, max_depth + 1):
        label = "Origin Accounts" if d == 0 else f"Layer {d}"
        c.drawString(col_x[d], header_y, label)

    # cards
    for nid, (x, y) in pos.items():
        card = get_card(nid)
        h = card["h"]
        yb = flip(y, h)
        c.setLineWidth(1.6)
        c.setStrokeColor(colors.HexColor("#111111"))
        c.setFillColor(colors.white)
        c.roundRect(x, yb, BOX_W, h, 8, stroke=1, fill=1)
        cy = yb + h - PAD - 2
        for kind, *rest in card["lines"]:
            if kind == "spacer":
                cy -= 6
                c.setStrokeColor(colors.HexColor("#dddddd"))
                c.setLineWidth(0.6)
                c.line(x + PAD, cy + 9, x + BOX_W - PAD, cy + 9)
                continue
            if kind == "title":
                c.setFont(*FONT_TITLE)
                c.setFillColor(colors.HexColor("#111111"))
                c.rect(x + PAD, cy - 8, 8, 8, stroke=1, fill=0)
                c.drawString(x + PAD + 13, cy - 8, rest[0])
                cy -= 16
            elif kind == "field":
                label, val = rest
                fc = FIELD_COLORS.get(label, DEFAULT_FIELD_COLOR)
                c.setFont(*FONT_LABEL)
                c.setFillColor(fc)
                c.drawString(x + PAD, cy - 8, label)
                lw = stringWidth(label + " ", FONT_LABEL[0], FONT_LABEL[1])
                c.setFont(*FONT_VAL)
                c.setFillColor(fc)
                c.drawString(x + PAD + lw, cy - 8, str(val))
                cy -= LINE_H
            elif kind == "subtitle":
                c.setFont("Helvetica-Bold", 8.3)
                c.setFillColor(colors.HexColor("#20406b"))
                c.drawString(x + PAD, cy - 8, rest[0])
                cy -= LINE_H
            elif kind == "plain":
                c.setFont(*FONT_VAL)
                c.setFillColor(colors.HexColor("#222222"))
                c.drawString(x + PAD, cy - 8, rest[0])
                cy -= LINE_H
            elif kind == "remark":
                c.setFont("Helvetica-Oblique", 7.6)
                c.setFillColor(colors.HexColor("#555555"))
                c.drawString(x + PAD, cy - 8, rest[0])
                cy -= 10.5

    # Printing note. This diagram's page size is sized to its content
    # and can be far larger than any standard paper size, so it can
    # only ever come out correctly on a single physical sheet if the
    # print dialog's own "Fit to Printable Area" / "Shrink to Fit"
    # scaling is used -- no setting inside a PDF file can force that
    # choice for the person printing it, so the instruction is made
    # explicit directly on the page itself instead.
    c.setFont("Helvetica-Oblique", 8)
    c.setFillColor(colors.HexColor("#888888"))
    c.drawCentredString(
        canvas_w / 2, 18,
        "To print on a single sheet of any paper size (A4, A3, A2, A1, A0), "
        "select \"Fit to Printable Area\" or \"Shrink to Fit\" in your print dialog."
    )

    c.save()
    return str(out_path)
