import frappe
from frappe.tests import IntegrationTestCase


class TestCoupon(IntegrationTestCase):
    def test_coupon(self):
        coupon = frappe.get_doc({"doctype": "Coupon", "code": "SAVE10", "discount_type": "Percentage", "value": 10, "active": 1, "maximum_uses": 1}).insert()
        self.assertEqual(coupon.discount_amount(200), 20)
        coupon.used_count = 1
        coupon.save()
        self.assertEqual(coupon.discount_amount(200), 0)
        fixed = frappe.get_doc({"doctype": "Coupon", "code": "FLAT50", "discount_type": "Fixed Amount", "value": 50, "active": 1}).insert()
        self.assertEqual(fixed.discount_amount(30), 30)
