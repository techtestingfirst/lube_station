import frappe
from contextlib import contextmanager
from frappe.tests import IntegrationTestCase

from lube_station.lube_station.doctype.tax_rule.tax_rule import normalize_state, tax_breakup


def _customer(email, state=None):
    name = frappe.db.get_value("Hosting Customer", {"user": email}, "name")
    if name:
        cust = frappe.get_doc("Hosting Customer", name)
    else:
        user = email if frappe.db.exists("User", email) else frappe.get_doc(
            {"doctype": "User", "email": email, "first_name": "GST", "enabled": 1}
        ).insert(ignore_permissions=True).name
        cust = frappe.get_doc({"doctype": "Hosting Customer", "user": user, "status": "Active"}).insert()
    if state is not None:
        frappe.db.set_value("Hosting Customer", cust.name, "state", state)
    return cust.name


def _set_gst(seller_state, rate=18):
    frappe.db.set_single_value("GST Settings", "seller_state", seller_state)
    frappe.db.set_single_value("GST Settings", "gst_rate", rate)


class TestGst(IntegrationTestCase):
    @contextmanager
    def _regulated(self):
        """Deactivate seller rules so GST assertions are deterministic."""
        others = [r.name for r in frappe.get_all("Tax Rule", {"active": 1}, ["name"])]
        for name in others:
            frappe.db.set_value("Tax Rule", name, "active", 0)
        try:
            yield
        finally:
            for name in others:
                try:
                    frappe.db.set_value("Tax Rule", name, "active", 1)
                except Exception:
                    pass
    @classmethod
    def tearDownClass(cls):
        for email in ("gst-bihar@test.com", "gst-maha@test.com", "gst-chd@test.com", "gst-delhi@test.com", "gst-nostate@test.com", "gst-foreign@test.com"):
            name = frappe.db.get_value("Hosting Customer", {"user": email}, "name")
            if name:
                frappe.delete_doc("Hosting Customer", name, ignore_permissions=True)
            if frappe.db.exists("User", email):
                frappe.delete_doc("User", email, ignore_permissions=True)
        frappe.db.set_single_value("GST Settings", "seller_state", "")
        frappe.db.set_single_value("GST Settings", "gst_rate", 18)
        super().tearDownClass()

    def test_normalize(self):
        self.assertEqual(normalize_state("  BIHAR "), "Bihar")
        self.assertEqual(normalize_state("pondicherry"), "Puducherry")
        self.assertEqual(normalize_state("Sikkim"), "Sikkim")
        self.assertIsNone(normalize_state("Narnia"))
        self.assertIsNone(normalize_state(None))

    def test_intra_state_cgst_sgst(self):
        _set_gst("Bihar")
        cust = _customer("gst-bihar@test.com", "bihar")
        out = tax_breakup(cust, 1000)
        self.assertEqual(out["mode"], "gst")
        self.assertEqual(out["cgst"], 90)
        self.assertEqual(out["sgst"], 90)
        self.assertEqual(out["igst"], 0)
        self.assertEqual(out["total"], 180)

    def test_inter_state_igst(self):
        _set_gst("Bihar")
        cust = _customer("gst-maha@test.com", "Maharashtra")
        with self._regulated():
            out = tax_breakup(cust, 1000)
        self.assertEqual(out["igst"], 180)
        self.assertEqual(out["cgst"], 0)
        self.assertEqual(out["total"], 180)

    def test_same_ut_cgst_ugst(self):
        _set_gst("Chandigarh")
        cust = _customer("gst-chd@test.com", "Chandigarh")
        with self._regulated():
            out = tax_breakup(cust, 1000)
        self.assertEqual(out["cgst"], 90)
        self.assertEqual(out["ugst"], 90)
        self.assertEqual(out["total"], 180)

    def test_ut_with_legislature_uses_sgst(self):
        _set_gst("Delhi")
        cust = _customer("gst-delhi@test.com", "Delhi")
        with self._regulated():
            out = tax_breakup(cust, 1000)
        self.assertEqual(out["cgst"], 90)
        self.assertEqual(out["sgst"], 90)
        self.assertEqual(out["total"], 180)

    def test_ut_to_state_igst(self):
        _set_gst("Chandigarh")
        cust = _customer("gst-maha@test.com", "Maharashtra")
        with self._regulated():
            out = tax_breakup(cust, 1000)
        self.assertEqual(out["igst"], 180)
        self.assertEqual(out["total"], 180)

    def test_cess_rule_applies_on_top_of_gst(self):
        _set_gst("Bihar")
        name = frappe.db.get_value("Tax Rule", {"tax_name": "GST-Cess"}, "name")
        if not name:
            name = frappe.get_doc({"doctype": "Tax Rule", "tax_name": "GST-Cess", "percentage": 2, "active": 1}).insert(ignore_permissions=True).name
        try:
            cust = _customer("gst-bihar@test.com", "Bihar")
            out = tax_breakup(cust, 1000)
            self.assertEqual(out["cgst"], 90)
            self.assertEqual(out["total"], 200)  # 180 GST + 20 Cess
        finally:
            try:
                frappe.delete_doc("Tax Rule", name, ignore_permissions=True, force=True)
            except Exception:
                pass

    def test_foreign_buyer_skips_gst(self):
        _set_gst("Bihar")
        cust = _customer("gst-foreign@test.com", None)
        frappe.db.set_value("Hosting Customer", cust, {"country": "USA", "state": "Texas"})
        with self._regulated():
            out = tax_breakup(cust, 1000)
        self.assertEqual(out["mode"], "legacy")
        self.assertEqual(out["total"], 0)

    def test_foreign_rule_applies_by_country_state(self):
        _set_gst("Bihar")
        name = frappe.db.get_value("Tax Rule", {"tax_name": "GST-US-TX"}, "name")
        if not name:
            name = frappe.get_doc(
                {"doctype": "Tax Rule", "tax_name": "GST-US-TX", "percentage": 8, "country": "USA", "state": "Texas", "active": 1}
            ).insert(ignore_permissions=True).name
        try:
            cust = _customer("gst-foreign@test.com", None)
            frappe.db.set_value("Hosting Customer", cust, {"country": "USA", "state": "Texas"})
            out = tax_breakup(cust, 1000)
            self.assertEqual(out["total"], 80)
            self.assertIn("GST-US-TX", out["label"])
        finally:
            try:
                frappe.delete_doc("Tax Rule", name, ignore_permissions=True, force=True)
            except Exception:
                pass

    def test_missing_state_falls_back_legacy(self):
        _set_gst("Bihar")
        cust = _customer("gst-nostate@test.com", None)
        frappe.db.set_value("Hosting Customer", cust, "state", "")
        out = tax_breakup(cust, 100)
        self.assertEqual(out["mode"], "legacy")

    def test_invoice_stores_breakup(self):
        from lube_station.lube_station.doctype.hosting_invoice.hosting_invoice import _from_order

        _set_gst("Bihar")
        cust = _customer("gst-bihar@test.com", "Bihar")
        order = frappe.get_doc(
            {
                "doctype": "Order",
                "customer": cust,
                "status": "Pending Review",
                "items": [{"item_type": "Hosting Plan", "reference": "X", "billing_cycle": "Monthly", "unit_price": 1000, "quantity": 1}],
            }
        ).insert(ignore_permissions=True)
        inv = _from_order(order.name, f"gst-test:{order.name}")
        try:
            self.assertEqual(inv.cgst_amount, 90)
            self.assertEqual(inv.sgst_amount, 90)
            self.assertEqual(inv.tax_amount, 180)
        finally:
            frappe.delete_doc("Hosting Invoice", inv.name, ignore_permissions=True)
            frappe.delete_doc("Order", order.name, ignore_permissions=True)
