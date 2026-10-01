import frappe

from .base import PaymentGatewayAdapter


class BankTransferAdapter(PaymentGatewayAdapter):
    adapter_name = "Bank Transfer"

    def create_payment(self, invoice):
        return {"gateway": "Bank Transfer", "invoice": invoice, "manual": True}

    def verify_payment(self, payload):
        frappe.throw("Bank transfer has no automatic verification")

    def handle_webhook(self, payload, headers):
        frappe.throw("Bank transfer has no webhooks")

    def refund_payment(self, transaction, amount=None):
        return {"refunded": transaction, "amount": amount, "manual": True}

    def create_payment_method(self, customer, token):
        frappe.throw("Bank transfer supports no tokenization")

    def charge_saved_method(self, payment_method, invoice):
        frappe.throw("Bank transfer supports no auto-charge")
