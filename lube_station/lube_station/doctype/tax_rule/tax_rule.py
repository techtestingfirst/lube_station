import frappe
from frappe.model.document import Document


class TaxRule(Document):
    def validate(self):
        if (self.percentage or 0) < 0:
            frappe.throw("Percentage cannot be negative")


def matching_rules(customer: str) -> list:
    group = frappe.db.get_value("Hosting Customer", customer, "client_group")
    rules = frappe.get_all("Tax Rule", filters={"active": 1}, fields=["name"])
    out = []
    for r in rules:
        doc = frappe.get_doc("Tax Rule", r.name)
        if doc.eligible_groups:
            allowed = [g.client_group for g in doc.eligible_groups]
            if group not in allowed:
                continue
        out.append(doc)
    return out


def tax_for(customer: str, subtotal: float) -> float:
    total = 0
    for rule in matching_rules(customer):
        total += subtotal * (rule.percentage or 0) / 100
    return round(total, 2)
