import frappe
from frappe.model.document import Document


class HostingPlan(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF
        from lube_station.lube_station.doctype.plan_config_field.plan_config_field import PlanConfigField

        config_fields: DF.Table[PlanConfigField]
        is_active: DF.Check
        plan_name: DF.Data
        product_group: DF.Link
        product_type: DF.Literal["Shared Hosting", "Reseller", "VPS", "Dedicated Server", "Cloud", "Email Hosting", "Website Builder", "SSL", "Backup Addon", "Migration Service", "Downloadable Product"]
        product_type_schema: DF.Link | None
        provisioning_module: DF.Link | None
        qty_available: DF.Int
        server_group: DF.Link | None
        stock_control: DF.Check
        welcome_email_template: DF.Link | None
    # end: auto-generated types

    def validate(self):
        if self.stock_control and (self.qty_available or 0) < 0:
            frappe.throw("Qty available cannot be negative")
