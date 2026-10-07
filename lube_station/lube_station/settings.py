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
    "enabled_gateways": "Stripe\nRazorpay\nBank Transfer",
    "tos_required": 1,
    "tax_mode": "Exclusive",
    "tax_domains": 1,
    "invoice_due_days": 7,
    "fraud_free_email_score": 10,
    "fraud_no_company_score": 5,
    "fraud_large_order_total": 1000,
    "fraud_large_order_score": 15,
    "razorpay_auto_capture": 1,
    "bank_details": "",
    "payu_merchant_key": "",
    "payu_merchant_salt": "",
    "payu_sandbox": 1,
}

# Gateways with a real payment bridge behind them.
BRIDGED_GATEWAYS = ("Stripe", "Razorpay", "Bank Transfer")


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
    """Enabled gateways in display order, restricted to real bridges."""
    raw = get_setting("enabled_gateways") or ""
    configured = [line.strip() for line in str(raw).splitlines() if line.strip()]
    if not configured:
        configured = [line.strip() for line in str(DEFAULTS["enabled_gateways"]).splitlines()]
    return [g for g in configured if g in BRIDGED_GATEWAYS]
