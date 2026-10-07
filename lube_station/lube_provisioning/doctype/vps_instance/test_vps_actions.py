import json

import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_provisioning.doctype.vps_instance.vps_instance import create_vps_instance, vps_action
from lube_station.lube_customers.doctype.order.order import place_order
from lube_station.lube_station.payments.webhooks import handle_webhook

PLAN_NAME = "VPS Plan"
GROUP_NAME = "VPS Group"
SESSION_ID = "vps-1"


def _wipe(doctype, names):
    for name in names:
        try:
            frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
        except Exception:
            pass


def _cleanup_vps_artifacts():
    """Delete this test's fixed-name artifacts so reruns start clean."""
    plans = [p.name for p in frappe.get_all("Hosting Plan", {"plan_name": PLAN_NAME}, ["name"])]
    carts = [c.name for c in frappe.get_all("Cart", {"session_id": SESSION_ID}, ["name"])]
    orders = (
        [o.name for o in frappe.get_all("Order", {"source_cart": ("in", carts)}, ["name"])] if carts else []
    )
    cfgs = (
        [c.name for c in frappe.get_all("VPS Configuration", {"hosting_plan": ("in", plans)}, ["name"])]
        if plans
        else []
    )
    by_order = lambda dt, field: (
        [d.name for d in frappe.get_all(dt, {field: ("in", orders)}, ["name"])] if orders else []
    )
    by_cfg = (
        [d.name for d in frappe.get_all("VPS Instance", {"configuration": ("in", cfgs)}, ["name"])]
        if cfgs
        else []
    )
    # Dependents first.
    _wipe("VPS Instance", list(dict.fromkeys(by_order("VPS Instance", "order_ref") + by_cfg)))
    _wipe(
        "Payment Transaction",
        [
            t.name
            for t in frappe.get_all(
                "Payment Transaction", {"gateway": "Stripe", "gateway_txn_id": "vps-txn"}, ["name"]
            )
        ],
    )
    _wipe("Service", by_order("Service", "order_ref"))
    _wipe("Hosting Invoice", by_order("Hosting Invoice", "order_ref"))
    _wipe("Order", orders)
    _wipe("Cart", carts)
    _wipe("VPS Configuration", cfgs)
    _wipe(
        "Plan Pricing",
        (
            [p.name for p in frappe.get_all("Plan Pricing", {"hosting_plan": ("in", plans)}, ["name"])]
            if plans
            else []
        ),
    )
    _wipe("Hosting Plan", plans)
    _wipe(
        "Product Group",
        [g.name for g in frappe.get_all("Product Group", {"group_name": GROUP_NAME}, ["name"])],
    )


def _get_or_create_customer():
    name = frappe.db.get_value("Hosting Customer", {"user": "Administrator"}, "name")
    if name:
        return frappe.get_doc("Hosting Customer", name)
    return frappe.get_doc({"doctype": "Hosting Customer", "user": "Administrator", "status": "Active"}).insert()


class TestVpsActions(IntegrationTestCase):
    def setUp(self):
        _cleanup_vps_artifacts()
        super().setUp()

    @classmethod
    def tearDownClass(cls):
        _cleanup_vps_artifacts()
        super().tearDownClass()

    def test_vps_actions(self):
        group = frappe.get_doc({"doctype": "Product Group", "group_name": GROUP_NAME}).insert()
        plan = frappe.get_doc({"doctype": "Hosting Plan", "plan_name": PLAN_NAME, "product_group": group.name, "product_type": "VPS", "is_active": 1}).insert()
        frappe.get_doc({"doctype": "Plan Pricing", "hosting_plan": plan.name, "billing_cycle": "Monthly", "recurring_amount": 200}).insert()
        cfg = frappe.get_doc({"doctype": "VPS Configuration", "hosting_plan": plan.name, "os_images_json": json.dumps(["ubuntu-24.04"]), "locations_json": json.dumps(["eu-1"])}).insert()
        cust = _get_or_create_customer()
        cart = frappe.get_doc({"doctype": "Cart", "customer": cust.name, "session_id": SESSION_ID}).insert()
        cart.append("items", {"item_type": "Hosting Plan", "hosting_plan": plan.name, "billing_cycle": "Monthly", "quantity": 1})
        cart.save()
        out = place_order(cart.name, cust.name)
        inv = frappe.get_doc({"doctype": "Hosting Invoice", "customer": cust.name, "order_ref": out["order"], "invoice_items": [{"description": "vps", "amount": 200}], "status": "Unpaid"}).insert()
        handle_webhook("Stripe", {"id": "vps-txn", "event": "vps-evt", "invoice": inv.name, "status": "paid", "amount": 200})
        created = create_vps_instance(out["order"], cfg.name, "ubuntu-24.04", "eu-1")
        self.assertTrue(frappe.db.exists("VPS Instance", created["instance"]))
        self.assertEqual(vps_action(created["instance"], "reboot")["action"], "reboot")
        self.assertIn("url", vps_action(created["instance"], "console"))
