import frappe
from frappe.model.document import Document


class HostingCustomer(Document):
    def validate(self):
        if self.user and not frappe.db.exists("User", self.user):
            frappe.throw("Linked User missing")

    def has_permission(self, permtype, user=None):
        if self.flags.ignore_permissions:
            return True
        user = user or frappe.session.user
        if "System Manager" in frappe.get_roles(user):
            return True
        if permtype == "read":
            linked = frappe.db.get_value("Hosting Customer", {"user": user}, "name")
            return linked == self.name
        return False
