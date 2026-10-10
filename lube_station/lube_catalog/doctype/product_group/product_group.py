import frappe
from frappe.model.document import Document


class ProductGroup(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        description: DF.TextEditor | None
        group_name: DF.Data
        icon: DF.AttachImage | None
        show_on_portal: DF.Check
        slug: DF.Data | None
        sort_order: DF.Int
    # end: auto-generated types

    def validate(self):
        if self.slug:
            self.slug = self.slug.strip().lower().replace(" ", "-")
