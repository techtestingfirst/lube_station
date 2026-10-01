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
    return json.dumps(config, sort_keys=True)


@frappe.whitelist(methods=["POST"])
def place_order(cart: str, customer: str | None = None) -> dict:
    cart_doc = frappe.get_doc("Cart", cart)
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
    order = frappe.get_doc(
        {
            "doctype": "Order",
            "customer": customer or cart_doc.customer,
            "source_cart": cart_doc.name,
            "status": "Pending Review",
            "coupon_code": cart_doc.coupon_code,
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
    ).insert()
    order.save()
    if cart_doc.coupon_code and frappe.db.exists("Coupon", {"code": cart_doc.coupon_code}):
        coupon = frappe.get_doc("Coupon", {"code": cart_doc.coupon_code})
        coupon.used_count = (coupon.used_count or 0) + 1
        coupon.save(ignore_permissions=True)
    return {"order": order.name, "total": order.total, "status": order.status}
