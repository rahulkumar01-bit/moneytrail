"""
html_gen.py
-----------
Builds the interactive, self-contained HTML money-trail report.

Rather than re-writing the front-end from scratch, we take the reference
template (core/templates/money_trail_template.html) and splice in three
JSON blobs (GRAPH, WITHDRAWALS, WITHDRAWAL_TXNS) plus the toolbar summary
line, computed from the freshly extracted workbook data. This guarantees
the output always matches the approved reference look-and-feel exactly,
regardless of which source workbook is uploaded.
"""

import json
import re
from pathlib import Path

from .layout import compute_simple_layout

TEMPLATE_PATH = Path(__file__).parent / "templates" / "money_trail_template.html"


def _fmt_inr(v):
    if v is None:
        return "0"
    return format(round(v), ",")


def _build_withdrawals(data):
    """Per-account {atm, cheque, hold} totals, only for accounts that have
    at least one of the three values > 0 (keeps the JSON small)."""
    accounts = set(data["atm_totals"]) | set(data["cheque_totals"]) | set(data["hold_totals"])
    out = {}
    for acct in accounts:
        atm = data["atm_totals"].get(acct, 0.0)
        cheque = data["cheque_totals"].get(acct, 0.0)
        hold = data["hold_totals"].get(acct, 0.0)
        if atm or cheque or hold:
            out[acct] = {"atm": atm, "cheque": cheque, "hold": hold}
    return out


def _build_withdrawal_txns(data):
    out = {}
    for acct, txns in data["atm_txns"].items():
        if txns:
            out.setdefault(acct, {})["atm"] = txns
    for acct, txns in data["cheque_txns"].items():
        if txns:
            out.setdefault(acct, {})["cheque"] = txns
    return out


def _build_extra_txns(data):
    """Entries from the 'Others Less Then 500' / 'Other' sheets, keyed by
    the exact node id they're attached to (see extract.py)."""
    return data.get("extra_txns_by_node", {})


def generate_html(data, out_path, template_path=None):
    template_path = Path(template_path) if template_path else TEMPLATE_PATH
    html = template_path.read_text(encoding="utf-8")

    layout = compute_simple_layout(data)
    graph = {
        "nodes": layout["nodes"],
        "edges": layout["edges"],
        "canvas_w": layout["canvas_w"],
        "canvas_h": layout["canvas_h"],
        "unref_section_y": layout["unref_section_y"],
        "ack_no": data.get("ack_no"),
        "layer1_total": data.get("layer1_total"),
    }
    withdrawals = _build_withdrawals(data)
    withdrawal_txns = _build_withdrawal_txns(data)
    extra_txns = _build_extra_txns(data)

    graph_json = json.dumps(graph)
    withdrawals_json = json.dumps(withdrawals)
    withdrawal_txns_json = json.dumps(withdrawal_txns)
    extra_txns_json = json.dumps(extra_txns)

    html = re.sub(
        r"const GRAPH = .*?;\n",
        lambda m: "const GRAPH = " + graph_json + ";\n",
        html, count=1, flags=re.DOTALL,
    )
    html = re.sub(
        r"const WITHDRAWALS = .*?;\n",
        lambda m: "const WITHDRAWALS = " + withdrawals_json + ";\n",
        html, count=1, flags=re.DOTALL,
    )
    html = re.sub(
        r"const WITHDRAWAL_TXNS = .*?;\n",
        lambda m: "const WITHDRAWAL_TXNS = " + withdrawal_txns_json + ";\n",
        html, count=1, flags=re.DOTALL,
    )
    html = re.sub(
        r"const EXTRA_TXNS = .*?;\n",
        lambda m: "const EXTRA_TXNS = " + extra_txns_json + ";\n",
        html, count=1, flags=re.DOTALL,
    )

    # toolbar summary line
    n_accounts = len(data["nodes"])
    n_txns = len(data["edges"])
    flow_depths = [n["depth"] for n in data["nodes"] if not n.get("unreferenced")]
    max_depth = max(flow_depths) if flow_depths else 0
    n_unref = sum(1 for n in data["nodes"] if n.get("unreferenced"))
    summary = (
        f"{n_accounts} accounts &middot; {n_txns} transactions &middot; "
        f"layers 0&ndash;{max_depth} &middot; "
        f"&#8377;{_fmt_inr(data['total_atm'])} cash &middot; "
        f"&#8377;{_fmt_inr(data['total_cheque'])} cheque &middot; "
        f"&#8377;{_fmt_inr(data['total_hold'])} on hold"
    )
    if n_unref:
        summary += f" &middot; {n_unref} with no linked transaction"
    html = re.sub(
        r'(<div class="sub">).*?(</div>)',
        lambda m: m.group(1) + summary + m.group(2),
        html, count=1, flags=re.DOTALL,
    )

    out_path = Path(out_path)
    out_path.write_text(html, encoding="utf-8")
    return str(out_path)
