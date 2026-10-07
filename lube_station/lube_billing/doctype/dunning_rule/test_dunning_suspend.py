from datetime import date, timedelta

import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_billing.doctype.dunning_rule.dunning_rule import evaluate_invoice


class TestDunningSuspend(IntegrationTestCase):
    def test_dunning_suspend(self):
        cust = frappe.get_doc({"doctype": "Hosting Customer", "user": "Administrator", "status": "Active"}).insert()
        frappe.get_doc({"doctype": "Dunning Rule", "rule_name": "Default-Test", "grace_days": 7, "termination_days": 30, "active": 1}).insert()
        inv = frappe.get_doc(
            {
                "doctype": "Hosting Invoice",
                "customer": cust.name,
                "invoice_items": [{"description": "test", "amount": 10}],
                "due_date": date.today() - timedelta(days=10),
                "status": "Unpaid",
            }
        ).insert()
        self.assertEqual(evaluate_invoice(inv.name)["action"], "suspend")
        inv.due_date = date.today() - timedelta(days=40)
        inv.save()
        self.assertEqual(evaluate_invoice(inv.name)["action"], "queue_termination")
        inv.due_date = date.today() + timedelta(days=3)
        inv.save()
        self.assertEqual(evaluate_invoice(inv.name)["action"], "notify")
