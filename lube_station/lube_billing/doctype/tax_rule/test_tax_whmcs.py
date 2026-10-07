from contextlib import contextmanager

import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_billing.doctype.tax_rule.tax_rule import matching_rules, tax_breakup


def _cust(email, country="India", state="Bihar"):
    name = frappe.db.get_value("Hosting Customer", {"user": email}, "name")
    if name:
        cust = frappe.get_doc("Hosting Customer", name)
    else:
        user = email if frappe.db.exists("User", email) else frappe.get_doc(
            {"doctype": "User", "email": email, "first_name": "Tax", "enabled": 1}
        ).insert(ignore_permissions=True).name
        cust = frappe.get_doc({"doctype": "Hosting Customer", "user": user, "status": "Active"}).insert()
    frappe.db.set_value("Hosting Customer", cust.name, {"country": country, "state": state})
    return cust.name


def _rule(tax_name, percentage, country="", state="", level="1"):
    name = frappe.db.get_value("Tax Rule", {"tax_name": tax_name}, "name")
    if name:
        return name
    doc = frappe.get_doc(
        {"doctype": "Tax Rule", "tax_name": tax_name, "percentage": percentage, "country": country, "state": state, "active": 1}
    )
    doc.set("level", level)
    return doc.insert(ignore_permissions=True).name


class TestWhmcsTax(IntegrationTestCase):
    @contextmanager
    def _only_my_rules(self):
        """Deactivate every non-W rule so seller config can't skew totals."""
        others = [
            r.name
            for r in frappe.get_all("Tax Rule", {"active": 1}, ["name", "tax_name"])
            if not (r.tax_name or "").startswith("W-")
        ]
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

    def setUp(self):
        # Deterministic base: only rules this test owns may exist as W-*,
        # and GST stays off (global Settings leak across test classes).
        for tn in ("W-State", "W-Other", "W-L1", "W-L2", "W-Incl"):
            name = frappe.db.get_value("Tax Rule", {"tax_name": tn}, "name")
            if name:
                try:
                    frappe.delete_doc("Tax Rule", name, ignore_permissions=True, force=True)
                except Exception:
                    pass
        self._gst_state = frappe.db.get_single_value("GST Settings", "seller_state")
        frappe.db.set_single_value("GST Settings", "seller_state", "")
        super().setUp()

    def tearDown(self):
        frappe.db.set_single_value("GST Settings", "seller_state", self._gst_state or "")
        super().tearDown()

    @classmethod
    def tearDownClass(cls):
        for tn in ("W-State", "W-Other", "W-L1", "W-L2", "W-Incl"):
            name = frappe.db.get_value("Tax Rule", {"tax_name": tn}, "name")
            if name:
                frappe.delete_doc("Tax Rule", name, ignore_permissions=True, force=True)
        for email in ("w-bihar@test.com", "w-maha@test.com", "w-us@test.com"):
            name = frappe.db.get_value("Hosting Customer", {"user": email}, "name")
            if name:
                frappe.delete_doc("Hosting Customer", name, ignore_permissions=True)
            if frappe.db.exists("User", email):
                frappe.delete_doc("User", email, ignore_permissions=True)
        super().tearDownClass()

    def test_state_rule_matches_only_that_state(self):
        _rule("W-State", 5, country="India", state="Bihar")
        _rule("W-Other", 7, country="India", state="Maharashtra")
        names = [r.tax_name for r in matching_rules(_cust("w-bihar@test.com", "India", "Bihar"))]
        self.assertIn("W-State", names)
        self.assertNotIn("W-Other", names)

    def test_country_mismatch_excluded(self):
        _rule("W-State", 5, country="India", state="Bihar")
        names = [r.tax_name for r in matching_rules(_cust("w-us@test.com", "United States", "Texas"))]
        self.assertNotIn("W-State", names)

    def test_two_levels_compound(self):
        _rule("W-L1", 10)
        _rule("W-L2", 5, level="2")
        with self._only_my_rules():
            out = tax_breakup(_cust("w-bihar@test.com", "India", "Bihar"), [{"amount": 100, "taxable": True}])
        # L1 = 10 on 100, L2 = 5% on (100+10) = 5.5
        self.assertEqual(out["total"], 15.5)
        self.assertEqual(out["mode"], "exclusive")

    def test_inclusive_backs_out(self):
        _rule("W-Incl", 10)
        frappe.db.set_single_value("Lube Station Settings", "tax_mode", "Inclusive")
        try:
            with self._only_my_rules():
                out = tax_breakup(_cust("w-maha@test.com", "India", "Maharashtra"), [{"amount": 110, "taxable": True}])
            self.assertAlmostEqual(out["total"], 10, places=2)
        finally:
            frappe.db.set_single_value("Lube Station Settings", "tax_mode", "Exclusive")

    def test_nontaxable_line_excluded(self):
        _rule("W-State", 5, country="India", state="Bihar")
        with self._only_my_rules():
            out = tax_breakup(
                _cust("w-bihar@test.com", "India", "Bihar"),
                [{"amount": 100, "taxable": True}, {"amount": 100, "taxable": False}],
            )
        self.assertEqual(out["taxable_base"], 100)
        self.assertEqual(out["total"], 5)
