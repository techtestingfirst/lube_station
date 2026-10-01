import frappe
from frappe.model.document import Document


class PaymentGatewayAdapter(Document):
    def validate(self):
        if self.active and not self.class_path:
            frappe.throw("Active adapter needs class_path")
