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
        unpaid = self._invoice(cust_name, 20)
        paid = self._invoice(cust_name, 15)
        doc = frappe.get_doc("Hosting Invoice", paid.name)
        doc.status = "Paid"
        doc.save()  # on_update consumes the reservation
        cancelled = self._invoice(cust_name, 999)
        frappe.db.set_value("Hosting Invoice", cancelled.name, "status", "Cancelled")
        frappe.set_user(user)
        w = wallet.my_wallet()
        # 50 - 15 consumed; 20 still only reserved.
        self.assertEqual(w["balance"], 35)
        self.assertEqual(w["reserved"], 20)
        self.assertEqual(w["available"], 15)
        rows = wallet.my_wallet_transactions()
        by_ref = {r["ref"]: r for r in rows}
        self.assertEqual(by_ref[cn.name]["kind"], "credit")
        self.assertEqual(by_ref[cn.name]["amount"], 50)
        self.assertEqual(by_ref[unpaid.name]["state"], "reserved")
        self.assertEqual(by_ref[unpaid.name]["amount"], -20)
        self.assertEqual(by_ref[paid.name]["state"], "consumed")
        self.assertEqual(by_ref[paid.name]["amount"], -15)
        self.assertNotIn(cancelled.name, by_ref)
        self.assertFalse(any(r["amount"] == 999 for r in rows))
        # Newest first.
        dates = [str(r["date"]) for r in rows]
        self.assertEqual(dates, sorted(dates, reverse=True))

    def test_debit_shows_plan_group_and_name(self):
        cust_name, user = self._customer("walletplan")
        group = frappe.get_doc({"doctype": "Product Group", "group_name": "Wallet Group"}).insert()
        plan = frappe.get_doc(
            {
                "doctype": "Hosting Plan",
                "plan_name": "Wallet Basic",
                "product_group": group.name,
                "product_type": "Shared Hosting",
                "is_active": 1,
            }
        ).insert()
        inv = frappe.get_doc(
            {
                "doctype": "Hosting Invoice",
                "customer": cust_name,
                "status": "Unpaid",
                "credit_applied": 5,
                "total_due": 5,
                "invoice_items": [{"description": "Hosting", "service_ref": plan.name, "amount": 10}],
            }
        ).insert(ignore_permissions=True)
        frappe.set_user(user)
        rows = wallet.my_wallet_transactions()
        row = next(r for r in rows if r["ref"] == inv.name)
        self.assertIn("Wallet Basic", row["plans"][0])
        self.assertIn("Wallet Group", row["plans"][0])
        self.assertNotIn(plan.name, row["plans"][0])

    def test_downgrade_reason_shows_names(self):
        from lube_station.lube_station.portal import apis

        cust_name, _ = self._customer("walletdown")
        group = frappe.get_doc({"doctype": "Product Group", "group_name": "Down Group"}).insert()
        old = frappe.get_doc(
            {
                "doctype": "Hosting Plan",
                "plan_name": "Down Business",
                "product_group": group.name,
                "product_type": "Shared Hosting",
                "is_active": 1,
            }
        ).insert()
        new = frappe.get_doc(
            {
                "doctype": "Hosting Plan",
                "plan_name": "Down Lite",
                "product_group": group.name,
                "product_type": "Shared Hosting",
                "is_active": 1,
            }
        ).insert()
        svc = frappe.get_doc(
            {"doctype": "Service", "customer": cust_name, "hosting_plan": old.name, "status": "Active", "recurring_amount": 100}
        ).insert()
        out = apis._apply_plan_swap(svc.name, new.name, credit_amount=10)
        self.assertTrue(out.get("applied"))
        reason = frappe.db.get_value("Credit Note", out["credit_note"], "reason")
        self.assertIn("Down Business", reason)
        self.assertIn("Down Lite", reason)
        self.assertIn("Down Group", reason)
        self.assertNotIn(old.name, reason)
        self.assertNotIn(new.name, reason)

    def test_migration_restores_unpaid_deductions(self):
        """Old model deducted at generation: patch returns it to open invoices."""
        from lube_station.patches.restore_wallet_credit_on_unpaid import execute

        cust_name, _ = self._customer("walletmig")
        cn = frappe.get_doc(
            {"doctype": "Credit Note", "customer": cust_name, "amount": 50, "reason": "refund"}
        ).insert()
        cn.submit()
        # Simulate old-model state: generation already took 20 for an Unpaid invoice.
        frappe.db.set_value("Hosting Customer", cust_name, "credit_balance", 30)
        self._invoice(cust_name, 20)
        execute()
        self.assertEqual(frappe.db.get_value("Hosting Customer", cust_name, "credit_balance"), 50)

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
