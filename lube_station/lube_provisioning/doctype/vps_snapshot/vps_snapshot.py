import frappe
from frappe.model.document import Document


class VPSSnapshot(Document):
    def validate(self):
        if self.instance and not frappe.db.exists("VPS Instance", self.instance):
            frappe.throw(f"Unknown VPS instance {self.instance}")
