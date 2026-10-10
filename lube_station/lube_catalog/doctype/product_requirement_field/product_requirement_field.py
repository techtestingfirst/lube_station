from frappe.model.document import Document


class ProductRequirementField(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        field_key: DF.Data
        field_type: DF.Literal["Text", "Password", "Integer", "Decimal", "Select", "Multi Select", "Checkbox", "JSON"]
        label: DF.Data
        maps_to: DF.Data | None
        options_json: DF.Code | None
        options_source: DF.Literal["Static", "OS Image Catalog", "Location Catalog", "Server Inventory", "Provider API"]
        parent: DF.Data
        parentfield: DF.Data
        parenttype: DF.Data
        required: DF.Check
        validation_rule: DF.Data | None
    # end: auto-generated types

    pass
