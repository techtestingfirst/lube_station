import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_station.doctype.credit_note.credit_note import apply_credit


class TestCreditApply(IntegrationTestCase):
    def test_credit_apply(self):
        cust = frappe.get_doc({"doctype": "Hosting Customer", "user": "Administrator", "status": "Active"}).insert()
        cn = frappe.get_doc({"doctype": "Credit Note", "customer": cust.name, "amount": 50, "reason": "goodwill"}).insert()
        cn.submit()
        self.assertEqual(frappe.db.get_value("Hosting Customer", cust.name, "credit_balance"), 50)
        applied = apply_credit(cust.name, 30)
        self.assertEqual(applied, 30)
        self.assertEqual(frappe.db.get_value("Hosting Customer", cust.name, "credit_balance"), 20)
        cn.cancel()
        self.assertEqual(frappe.db.get_value("Hosting Customer", cust.name, "credit_balance"), -30)
