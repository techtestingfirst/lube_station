"""Customer wallet: balance + unified transaction ledger.

No new DocType. Balance lives on Hosting Customer.credit_balance; movements
are derived from existing records:
  credit in  <- submitted Credit Notes (refunds, downgrade credit, goodwill)
  reserved   <- open invoice credit_applied (deducted only when Paid)
  consumed   <- Paid invoice credit_consumed (actually left the wallet)
Uses get_all (ignores perms, server-side logic) + my_customer ownership,
same pattern as portal my_invoices and support my_tickets.
"""

import frappe

from lube_station.lube_station.portal.apis import _plan_label
from lube_station.lube_station.portal.guards import my_customer


def _invoice_plan_labels(invoice: str) -> list:
    """Distinct 'Group PlanName' labels for an invoice. Never raises."""
    labels = []
    try:
        items = frappe.db.get_all("Invoice Item", {"parent": invoice}, ["service_ref"])
    except Exception:
        return labels
    for it in items:
        ref = (it.get("service_ref") or "").strip()
        if not ref:
            continue
        plan = None
        try:
            if frappe.db.exists("Service", ref):
                plan = frappe.db.get_value("Service", ref, "hosting_plan")
            elif frappe.db.exists("Hosting Plan", ref):
                plan = ref
        except Exception:
            continue
        if not plan:
            continue
        name, group = _plan_label(plan)
        label = f"{group} {name}".strip() if group else name
        if label and label not in labels:
            labels.append(label)
    return labels


@frappe.whitelist(methods=["GET"])
def my_wallet() -> dict:
    from lube_station.lube_customers.doctype.credit_note.credit_note import reserved_total

    customer = my_customer()
    balance = float(frappe.db.get_value("Hosting Customer", customer, "credit_balance") or 0)
    reserved = reserved_total(customer)
    return {
        "balance": balance,
        "reserved": reserved,
        "available": round(max(balance - reserved, 0), 2),
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
        ["name", "credit_applied", "credit_consumed", "creation", "status"],
    ):
        plans = _invoice_plan_labels(inv["name"])
        consumed = float(inv.get("credit_consumed") or 0)
        if inv["status"] == "Paid" and consumed > 0:
            state, amount = "consumed", -consumed
            desc = f"Wallet used on invoice {inv['name']} (Paid)"
        elif inv["status"] == "Cancelled":
            continue
        else:
            state, amount = "reserved", -float(inv["credit_applied"] or 0)
            desc = f"Reserved for invoice {inv['name']} ({inv['status']})"
        rows.append(
            {
                "date": inv["creation"],
                "kind": "debit",
                "state": state,
                "amount": amount,
                "description": desc,
                "plans": plans,
                "ref": inv["name"],
                "ref_type": "Hosting Invoice",
            }
        )
    rows.sort(key=lambda d: str(d["date"] or ""), reverse=True)
    return rows[:limit]
