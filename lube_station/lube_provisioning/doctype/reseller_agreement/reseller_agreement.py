from frappe.model.document import Document


class ResellerAgreement(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        active: DF.Check
        agreement_name: DF.Data
        billing_model: DF.Literal["Wholesale Recurring", "Prepaid Credit", "Per Usage", "Commission"]
        markup_type: DF.Literal["Percentage", "Fixed"]
        markup_value: DF.Float
        provider: DF.Link
        terms_json: DF.Code | None
    # end: auto-generated types

    pass
