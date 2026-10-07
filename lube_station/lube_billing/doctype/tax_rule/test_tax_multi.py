import frappe
from contextlib import contextmanager
from frappe.tests import IntegrationTestCase

from lube_station.lube_billing.doctype.tax_rule.tax_rule import tax_for


@contextmanager
def _only_owned(owned):
    """Deactivate ambient seller rules so the total is deterministic."""
    others = [r.name for r in frappe.get_all("Tax Rule", {"active": 1}, ["name"]) if r.name not in owned]
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


class TestTaxMulti(IntegrationTestCase):
    def test_tax_multi(self):
        cust = frappe.get_doc({"doctype": "Hosting Customer", "user": "Administrator", "status": "Active"}).insert()
        rules = []
        for tax_name, percentage in (("GST", 10), ("Cess", 5)):
            name = frappe.db.get_value("Tax Rule", {"tax_name": tax_name}, "name")
            if not name:
                name = frappe.get_doc({"doctype": "Tax Rule", "tax_name": tax_name, "percentage": percentage, "active": 1}).insert().name
            rules.append(name)
        try:
            with _only_owned(rules):
                self.assertEqual(tax_for(cust.name, 100), 15)
        finally:
            for name in rules:
                try:
                    frappe.delete_doc("Tax Rule", name, ignore_permissions=True, force=True)
                except Exception:
                    pass
