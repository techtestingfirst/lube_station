import frappe

TEMPLATES = {
    "signup": "Welcome, account created",
    "order": "Order received",
    "invoice": "Invoice issued",
    "payment": "Payment confirmed",
    "renewal": "Renewal due",
    "overdue": "Invoice overdue",
    "suspension": "Service suspended",
    "unsuspension": "Service restored",
    "termination": "Service terminated",
    "credentials": "Provisioning ready, check portal vault",
    "domain_renewal": "Domain renewal due",
    "download": "Download available",
    "support": "Support ticket updated",
}


@frappe.whitelist(methods=["POST"])
def fire(event_type: str, reference: str, recipient: str | None = None) -> dict:
    if event_type not in TEMPLATES:
        frappe.throw("Unknown event")
    key = f"{event_type}:{reference}"
    if frappe.db.exists("Notification Event", {"event_key": key}):
        return {"reused": True, "key": key}
    frappe.get_doc({"doctype": "Notification Event", "event_key": key, "event_type": event_type, "reference": reference, "recipient": recipient}).insert(ignore_permissions=True)
    try:
        if recipient and "@" in recipient:
            frappe.sendmail(recipients=[recipient], subject=TEMPLATES[event_type], message=f"{TEMPLATES[event_type]} ref {reference}")
    except Exception:
        pass
    return {"reused": False, "key": key}
