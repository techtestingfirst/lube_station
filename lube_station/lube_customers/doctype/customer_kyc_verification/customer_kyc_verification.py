import uuid

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class CustomerKYCVerification(Document):
    pass


def _touch_customer(customer: str, status: str, reference: str | None = None) -> None:
    update = {"kyc_status": status}
    if reference:
        update["kyc_reference"] = reference
    if status == "Verified":
        update["kyc_verified_on"] = now_datetime()
    frappe.db.set_value("Hosting Customer", customer, update)


def is_kyc_verified(customer: str | None) -> bool:
    if not customer:
        return False
    return frappe.db.get_value("Hosting Customer", customer, "kyc_status") == "Verified"


@frappe.whitelist(methods=["POST"])
def request_kyc(customer: str, provider: str = "Manual", ovd_type: str | None = None) -> dict:
    if provider not in ("Manual", "Digio Mock", "Digio"):
        frappe.throw("Unknown provider")
    if provider == "Digio" and not frappe.db.exists("DocType", "Digio Request Log"):
        frappe.throw("Digio not configured")
    roles = set(frappe.get_roles())
    if not roles.intersection({"System Manager", "Billing Admin", "Support Agent", "Provisioning Operator"}):
        linked = frappe.db.get_value("Hosting Customer", {"user": frappe.session.user}, "name")
        if linked != customer:
            frappe.throw("Can request KYC only for own customer", frappe.PermissionError)
    doc = frappe.get_doc(
        {
            "doctype": "Customer KYC Verification",
            "customer": customer,
            "status": "Pending",
            "provider": provider,
            "request_id": f"{provider}-{uuid.uuid4().hex[:12]}",
            "ovd_type": ovd_type or "",
        }
    ).insert(ignore_permissions=True)
    _touch_customer(customer, "Pending", doc.request_id)
    frappe.db.set_value("Hosting Customer", customer, {"consent": 1, "consent_on": now_datetime()})
    return {"name": doc.name, "request_id": doc.request_id, "status": "Pending"}


@frappe.whitelist(methods=["POST"])
def mark_verified(name: str, notes: str | None = None) -> dict:
    roles = set(frappe.get_roles())
    if not roles.intersection({"System Manager", "Billing Admin", "Support Agent"}):
        frappe.throw("Only staff can verify KYC", frappe.PermissionError)
    doc = frappe.get_doc("Customer KYC Verification", name)
    doc.status = "Verified"
    doc.verified_on = now_datetime()
    if notes:
        doc.notes = notes
    doc.save(ignore_permissions=True)
    _touch_customer(doc.customer, "Verified", doc.request_id)
    return {"status": "Verified"}


@frappe.whitelist(methods=["POST"])
def mark_manual_review(name: str, notes: str | None = None) -> dict:
    roles = set(frappe.get_roles())
    if not roles.intersection({"System Manager", "Billing Admin", "Support Agent"}):
        frappe.throw("Only staff can flag manual review", frappe.PermissionError)
    doc = frappe.get_doc("Customer KYC Verification", name)
    doc.status = "Manual Review"
    if notes:
        doc.notes = notes
    doc.save(ignore_permissions=True)
    _touch_customer(doc.customer, "Manual Review", doc.request_id)
    return {"status": "Manual Review"}
