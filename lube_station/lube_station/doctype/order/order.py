import json

import frappe
from frappe.model.document import Document


class Order(Document):
    def validate(self):
        total = sum((i.unit_price or 0) * (i.quantity or 1) for i in self.items)
        self.total = total


def _snapshot_config(cart_item) -> str:
    raw = cart_item.configuration_json or "{}"
    try:
        config = json.loads(raw) if isinstance(raw, str) else dict(raw)
    except Exception:
        config = {}
    if cart_item.domain:
        config["_domain"] = cart_item.domain
    return json.dumps(config, sort_keys=True)


@frappe.whitelist(methods=["POST"])
def place_order(cart: str, customer: str | None = None, notes: str | None = None) -> dict:
    from lube_station.lube_station.portal.guards import my_customer

    roles = frappe.get_roles()
    if "System Manager" not in roles and frappe.session.user != "Administrator":
        mine = my_customer()
        if customer and customer != mine:
            frappe.throw("Cross-customer access denied", frappe.PermissionError)
        customer = mine
    cart_doc = frappe.get_doc("Cart", cart)
    if "System Manager" not in roles and frappe.session.user != "Administrator":
        if cart_doc.customer and cart_doc.customer != customer:
            frappe.throw("Cross-customer access denied", frappe.PermissionError)
        if not cart_doc.customer:
            cart_doc.customer = customer
            cart_doc.save(ignore_permissions=True)
    if not cart_doc.items:
        frappe.throw("Cart empty")
    for item in cart_doc.items:
        if item.item_type == "Hosting Plan" and item.hosting_plan:
            schema = frappe.db.get_value("Hosting Plan", item.hosting_plan, "product_type_schema")
            if schema:
                from lube_station.lube_station.doctype.product_type_schema.product_type_schema import validate_config

                try:
                    config = json.loads(item.configuration_json or "{}")
                except Exception:
                    config = {}
                validate_config(schema, config)
    fraud_score = _fraud_score(customer or cart_doc.customer, cart_doc)
    order = frappe.get_doc(
        {
            "doctype": "Order",
            "customer": customer or cart_doc.customer,
            "source_cart": cart_doc.name,
            "status": "Pending Review",
            "coupon_code": cart_doc.coupon_code,
            "customer_notes": notes,
            "fraud_score": fraud_score,
            "items": [
                {
                    "item_type": i.item_type,
                    "reference": i.hosting_plan or i.domain,
                    "billing_cycle": i.billing_cycle,
                    "unit_price": i.unit_price,
                    "quantity": i.quantity,
                    "configuration_snapshot": _snapshot_config(i),
                }
                for i in cart_doc.items
            ],
        }
    ).insert(ignore_permissions=True)
    order.save(ignore_permissions=True)
    if cart_doc.coupon_code and frappe.db.exists("Coupon", {"code": cart_doc.coupon_code}):
        coupon = frappe.get_doc("Coupon", {"code": cart_doc.coupon_code})
        coupon.used_count = (coupon.used_count or 0) + 1
        coupon.save(ignore_permissions=True)
    return {"order": order.name, "total": order.total, "status": order.status}


def _fraud_score(customer: str | None, cart_doc) -> float:
    """Starter fraud screening (WHMCS-style checkpoint, staff reviews flags).

    Thresholds live in Lube Station Settings; any rule set to 0 is disabled.
    Orders stay Pending Review; staff accepts or cancels in Desk.
    """
    from lube_station.lube_station.settings import get_setting

    score = 0
    email = (frappe.db.get_value("User", frappe.db.get_value("Hosting Customer", customer, "user"), "email") or "") if customer else ""
    free = ("gmail.", "yahoo.", "hotmail.", "outlook.", "proton.")
    if email and email.split("@")[-1].lower().startswith(free):
        score += get_setting("fraud_free_email_score") or 0
    if customer and not frappe.db.get_value("Hosting Customer", customer, "company"):
        score += get_setting("fraud_no_company_score") or 0
    total = sum((i.unit_price or 0) * (i.quantity or 1) for i in cart_doc.items)
    large_above = get_setting("fraud_large_order_total") or 0
    if large_above and total > large_above:
        score += get_setting("fraud_large_order_score") or 0
    return score
