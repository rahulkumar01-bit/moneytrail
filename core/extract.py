"""
extract.py
----------
Reads a "BankAction_CompleteTrail" style .xlsx workbook and produces a single
plain-Python data structure that both the HTML generator and the PDF
generator build their output from.

Expected sheets (same as the sample workbook):
    - "Money Transfer to"                (the money-trail graph itself)
    - "Withdrawal through ATM"           (per-account cash withdrawal records)
    - "Cash Withdrawal through Cheque"   (per-account cheque withdrawal records)
    - "Transaction put on hold"          (per-account hold amounts)

Sheets that are missing are simply treated as empty - the app will still
run on a workbook that only has the "Money Transfer to" sheet, it just
won't have any withdrawal/hold figures to show.
"""

import openpyxl


REQUIRED_SHEET = "Money Transfer to"
OPTIONAL_SHEETS = [
    "Withdrawal through ATM",
    "Cash Withdrawal through Cheque",
    "Transaction put on hold",
]


class ExtractionError(Exception):
    pass


def _clean_amt(v):
    """Turn a cell value like ' 1,23,456.00' or 1234 into a float, or None."""
    if v is None:
        return None
    s = str(v).strip().replace(",", "")
    if s == "":
        return None
    try:
        return round(float(s), 2)
    except ValueError:
        return None


def _clean_str(v):
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def _normalize_account(acct):
    """
    Bank statements sometimes render the SAME account number two different
    ways in different rows -- e.g. plain '34791803628' in one row and
    zero-padded '00000034791803628' in another (common with fixed-width
    CBS/IMPS reporting formats). Left as-is, the tool would treat these as
    two unrelated accounts, which can misclassify a real destination
    account as an untouched origin/"Victim's Account" if the padded and
    unpadded forms happen to land on opposite sides of a transfer.

    Purely numeric account numbers are normalized by stripping leading
    zeros so both forms collapse to one node. Anything non-numeric (UPI
    VPAs, card references, wallet IDs, etc.) is left completely untouched,
    since zero-stripping has no meaning for those and could corrupt a
    genuine identifier.
    """
    if acct is None:
        return acct
    s = str(acct).strip()
    if s.isdigit():
        stripped = s.lstrip("0")
        return stripped if stripped else "0"
    return s


def extract_data(xlsx_path):
    """
    Parse the workbook at xlsx_path and return a dict:

    {
        'ack_no': str,
        'nodes': [{'id','depth','bank'}, ...],
        'edges': [{'src','dst','layer','txn_id','amt','disputed','date',
                    'remarks','dest_bank','type'}, ...],
        'atm_totals':    {account_id: total_amount},
        'cheque_totals': {account_id: total_amount},
        'hold_totals':   {account_id: total_amount},
        'atm_txns':      {account_id: [ {date,amt,disputed,atm_id,place,remarks} ]},
        'cheque_txns':   {account_id: [ {date,amt,disputed,cheque_no,branch,remarks} ]},
        'total_atm': float, 'total_cheque': float, 'total_hold': float,
        'layer1_total': float,
    }
    """
    try:
        wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    except Exception as e:
        raise ExtractionError(f"Could not open workbook: {e}")

    if REQUIRED_SHEET not in wb.sheetnames:
        raise ExtractionError(
            f"This workbook has no '{REQUIRED_SHEET}' sheet. "
            f"Found sheets: {', '.join(wb.sheetnames)}"
        )

    # ---------------- main money-trail sheet ----------------
    ws = wb[REQUIRED_SHEET]
    rows = list(ws.iter_rows(min_row=2, max_row=ws.max_row, values_only=True))

    edges = []
    bank_map = {}
    ack_no = None

    for r in rows:
        if r is None or len(r) < 15:
            continue
        if r[2] is None or r[6] is None:
            continue
        src, dst = _normalize_account(str(r[2])), _normalize_account(str(r[6]))
        layer = r[5]
        txn_id = r[3]
        dest_bank = _clean_str(r[4])
        src_bank = _clean_str(r[14]) if len(r) > 14 else None
        amt = _clean_amt(r[10])
        disputed = _clean_amt(r[11])
        date = r[8]
        remarks = r[13] if len(r) > 13 else None
        ack_no = r[1] or ack_no

        edges.append({
            "src": src, "dst": dst, "layer": layer, "txn_id": txn_id,
            "amt": amt, "disputed": disputed,
            "date": str(date) if date else None,
            "remarks": _clean_str(remarks),
            "dest_bank": dest_bank, "type": "Transfer",
        })
        if dest_bank:
            bank_map[dst] = dest_bank
        if src_bank:
            bank_map.setdefault(src, src_bank)

    if not edges:
        raise ExtractionError(
            f"No usable rows found in the '{REQUIRED_SHEET}' sheet."
        )

    node_ids = set()
    for e in edges:
        node_ids.add(e["src"])
        node_ids.add(e["dst"])

    depth = {}
    for e in edges:
        d = e["layer"]
        if d is None:
            continue
        if e["dst"] not in depth or d < depth[e["dst"]]:
            depth[e["dst"]] = d
    for n in node_ids:
        if n not in depth:
            depth[n] = 0

    nodes = [{"id": n, "display_account": n, "depth": depth[n], "bank": bank_map.get(n, "Unknown")}
              for n in node_ids]
    node_by_acct_depth = {(n["id"], n["depth"]): n for n in nodes}
    nodes_by_id = {n["id"]: n for n in nodes}

    layer1_total = sum(e["amt"] for e in edges if e["layer"] == 1 and e["amt"])

    # ---------------- ATM withdrawals ----------------
    atm_totals, atm_txns = {}, {}
    if "Withdrawal through ATM" in wb.sheetnames:
        aws = wb["Withdrawal through ATM"]
        for r in aws.iter_rows(min_row=2, max_row=aws.max_row, values_only=True):
            if r is None or r[2] is None:
                continue
            acct = _normalize_account(str(r[2]))
            amt = _clean_amt(r[5]) if len(r) > 5 else None
            disputed = _clean_amt(r[6]) if len(r) > 6 else None
            if amt is not None:
                atm_totals[acct] = atm_totals.get(acct, 0) + amt
            atm_txns.setdefault(acct, []).append({
                "date": _clean_str(r[4]) if len(r) > 4 else None,
                "amt": amt,
                "disputed": disputed,
                "atm_id": _clean_str(r[7]) if len(r) > 7 else None,
                "place": _clean_str(r[8]) if len(r) > 8 else None,
                "remarks": _clean_str(r[10]) if len(r) > 10 else None,
            })

    # ---------------- Cheque withdrawals ----------------
    cheque_totals, cheque_txns = {}, {}
    if "Cash Withdrawal through Cheque" in wb.sheetnames:
        cws = wb["Cash Withdrawal through Cheque"]
        for r in cws.iter_rows(min_row=2, max_row=cws.max_row, values_only=True):
            if r is None or r[2] is None:
                continue
            acct = _normalize_account(str(r[2]))
            amt = _clean_amt(r[8]) if len(r) > 8 else None
            disputed = _clean_amt(r[9]) if len(r) > 9 else None
            if amt is not None:
                cheque_totals[acct] = cheque_totals.get(acct, 0) + amt
            cheque_txns.setdefault(acct, []).append({
                "date": _clean_str(r[7]) if len(r) > 7 else None,
                "amt": amt,
                "disputed": disputed,
                "cheque_no": r[6] if len(r) > 6 else None,
                "branch": _clean_str(r[10]) if len(r) > 10 else None,
                "remarks": _clean_str(r[13]) if len(r) > 13 else None,
            })

    # ---------------- Hold amounts ----------------
    hold_totals = {}
    if "Transaction put on hold" in wb.sheetnames:
        hws = wb["Transaction put on hold"]
        for r in hws.iter_rows(min_row=2, max_row=hws.max_row, values_only=True):
            if r is None or r[2] is None:
                continue
            acct = _normalize_account(str(r[2]))
            amt = _clean_amt(r[5]) if len(r) > 5 else None
            if amt is not None:
                hold_totals[acct] = hold_totals.get(acct, 0) + amt

    # ---------------- "Others Less Then 500" and "Other" sheets ----------------
    # These sheets list per-account entries (not src->dst transfers) tagged
    # with a Layer. Each entry is attached to the existing node for that
    # exact (account, layer) pair if one already exists; otherwise a new,
    # standalone node is created for that account at that layer (with no
    # connectors of its own, since these aren't transfer edges).
    extra_txns_by_node = {}
    new_node_lookup = {}  # (account, layer) -> node id, for nodes created here

    def _attach_extra_txn(acct, layer, txn, bank_for_new_node):
        if layer is None:
            return
        existing = node_by_acct_depth.get((acct, layer))
        if existing is not None:
            node_id = existing["id"]
        else:
            node_id = new_node_lookup.get((acct, layer))
            if node_id is None:
                node_id = f"{acct}__L{layer}"
                new_node_lookup[(acct, layer)] = node_id
                new_node = {
                    "id": node_id, "display_account": acct, "depth": layer,
                    "bank": bank_for_new_node or "Unknown",
                }
                nodes.append(new_node)
                nodes_by_id[node_id] = new_node
                node_by_acct_depth[(acct, layer)] = new_node
        extra_txns_by_node.setdefault(node_id, []).append(txn)

    if "Others Less Then 500" in wb.sheetnames:
        ows = wb["Others Less Then 500"]
        for r in ows.iter_rows(min_row=2, max_row=ows.max_row, values_only=True):
            if r is None or r[2] is None:
                continue
            acct = _normalize_account(str(r[2]))
            layer = r[8] if len(r) > 8 else None
            bank = _clean_str(r[6]) if len(r) > 6 else None
            txn = {
                "txn_id": r[3] if len(r) > 3 else None,
                "date": _clean_str(r[7]) if len(r) > 7 else None,  # Date of Action (only date field on this sheet)
                "amt": None,
                "disputed": None,
                "remarks": _clean_str(r[5]) if len(r) > 5 else None,
                "type": "Other (below Rs. 500)",
                "show_remarks": True,
            }
            _attach_extra_txn(acct, layer, txn, bank)

    if "Other" in wb.sheetnames:
        ows2 = wb["Other"]
        for r in ows2.iter_rows(min_row=2, max_row=ows2.max_row, values_only=True):
            if r is None or r[2] is None:
                continue
            acct = _normalize_account(str(r[2]))
            layer = r[10] if len(r) > 10 else None
            bank = _clean_str(r[8]) if len(r) > 8 else None
            txn = {
                "txn_id": r[3] if len(r) > 3 else None,
                "date": _clean_str(r[4]) if len(r) > 4 else None,
                "amt": _clean_amt(r[5]) if len(r) > 5 else None,
                "disputed": None,
                "remarks": _clean_str(r[7]) if len(r) > 7 else None,
                "type": "Other",
                "show_remarks": True,
            }
            _attach_extra_txn(acct, layer, txn, bank)

    data = {
        "ack_no": ack_no,
        "nodes": nodes,
        "edges": edges,
        "atm_totals": atm_totals,
        "cheque_totals": cheque_totals,
        "hold_totals": hold_totals,
        "atm_txns": atm_txns,
        "cheque_txns": cheque_txns,
        "extra_txns_by_node": extra_txns_by_node,
        "total_atm": sum(atm_totals.values()),
        "total_cheque": sum(cheque_totals.values()),
        "total_hold": sum(hold_totals.values()),
        "layer1_total": layer1_total,
        "source_file": str(xlsx_path),
    }
    return data
