from .base import PaymentGatewayAdapter


class StripeAdapter(PaymentGatewayAdapter):
    adapter_name = "Stripe"

    def create_payment(self, invoice):
        return {"gateway": "Stripe", "invoice": invoice, "mode": "one-time"}

    def verify_payment(self, payload):
        return {"verified": True, "gateway_reference": payload.get("id")}

    def handle_webhook(self, payload, headers):
        return {"event_id": payload.get("id"), "type": payload.get("type")}

    def refund_payment(self, transaction, amount=None):
        return {"refunded": transaction, "amount": amount}

    def create_payment_method(self, customer, token):
        return {"customer": customer, "token": token}

    def charge_saved_method(self, payment_method, invoice):
        return {"charged": payment_method, "invoice": invoice}
