from frappe.model.document import Document


class DownloadCategory(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        category_name: DF.Data
        is_public: DF.Check
        parent_category: DF.Link | None
    # end: auto-generated types

    pass
