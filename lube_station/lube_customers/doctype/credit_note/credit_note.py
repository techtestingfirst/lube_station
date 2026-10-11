import frappe
from frappe.model.document import Document

# Invoices holding a wallet reservation: payable, never settled.
OPEN_STATUSES = ("Draft", "Unpaid", "Overdue")


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
        try:
            from lube_station.lube_station.notifications.events import notify_customer

            notify_customer(self.customer, "credit", self.name, {"credit_note": self.name, "amount": self.amount, "invoice": self.get("reference_invoice") or ""})
        except Exception:
            pass

    def on_cancel(self):
        _adjust_balance(self.customer, -1 * self.amount)


def reserved_total(customer: str, exclude_invoice: str | None = None) -> float:
    """Wallet amount reserved by open invoices (not yet paid, never deducted)."""
    filters: dict = {"customer": customer, "status": ["in", list(OPEN_STATUSES)], "credit_applied": [">", 0]}
    rows = frappe.db.get_all("Hosting Invoice", filters, ["name", "credit_applied"])
    total = 0.0
    for r in rows:
        if exclude_invoice and r["name"] == exclude_invoice:
            continue
        total += float(r["credit_applied"] or 0)
    return round(total, 2)


def available_credit(customer: str, exclude_invoice: str | None = None) -> float:
    """Spendable wallet balance: balance minus open reservations. Never negative."""
    balance = float(frappe.db.get_value("Hosting Customer", customer, "credit_balance") or 0)
    return round(max(balance - reserved_total(customer, exclude_invoice), 0), 2)


def apply_credit(customer: str, invoice_total: float, exclude_invoice: str | None = None) -> float:
    """Reserve wallet credit for an invoice total. Never touches the balance.

    Deduction happens once, in consume_credit(), when the invoice is Paid.
    """
    return round(min(available_credit(customer, exclude_invoice), max(float(invoice_total or 0), 0)), 2)


def consume_credit(invoice_name: str, allow_unpaid_zero: bool = False) -> float:
    """Deduct a Paid invoice's reserved credit from the wallet. Idempotent.

    allow_unpaid_zero covers fully-covered (total_due 0) invoices: no payment
    will ever arrive, so the reservation settles at generation instead of
    sitting open forever.
    """
    inv = frappe.db.get_value(
        "Hosting Invoice",
        invoice_name,
        ["customer", "status", "total_due", "credit_applied", "credit_consumed"],
        as_dict=True,
    )
    if not inv:
        return 0
    if inv["status"] != "Paid" and not (
        allow_unpaid_zero and float(inv["total_due"] or 0) == 0
    ):
        return 0
    due = float(inv["credit_applied"] or 0) - float(inv["credit_consumed"] or 0)
    if due <= 0:
        return 0
    balance = float(frappe.db.get_value("Hosting Customer", inv["customer"], "credit_balance") or 0)
    take = round(min(due, max(balance, 0)), 2)
    if take <= 0:
        return 0
    _adjust_balance(inv["customer"], -take)
    frappe.db.set_value(
        "Hosting Invoice", invoice_name, "credit_consumed", round(float(inv["credit_consumed"] or 0) + take, 2)
    )
    return take
