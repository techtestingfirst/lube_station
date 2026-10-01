from .base import PaymentGatewayAdapter


class RazorpayAdapter(PaymentGatewayAdapter):
    adapter_name = "Razorpay"

    def create_payment(self, invoice):
        return {"gateway": "Razorpay", "invoice": invoice}

    def verify_payment(self, payload):
        return {"verified": True, "gateway_reference": payload.get("razorpay_payment_id")}

    def handle_webhook(self, payload, headers):
        return {"event_id": payload.get("event_id"), "type": payload.get("event")}

    def refund_payment(self, transaction, amount=None):
        return {"refunded": transaction, "amount": amount}

    def create_payment_method(self, customer, token):
        return {"customer": customer, "token": token}

    def charge_saved_method(self, payment_method, invoice):
        return {"charged": payment_method, "invoice": invoice}
