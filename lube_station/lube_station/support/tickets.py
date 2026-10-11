import frappe
from frappe.utils import add_to_date, now_datetime

from lube_station.lube_station.portal.guards import assert_owns, my_customer

from .sla import priority_for, sla_hours

TICKET_FIELDS = ["name", "subject", "status", "priority", "modified", "response_by", "raised_by"]


def _product_type(service: str | None) -> str | None:
    if service and frappe.db.exists("Service", service):
        plan = frappe.db.get_value("Service", service, "hosting_plan")
        if plan:
            return frappe.db.get_value("Hosting Plan", plan, "product_type")
    return None


def _is_staff() -> bool:
    return "System Manager" in frappe.get_roles()


def _resolve_customer(customer: str | None, service: str | None, invoice: str | None) -> str:
    if customer:
        if not frappe.db.exists("Hosting Customer", customer):
            frappe.throw("Unknown customer", frappe.DoesNotExistError)
    elif service and frappe.db.exists("Service", service):
        customer = frappe.db.get_value("Service", service, "customer")
    elif invoice and frappe.db.exists("Hosting Invoice", invoice):
        customer = frappe.db.get_value("Hosting Invoice", invoice, "customer")
    if not customer:
        customer = my_customer()
    if not _is_staff():
        assert_owns(customer)
    if service and frappe.db.exists("Service", service):
        owner = frappe.db.get_value("Service", service, "customer")
        if owner != customer:
            frappe.throw("Service does not belong to customer", frappe.ValidationError)
    if invoice and frappe.db.exists("Hosting Invoice", invoice):
        owner = frappe.db.get_value("Hosting Invoice", invoice, "customer")
        if owner != customer:
            frappe.throw("Invoice does not belong to customer", frappe.ValidationError)
    return customer


def _raised_by_email(customer: str | None) -> str:
    if customer and frappe.db.exists("Hosting Customer", customer):
        user = frappe.db.get_value("Hosting Customer", customer, "user")
        if user:
            return user
    return frappe.session.user


def _ensure_hd_customer_role(user: str | None) -> None:
    """Grant HD Customer so the native Helpdesk chain works as designed.

    Helpdesk's portal reply path (Communication.on_update ->
    on_communication_update -> ticket.save()) assumes the actor holds HD
    Ticket write via role. Same role unlocks /helpdesk/my-tickets deep links.
    Called from POST endpoints only (they commit); GET readers need no roles.
    """
    if not user or user in ("Administrator", "Guest"):
        return
    if not frappe.db.exists("Role", "HD Customer"):
        return
    if frappe.db.exists("Has Role", {"parent": user, "role": "HD Customer"}):
        return
    original = frappe.session.user
    try:
        frappe.set_user("Administrator")
        frappe.get_doc("User", user).add_roles("HD Customer")
    finally:
        frappe.set_user(original)


def auto_link_helpdesk_ticket(doc, method=None) -> None:
    """Link Helpdesk-created tickets back to the Hosting Customer.

    Wired as HD Ticket after_insert (hooks.py). Covers tickets customers open
    directly in the Helpdesk portal (/helpdesk/my-tickets/new), which bypass
    create_ticket and would otherwise vanish from the Lube My-tickets list
    and dashboard count. Idempotent: skips when a reference already exists
    (e.g. create_ticket inserts its own richer row right after).
    No service/invoice context here — customer linkage only.
    """
    if frappe.db.exists("Ticket Hosting Reference", {"ticket": doc.name}):
        return
    email = (getattr(doc, "raised_by", None) or "").strip()
    user = email if email and frappe.db.exists("User", email) else None
    if not user and getattr(doc, "contact", None):
        user = frappe.db.get_value("Contact", doc.contact, "user") or None
    customer = frappe.db.get_value("Hosting Customer", {"user": user}, "name") if user else None
    if not customer:
        return
    frappe.get_doc(
        {"doctype": "Ticket Hosting Reference", "ticket": doc.name, "customer": customer}
    ).insert(ignore_permissions=True)


def _ref_for_ticket_or_throw(ticket: str) -> dict:
    rows = frappe.db.get_all(
        "Ticket Hosting Reference",
        {"ticket": ticket},
        ["name", "ticket", "customer", "service", "invoice"],
    )
    if not rows:
        frappe.throw("Ticket not found", frappe.DoesNotExistError)
    ref = rows[0]
    if not _is_staff():
        assert_owns(ref["customer"])
    return ref


def _ticket_summary(name: str) -> dict:
    rows = frappe.db.get_all("HD Ticket", {"name": name}, TICKET_FIELDS)
    if not rows:
        frappe.throw("Ticket not found", frappe.DoesNotExistError)
    return rows[0]


@frappe.whitelist(methods=["POST"])
def create_ticket(subject: str, description: str, customer: str | None = None, service: str | None = None, invoice: str | None = None) -> dict:
    customer = _resolve_customer(customer, service, invoice)
    raised_by = _raised_by_email(customer)
    if not _is_staff():
        _ensure_hd_customer_role(raised_by)
    ptype = _product_type(service)
    ticket = frappe.get_doc(
        {
            "doctype": "HD Ticket",
            "subject": subject,
            "description": description,
            "priority": priority_for(ptype),
            "ticket_type": "Incident",
            "response_by": add_to_date(now_datetime(), hours=sla_hours(ptype)),
            # Helpdesk portal visibility: customer criteria match on raised_by.
            # Reference: helpdesk/.../hd_ticket/api.py new() sets raised_by +
            # via_customer_portal the same way.
            "raised_by": raised_by,
            "via_customer_portal": 1,
        }
    ).insert(ignore_permissions=True)
    # The after_insert hook above may have already linked this ticket (it runs
    # before this line). Enrich that row instead of colliding on unique ticket.
    existing = frappe.db.get_value("Ticket Hosting Reference", {"ticket": ticket.name}, "name")
    if existing:
        frappe.db.set_value(
            "Ticket Hosting Reference",
            existing,
            {"customer": customer, "service": service, "invoice": invoice},
        )
    else:
        frappe.get_doc({"doctype": "Ticket Hosting Reference", "ticket": ticket.name, "customer": customer, "service": service, "invoice": invoice}).insert(ignore_permissions=True)
    try:
        from lube_station.lube_station.notifications.events import notify_customer

        notify_customer(customer, "support_opened", ticket.name, {"ticket": ticket.name, "subject": subject, "service": service or "", "priority": ticket.priority})
        notify_customer(customer, "support", f"{ticket.name}:open", {"ticket": ticket.name, "subject": subject})
    except Exception:
        pass
    return {"ticket": ticket.name, "priority": ticket.priority, "response_by": str(ticket.response_by)}


@frappe.whitelist(methods=["GET"])
def my_tickets(limit: int = 50) -> list:
    """Customer ticket list. Ownership via Ticket Hosting Reference link table.

    Uses get_all (ignores perms, server-side logic) + manual assert_owns guard,
    same pattern as portal my_invoices/my_service_detail.
    """
    customer = my_customer()
    limit = max(1, min(int(limit or 50), 100))
    refs = frappe.db.get_all(
        "Ticket Hosting Reference",
        {"customer": customer},
        ["ticket", "service", "invoice"],
    )
    if not refs:
        return []
    names = [r["ticket"] for r in refs]
    tickets = frappe.db.get_all(
        "HD Ticket",
        {"name": ["in", names]},
        TICKET_FIELDS,
    )
    by_name = {t["name"]: t for t in tickets}
    out = []
    for r in refs:
        t = by_name.get(r["ticket"])
        if not t:
            continue
        out.append({**t, "service": r.get("service"), "invoice": r.get("invoice")})
    out.sort(key=lambda d: str(d.get("modified") or ""), reverse=True)
    return out[:limit]


@frappe.whitelist(methods=["GET"])
def my_ticket_detail(ticket: str) -> dict:
    """Single ticket + thread. Guarded per-ticket via link table."""
    ref = _ref_for_ticket_or_throw(ticket)
    comments = frappe.db.get_all(
        "HD Ticket Comment",
        {"reference_ticket": ticket},
        ["name", "content", "commented_by", "creation"],
        order_by="creation asc",
    )
    communications = frappe.db.get_all(
        "Communication",
        {"reference_doctype": "HD Ticket", "reference_name": ticket},
        ["name", "content", "sender", "sent_or_received", "communication_date", "creation"],
        order_by="creation asc",
    )
    return {
        "ticket": _ticket_summary(ticket),
        "reference": ref,
        "comments": comments,
        "communications": communications,
    }


@frappe.whitelist(methods=["POST"])
def add_ticket_reply(ticket: str, content: str) -> dict:
    """Customer reply. Uses Communication path (customer portal reply).

    Never HD Ticket Comment: new_comment() is agent-only
    (hd_ticket.py raises PermissionError for non-agents).
    Reference: test_hd_ticket.py "Customer portal reply" via
    create_communication_via_contact.
    """
    text = (content or "").strip()
    if not text:
        frappe.throw("Reply cannot be empty", frappe.ValidationError)
    if len(text) > 20000:
        frappe.throw("Reply too long", frappe.ValidationError)
    _ref_for_ticket_or_throw(ticket)
    if not _is_staff():
        _ensure_hd_customer_role(frappe.session.user)
    doc = frappe.get_doc("HD Ticket", ticket)
    # Native Helpdesk customer-reply path (same call TicketCustomer.vue makes
    # via run_doc_method). Ownership already guarded via link table above.
    doc.create_communication_via_contact(text)
    return {"replied": True}


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
