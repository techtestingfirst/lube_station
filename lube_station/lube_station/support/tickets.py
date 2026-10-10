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
    try:
        from lube_station.lube_station.notifications.events import notify_customer

        notify_customer(customer, "support_opened", ticket.name, {"ticket": ticket.name, "subject": subject, "service": service or "", "priority": ticket.priority})
        notify_customer(customer, "support", f"{ticket.name}:open", {"ticket": ticket.name, "subject": subject})
    except Exception:
        pass
    return {"ticket": ticket.name, "priority": ticket.priority, "response_by": str(ticket.response_by)}


@frappe.whitelist(methods=["POST"])
def notify_reply(ticket: str, message: str = "") -> dict:
    """WHMCS support reply / status notices. Called by HD hooks or staff."""
    try:
        ref = frappe.get_doc("Ticket Hosting Reference", {"ticket": ticket})
        customer = ref.customer
    except Exception:
        customer = None
    try:
        from lube_station.lube_station.notifications.events import notify_customer

        notify_customer(customer, "support_reply", f"{ticket}:reply", {"ticket": ticket, "message": message[:500]})
    except Exception:
        pass
    return {"notified": bool(customer)}


@frappe.whitelist(methods=["POST"])
def notify_status(ticket: str, status: str) -> dict:
    try:
        ref = frappe.get_doc("Ticket Hosting Reference", {"ticket": ticket})
        customer = ref.customer
    except Exception:
        customer = None
    try:
        from lube_station.lube_station.notifications.events import notify_customer

        event = "support_closed" if status.lower() in ("closed", "resolved") else "support_status"
        notify_customer(customer, event, f"{ticket}:{status}", {"ticket": ticket, "status": status})
    except Exception:
        pass
    return {"notified": bool(customer)}
