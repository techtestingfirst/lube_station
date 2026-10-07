import json

import frappe
from frappe.model.document import Document


class ProviderProduct(Document):
    def validate(self):
        for field in ("regions_json", "plans_json"):
            value = (self.get(field) or "").strip()
            if not value:
                continue
            try:
                json.loads(value)
            except ValueError:
                frappe.throw(f"{self.meta.get_label(field)} must be valid JSON")
