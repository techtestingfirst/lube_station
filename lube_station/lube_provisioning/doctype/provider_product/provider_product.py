import json

import frappe
from frappe.model.document import Document


class ProviderProduct(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        available_quantity: DF.Int
        external_product_id: DF.Data | None
        plans_json: DF.Code | None
        product_type: DF.Literal["Shared Hosting", "Reseller", "VPS", "Dedicated Server", "Cloud", "Email Hosting", "Website Builder", "SSL", "Backup Addon", "Migration Service", "Downloadable Product"]
        provider: DF.Link
        regions_json: DF.Code | None
        sync_status: DF.Literal["Manual", "Synced", "Stale", "Sync Failed"]
    # end: auto-generated types

    def validate(self):
        for field in ("regions_json", "plans_json"):
            value = (self.get(field) or "").strip()
            if not value:
                continue
            try:
                json.loads(value)
            except ValueError:
                frappe.throw(f"{self.meta.get_label(field)} must be valid JSON")
