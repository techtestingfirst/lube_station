"""Digio eKYC glue via the ekyc_india app (live creds land later).

Manual stays the default (Lube Station Settings -> kyc_provider). When the
seller flips it to Digio:

* request flow calls start_digio_verification() after creating our local
  Pending row; any Digio failure raises a friendly error and the local row
  stays Pending for retry,
* status flows back through ekyc's Digio Request Log, and on_digio_log_update
  mirrors it into our verification rows (verify + auto-activate paid-pending
  services, or fail/expire with notice).

Runs unprivileged-safe: the webhook request executes as Guest, so every
write here uses ignore_permissions and no role checks.
"""

import frappe


def active_provider() -> str:
    from lube_station.lube_station.settings import get_setting

    provider = get_setting("kyc_provider") or "Manual"
    return provider if provider in ("Manual", "Digio") else "Manual"


def start_digio_verification(customer: str) -> dict:
    """Send an eKYC request for a Hosting Customer via ekyc_india.

    Needs Desk config (manual gate): Digio Settings creds + an e-Signature
    Document row (DocType Hosting Customer, recipient field user). Raises a
    customer-safe error on any failure; the local Pending row is untouched.
    """
    try:
        from ekyc_india.ekyc_india.doctype.digio_settings.digio_settings import (
            make_ekyc_request,
        )
    except Exception:
        frappe.throw("Digio integration is not available right now, try again later")
    doc = frappe.get_doc("Hosting Customer", customer)
    try:
        make_ekyc_request(doc)
    except frappe.ValidationError:
        raise
    except Exception:
        frappe.throw("Could not reach Digio, please try again later")
    log = frappe.db.get_value(
        "Digio Request Log",
        {"linked_doctype": "Hosting Customer", "linked_docname": customer},
        ["name", "digio_id"],
        order_by="creation desc",
        as_dict=True,
    ) or {}
    return {"log": log.get("name"), "digio_id": log.get("digio_id")}


def _oldest_pending_kyc(customer: str) -> str | None:
    return frappe.db.get_value(
        "Customer KYC Verification",
        {"customer": customer, "status": "Pending"},
        "name",
        order_by="creation asc",
    )


def on_digio_log_update(doc, method=None) -> None:
    """Mirror an ekyc Digio Request Log change into our verification rows.

    Idempotent: acts only when a Pending row exists for the customer, so
    repeat webhooks are no-ops. In-flight statuses are ignored on purpose
    (Approved-vs-Completed semantics get confirmed against sandbox first).
    """
    try:
        if doc.get("linked_doctype") != "Hosting Customer":
            return
        if doc.get("request_type") not in (None, "", "eKYC"):
            return
        customer = doc.get("linked_docname")
        if not customer or not frappe.db.exists("Hosting Customer", customer):
            return
        from lube_station.lube_customers.doctype.customer_kyc_verification.customer_kyc_verification import (
            _apply_expired,
            _apply_failed,
            _apply_manual_review,
            _apply_verified,
        )

        status = doc.get("status")
        pending = _oldest_pending_kyc(customer)
        if status == "KYC Approved":
            if pending:
                _apply_verified(pending, "Digio eKYC approved")
        elif status in ("KYC Rejected", "KYC Terminated"):
            if pending:
                _apply_failed(pending, f"Digio reported {status}")
        elif status == "KYC Expired":
            if pending:
                _apply_expired(pending, "Digio request expired")
        elif status == "KYC Review Ready":
            if pending:
                _apply_manual_review(pending, "Digio asked for manual review")
    except Exception:
        frappe.log_error(
            title="KYC Digio mirror failed", message=frappe.get_traceback()
        )
