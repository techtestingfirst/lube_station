import frappe
from frappe.tests import IntegrationTestCase
from unittest.mock import patch

from lube_station.lube_station.payments.methods import auto_charge_invoice
from lube_station.lube_station.payments.webhooks import handle_webhook
from lube_station.lube_station.adapters.seed import seed


def _customer(tag: str) -> str:
    email = f"fulfill-{tag}@example.com"
    if not frappe.db.exists("User", email):
        frappe.get_doc({"doctype": "User", "email": email, "first_name": "Fulfill", "enabled": 1, "roles": [{"role": "Customer"}]}).insert(ignore_permissions=True)
    return frappe.get_doc({"doctype": "Hosting Customer", "user": email, "status": "Active", "kyc_status": "Verified"}).insert().name


def _order_with_plan(customer: str, tag: str):
    group = frappe.get_doc({"doctype": "Product Group", "group_name": f"Fulfill Group {tag}"}).insert()
    plan = frappe.get_doc(
        {
            "doctype": "Hosting Plan",
            "plan_name": f"Fulfill Plan {tag}",
            "product_group": group.name,
            "product_type": "Shared Hosting",
            "is_active": 1,
        }
    ).insert()
    frappe.get_doc(
        {"doctype": "Plan Pricing", "hosting_plan": plan.name, "billing_cycle": "Monthly", "recurring_amount": 50}
    ).insert()
    order = frappe.get_doc(
        {
            "doctype": "Order",
            "customer": customer,
            "status": "Pending Review",
            "items": [
                {
                    "item_type": "Hosting Plan",
                    "reference": plan.name,
                    "billing_cycle": "Monthly",
                    "unit_price": 50,
                    "quantity": 1,
                    "configuration_snapshot": '{"domain_action": "none"}',
                }
            ],
        }
    ).insert()
    return order


class TestFulfillPaths(IntegrationTestCase):
    def test_webhook_creates_and_activates_once(self):
        cust = _customer("webhook")
        order = _order_with_plan(cust, "webhook")
        inv = frappe.get_doc(
            {"doctype": "Hosting Invoice", "customer": cust, "order_ref": order.name, "invoice_items": [{"description": "t", "amount": 50}], "status": "Unpaid"}
        ).insert()
        payload = {"id": "txn-fulfill-1", "event": "evt-fulfill-1", "invoice": inv.name, "status": "paid", "amount": 50}
        handle_webhook("Bank Transfer", payload)
        handle_webhook("Bank Transfer", payload)  # retry must not duplicate
        services = frappe.get_all("Service", {"order_ref": order.name}, ["name", "status"])
        self.assertEqual(len(services), 1)
        self.assertEqual(services[0].status, "Active")

    def test_auto_charge_fulfills_order(self):
        seed()
        cust = _customer("autocharge")
        method = frappe.get_doc({"doctype": "Saved Payment Method", "customer": cust, "gateway": "Stripe", "token": "tok_fulfill", "default_method": 1}).insert()
        order = _order_with_plan(cust, "autocharge")
        inv = frappe.get_doc(
            {"doctype": "Hosting Invoice", "customer": cust, "order_ref": order.name, "invoice_items": [{"description": "t", "amount": 50}], "status": "Unpaid"}
        ).insert()
        with patch(
            "lube_station.lube_station.adapters.payments.stripe.StripeAdapter.charge_saved_method",
            lambda self, pm, inv_name: {"charged": "pi_fulfill_1", "invoice": inv_name},
        ):
            out = auto_charge_invoice(inv.name)
        self.assertEqual(out["action"], "charged")
        services = frappe.get_all("Service", {"order_ref": order.name}, ["name", "status"])
        self.assertEqual(len(services), 1)
        self.assertEqual(services[0].status, "Active")
        self.assertEqual(method.name, frappe.db.get_value("Saved Payment Method", method.name, "name"))
