import frappe
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
        wholesale_cost: DF.Currency | None
    # end: auto-generated types

    def validate(self):
        self._apply_markup()

    def _apply_markup(self):
        """Auto-compute customer recurring_amount from wholesale cost + Reseller Agreement markup.

        Skips when wholesale_cost is 0/unset, no agreement is linked, the agreement
        is inactive, or billing model is Per Usage (metered; needs Usage Snapshot).
        When markup is skipped but wholesale_cost is set, recurring_amount defaults
        to the wholesale cost (no margin).
        """
        if not self.wholesale_cost:
            return

        plan = frappe.get_doc("Hosting Plan", self.hosting_plan)
        agreement_name = plan.reseller_agreement
        if not agreement_name:
            self.recurring_amount = self.wholesale_cost
            return

        agreement = frappe.get_doc("Reseller Agreement", agreement_name)
        if not agreement.active:
            self.recurring_amount = self.wholesale_cost
            return

        if agreement.billing_model == "Per Usage":
            # Metered pricing is driven by Usage Snapshot; cost is the base price.
            self.recurring_amount = self.wholesale_cost
            return

        cost = float(self.wholesale_cost or 0)
        markup_type = agreement.markup_type or "Fixed"
        markup_value = float(agreement.markup_value or 0)

        if markup_type == "Percentage":
            self.recurring_amount = round(cost * (1 + markup_value / 100), 2)
        else:
            self.recurring_amount = round(cost + markup_value, 2)
