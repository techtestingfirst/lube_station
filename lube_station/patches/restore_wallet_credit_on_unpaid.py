"""Restore wallet credit deducted at invoice generation (pre-paid model).

Before this change, apply_credit reduced credit_balance when the invoice was
generated, even though the invoice was still Unpaid. Deduction now happens in
consume_credit() on the Paid transition, so every still-open (or cancelled)
invoice with credit_applied holds money the wallet already lost: add it back.

Paid invoices are already correct (deducted once at generation, owed). Runs
post-model-sync, once per site.
"""

import frappe


def execute():
    rows = frappe.db.get_all(
        "Hosting Invoice",
        {"credit_applied": [">", 0], "status": ["in", ["Draft", "Unpaid", "Overdue", "Cancelled"]]},
        ["name", "customer", "credit_applied"],
    )
    for r in rows:
        try:
            doc = frappe.get_doc("Hosting Customer", r["customer"])
            doc.credit_balance = (doc.credit_balance or 0) + float(r["credit_applied"] or 0)
            doc.save(ignore_permissions=True)
        except Exception:
            continue
