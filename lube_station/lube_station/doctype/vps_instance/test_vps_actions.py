import json

import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_station.doctype.vps_instance.vps_instance import create_vps_instance, vps_action
from lube_station.lube_station.doctype.order.order import place_order
from lube_station.lube_station.payments.webhooks import handle_webhook


class TestVpsActions(IntegrationTestCase):
    def test_vps_actions(self):
        group = frappe.get_doc({"doctype": "Product Group", "group_name": "VPS Group"}).insert()
        plan = frappe.get_doc({"doctype": "Hosting Plan", "plan_name": "VPS Plan", "product_group": group.name, "product_type": "VPS", "is_active": 1}).insert()
        frappe.get_doc({"doctype": "Plan Pricing", "hosting_plan": plan.name, "billing_cycle": "Monthly", "recurring_amount": 200}).insert()
        cfg = frappe.get_doc({"doctype": "VPS Configuration", "hosting_plan": plan.name, "os_images_json": json.dumps(["ubuntu-24.04"]), "locations_json": json.dumps(["eu-1"])}).insert()
        cust = frappe.get_doc({"doctype": "Hosting Customer", "user": "Administrator", "status": "Active"}).insert()
        cart = frappe.get_doc({"doctype": "Cart", "customer": cust.name, "session_id": "vps-1"}).insert()
        cart.append("items", {"item_type": "Hosting Plan", "hosting_plan": plan.name, "billing_cycle": "Monthly", "quantity": 1})
        cart.save()
        out = place_order(cart.name, cust.name)
        inv = frappe.get_doc({"doctype": "Hosting Invoice", "customer": cust.name, "order_ref": out["order"], "invoice_items": [{"description": "vps", "amount": 200}], "status": "Unpaid"}).insert()
        handle_webhook("Stripe", {"id": "vps-txn", "event": "vps-evt", "invoice": inv.name, "status": "paid", "amount": 200})
        created = create_vps_instance(out["order"], cfg.name, "ubuntu-24.04", "eu-1")
        self.assertTrue(frappe.db.exists("VPS Instance", created["instance"]))
        self.assertEqual(vps_action(created["instance"], "reboot")["action"], "reboot")
        self.assertIn("url", vps_action(created["instance"], "console"))
