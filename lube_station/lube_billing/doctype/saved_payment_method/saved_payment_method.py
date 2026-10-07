import frappe
from frappe.model.document import Document


class SavedPaymentMethod(Document):
    def validate(self):
        banned = ("pan", "cvv", "card_number")
        blob = f"{self.token or ''} {self.last_four or ''}".lower()
        if any(b in blob for b in banned):
            frappe.throw("Never store PAN or CVV")
        if self.default_method:
            others = frappe.get_all("Saved Payment Method", {"customer": self.customer, "name": ["!=", self.name]}, ["name"])
            for o in others:
                frappe.db.set_value("Saved Payment Method", o.name, "default_method", 0)
