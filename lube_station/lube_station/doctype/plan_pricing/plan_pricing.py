from frappe.model.document import Document


class PlanPricing(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        billing_cycle: DF.Literal["Monthly", "Quarterly", "Semi-Annually", "Annually", "Biennially", "Triennially", "One Time"]
        currency: DF.Link | None
        hosting_plan: DF.Link
        recurring_amount: DF.Currency
        setup_fee: DF.Currency
    # end: auto-generated types

    pass
