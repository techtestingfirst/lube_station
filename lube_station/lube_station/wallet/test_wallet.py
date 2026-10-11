import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_station.tests.helpers import make_user
from lube_station.lube_station.wallet import wallet


class TestWallet(IntegrationTestCase):
    def tearDown(self):
        frappe.set_user("Administrator")
        super().tearDown()

    def _customer(self, prefix: str):
        user = make_user(prefix)
        cust = frappe.get_doc({"doctype": "Hosting Customer", "user": user, "status": "Active"}).insert()
        return cust.name, user

    def test_wallet_ledger(self):
        cust_name, user = self._customer("wallet")
        cn = frappe.get_doc(
            {"doctype": "Credit Note", "customer": cust_name, "amount": 50, "reason": "refund"}
        ).insert()
        cn.submit()
        # Draft notes never hit the ledger.
        frappe.get_doc(
            {"doctype": "Credit Note", "customer": cust_name, "amount": 999, "reason": "draft"}
        ).insert()
        inv = frappe.get_doc(
            {
                "doctype": "Hosting Invoice",
                "customer": cust_name,
                "status": "Unpaid",
                "credit_applied": 20,
                "total_due": 80,
            }
        ).insert(ignore_permissions=True)
        frappe.set_user(user)
        w = wallet.my_wallet()
        self.assertEqual(w["balance"], 50)
        rows = wallet.my_wallet_transactions()
        by_ref = {r["ref"]: r for r in rows}
        self.assertEqual(by_ref[cn.name]["kind"], "credit")
        self.assertEqual(by_ref[cn.name]["amount"], 50)
        self.assertEqual(by_ref[inv.name]["kind"], "debit")
        self.assertEqual(by_ref[inv.name]["amount"], -20)
        self.assertFalse(any(r["amount"] == 999 for r in rows))
        # Newest first.
        dates = [str(r["date"]) for r in rows]
        self.assertEqual(dates, sorted(dates, reverse=True))

    def test_wallet_isolation(self):
        cust_a, user_a = self._customer("walleta")
        cust_b, user_b = self._customer("walletb")
        cn = frappe.get_doc(
            {"doctype": "Credit Note", "customer": cust_a, "amount": 10, "reason": "x"}
        ).insert()
        cn.submit()
        frappe.set_user(user_b)
        self.assertEqual(wallet.my_wallet()["balance"], 0)
        self.assertFalse(any(r["ref"] == cn.name for r in wallet.my_wallet_transactions()))
        frappe.set_user("Guest")
        self.assertRaises(frappe.PermissionError, wallet.my_wallet)
        self.assertRaises(frappe.PermissionError, wallet.my_wallet_transactions)
        frappe.set_user(user_a)
        self.assertEqual(wallet.my_wallet()["balance"], 10)
