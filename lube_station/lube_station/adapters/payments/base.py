import frappe


class PaymentGatewayAdapter:
    """Common payment interface. No vendor branching in controllers."""

    adapter_name = ""

    def create_payment(self, invoice):
        raise NotImplementedError

    def verify_payment(self, payload):
        raise NotImplementedError

    def handle_webhook(self, payload, headers):
        raise NotImplementedError

    def refund_payment(self, transaction, amount=None):
        raise NotImplementedError

    def create_payment_method(self, customer, token):
        raise NotImplementedError

    def charge_saved_method(self, payment_method, invoice):
        raise NotImplementedError


def require_capability(record, flag: str):
    if not record.get(flag):
        frappe.throw(f"Gateway does not support {flag}")
