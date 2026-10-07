"""Live Bank Transfer tests: pending record, idempotency, staff approval."""

import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_station.adapters.payments.bank_transfer import BankTransferAdapter
from lube_station.lube_station.payments.methods import approve_bank_transfer


def _invoice(amount=400):
    cust = frappe.db.get_value("Hosting Customer", {"user": "Administrator"}, "name")
    if not cust:
        cust = frappe.get_doc({"doctype": "Hosting Customer", "user": "Administrator", "status": "Active"}).insert().name
    return frappe.get_doc(
        {
            "doctype": "Hosting Invoice",
            "customer": cust,
            "invoice_items": [{"description": "bt", "amount": amount}],
            "status": "Unpaid",
        }
    ).insert(ignore_permissions=True)


class TestBankTransferLive(IntegrationTestCase):
    def test_create_verify_approve(self):
        inv = _invoice(400)
        try:
            out = BankTransferAdapter().create_payment(inv.name)
            self.assertIn(inv.name, out["reference"])
            self.assertIn(out["reference"], out["instructions"])
            self.assertEqual(
                frappe.db.get_value(
                    "Payment Transaction", {"gateway_txn_id": out["reference"]}, "status"
                ),
                "Pending",
            )
            # Idempotent: second call reuses the same pending record.
            again = BankTransferAdapter().create_payment(inv.name)
            self.assertEqual(again["reference"], out["reference"])
            self.assertEqual(
                frappe.db.count("Payment Transaction", {"gateway_txn_id": out["reference"]}), 1
            )
            # Not yet approved.
            self.assertFalse(BankTransferAdapter().verify_payment({"invoice": inv.name})["verified"])
            # Staff approval flips everything.
            approved = approve_bank_transfer(inv.name)
            self.assertEqual(approved["status"], "Success")
            self.assertEqual(frappe.db.get_value("Hosting Invoice", inv.name, "status"), "Paid")
            self.assertTrue(BankTransferAdapter().verify_payment({"invoice": inv.name})["verified"])
        finally:
            name = frappe.db.get_value(
                "Payment Transaction", {"gateway": "Bank Transfer", "invoice": inv.name}, "name"
            )
            if name:
                frappe.delete_doc("Payment Transaction", name, ignore_permissions=True, force=True)
            frappe.delete_doc("Hosting Invoice", inv.name, ignore_permissions=True, force=True)

    def test_approve_needs_pending(self):
        inv = _invoice(10)
        try:
            self.assertRaises(frappe.ValidationError, approve_bank_transfer, inv.name)
        finally:
            frappe.delete_doc("Hosting Invoice", inv.name, ignore_permissions=True, force=True)
