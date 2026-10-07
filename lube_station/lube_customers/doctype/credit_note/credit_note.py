import frappe
from frappe.model.document import Document


def _adjust_balance(customer: str, delta: float):
    doc = frappe.get_doc("Hosting Customer", customer)
    doc.credit_balance = (doc.credit_balance or 0) + delta
    doc.save(ignore_permissions=True)


class CreditNote(Document):
    def validate(self):
        if (self.amount or 0) <= 0:
            frappe.throw("Credit amount must be positive")

    def on_submit(self):
        _adjust_balance(self.customer, self.amount)

    def on_cancel(self):
        _adjust_balance(self.customer, -1 * self.amount)


def apply_credit(customer: str, invoice_total: float) -> float:
    """Apply available credit to invoice total. Returns applied amount."""
    balance = frappe.db.get_value("Hosting Customer", customer, "credit_balance") or 0
    applied = min(balance, invoice_total)
    if applied > 0:
        _adjust_balance(customer, -1 * applied)
    return applied
