import frappe
from frappe.model.document import Document
from frappe.utils import add_days, today


class HostingInvoice(Document):
    def validate(self):
        items_total = sum(i.amount or 0 for i in self.invoice_items)
        self.total_due = max(items_total + (self.tax_amount or 0) - (self.credit_applied or 0), 0)


def _from_order(order_name: str, key: str, gateway: str | None = None):
    order = frappe.get_doc("Order", order_name)
    customer = order.customer
    if not customer:
        frappe.throw("Order has no customer")
    items = [{"description": f"{i.item_type}: {i.reference} x{i.quantity}", "service_ref": i.reference, "amount": (i.unit_price or 0) * (i.quantity or 1)} for i in order.items]
    items_total = sum(i["amount"] for i in items)
    tax = 0
    if frappe.db.exists("DocType", "Tax Rule"):
        from lube_station.lube_station.doctype.tax_rule.tax_rule import tax_for

        tax = tax_for(customer, items_total)
    credit = 0
    if frappe.db.exists("DocType", "Credit Note"):
        from lube_station.lube_station.doctype.credit_note.credit_note import apply_credit

        credit = apply_credit(customer, items_total + tax)
    doc = frappe.get_doc(
        {
            "doctype": "Hosting Invoice",
            "customer": customer,
            "order_ref": order_name,
            "invoice_items": items,
            "tax_amount": tax,
            "credit_applied": credit,
            "due_date": add_days(today(), 7),
            "status": "Unpaid",
            "gateway": gateway,
            "idempotency_key": key,
        }
    ).insert()
    return doc


@frappe.whitelist(methods=["POST"])
def generate_invoice(order: str, gateway: str | None = None) -> dict:
    key = f"init:{order}"
    if frappe.db.exists("Hosting Invoice", {"idempotency_key": key}):
        doc = frappe.get_doc("Hosting Invoice", {"idempotency_key": key})
        return {"invoice": doc.name, "total_due": doc.total_due, "reused": True}
    doc = _from_order(order, key, gateway)
    return {"invoice": doc.name, "total_due": doc.total_due, "reused": False}


@frappe.whitelist(methods=["POST"])
def generate_renewal(order: str, period: str, gateway: str | None = None) -> dict:
    key = f"renew:{order}:{period}"
    if frappe.db.exists("Hosting Invoice", {"idempotency_key": key}):
        doc = frappe.get_doc("Hosting Invoice", {"idempotency_key": key})
        return {"invoice": doc.name, "total_due": doc.total_due, "reused": True}
    doc = _from_order(order, key, gateway)
    return {"invoice": doc.name, "total_due": doc.total_due, "reused": False}
