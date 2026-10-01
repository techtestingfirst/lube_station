import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_station.reports.metrics import credit_affiliate, mrr


class TestAffiliateCredit(IntegrationTestCase):
    def test_affiliate_credit(self):
        cust = frappe.get_doc({"doctype": "Hosting Customer", "user": "Administrator", "status": "Active"}).insert()
        aff = frappe.get_doc({"doctype": "Affiliate", "customer": cust.name, "referral_code": "REF-1", "commission_percentage": 10}).insert()
        inv = frappe.get_doc({"doctype": "Hosting Invoice", "customer": cust.name, "invoice_items": [{"description": "t", "amount": 100}], "status": "Unpaid"}).insert()
        self.assertFalse(credit_affiliate(aff.name, inv.name)["credited"])
        inv.status = "Paid"
        inv.save()
        first = credit_affiliate(aff.name, inv.name)
        self.assertTrue(first["credited"])
        self.assertEqual(first["amount"], 10)
        self.assertFalse(credit_affiliate(aff.name, inv.name)["credited"])
        self.assertTrue(mrr()["mrr"] >= 0)
