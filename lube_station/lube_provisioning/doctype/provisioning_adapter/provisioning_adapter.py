import frappe
from frappe.model.document import Document

from lube_station.lube_station.adapters.registry import (
    PROVISIONING_PATHS,
    ensure_importable,
    implemented_lifecycle,
    resolve_class_path,
)


class ProvisioningAdapter(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        active: DF.Check
        adapter_name: DF.Data
        api_mode: DF.Literal["", "REST", "XML API", "JSON API", "HTTP API", "WHM API", "EPP", "Custom"]
        class_path: DF.Data | None
        lifecycle_methods: DF.SmallText | None
        supports_change_plan: DF.Check
        supports_resize: DF.Check
        supports_sso: DF.Check
        supports_usage: DF.Check
        vendor_name: DF.Literal["cPanel", "Plesk", "DirectAdmin", "Virtualizor", "Proxmox", "Hetzner", "AWS", "Cloudflare", "Custom"]
    # end: auto-generated types

    def validate(self):
        self.class_path = resolve_class_path(PROVISIONING_PATHS, self.adapter_name, self.class_path)
        if self.class_path:
            self.lifecycle_methods = ", ".join(implemented_lifecycle(self.class_path))
        if self.active and not self.class_path:
            frappe.throw("Active adapter needs class_path")
        if self.active and self.class_path:
            ensure_importable(self.class_path, self.adapter_name)
