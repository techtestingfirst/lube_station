import uuid

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class CustomerKYCVerification(Document):
    def on_update(self):
        """Desk-driven transitions: changing Status + Save runs everything.

        Staff never needs an API call — the dropdown is the action. API and
        mirror paths set the same field and save, so they flow through here
        too (their writes touch other docs only, no recursion).
        """
        try:
            changed = self.has_value_changed("status")
        except Exception:
            changed = True
        if not changed:
            return
        _after_status_change(self.status, self.customer, self.request_id, self.provider)


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


def _after_status_change(status: str, customer: str, request_id: str | None, provider: str | None) -> None:
    """Shared side effects for Desk edits, staff API, and Digio mirror."""
    if status == "Verified":
        _touch_customer(customer, "Verified", request_id)
        try:
            from lube_station.lube_station.notifications.events import notify_customer

            notify_customer(customer, "kyc_verified", request_id or customer, {"provider": provider})
        except Exception:
            pass
        # Paid-but-waiting services activate now. Only orders with a Paid
        # invoice qualify: verification must never activate unpaid services.
        try:
            for svc in frappe.get_all(
                "Service", {"customer": customer, "status": "Pending"}, ["name", "order_ref"]
            ):
                try:
                    if svc.get("order_ref") and not frappe.db.exists(
                        "Hosting Invoice", {"order_ref": svc["order_ref"], "status": "Paid"}
                    ):
                        continue
                    sdoc = frappe.get_doc("Service", svc.name)
                    sdoc.activate()
                except Exception:
                    continue
        except Exception:
            pass
    elif status == "Failed":
        _touch_customer(customer, "Failed", request_id)
        try:
            from lube_station.lube_station.notifications.events import notify_customer

            notify_customer(customer, "kyc_failed", request_id or customer, {"provider": provider})
        except Exception:
            pass
    elif status == "Expired":
        _touch_customer(customer, "Expired", request_id)
        try:
            from lube_station.lube_station.notifications.events import notify_customer

            notify_customer(customer, "kyc_failed", request_id or customer, {"provider": provider, "reason": "expired"})
        except Exception:
            pass
    elif status == "Manual Review":
        _touch_customer(customer, "Manual Review", request_id)


def _notify_staff_manual_queue(customer: str, request_name: str, provider: str) -> None:
    """Tell the back office a Manual request waits. Best-effort, queued mail."""
    try:
        from lube_station.lube_station.settings import get_setting

        support = get_setting("support_email")
        if not support or "@" not in str(support):
            return
        frappe.sendmail(
            recipients=[support],
            subject=f"KYC review needed: {customer}",
            message=(
                f"Customer {customer} requested {provider} verification ({request_name}).\n"
                "Open Customer KYC Verification in Desk, review, and set Status."
            ),
        )
    except Exception:
        pass


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
    if provider in ("Manual", "Digio Mock"):
        _notify_staff_manual_queue(customer, doc.name, provider)
    return {"name": doc.name, "request_id": doc.request_id, "status": "Pending"}


@frappe.whitelist(methods=["POST"])
def mark_verified(name: str, notes: str | None = None) -> dict:
    roles = set(frappe.get_roles())
    if not roles.intersection({"System Manager", "Billing Admin", "Support Agent"}):
        frappe.throw("Only staff can verify KYC", frappe.PermissionError)
    return _apply_verified(name, notes)


def _apply_verified(name: str, notes: str | None = None) -> dict:
    """Core verify step without role checks (staff Desk + Digio mirror share it).

    Sets the field and saves; on_update runs the side effects.
    """
    doc = frappe.get_doc("Customer KYC Verification", name)
    doc.status = "Verified"
    doc.verified_on = now_datetime()
    if notes:
        doc.notes = notes
    doc.save(ignore_permissions=True)
    return {"status": "Verified"}


@frappe.whitelist(methods=["POST"])
def mark_manual_review(name: str, notes: str | None = None) -> dict:
    roles = set(frappe.get_roles())
    if not roles.intersection({"System Manager", "Billing Admin", "Support Agent"}):
        frappe.throw("Only staff can flag manual review", frappe.PermissionError)
    return _apply_manual_review(name, notes)


def _apply_manual_review(name: str, notes: str | None = None) -> dict:
    """Core manual-review step without role checks (sets field; on_update acts)."""
    doc = frappe.get_doc("Customer KYC Verification", name)
    doc.status = "Manual Review"
    if notes:
        doc.notes = notes
    doc.save(ignore_permissions=True)
    return {"status": "Manual Review"}


def _apply_failed(name: str, notes: str | None = None) -> dict:
    """Core reject step without role checks (sets field; on_update acts)."""
    doc = frappe.get_doc("Customer KYC Verification", name)
    doc.status = "Failed"
    if notes:
        doc.notes = notes
    doc.save(ignore_permissions=True)
    return {"status": "Failed"}


def _apply_expired(name: str, notes: str | None = None) -> dict:
    """Core expiry step without role checks (sets field; on_update acts)."""
    doc = frappe.get_doc("Customer KYC Verification", name)
    doc.status = "Expired"
    if notes:
        doc.notes = notes
    doc.save(ignore_permissions=True)
    return {"status": "Expired"}
