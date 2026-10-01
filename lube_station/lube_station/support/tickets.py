import frappe
from frappe.utils import add_to_date, now_datetime

from .sla import priority_for, sla_hours


def _product_type(service: str | None) -> str | None:
    if service and frappe.db.exists("Service", service):
        plan = frappe.db.get_value("Service", service, "hosting_plan")
        if plan:
            return frappe.db.get_value("Hosting Plan", plan, "product_type")
    return None


@frappe.whitelist(methods=["POST"])
def create_ticket(subject: str, description: str, customer: str | None = None, service: str | None = None, invoice: str | None = None) -> dict:
    ptype = _product_type(service)
    ticket = frappe.get_doc({"doctype": "HD Ticket", "subject": subject, "description": description, "status": "Open", "priority": priority_for(ptype), "ticket_type": "Incident", "response_by": add_to_date(now_datetime(), hours=sla_hours(ptype))}).insert(ignore_permissions=True)
    frappe.get_doc({"doctype": "Ticket Hosting Reference", "ticket": ticket.name, "customer": customer, "service": service, "invoice": invoice}).insert(ignore_permissions=True)
    return {"ticket": ticket.name, "priority": ticket.priority, "response_by": str(ticket.response_by)}
