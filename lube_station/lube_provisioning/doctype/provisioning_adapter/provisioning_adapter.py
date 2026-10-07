import frappe
from frappe.model.document import Document

from lube_station.lube_station.adapters.registry import (
    PROVISIONING_PATHS,
    ensure_importable,
    implemented_lifecycle,
    resolve_class_path,
)


class ProvisioningAdapter(Document):
    def validate(self):
        self.class_path = resolve_class_path(PROVISIONING_PATHS, self.adapter_name, self.class_path)
        if self.class_path:
            self.lifecycle_methods = ", ".join(implemented_lifecycle(self.class_path))
        if self.active and not self.class_path:
            frappe.throw("Active adapter needs class_path")
        if self.active and self.class_path:
            ensure_importable(self.class_path, self.adapter_name)
