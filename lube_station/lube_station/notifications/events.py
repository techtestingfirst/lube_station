import frappe

# WHMCS parity: General, Product/Service, Domain, Invoice, Support, Affiliate.
# Trigger map (event -> producer). Events with no producer yet are reserved
# for the per-plan Dunning Step engine / registrar webhooks; fire() rejects
# unknown events but never invents mail for reserved ones.
#   signup -> portal/apis.py signup_customer
#   order, invoice -> portal/apis.py checkout via place_order/generate_invoice
#   payment, credentials -> hosting_invoice._fulfill_order on Paid
#   welcome, credentials, suspension, unsuspension, termination,
#     cancellation_confirm -> Service lifecycle (service.py)
#   invoice_reminder, overdue_first, overdue_third -> apply_dunning (service.py)
#   payment_failed -> auto_charge_invoice / gateway webhooks
#   refund, credit -> issue_refund / CreditNote.on_submit
#   renewal -> renewal invoice; renewal_confirm -> on_invoice_paid
#   domain_* -> registered_domain.py; support_* -> support/tickets.py
#   affiliate_signup, affiliate_commission -> affiliate.py / metrics.py
#   download -> downloadable_asset.log_download
#   password_reset -> audit only (Frappe core sends the link)
# Reserved (no producer yet): email_verification, overdue, overdue_second,
#   trial_ending, domain_expired, domain_transfer_away, domain_contact_update,
#   affiliate_withdrawal.
TEMPLATES = {
    "signup": "Welcome, account created",
    "email_verification": "Please verify your email",
    "password_reset": "Password reset requested",
    "order": "Order received",
    "invoice": "Invoice issued",
    "invoice_reminder": "Invoice payment reminder",
    "overdue": "Invoice overdue",
    "overdue_first": "First invoice overdue notice",
    "overdue_second": "Second invoice overdue notice",
    "overdue_third": "Final invoice overdue notice",
    "payment": "Payment confirmed",
    "payment_failed": "Payment failed",
    "refund": "Refund issued",
    "credit": "Account credit applied",
    "welcome": "Service activated, welcome",
    "credentials": "Provisioning ready, check portal vault",
    "upgrade": "Service upgraded",
    "suspension": "Service suspended",
    "unsuspension": "Service restored",
    "termination": "Service terminated",
    "cancellation_request": "Cancellation requested",
    "cancellation_confirm": "Cancellation confirmed",
    "renewal": "Renewal due",
    "renewal_confirm": "Renewal confirmed",
    "trial_ending": "Trial ending soon",
    "domain_registered": "Domain registered",
    "domain_transfer_initiated": "Domain transfer started",
    "domain_transfer_completed": "Domain transfer completed",
    "domain_renewal": "Domain renewal due",
    "domain_renewed": "Domain renewed",
    "domain_expiry_warning": "Domain expiring soon",
    "domain_expired": "Domain expired",
    "domain_transfer_away": "Domain transferred away",
    "domain_contact_update": "Domain contact updated",
    "domain_ns_update": "Domain nameservers updated",
    "support": "Support ticket updated",
    "support_opened": "Support ticket opened",
    "support_reply": "Support ticket reply",
    "support_status": "Support ticket status changed",
    "support_closed": "Support ticket closed",
    "affiliate_signup": "Affiliate welcome",
    "affiliate_commission": "Affiliate commission earned",
    "affiliate_withdrawal": "Affiliate payout sent",
    "download": "Download available",
    "kyc_required": "Identity verification needed to activate services",
    "kyc_verified": "Identity verification complete",
    "kyc_failed": "Identity verification needs attention",
}


def customer_email(customer: str | None) -> str | None:
    """Customer portal email for a Hosting Customer, or None."""
    if not customer:
        return None
    try:
        user = frappe.db.get_value("Hosting Customer", customer, "user")
        return frappe.db.get_value("User", user, "email") if user else None
    except Exception:
        return None


def _sender() -> str | None:
    try:
        from lube_station.lube_station.settings import get_setting

        sender = get_setting("support_email")
        return sender or None
    except Exception:
        return None


def _context_for(event_type: str, reference: str, context: dict | None) -> dict:
    base = {"event": event_type, "reference": reference}
    if context:
        base.update(context)
    return base


def _render_with_template(template_name: str | None, ctx: dict) -> dict | None:
    """Render Email Template if it exists, else None (fallback to plain)."""
    if not template_name:
        return None
    try:
        if not frappe.db.exists("Email Template", template_name):
            return None
        tpl = frappe.get_doc("Email Template", template_name)
        out = tpl.get_formatted_email(ctx)
        return {"subject": out.get("subject"), "message": out.get("message")}
    except Exception:
        return None


def _default_template_name(event_type: str) -> str:
    return f"Lube {event_type.replace('_', ' ').title()}"


def notify_customer(customer: str | None, event_type: str, reference: str, context: dict | None = None, template: str | None = None) -> dict:
    return fire(event_type, reference, customer_email(customer), context, template)


@frappe.whitelist(methods=["POST"])
def fire(event_type: str, reference: str, recipient: str | None = None, context: dict | None = None, template: str | None = None, send_mail: bool = True) -> dict:
    if event_type not in TEMPLATES:
        frappe.throw("Unknown event")
    if not isinstance(reference, str) or not reference.strip():
        frappe.throw("Reference required")
    if recipient is not None and not isinstance(recipient, str):
        frappe.throw("Invalid recipient")
    key = f"{event_type}:{reference.strip()}"
    if frappe.db.exists("Notification Event", {"event_key": key}):
        return {"reused": True, "key": key}
    frappe.get_doc({"doctype": "Notification Event", "event_key": key, "event_type": event_type, "reference": reference.strip(), "recipient": recipient}).insert(ignore_permissions=True)
    if send_mail and recipient and "@" in recipient:
        _send(event_type, recipient, reference.strip(), context, template)
    return {"reused": False, "key": key}


def _send(event_type: str, recipient: str, reference: str, context: dict | None, template: str | None):
    ctx = _context_for(event_type, reference, context)
    rendered = _render_with_template(template, ctx)
    if not rendered:
        rendered = _render_with_template(_default_template_name(event_type), ctx)
    if rendered and rendered.get("subject"):
        subject = rendered["subject"]
        message = rendered["message"]
    else:
        subject = TEMPLATES[event_type]
        lines = [f"{subject} ref {reference}"]
        for k in sorted((context or {}).keys()):
            lines.append(f"{k}: {context[k]}")
        message = "\n".join(lines)
    try:
        # now=True: transactional mail sends over SMTP immediately instead of
        # waiting for the scheduler's Email Queue flush (scheduler off == silent pile-up).
        frappe.sendmail(recipients=[recipient], subject=subject, message=message, sender=_sender(), now=True)
    except Exception:
        pass
