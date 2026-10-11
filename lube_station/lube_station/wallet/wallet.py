"""Customer wallet: balance + unified transaction ledger.

No new DocType. Balance lives on Hosting Customer.credit_balance; movements
are derived from existing records:
  credit in  <- submitted Credit Notes (refunds, downgrade credit, goodwill)
  credit out -> Hosting Invoice.credit_applied (consumed at generation)
Uses get_all (ignores perms, server-side logic) + my_customer ownership,
same pattern as portal my_invoices and support my_tickets.
"""

import frappe

from lube_station.lube_station.portal.guards import my_customer


@frappe.whitelist(methods=["GET"])
def my_wallet() -> dict:
    customer = my_customer()
    balance = frappe.db.get_value("Hosting Customer", customer, "credit_balance") or 0
    return {
        "balance": float(balance),
        "credits_in": frappe.db.count("Credit Note", {"customer": customer, "docstatus": 1}),
    }


@frappe.whitelist(methods=["GET"])
def my_wallet_transactions(limit: int = 50) -> list:
    customer = my_customer()
    limit = max(1, min(int(limit or 50), 100))
    rows = []
    for cn in frappe.db.get_all(
        "Credit Note",
        {"customer": customer, "docstatus": 1},
        ["name", "amount", "reason", "creation"],
    ):
        rows.append(
            {
                "date": cn["creation"],
                "kind": "credit",
                "amount": float(cn["amount"] or 0),
                "description": cn["reason"] or "Credit added",
                "ref": cn["name"],
                "ref_type": "Credit Note",
            }
        )
    for inv in frappe.db.get_all(
        "Hosting Invoice",
        {"customer": customer, "credit_applied": [">", 0]},
        ["name", "credit_applied", "creation", "status"],
    ):
        rows.append(
            {
                "date": inv["creation"],
                "kind": "debit",
                "amount": -float(inv["credit_applied"] or 0),
                "description": f"Applied to invoice {inv['name']} ({inv['status']})",
                "ref": inv["name"],
                "ref_type": "Hosting Invoice",
            }
        )
    rows.sort(key=lambda d: str(d["date"] or ""), reverse=True)
    return rows[:limit]
