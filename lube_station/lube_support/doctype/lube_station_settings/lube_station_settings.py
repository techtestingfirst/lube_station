from frappe.model.document import Document


class LubeStationSettings(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        aws_access_key_id: DF.Data | None
        aws_region: DF.Data | None
        aws_secret_access_key: DF.Password | None
        bank_details: DF.SmallText | None
        cashfree_app_id: DF.Data | None
        cashfree_sandbox: DF.Check
        cashfree_secret_key: DF.Password | None
        ccavenue_access_code: DF.Data | None
        ccavenue_merchant_id: DF.Data | None
        ccavenue_working_key: DF.Password | None
        company_address: DF.SmallText | None
        company_logo: DF.AttachImage | None
        company_name: DF.Data | None
        company_tax_id: DF.Data | None
        default_tax_code: DF.Link | None
        domain_year_price: DF.Currency
        enabled_gateways: DF.SmallText | None
        fraud_free_email_score: DF.Int
        fraud_large_order_score: DF.Int
        fraud_large_order_total: DF.Currency
        fraud_no_company_score: DF.Int
        free_subdomain_suffixes: DF.SmallText | None
        gocardless_access_token: DF.Password | None
        gocardless_sandbox: DF.Check
        gocardless_webhook_secret: DF.Password | None
        invoice_due_days: DF.Int
        kyc_provider: DF.Literal["Manual", "Digio"]
        mollie_secret_key: DF.Password | None
        payu_merchant_key: DF.Data | None
        payu_merchant_salt: DF.Password | None
        payu_sandbox: DF.Check
        razorpay_auto_capture: DF.Check
        renewal_advance_days: DF.Int
        show_cancellation_link: DF.Check
        support_email: DF.Data | None
        tax_domains: DF.Check
        tax_mode: DF.Literal["Exclusive", "Inclusive"]
        tos_required: DF.Check
        twocheckout_merchant_code: DF.Data | None
        twocheckout_sandbox: DF.Check
        twocheckout_secret_key: DF.Password | None
    # end: auto-generated types

    pass
