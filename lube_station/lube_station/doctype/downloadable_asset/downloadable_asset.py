import frappe
from frappe.model.document import Document


class DownloadableAsset(Document):
    def validate(self):
        if self.storage_type == "Frappe File" and not self.file:
            frappe.throw("Frappe File storage needs file")
        if self.storage_type == "Remote URL" and not self.remote_url:
            frappe.throw("Remote URL storage needs remote_url")


def _purchased_product_access(asset, user: str) -> bool:
    if not frappe.db.exists("DocType", "Order"):
        return False
    plans = [r.hosting_plan for r in asset.allowed_products if r.hosting_plan]
    if not plans or not frappe.db.exists("DocType", "Order Item"):
        return False
    return bool(
        frappe.db.sql(
            """select 1 from `tabOrder Item` oi join `tabOrder` o on o.name=oi.parent
            where o.customer=(select name from `tabHosting Customer` where user=%s limit 1)
            and oi.type='Hosting Plan' and oi.reference in %s limit 1""",
            (user, tuple(plans)),
        )
    )


def _active_service_access(asset, user: str) -> bool:
    if not frappe.db.exists("DocType", "Service"):
        return False
    plans = [r.hosting_plan for r in asset.allowed_products if r.hosting_plan]
    if not plans or not frappe.db.exists("DocType", "Hosting Customer"):
        return False
    return bool(
        frappe.db.get_all(
            "Service",
            filters={"customer": ["in", frappe.db.get_all("Hosting Customer", {"user": user}, pluck="name")], "hosting_plan": ["in", plans], "status": "Active"},
            limit=1,
        )
    )


@frappe.whitelist(methods=["GET", "POST"])
def check_entitlement(asset: str, user: str | None = None) -> dict:
    doc = frappe.get_doc("Downloadable Asset", asset)
    user = user or frappe.session.user
    if not doc.active:
        return {"allowed": False, "reason": "inactive"}
    if doc.access_policy == "Public":
        return {"allowed": True}
    if user in (None, "", "Guest"):
        return {"allowed": False, "reason": "login required"}
    if doc.access_policy == "Logged-in Customers":
        return {"allowed": True}
    if doc.access_policy == "Purchased Product":
        return {"allowed": _purchased_product_access(doc, user)}
    if doc.access_policy == "Active Service":
        return {"allowed": _active_service_access(doc, user)}
    return {"allowed": False}
