import frappe
from frappe.model.document import Document
from frappe.utils import add_to_date, today


def _log(doc, msg: str):
    doc.provisioning_log = ((doc.provisioning_log or "") + f"\n{msg}").strip()[-2000:]
    doc.save(ignore_permissions=True)


class Service(Document):
    def activate(self):
        if self.status == "Terminated":
            frappe.throw("Terminated services stay terminated")
        self.status = "Active"
        self.save(ignore_permissions=True)
        _log(self, "activated")

    def suspend(self, reason: str = ""):
        if self.status != "Active":
            frappe.throw(f"Cannot suspend from {self.status}")
        self.status = "Suspended"
        self.save(ignore_permissions=True)
        _log(self, f"suspended {reason}")

    def unsuspend(self):
        if self.status != "Suspended":
            frappe.throw(f"Cannot unsuspend from {self.status}")
        self.status = "Active"
        self.save(ignore_permissions=True)
        _log(self, "unsuspended")

    def terminate(self, approval_note: str | None = None):
        if not approval_note:
            frappe.throw("Termination needs approval note")
        self.status = "Terminated"
        self.save(ignore_permissions=True)
        _log(self, f"terminated: {approval_note}")


@frappe.whitelist(methods=["POST"])
def create_from_order(order: str) -> dict:
    order_doc = frappe.get_doc("Order", order)
    if not order_doc.customer:
        frappe.throw("Order has no customer")
    made = []
    for item in order_doc.items:
        if item.item_type != "Hosting Plan" or not frappe.db.exists("Hosting Plan", item.reference):
            continue
        plan = frappe.get_doc("Hosting Plan", item.reference)
        price = frappe.db.get_value("Plan Pricing", {"hosting_plan": plan.name, "billing_cycle": item.billing_cycle}, "recurring_amount") or item.unit_price
        svc = frappe.get_doc({"doctype": "Service", "customer": order_doc.customer, "hosting_plan": plan.name, "order_ref": order, "billing_cycle": item.billing_cycle, "status": "Pending", "next_due_date": add_to_date(today(), months=1), "recurring_amount": price}).insert(ignore_permissions=True)
        made.append(svc.name)
    return {"services": made}


@frappe.whitelist(methods=["POST"])
def on_invoice_paid(invoice: str) -> dict:
    inv = frappe.get_doc("Hosting Invoice", invoice)
    if inv.status != "Paid":
        return {"action": "none"}
    out = []
    if inv.order_ref:
        for svc in frappe.get_all("Service", {"order_ref": inv.order_ref}, ["name", "status"]):
            doc = frappe.get_doc("Service", svc.name)
            if doc.status == "Pending":
                doc.activate()
                out.append(doc.name)
            elif doc.status == "Suspended":
                doc.unsuspend()
                out.append(doc.name)
    return {"action": "activated", "services": out}


@frappe.whitelist(methods=["POST"])
def apply_dunning(invoice: str) -> dict:
    from lube_station.lube_station.doctype.dunning_rule.dunning_rule import evaluate_invoice

    result = evaluate_invoice(invoice)
    inv = frappe.get_doc("Hosting Invoice", invoice)
    if not inv.order_ref:
        return result
    if result["action"] == "suspend":
        for svc in frappe.get_all("Service", {"order_ref": inv.order_ref, "status": "Active"}, ["name"]):
            frappe.get_doc("Service", svc.name).suspend(f"invoice {invoice} overdue")
    return result
