import frappe
from frappe.model.document import Document


class HostingPlan(Document):
    def validate(self):
        if self.stock_control and (self.qty_available or 0) < 0:
            frappe.throw("Qty available cannot be negative")
