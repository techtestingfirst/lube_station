import frappe
from frappe.model.document import Document


class ProductGroup(Document):
    def validate(self):
        if self.slug:
            self.slug = self.slug.strip().lower().replace(" ", "-")
