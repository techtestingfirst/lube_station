import frappe
from frappe.model.document import Document

from lube_station.lube_station.adapters.registry import (
    PAYMENT_PATHS,
    ensure_importable,
    resolve_class_path,
)


class PaymentGatewayAdapter(Document):
    def validate(self):
        self.class_path = resolve_class_path(PAYMENT_PATHS, self.adapter_name, self.class_path)
        if self.active and not self.class_path:
            frappe.throw("Active adapter needs class_path")
        if self.active and self.class_path:
            ensure_importable(self.class_path, self.adapter_name)
