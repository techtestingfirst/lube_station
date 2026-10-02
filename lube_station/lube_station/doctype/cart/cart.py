import json

import frappe
from frappe.model.document import Document


def server_price(hosting_plan: str, billing_cycle: str) -> float:
    price = frappe.db.get_value("Plan Pricing", {"hosting_plan": hosting_plan, "billing_cycle": billing_cycle}, "recurring_amount")
    if price is None:
        frappe.throw(f"No pricing for {hosting_plan} / {billing_cycle}")
    return price


def recalc(doc):
    subtotal = 0
    for item in doc.items:
        if item.item_type == "Hosting Plan":
            if not item.hosting_plan:
                frappe.throw("Hosting Plan required")
            item.unit_price = server_price(item.hosting_plan, item.billing_cycle)
        elif item.item_type == "Domain":
            if not item.domain:
                frappe.throw("Domain required")
            # Per-year fee from Lube Station Settings (same rate renewal bills).
            from lube_station.lube_station.settings import get_setting

            item.unit_price = get_setting("domain_year_price")
            item.quantity = item.quantity or 1
        item.unit_price = item.unit_price or 0
        item.quantity = item.quantity or 1
        subtotal += item.unit_price * item.quantity
    doc.subtotal = subtotal
    doc.discount_total = discount_for(doc.coupon_code, subtotal, doc)
    doc.grand_total = max(subtotal - doc.discount_total, 0)


def discount_for(coupon_code: str | None, subtotal: float, cart=None) -> float:
    if not coupon_code or not frappe.db.exists("DocType", "Coupon"):
        return 0
    if not frappe.db.exists("Coupon", {"code": coupon_code}):
        return 0
    coupon = frappe.get_doc("Coupon", {"code": coupon_code})
    if cart is not None:
        try:
            coupon.check_cart(cart)
        except Exception:
            return 0
    return coupon.discount_amount(subtotal)


class Cart(Document):
    def validate(self):
        recalc(self)


def _check_access(doc):
    from lube_station.lube_station.portal.guards import my_customer

    if "System Manager" in frappe.get_roles() or frappe.session.user == "Administrator":
        return
    mine = my_customer()
    if doc.customer and doc.customer != mine:
        frappe.throw("Cross-customer access denied", frappe.PermissionError)


@frappe.whitelist(methods=["POST"])
def add_item(cart: str, item_type: str, hosting_plan: str | None = None, billing_cycle: str = "Monthly", domain: str | None = None, quantity: int = 1, configuration: dict | str | None = None):
    doc = frappe.get_doc("Cart", cart)
    _check_access(doc)
    if isinstance(configuration, dict):
        configuration = json.dumps(configuration)
    doc.append("items", {"item_type": item_type, "hosting_plan": hosting_plan, "billing_cycle": billing_cycle, "domain": domain, "quantity": quantity, "configuration_json": configuration})
    doc.save(ignore_permissions=True)
    return {"subtotal": doc.subtotal, "grand_total": doc.grand_total}


@frappe.whitelist(methods=["POST"])
def update_item(cart: str, row: str, quantity: int):
    doc = frappe.get_doc("Cart", cart)
    _check_access(doc)
    for item in doc.items:
        if item.name == row:
            item.quantity = quantity
    doc.save(ignore_permissions=True)
    return {"grand_total": doc.grand_total}


@frappe.whitelist(methods=["POST"])
def remove_item(cart: str, row: str):
    doc = frappe.get_doc("Cart", cart)
    _check_access(doc)
    doc.items = [i for i in doc.items if i.name != row]
    doc.save(ignore_permissions=True)
    return {"grand_total": doc.grand_total}


@frappe.whitelist(methods=["POST"])
def apply_coupon(cart: str, coupon_code: str):
    doc = frappe.get_doc("Cart", cart)
    _check_access(doc)
    coupon = frappe.get_doc("Coupon", {"code": coupon_code})
    coupon.check_cart(doc)
    doc.coupon_code = coupon.code
    doc.save(ignore_permissions=True)
    return {"discount": doc.discount_total, "grand_total": doc.grand_total}


@frappe.whitelist(methods=["GET", "POST"])
def totals(cart: str):
    doc = frappe.get_doc("Cart", cart)
    _check_access(doc)
    return {"subtotal": doc.subtotal, "discount": doc.discount_total, "grand_total": doc.grand_total}
