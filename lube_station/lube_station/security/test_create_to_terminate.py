from datetime import date, timedelta

import frappe

from lube_station.lube_station.tests.helpers import make_customer, make_user
from frappe.tests import IntegrationTestCase

from lube_station.lube_billing.doctype.dunning_rule.dunning_rule import evaluate_invoice
from lube_station.lube_customers.doctype.order.order import place_order
from lube_station.lube_station.payments.webhooks import handle_webhook
from lube_station.lube_station.security.roles import ensure_roles


class TestCreateToTerminate(IntegrationTestCase):
    def test_create_to_terminate(self):
        ensure_roles()
        for r in ["Customer", "Support Agent", "Billing Admin", "Provisioning Operator"]:
            self.assertTrue(frappe.db.exists("Role", r))
        cust = frappe.get_doc({"doctype": "Hosting Customer", "user": make_user(__name__.split(".")[-1]), "status": "Active"}).insert()
        from lube_station.lube_customers.doctype.customer_kyc_verification.customer_kyc_verification import mark_verified, request_kyc

        req = request_kyc(cust.name, "Manual", "Aadhaar")
        mark_verified(req["name"], "e2e kyc verified")
        group = frappe.get_doc({"doctype": "Product Group", "group_name": "E2E Group"}).insert()
        plan = frappe.get_doc({"doctype": "Hosting Plan", "plan_name": "E2E Plan", "product_group": group.name, "product_type": "Shared Hosting", "is_active": 1}).insert()
        frappe.get_doc({"doctype": "Plan Pricing", "hosting_plan": plan.name, "billing_cycle": "Monthly", "recurring_amount": 120}).insert()
        cart = frappe.get_doc({"doctype": "Cart", "customer": cust.name, "session_id": "e2e-1"}).insert()
        cart.append("items", {"item_type": "Hosting Plan", "hosting_plan": plan.name, "billing_cycle": "Monthly", "quantity": 1})
        cart.save()
        order = place_order(cart.name, cust.name)["order"]
        inv = frappe.get_doc({"doctype": "Hosting Invoice", "customer": cust.name, "order_ref": order, "invoice_items": [{"description": "e2e", "amount": 120}], "due_date": date.today() + timedelta(days=7), "status": "Unpaid"}).insert()
        payload = {"id": "e2e-txn", "event": "e2e-evt", "invoice": inv.name, "status": "paid", "amount": 120}
        handle_webhook("Stripe", payload)
        again = handle_webhook("Stripe", payload)
        self.assertTrue(again["reused"])
        from lube_station.lube_provisioning.doctype.service.service import apply_dunning, create_from_order

        created = create_from_order(order)
        self.assertTrue(created["services"])
        svc_name = created["services"][0]
        frappe.get_doc("Service", svc_name).activate()
        frappe.get_doc("Service", svc_name).reload()
        inv.reload()
        inv.due_date = date.today() - timedelta(days=10)
        inv.status = "Unpaid"
        inv.save()
        self.assertEqual(evaluate_invoice(inv.name)["action"], "suspend")
        apply_dunning(inv.name)
        self.assertEqual(frappe.db.get_value("Service", svc_name, "status"), "Suspended")
        inv.reload()
        inv.status = "Paid"
        inv.save()
        from lube_station.lube_provisioning.doctype.service.service import on_invoice_paid

        on_invoice_paid(inv.name)
        self.assertEqual(frappe.db.get_value("Service", svc_name, "status"), "Active")
        frappe.get_doc("Service", svc_name).terminate("e2e approved teardown")
        self.assertEqual(frappe.db.get_value("Service", svc_name, "status"), "Terminated")
