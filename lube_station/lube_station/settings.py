"""Central setup values (Desk: Lube Station Settings) with code fallbacks.

Every value stays editable by the seller in one Settings page; code only
defines defaults used before first save.
"""

import frappe

DEFAULTS = {
    "company_name": "Lube Station",
    "company_address": "",
    "support_email": "",
    "domain_year_price": 15,
    "free_subdomain_suffixes": "",
    "enabled_gateways": "Stripe\nRazorpay\nBank Transfer",
    "tos_required": 1,
    "show_cancellation_link": 1,
    "tax_mode": "Exclusive",
    "tax_domains": 1,
    "invoice_due_days": 7,
    "fraud_free_email_score": 10,
    "fraud_no_company_score": 5,
    "fraud_large_order_total": 1000,
    "fraud_large_order_score": 15,
    "kyc_provider": "Manual",
    "razorpay_auto_capture": 1,
    "bank_details": "",
    "payu_merchant_key": "",
    "payu_merchant_salt": "",
    "payu_sandbox": 1,
    "cashfree_app_id": "",
    "cashfree_secret_key": "",
    "cashfree_sandbox": 1,
    "mollie_secret_key": "",
    "gocardless_access_token": "",
    "gocardless_webhook_secret": "",
    "gocardless_sandbox": 1,
    "twocheckout_merchant_code": "",
    "twocheckout_secret_key": "",
    "twocheckout_sandbox": 1,
    "ccavenue_merchant_id": "",
    "ccavenue_access_code": "",
    "ccavenue_working_key": "",
    "aws_access_key_id": "",
    "aws_secret_access_key": "",
    "aws_region": "us-east-1",
}

# Gateways the checkout bridge knows by Adapter Name. One-time availability
# is still gated per row by Payment Gateway Adapter.active + supports_one_time,
# so GoCardless (mandate flow) and 2Checkout (panel buy-links) stay out of
# one-time checkout through their own flags. Currency support is enforced by
# each adapter (Mollie/PayPal throw on INR until invoice currency lands).
BRIDGED_GATEWAYS = (
    "Stripe",
    "Razorpay",
    "PayPal Checkout",
    "Bank Transfer",
    "CCAvenue",
    "PayU India",
    "Cashfree Payments",
    "Mollie",
    "GoCardless",
    "2Checkout / Verifone",
)


def get_setting(key: str):
    default = DEFAULTS[key]
    try:
        value = frappe.db.get_single_value("Lube Station Settings", key)
    except Exception:
        return default
    if value in (None, ""):
        return default
    return value


def gateway_order() -> list:
    """Enabled gateways in display order, restricted to known registry names."""
    raw = get_setting("enabled_gateways") or ""
    configured = [line.strip() for line in str(raw).splitlines() if line.strip()]
    if not configured:
        configured = [line.strip() for line in str(DEFAULTS["enabled_gateways"]).splitlines()]
    return [g for g in configured if g in BRIDGED_GATEWAYS]
