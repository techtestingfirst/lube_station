"""Backfill Service.next_due_date from paid invoice history (one-shot).

next_due_date was set once at creation and never advanced, so live values
are stale. Reconstruct: last Paid invoice on the service's order + one
billing cycle; never-paid services fall back to creation + one cycle.
Skips Terminated/Cancelled services. Safe to run once per site.
"""

import frappe
from frappe.utils import add_to_date, getdate

CYCLE_MONTHS = {
    "Monthly": 1,
    "Quarterly": 3,
    "Semi-Annually": 6,
    "Annually": 12,
    "Biennially": 24,
    "Triennially": 36,
}


def execute():
    for svc in frappe.db.get_all(
        "Service",
        {"status": ["not in", ["Terminated", "Cancelled"]]},
        ["name", "order_ref", "billing_cycle", "creation"],
    ):
        try:
            months = CYCLE_MONTHS.get(svc.get("billing_cycle"), 1)
            base = None
            if svc.get("order_ref"):
                last_paid = frappe.db.get_all(
                    "Hosting Invoice",
                    {"order_ref": svc["order_ref"], "status": "Paid"},
                    ["modified"],
                    order_by="modified desc",
                    limit=1,
                )
                if last_paid:
                    base = getdate(last_paid[0]["modified"])
            if base is None:
                created = getdate(svc.get("creation")) if svc.get("creation") else getdate()
                base = created
            frappe.db.set_value("Service", svc["name"], "next_due_date", add_to_date(base, months=months))
        except Exception:
            continue
