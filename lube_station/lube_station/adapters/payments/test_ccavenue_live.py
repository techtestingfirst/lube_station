"""Live CCAvenue adapter tests. Pure crypto + fakes; no network happens."""

import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_station.adapters.payments.ccavenue import CCAvenueAdapter, decrypt, encrypt


def _keys():
    frappe.db.set_single_value("Lube Station Settings", "ccavenue_merchant_id", "MID1")
    frappe.db.set_single_value("Lube Station Settings", "ccavenue_access_code", "AC1")
    frappe.db.set_single_value("Lube Station Settings", "ccavenue_working_key", "WK" * 16)


def _clearkeys():
    frappe.db.set_single_value("Lube Station Settings", "ccavenue_merchant_id", "")
    frappe.db.set_single_value("Lube Station Settings", "ccavenue_access_code", "")
    frappe.db.set_single_value("Lube Station Settings", "ccavenue_working_key", "")


def _invoice(amount=1100):
    cust = frappe.db.get_value("Hosting Customer", {"user": "Administrator"}, "name")
    if not cust:
        cust = frappe.get_doc({"doctype": "Hosting Customer", "user": "Administrator", "status": "Active"}).insert().name
    return frappe.get_doc(
        {
            "doctype": "Hosting Invoice",
            "customer": cust,
            "invoice_items": [{"description": "cca", "amount": amount}],
            "status": "Unpaid",
        }
    ).insert(ignore_permissions=True)


class TestCCAvenueLiveAdapter(IntegrationTestCase):
    def test_crypto_roundtrip(self):
        enc = encrypt("WK" * 16, "order_id=INV-1&amount=100.00")
        self.assertNotIn("INV-1", enc)
        self.assertEqual(decrypt("WK" * 16, enc), "order_id=INV-1&amount=100.00")
        self.assertNotEqual(decrypt("X" * 32, enc), "order_id=INV-1&amount=100.00")

    def test_create_and_return(self):
        from lube_station.lube_station.payments.methods import ccavenue_return

        _keys()
        inv = _invoice(1100)
        try:
            out = CCAvenueAdapter().create_payment(inv.name)
            self.assertIn("initiateTransaction", out["post_url"])
            self.assertEqual(out["access_code"], "AC1")
            self.assertEqual(len(out["enc_request"]) % 32, 0)
            body = decrypt("WK" * 16, out["enc_request"])
            self.assertIn(f"order_id={inv.name}", body)
            self.assertIn("amount=1100.00", body)

            success = encrypt("WK" * 16, f"order_id={inv.name}&order_status=Success&tracking_id=T1")
            out = ccavenue_return(encResp=success)
            self.assertEqual(out["status"], "success")
            self.assertEqual(frappe.db.get_value("Hosting Invoice", inv.name, "status"), "Paid")

            failed = encrypt("WK" * 16, f"order_id={inv.name}&order_status=Failure")
            self.assertRaises(frappe.ValidationError, ccavenue_return, encResp=failed)
        finally:
            _clearkeys()
            frappe.delete_doc("Hosting Invoice", inv.name, ignore_permissions=True, force=True)
