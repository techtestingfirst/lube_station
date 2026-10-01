from .base import PaymentGatewayAdapter


class _Stub(PaymentGatewayAdapter):
    def create_payment(self, invoice):
        raise NotImplementedError("Phase 2 gateway inactive")

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


class CCAvenueAdapter(_Stub):
    adapter_name = "CCAvenue"


class PayUIndiaAdapter(_Stub):
    adapter_name = "PayU India"


class CashfreeAdapter(_Stub):
    adapter_name = "Cashfree Payments"


class MollieAdapter(_Stub):
    adapter_name = "Mollie"


class GoCardlessAdapter(_Stub):
    adapter_name = "GoCardless"


class TwoCheckoutAdapter(_Stub):
    adapter_name = "2Checkout / Verifone"
