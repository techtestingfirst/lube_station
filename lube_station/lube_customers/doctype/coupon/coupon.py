from datetime import date

import frappe
from frappe.model.document import Document

CYCLE_RANK = {"Monthly": 1, "Quarterly": 3, "Semi-Annually": 6, "Annually": 12, "Biennially": 24, "Triennially": 36, "One Time": 0}


class Coupon(Document):
    def validate(self):
        self.code = (self.code or "").strip().upper()
        if (self.value or 0) <= 0:
            frappe.throw("Coupon value must be positive")
        if self.discount_type == "Percentage" and self.value > 100:
            frappe.throw("Percentage cannot exceed 100")

    def is_live(self, today: date | None = None) -> bool:
        today = today or date.today()
        if not self.active:
            return False
        if self.valid_from and today < self.valid_from:
            return False
        if self.valid_to and today > self.valid_to:
            return False
        if self.maximum_uses and (self.used_count or 0) >= self.maximum_uses:
            return False
        return True

    def discount_amount(self, subtotal: float) -> float:
        if not self.is_live():
            return 0
        if self.discount_type == "Fixed Amount":
            return min(self.value, subtotal)
        return round(subtotal * self.value / 100, 2)

    def check_cart(self, cart):
        if not self.is_live():
            frappe.throw("Coupon expired or fully used")
        if self.eligible_groups and cart.get("customer"):
            group = frappe.db.get_value("Hosting Customer", cart.customer, "client_group")
            allowed = [r.client_group for r in self.eligible_groups]
            if group not in allowed:
                frappe.throw("Coupon not valid for your group")
        if self.minimum_cycle:
            need = CYCLE_RANK.get(self.minimum_cycle, 0)
            for item in cart.get("items", []):
                if CYCLE_RANK.get(item.get("billing_cycle"), 0) < need:
                    frappe.throw(f"Coupon needs minimum cycle {self.minimum_cycle}")
