from datetime import date

import frappe
from frappe.model.document import Document


class DunningRule(Document):
    def validate(self):
        if (self.grace_days or 0) < 0 or (self.termination_days or 0) < 0:
            frappe.throw("Days cannot be negative")
        if (self.termination_days or 0) < (self.grace_days or 0):
            frappe.throw("Termination must be >= grace")


def _rule_for_invoice(invoice) -> Document | None:
    plan = None
    if invoice.order_ref:
        order = frappe.get_doc("Order", invoice.order_ref)
        if order.items:
            ref = order.items[0].reference
            if frappe.db.exists("Hosting Plan", ref):
                plan = frappe.get_doc("Hosting Plan", ref)
    if plan:
        rule = frappe.db.get_value("Dunning Rule", {"hosting_plan": plan.name, "active": 1}, "name")
        if rule:
            return frappe.get_doc("Dunning Rule", rule)
        if plan.product_type:
            rule = frappe.db.get_value("Dunning Rule", {"product_type": plan.product_type, "active": 1}, "name")
            if rule:
                return frappe.get_doc("Dunning Rule", rule)
    rule = frappe.db.get_value("Dunning Rule", {"hosting_plan": ["in", ["", None]], "active": 1}, "name")
    return frappe.get_doc("Dunning Rule", rule) if rule else None


@frappe.whitelist(methods=["GET", "POST"])
def evaluate_invoice(invoice: str, today: date | str | None = None) -> dict:
    inv = frappe.get_doc("Hosting Invoice", invoice)
    if inv.status == "Paid":
        return {"action": "none", "reason": "paid"}
    due = inv.due_date
    if isinstance(today, str):
        today = date.fromisoformat(today)
    today = today or date.today()
    overdue = (today - due).days if due else 0
    rule = _rule_for_invoice(inv)
    grace = rule.grace_days if rule else 7
    term = rule.termination_days if rule else 30
    if overdue >= term:
        return {"action": "queue_termination", "overdue_days": overdue, "needs_approval": True}
    if overdue >= grace:
        return {"action": "suspend", "overdue_days": overdue}
    return {"action": "notify", "overdue_days": overdue}
