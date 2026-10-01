import frappe
from frappe.model.document import Document


class DNSRecord(Document):
    def validate(self):
        if self.record_type == "MX" and not (self.priority or 0):
            frappe.throw("MX needs priority")

    def on_update(self):
        from lube_station.lube_station.domains.dns import sync_record

        try:
            sync_record(self.name)
        except Exception:
            pass
