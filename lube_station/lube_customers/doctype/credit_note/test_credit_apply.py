import frappe

from lube_station.lube_station.tests.helpers import make_customer, make_user
from frappe.tests import IntegrationTestCase

from lube_station.lube_customers.doctype.credit_note.credit_note import (
    apply_credit,
    available_credit,
    consume_credit,
)


class TestCreditApply(IntegrationTestCase):
    def tearDown(self):
        frappe.set_user("Administrator")
        super().tearDown()

    def _customer_with_credit(self, prefix: str, amount: float):
        cust = frappe.get_doc({"doctype": "Hosting Customer", "user": make_user(prefix), "status": "Active"}).insert()
        cn = frappe.get_doc({"doctype": "Credit Note", "customer": cust.name, "amount": amount, "reason": "goodwill"}).insert()
        cn.submit()
        return cust.name

    def _invoice(self, cust: str, applied: float, status: str = "Unpaid"):
        return frappe.get_doc(
            {
                "doctype": "Hosting Invoice",
                "customer": cust,
                "status": status,
                "credit_applied": applied,
                "invoice_items": [{"description": "Hosting", "amount": 100}],
            }
        ).insert(ignore_permissions=True)

    def test_apply_reserves_without_touching_balance(self):
        cust = self._customer_with_credit(__name__.split(".")[-1], 50)
        self.assertEqual(apply_credit(cust, 30), 30)
        # Generation reserves; balance stays until Paid.
        self.assertEqual(frappe.db.get_value("Hosting Customer", cust, "credit_balance"), 50)

    def test_reservation_blocks_double_spend(self):
        cust = self._customer_with_credit("dbl", 50)
        self._invoice(cust, 30)
        # Second invoice sees only 20 free, even though balance is still 50.
        self.assertEqual(apply_credit(cust, 100), 20)
        self.assertEqual(available_credit(cust), 20)

    def test_consume_on_paid_once(self):
        cust = self._customer_with_credit("con", 50)
        inv = self._invoice(cust, 30)
        self.assertEqual(consume_credit(inv.name), 0)  # Unpaid: nothing moves
        frappe.db.set_value("Hosting Invoice", inv.name, "status", "Paid")
        self.assertEqual(consume_credit(inv.name), 30)
        self.assertEqual(frappe.db.get_value("Hosting Customer", cust, "credit_balance"), 20)
        self.assertEqual(frappe.db.get_value("Hosting Invoice", inv.name, "credit_consumed"), 30)
        # Webhook retries / double saves never deduct twice.
        self.assertEqual(consume_credit(inv.name), 0)
        self.assertEqual(frappe.db.get_value("Hosting Customer", cust, "credit_balance"), 20)

    def test_consume_via_status_save(self):
        """Desk edits and gateway callbacks flow through on_update."""
        cust = self._customer_with_credit("via", 50)
        inv = self._invoice(cust, 30)
        doc = frappe.get_doc("Hosting Invoice", inv.name)
        doc.status = "Paid"
        doc.save()
        self.assertEqual(frappe.db.get_value("Hosting Customer", cust, "credit_balance"), 20)
        self.assertEqual(frappe.db.get_value("Hosting Invoice", inv.name, "credit_consumed"), 30)

    def test_cancel_needs_no_restore(self):
        cust = self._customer_with_credit("cncl", 50)
        inv = self._invoice(cust, 30)
        frappe.db.set_value("Hosting Invoice", inv.name, "status", "Cancelled")
        # Nothing was ever deducted, so nothing to return.
        self.assertEqual(frappe.db.get_value("Hosting Customer", cust, "credit_balance"), 50)
        self.assertEqual(available_credit(cust), 50)

    def test_zero_total_settles_immediately(self):
        cust = self._customer_with_credit("zero", 50)
        inv = frappe.get_doc(
            {
                "doctype": "Hosting Invoice",
                "customer": cust,
                "status": "Unpaid",
                "credit_applied": 10,
                "total_due": 0,
            }
        ).insert(ignore_permissions=True)
        self.assertEqual(consume_credit(inv.name, allow_unpaid_zero=True), 10)
        self.assertEqual(frappe.db.get_value("Hosting Customer", cust, "credit_balance"), 40)
