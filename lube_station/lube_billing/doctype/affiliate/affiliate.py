import frappe
from frappe.model.document import Document


class Affiliate(Document):
    def after_insert(self):
        try:
            from lube_station.lube_station.notifications.events import notify_customer

            notify_customer(self.customer, "affiliate_signup", self.name, {"affiliate": self.name, "code": self.get("referral_code") or ""})
        except Exception:
            pass
