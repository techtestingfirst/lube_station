# Lube Station Seller Setup Manual

Audience: seller or admin who sets up products for sale.
Goal: configure groups, servers, provisioning, plans, pricing, and add-ons so a customer can buy on the portal without seller help after setup.
Result after you follow this manual: each service has a buyable plan, correct checkout fields, correct price cycles, correct provisioning path, and correct invoice and dunning behavior.

Conventions used in this manual:

- Screen: Desk location and view to open.
- DocType: exact DocType name in `lube_station`.
- Field format in each table: Label (fieldname, type) — what to enter — use and purpose — example or rule.
- Required means Frappe blocks save when empty. Other fields are optional but affect checkout, provisioning, tax, or display.

Desk base URL in development: `http://lubestation.localhost:8000`.
Desk route pattern: `/app/<doctype-slug>`.
Portal base URL in development: `http://localhost:8080`.

How to read a service section: each of sections 8 to 19 follows the same shape.

1. When to use it.
2. Records you need.
3. Steps in order.
4. Every field explained.
5. Pricing guidance.
6. Test before you mark it live.
7. Common mistakes.

Do the global setup in sections 3 to 7 once. Then do only the service section you sell. Do not skip the test step.

## 0. Seller workflow in order

Do the work in this order. Each row depends on the row above it.

1. Lube Station Settings: company, tax mode, gateways, due days, fraud, KYC.
2. Payment Gateway Adapter: activate Stripe, Razorpay, PayPal, Bank Transfer. Add keys through site config or the linked payment implementation. Never store secrets in Data fields.
3. Tax: Tax Code, Tax Rule, GST Settings where India GST applies.
4. Dunning Rule: at least one active global rule.
5. Product Group: one per storefront section.
6. Infrastructure path: owned servers go in Server and Server Group. Rented or resold capacity goes in Infrastructure Provider, Provider Product, Reseller Agreement. Certificates and third-party services go in a Reseller Program provider.
7. Product Type Schema: checkout fields per product type.
8. Hosting Plan: one plan per sellable item. Select Product Type from the 11 options.
9. Type-specific configuration: VPS Configuration, Dedicated Server Configuration plus Inventory, Download Category plus Downloadable Asset, TLD Pricing plus Registrar Account for domains.
10. Plan Pricing: one record per billing cycle you sell.
11. Test order, invoice, payment, Service status, welcome email, suspend and unsuspend.

## 1. WHMCS to Lube Station concept map

| WHMCS concept | Lube Station equivalent | Notes |
|---|---|---|
| Product Group | Product Group | Same purpose. Lube Station has no per-group gateway list. |
| Product (Shared, Reseller, Server/VPS, Other) | Hosting Plan with Product Type | One DocType covers 11 types. See section 5. |
| Details tab, Require Domain | Product Type Schema | Flags plus custom fields. See section 6. |
| Pricing tab | Plan Pricing (child pricing per cycle) | One record per billing cycle. See section 7. |
| Configurable Options price on same invoice | Plan Config Field rows plus schema requirement fields | Same invoice and cycle as main plan. See section 16. |
| Product Addons with own cycle | Separate Hosting Plan (SSL, Backup Addon, Migration Service) | Independent billing cycle. See sections 14 and 16. |
| Module (cPanel, Plesk, SolusVM) | Provisioning Module + Provisioning Adapter + Infrastructure Provider + Provider Product + Reseller Agreement | Lube Station splits one WHMCS module into five records. See section 2. |
| Server | Server | Same purpose. Secret uses Password type. Health fields are read-only. |
| Server group assignment | Server Group with fill strategy | Round Robin, Least Full, Manual. |
| MarketConnect | Infrastructure Provider of type Reseller Program + Provider Product + Reseller Agreement | Manual setup. No built-in store. |
| Domain pricing per TLD | TLD Pricing | Register, renew, and transfer price per TLD. See section 15. |
| Welcome Email | Hosting Plan field Welcome Email Template (link to Email Template) | Same purpose. |
| Automation (create, suspend, terminate) | Provisioning jobs + Service status + Dunning Rule | See sections 17 and 18. |

## 2. How Lube Station handles modules

WHMCS uses one module. The module holds code and server binding.

Lube Station uses five records. Each record has one job.

1. Provisioning Adapter: code registry. Tells the system which Python class talks to cPanel, Plesk, DirectAdmin, Virtualizor, Proxmox, Hetzner, AWS, or Cloudflare. One row per vendor.
2. Provisioning Module: seller-facing pointer. You pick this on the Hosting Plan. It links to one adapter and records the control panel name.
3. Infrastructure Provider: upstream account. Holds the API endpoint, the masked credential, and Active or Maintenance or Disabled status.
4. Provider Product: upstream catalog entry. Holds the vendor product code and the regions and plans JSON that feed checkout choices.
5. Reseller Agreement: commercial terms. Holds billing model, markup, and terms JSON.

Use this rule:

- Sell from owned cPanel, Plesk, or DirectAdmin servers: set Provisioning Module and Server Group on the plan. Provider records stay empty, or use a Manual path for audit only.
- Sell from VPS, cloud, or dedicated inventory: set Infrastructure Provider, Provider Product, and Reseller Agreement. Link the plan to the correct configuration DocType (VPS Configuration, Dedicated Server Configuration).
- Resell third-party SSL, SEO, or builder services: create a Provider of type Reseller Program, one Provider Product per upstream item, and one active Reseller Agreement.

## 3. Prerequisites

Complete this section before you create any plan.

### 3.1 Lube Station Settings

DocType: Lube Station Settings (Single).
Screen: Desk > Lube Station > Lube Station Settings.

Open the record, fill each group, save once at the end.

Business group:

- Company Name (`company_name`, Data, default `Lube Station`). What to enter: legal or brand name shown on portal, invoices, and mail. Purpose: branding and invoice header. Example: `Acme Hosting Pvt Ltd`.
- Company Logo (`company_logo`, Attach Image). What to enter: logo file. Purpose: portal and invoice branding. Use a small PNG.
- Company Address (`company_address`, Small Text). What to enter: full postal address. Purpose: invoice footer and contact page. Enter street, city, state, PIN, country.
- Company Tax ID (GSTIN/VAT) (`company_tax_id`, Data). What to enter: GSTIN or VAT number. Purpose: printed on invoices for tax compliance. Leave empty only when you do not charge tax.
- Default Tax Code (SAC/HSN) (`default_tax_code`, Link to Tax Code). What to enter: pick the SAC or HSN row that covers most plans. Purpose: fallback tax code on invoice items when a plan has no Tax Code. See section 3.3.
- Support Email (`support_email`, Data with Email validation). What to enter: mailbox that receives support mail. Purpose: reply-to on system mail and support contact. Example: `support@example.com`.

Catalog and cart group:

- Domain Price / Year (`domain_year_price`, Currency, default 15). What to enter: fallback yearly domain price. Purpose: used when no TLD Pricing row matches the TLD. Set your most common `.com` price here, then override per TLD in TLD Pricing.
- Free Subdomain Suffixes (one per line) (`free_subdomain_suffixes`, Small Text). What to enter: one suffix per line, for example `example.in`. Purpose: list of suffixes a customer can pick when a plan allows a free subdomain instead of a paid domain. Leave empty when you do not offer free subdomains.

Payment gateways group:

- Enabled Gateways (one per line, in display order) (`enabled_gateways`, Small Text, default `Stripe`, `Razorpay`, `Bank Transfer`). What to enter: one adapter name per line, in the order the portal shows them. Purpose: controls which active Payment Gateway Adapter rows appear at checkout and in which order. Names must match Adapter Name exactly.

Checkout group:

- Require TOS Acceptance (`tos_required`, Check, default on). What to enter: keep on unless legal says otherwise. Purpose: blocks checkout until the customer accepts terms. The customer record stores `tos_accepted`.
- Show Cancellation Link (`show_cancellation_link`, Check, default on). What to enter: keep on. Purpose: shows the Cancel affordance on the portal Service page. Turn off only when you handle cancellations by ticket.

Tax group:

- Tax Mode (`tax_mode`, Select, default `Exclusive`). What to enter: `Exclusive` adds tax on top of the plan price. `Inclusive` treats the plan price as already holding tax. Purpose: controls invoice math for every taxable plan. Pick one and keep it. Changing it later changes every future invoice.
- Tax Domain Items (`tax_domains`, Check, default on). What to enter: keep on when domains are taxable in your region. Purpose: applies matching Tax Rules to domain line items. Turn off when domains are tax-exempt.
- Invoice Due In (days) (`invoice_due_days`, Int, default 7). What to enter: fallback grace for invoices with no Service date (domain-only, legacy, overage invoices). Purpose: WHMCS rule applies here — first invoices are due on receipt (today), renewal invoices are due on the Service Next Due Date (period boundary). This setting only fires when no Service Next Due Date exists, as `today + invoice_due_days`. Dunning `overdue_days` then counts from whatever Due Date lands on the invoice.
- Renewal Advance Days (`renewal_advance_days`, Int, default 14). What to enter: days before Next Due Date the daily cron `generate_upcoming_renewals()` raises the renewal invoice. Purpose: gives the customer time to pay before suspension. Only Active services with Next Due Date inside `(today, today + advance]` get invoiced; overdue ones are skipped as already invoiced; repeats are blocked by the `renew:{order}:{period}` idempotency key. Example: 14 means a service due on the 30th gets invoiced around the 16th, with Due Date set to the 30th itself. Yes, both settings are still live and WHMCS-matched — keep them.

Fraud screening group (0 disables a rule):

- Free-Email Score (`fraud_free_email_score`, Int, default 10). Purpose: points added to Order `fraud_score` when the customer uses a free mailbox (gmail, yahoo, and similar). Set 0 to stop this check.
- No-Company Score (`fraud_no_company_score`, Int, default 5). Purpose: points added when Hosting Customer `company` is empty on a business order. Set 0 to stop this check.
- Large Order Above (`fraud_large_order_total`, Currency, default 1000). Purpose: threshold that marks an order as large. Only orders above this get the large-order score.
- Large-Order Score (`fraud_large_order_score`, Int, default 15). Purpose: points added when Order `total` crosses the threshold above. High scores push the order toward Fraud status for manual review.

Identity verification (KYC) group:

- KYC Provider (`kyc_provider`, Select: Manual, Digio, default Manual). Purpose: default verification path for new customers. Manual means staff review documents. Digio means electronic OVD check. You can override per customer in Hosting Customer `kyc_provider`. Live Digio needs credentials before it works.

Payments group — read this first, two tracks:

Yes, the Frappe Payments app is installed (`apps.txt` holds `payments`) and Lube Station uses it — but only for one track. Keys live in two different places by design:

- Track A, through the Payments app: Stripe, Razorpay, PayPal, PayTM, Braintree. Keys go in the Payments-app DocTypes `Stripe Settings` (Publishable plus Secret keys; saving auto-creates a `Payment Gateway` row), `Razorpay Settings` (API Key plus Secret), `PayPal Settings`, `Paytm Settings` (Merchant ID plus Merchant Key, staging flag), `Braintree Settings` (Merchant ID, Public Key, Private Key, sandbox flag). Stripe and Razorpay check out through hosted-page helpers in `payments/links.py` (`_stripe_url`, `_razorpay_url`); PayPal, PayTM, and Braintree go through the generic `_adapter_url` dispatch to their adapter `create_payment`, which calls the same `settings.get_payment_url()`. The Payments app writes `Integration Request` rows, and on callback `webhooks._mark_paid()` flips Hosting Invoice to Paid and fulfils or unsuspends Services. Nothing in `Payment Gateway Adapter` holds these secrets.
- Track B, direct custom adapters: PayU, Cashfree, CCAvenue, Mollie, GoCardless, 2Checkout, Bank Transfer. Keys go in Lube Station Settings fields below (merchant key plus salt, app id plus secret, working key, access token, bank text). Each adapter under `adapters/payments/` reads them via `get_setting()` (`payu.py:68-72`, `cashfree.py:43-47`, `bank_transfer.py:45`) and verifies its own return: `payu_return`, `ccavenue_return`, or the generic `handle_webhook` with signing secrets from `webhook_secrets` in site config. Bank Transfer has no online capture — staff approve via `approve_bank_transfer`, which marks the Pending Payment Transaction Success and calls `_mark_paid`.
- Bridged checkout: `settings.py` `BRIDGED_GATEWAYS` holds all twelve registry names. `payment_link` keeps its Stripe, Razorpay, and Bank Transfer branches and sends every other active one-time gateway through `_adapter_url` (`links.py`), which calls `adapter.create_payment` and normalizes the vendor shape into what the portal `pay()` handler consumes. Per-gateway checkout behavior:
  - Stripe, Razorpay: Payments-app hosted pages (unchanged). Razorpay verify button still polls `verify_razorpay_payment` for stuck UPI flows.
  - Bank Transfer: manual instructions plus staff `approve_bank_transfer` (unchanged).
  - PayU India: portal auto-POSTs a hidden form to `post_url` with `params` (key, txnid, amount, hash). Return lands on `payu_return`, which verifies the hash and marks paid.
  - CCAvenue: portal auto-POSTs `encRequest` plus `access_code` to `post_url`. Return lands on `ccavenue_return`, which decrypts and marks paid.
  - Cashfree Payments: portal loads the Cashfree JS SDK and opens `checkout()` with `payment_session_id`. SDK mode follows Lube Station Settings `cashfree_sandbox` (sandbox vs production). Webhooks go through generic `handle_webhook` with `webhook_secrets` in site config.
  - Mollie: `approve_url` redirect. Throws `Mollie does not support INR` on INR invoices until invoice currency lands.
  - PayPal Checkout: REST `approve_url` redirect (replaces the old classic NVP page, which never supported INR). Throws on INR the same way until invoice currency lands.
  - PayTM: `paytm_checkout` redirect. INR-native, so it works on today's invoices. Checksum is verified locally with `paytmchecksum`; capture confirmation arrives on the Payments-app `verify_transaction` callback, which finalizes through Integration Request to `Hosting Invoice.on_payment_authorized`. Refunds stay manual (merchant panel).
  - Braintree: `braintree_checkout` redirect (Drop-in nonce flow). INR is in its supported list. Charge confirmation and vaulted auto-charge run through the braintree SDK; server webhooks are not used — confirmation comes back through the checkout page.
  - GoCardless: stays out through `supports_one_time = 0`. `pick_gateway` throws `lacks one-time support`. It is a mandate flow with no one-time hosted step.
  - 2Checkout: stays out through `supports_one_time = 0`. Sales start from panel buy-links; `create_payment` throws that message by design and `verify_payment` reconciles after payment.
- Listing rule: portal `payment_gateways` shows active rows with `supports_one_time = 1` in `enabled_gateways` order. So list every gateway you accept in `enabled_gateways`, then Active only the rows whose keys are set. Mollie and PayPal stay listed when active but error clearly at link time on INR.

Field reference:

- Razorpay Auto-Capture (`razorpay_auto_capture`, Check, default on). Purpose: passed as `payment_capture=1` in `_razorpay_url` (`links.py:71`). Captures at once instead of authorize-then-capture. Without it test payments sit `authorized`, reconcile sees no capture, invoice stays Unpaid. Turn off only when you capture manually.
- Bank Details (`bank_details`, Small Text). Purpose: instructions shown for Bank Transfer checkout (account name, number, IFSC, branch). Enter the exact text the customer must use to pay.
- PayU Merchant Key (`payu_merchant_key`, Data), PayU Merchant Salt (`payu_merchant_salt`, Password), PayU Sandbox (`payu_sandbox`, Check default on). Purpose: live PayU credentials and test flag. Keep Sandbox on until live payments pass.
- Cashfree App ID (`cashfree_app_id`, Data), Cashfree Secret Key (`cashfree_secret_key`, Password), Cashfree Sandbox (`cashfree_sandbox`, Check default on). Purpose: same pattern for Cashfree.
- Mollie Secret Key (`mollie_secret_key`, Password). Purpose: Mollie live secret. No sandbox flag here. Test with small live amounts or Mollie test keys per vendor docs.
- GoCardless Access Token (`gocardless_access_token`, Password), GoCardless Webhook Secret (`gocardless_webhook_secret`, Password), GoCardless Sandbox (`gocardless_sandbox`, Check default on). Purpose: direct-debit credentials plus webhook signing secret used to verify callbacks.
- CCAvenue Merchant ID (`ccavenue_merchant_id`, Data), CCAvenue Access Code (`ccavenue_access_code`, Data), CCAvenue Working Key (`ccavenue_working_key`, Password). Purpose: CCAvenue triple needed to sign payment requests.
- 2Checkout Merchant Code (`twocheckout_merchant_code`, Data), 2Checkout Secret Key (`twocheckout_secret_key`, Password), 2Checkout Sandbox (`twocheckout_sandbox`, Check default on). Purpose: 2Checkout credentials plus test flag.

AWS group (separate section, not payments):

These three fields sit under their own `AWS (Provisioning / Storage)` section in Desk. They were previously rendered inside the Payments area by field order — you were right to flag that. They have no payment role. Code use only: `adapters/provisioning/aws.py:79-81` reads them to sign AWS API calls for Cloud provisioning. Leave empty unless you sell AWS-backed Cloud or use AWS storage.

- AWS Access Key ID (`aws_access_key_id`, Data). Purpose: IAM key id for AWS API calls.
- AWS Secret Access Key (`aws_secret_access_key`, Password). Purpose: IAM secret, masked. Never paste into a Data field.
- AWS Region (`aws_region`, Data default `us-east-1`). Purpose: endpoint region, for example `us-east-1` or `ap-south-1`.

Steps:

1. Open Lube Station Settings.
2. Fill Business and Support Email.
3. Fill Tax Mode, Invoice Due In, Renewal Advance Days.
4. List Enabled Gateways in portal display order.
5. Fill fraud scores or set 0 to disable a check.
6. Select KYC Provider.
7. Fill only the gateway keys you sell with. Leave the rest empty.
8. Save.

### 3.2 Payment gateway adapter

DocType: Payment Gateway Adapter (registry).
Screen: Desk > Lube Station > Payment Gateway Adapter List.

This record does not hold secret keys. It holds the vendor name, the code path, and what the vendor can do. Key placement splits by track: Stripe, Razorpay, and PayPal keys live in the Frappe Payments app (`Stripe Settings`, `Razorpay Settings`, `PayPal Settings`) — create those rows with keys first or `payment_link` throws `not configured`. PayU, Cashfree, CCAvenue, Mollie, GoCardless, 2Checkout, and Bank Transfer keys live in Lube Station Settings section 3.1 or signing secrets in `webhook_secrets` in site config.

Every field:

- Adapter Name (`adapter_name`, Data, required, unique). What to enter: display name used in `enabled_gateways` and on Payment Transaction `gateway`. Purpose: join key between settings, checkout, and transaction log. Example: `Stripe`. Keep spelling stable. Renaming breaks the match with past transactions.
- Vendor Name (`vendor_name`, Select, required): Stripe, Razorpay, PayPal, Manual, CCAvenue, PayU, Cashfree, Mollie, GoCardless, 2Checkout, Custom. Purpose: picks the built-in code path on save. Select Custom only when a developer added a new adapter class.
- Class Path (`class_path`, Data). Purpose: dotted Python path to the adapter class, for example `lube_station.lube_station.adapters.payments.stripe.StripeAdapter`. Leave empty for known vendors. It fills on save. Enter a path only for Custom. A wrong path on an active record is rejected on save.
- Supported Methods (`supported_methods`, Small Text). Purpose: free note of card, UPI, netbanking, or EMI methods this gateway accepts. Display and audit note only.
- Supports One Time (`supports_one_time`, Check, default on). Purpose: gateway can take a single invoice payment. Keep on for cards, UPI, and bank transfer instructions.
- Supports Recurring (`supports_recurring`, Check, default off). Purpose: gateway can auto-charge a Saved Payment Method on renewal. Turn on only when the vendor supports mandates or subscriptions and you tested auto-charge.
- Supports Tokenization (`supports_tokenization`, Check, default off). Purpose: gateway can store a card or mandate token instead of raw details. Required before Saved Payment Method rows work. Saved rows hold tokens only, never card numbers.
- Supports Refunds (`supports_refunds`, Check, default off), Supports Partial Refunds (`supports_partial_refunds`, Check, default off). Purpose: marks whether Desk refund actions can call the vendor, and whether a part of the amount can return. Leave off when you refund by manual bank transfer.
- Webhook Events (`webhook_events`, Small Text). Purpose: note of which callback events you accept, for example `payment.success, payment.failed`. Used for audit and webhook setup.
- Supported Currencies (`supported_currencies`, Small Text). Purpose: note of ISO codes the gateway settles, for example `INR, USD`. Prevents selling a currency the gateway rejects.
- Supported Countries (`supported_countries`, Small Text). Purpose: note of country coverage. Used when you limit checkout by region.
- Sandbox Supported (`sandbox_supported`, Check, default on). Purpose: vendor has a test mode. Keep on until live traffic passes.
- Active (`active`, Check, default off). Purpose: makes this gateway available at checkout when its name also appears in Lube Station Settings `enabled_gateways`. Inactive hides it even when listed.

Steps:

1. Open the Payment Gateway Adapter list.
2. Confirm the row for your gateway exists. Ten rows seed with correct Class Paths. PayU, CCAvenue, Cashfree, and Mollie seed inactive — Active them only after keys are set.
3. For Stripe: create `Stripe Settings` in the Payments app with Publishable plus Secret keys first. Saving auto-creates the `Payment Gateway` row `_stripe_url` looks up. For Razorpay: create `Razorpay Settings` with API Key plus Secret first. For PayPal: create `PayPal Settings` first, and note REST PayPal throws on INR invoices until multi-currency lands. For PayTM: create `Paytm Settings` with Merchant ID plus Merchant Key first (staging on for tests). For Braintree: create `Braintree Settings` with Merchant ID, Public Key, Private Key first (sandbox on for tests). PayTM and Braintree seed inactive — Active them only after keys are set.
4. Open the adapter row.
5. Select Vendor Name.
6. Leave Class Path empty for known vendors. Enter a path only for Custom.
7. Set the Supports flags to match the vendor.
8. Check Active.
9. Save.
10. Add the gateway name on its own line in Lube Station Settings `enabled_gateways`. Only active rows with `supports_one_time = 1` list and check out; GoCardless and 2Checkout stay out by flag with a clear error.
11. For Track B gateways (PayU, Cashfree, CCAvenue, Mollie, GoCardless, 2Checkout, Bank Transfer) configure keys in Lube Station Settings per section 3.1. Do not store secret keys in Data fields. Put webhook signing secrets in `webhook_secrets` in site config.

WHMCS difference: WHMCS enables gateways per product group. Lube Station enables adapters globally and controls tax and due dates in Lube Station Settings.

For Vendor Custom, a developer must first add the adapter class. A seller cannot do this from Desk. Steps: create a file under `adapters/payments/`, subclass `PaymentGatewayAdapter`, implement each supported method, take no constructor arguments, reload the bench, then select Vendor Custom and enter the dotted path. Point webhooks at the generic endpoint with `gateway=<Adapter Name>`. Put the signing secret in `webhook_secrets` in site config when the vendor signs callbacks.

### 3.3 Tax setup: Tax Code, Tax Rule, GST Settings

You need this when any plan charges tax. Do all three when you sell in India. Do Tax Code plus Tax Rule elsewhere.

Tax Code DocType. Screen: Desk > Lube Station > Tax Code > New. Desk route: `/app/tax-code`.

- Code (`code`, Data, required). What to enter: SAC or HSN code, for example `9984` for hosting services. Purpose: printed on the invoice line and used for GST filing. Must be exact.
- Description (`description`, Small Text). Purpose: human note of what the code covers. Example: `Web hosting and domain services`.
- Label (e.g. SAC, HSN) (`label`, Data, default `Tax code`). Purpose: prefix shown before the code on prints. Use `SAC` for services, `HSN` for goods.
- Country (`country`, Link to Country). Purpose: limits this code to one country. Leave empty when the code applies everywhere.
- Active (`is_active`, Check, default on). Purpose: inactive codes do not appear on new invoices.

Tax Rule DocType, with child Tax Eligible Group. Screen: Desk > Lube Station > Tax Rule > New. Desk route: `/app/tax-rule`.

- Tax Name (`tax_name`, Data, required). Example: `CGST 9%`, `SGST 9%`, `IGST 18%`, `VAT 20%`. Purpose: label on the invoice tax breakup.
- Country (`country`, Link to Country). Purpose: applies this rule only to customers in that country. Leave empty for a global rule.
- State (`state`, Data). Purpose: applies this rule only to that state. Used for CGST plus SGST versus IGST splits. Leave empty when the rule is national.
- Percentage (`percentage`, Float, required). Purpose: rate applied to the taxable subtotal. Enter `9` for nine percent, not `0.09`.
- Tax Level (`level`, Select `1` or `2`, default `1`). Purpose: stacking order. Level 1 applies to the subtotal. Level 2 applies after Level 1. Use Level 2 for a tax-on-tax case only.
- Eligible Groups (`eligible_groups`, Table to Tax Eligible Group). Each row holds Client Group (Link, required). Purpose: limits this tax to those client groups. Leave the table empty to tax every customer that matches country and state.
- Active (`active`, Check, default on). Purpose: inactive rules never apply.

GST Settings DocType (Single, India only). Screen: Desk > Lube Station > GST Settings.

- Seller State / UT (`seller_state`, Select of Indian states and UTs). Purpose: origin used to decide CGST plus SGST (same state) versus IGST (other state).
- Seller Country (`seller_country`, Link to Country, default `India`). Purpose: anchors GST logic to India.
- Seller GSTIN (`gstin`, Data). Purpose: your GSTIN printed on invoices. Must match the registered number.
- GST Rate % (`gst_rate`, Float, default 18). Purpose: default rate when no Tax Rule matches. Set 18 for most hosting services unless your filing says otherwise.

Steps:

1. Create Tax Code rows for each SAC or HSN you use. Link the common one as Default Tax Code in Lube Station Settings.
2. Create Tax Rule rows. For intra-state India create CGST 9% and SGST 9% with the same State. For inter-state create IGST 18% with no state lock or with matching logic. For other countries create one row per rate.
3. Add Client Group rows under Eligible Groups only when a tax covers a subset, for example tax-exempt resellers excluded.
4. Check Active on each rule you sell with.
5. Fill GST Settings when you file in India.
6. Check Apply Tax on each Hosting Plan that is taxable, and set its Tax Code link.

### 3.4 Dunning Rule

DocTypes: Dunning Rule, Dunning Step (child table).
Screen: Desk > Lube Station > Dunning Rule > New. Desk route: `/app/dunning-rule`.

Create at least one active global rule before you sell. Per-plan rules override the global rule for that plan.

Rule fields:

- Rule Name (`rule_name`, Data, required). Example: `Global 7-30`, `VPS strict`. Purpose: admin label. Shown in logs.
- Hosting Plan (`hosting_plan`, Link to Hosting Plan). Purpose: scope. Leave empty for a global rule that covers every plan. Select a plan for a per-plan rule. Per-plan wins over global.
- Product Type (`product_type`, Select, same 11 options). Purpose: scope by type, for example stricter VPS handling. Leave empty to cover all types.
- Grace Days (`grace_days`, Int, default 7). Purpose: days after Due Date before the first suspend action fires. Customer can still pay without interruption inside grace.
- Termination Days (`termination_days`, Int, default 30). Purpose: days after Due Date when the system queues termination for approval. Termination needs approval and never runs at once.
- Steps (`steps`, Table to Dunning Step). Purpose: ordered reminders and actions. See below.
- Active (`active`, Check, default on). Purpose: inactive rules never fire.

Each Dunning Step row:

- Step Type (`step_type`, Select, required, default Overdue): Pre-due, Due, Overdue, Suspend, Terminate Queue. Purpose: when this row fires relative to due date. Pre-due warns before expiry. Suspend and Terminate Queue change Service status.
- Days Offset (`days_offset`, Int, default 0). Purpose: days from due date for this step. Negative means before due date for Pre-due. Example: Pre-due with -3 warns three days early. Overdue with 3 reminds three days late.
- Template (`template`, Link to Email Template). Purpose: mail sent for a Notify step. Pick from seeded Lube templates (Lube Invoice Reminder, Lube Overdue First, Lube Overdue Second, Lube Overdue Third). Leave empty for a pure Suspend or Queue Termination row with no mail.
- Action (`action`, Select, required, default Notify): Notify, Suspend, Queue Termination. Purpose: what the scheduler does. Notify sends mail. Suspend moves Service to Suspended. Queue Termination asks for approval before Terminated.

44 Lube email templates seed on migrate (one per lifecycle event: signup, order, invoice, payment, welcome, credentials, suspension, domain, support, affiliate, download). Trigger map lives in `lube_station/lube_station/notifications/events.py`. Edits you make to them are kept on update. Transactional mails send at once with no scheduler needed. Dunning and domain-expiry batches need the scheduler on.

Steps:

1. Select New.
2. Enter Rule Name.
3. Leave Hosting Plan empty for a global rule. Select a plan for a per-plan rule.
4. Select Product Type only when the rule covers one type.
5. Enter Grace Days and Termination Days.
6. Add steps in time order. Example: Pre-due -3 Notify, Due 0 Notify, Overdue 3 Notify, Overdue 7 Notify, Suspend after grace, Terminate Queue at 30.
7. Pick Template for each Notify step.
8. Check Active.
9. Save.

### 3.5 Client Group and Coupon (seller promos)

Client Group DocType. Screen: Desk > Lube Station > Client Group > New.

- Group Name (`group_name`, Data, required). Example: `Retail`, `Resellers`, `Tax Exempt`, `Staff`. Purpose: segment used by Tax Rule eligibility and Coupon eligibility. Assign one group per Hosting Customer.

Coupon DocType, with child Coupon Eligible Group. Screen: Desk > Lube Station > Coupon > New.

- Code (`code`, Data, required). Purpose: text the customer types at cart or checkout. Keep short and unique. Example: `DIWALI10`.
- Discount Type (`discount_type`, Select, required, default Percentage): Percentage, Fixed Amount. Purpose: math applied to the cart subtotal. Percentage takes a share off. Fixed Amount takes currency off.
- Value (`value`, Float, required). Purpose: the percent or amount. For Percentage enter `10` for ten percent. For Fixed Amount enter the currency value.
- Eligible Groups (`eligible_groups`, Table). Each row holds Client Group. Purpose: limits this coupon to those groups. Leave empty to allow every customer.
- Minimum Cycle (`minimum_cycle`, Select, empty plus 7 cycles). Purpose: coupon works only when the cart item cycle is at least this long. Use Annually here to push yearly prepay.
- Maximum Uses (`maximum_uses`, Int, default 0). Purpose: cap on total redemptions. 0 means unlimited.
- Used Count (`used_count`, Int, default 0). Purpose: counter raised by the system. Do not edit by hand.
- Valid From (`valid_from`, Date), Valid To (`valid_to`, Date). Purpose: sale window. Leave empty for no limit.
- Active (`active`, Check, default on). Purpose: inactive codes are rejected at cart totals time with server-side recalc.

Steps: create Client Groups first, assign them on Hosting Customer records, then create Coupon rows and test add, coupon, and totals APIs on a test cart.

### 3.6 Registrar account and TLD Pricing (only when you sell domains)

DocTypes: Registrar Adapter, Registrar Account, TLD Pricing, Registered Domain, DNS Record.
Screens: Desk > Registrar Adapter List, then Registrar Account > New, then TLD Pricing > New.

Registrar Adapter fields:

- Adapter Name (`adapter_name`, Data, required). Example: `Namecheap Live`. Purpose: display name picked on Registrar Account.
- Vendor Name (`vendor_name`, Select, required): OpenSRS, Namecheap, GoDaddy, LogicBoxes, eNom, CentralNic, HEXONET, Porkbun, Internet.bs, Nominet, Custom. Purpose: picks built-in code. Custom needs a developer class.
- Class Path (`class_path`, Data). Leave empty for known vendors. It fills on save. Enter a path only for Custom.
- API Mode (`api_mode`, Select: empty, REST, XML, EPP). Purpose: protocol note. Helps staff pick the right credential shape.
- Supported Operations (`supported_operations`, Small Text, auto-filled on save). Purpose: audit note of what the code can do.
- Supported TLDs (`supported_tlds`, Small Text). Purpose: comma list the vendor sells, for example `.com, .in`. You must type this. It is not read from code.
- Sandbox Supported (`sandbox_supported`, Check, default on), Supports DNS (`supports_dns`), Supports Privacy (`supports_privacy`), Supports Transfer (`supports_transfer`). Purpose: capability flags. Turn on only what you tested.
- Active (`active`, Check). Purpose: inactive adapters cannot back a Registrar Account.

Registrar Account fields:

- Registrar (`registrar`, Link to Registrar Adapter, required). Purpose: which vendor row this account uses.
- API Key (`api_key`, Password), API Secret (`api_secret`, Password). Purpose: live credentials. Masked in Desk. Never paste into Data fields.
- Active (`active`, Check, default on). Purpose: inactive accounts are skipped by availability and registration calls.
- Client IP (`client_ip`, Data). Purpose: egress IP Namecheap sees. Leave blank to try auto-detect. Fill when Namecheap whitelists one IP.

TLD Pricing fields (one row per TLD):

- TLD (`tld`, Data, required). Purpose: suffix with leading dot, lowercase, for example `.com` or `.co.in`. Longest suffix wins, so `.co.in` beats `.in` for `example.co.in`.
- Register Price / Year (`register_price`, Currency). Purpose: first-year price shown at cart and invoiced on registration.
- Renew Price / Year (`renew_price`, Currency). Purpose: yearly renewal price and renewal invoice amount.
- Transfer Price (`transfer_price`, Currency). Purpose: price for an inbound transfer order.

Steps:

1. Open the Registrar Adapter for OpenSRS, Namecheap, GoDaddy, or LogicBoxes.
2. Fill Supported TLDs by hand.
3. Check Active and save.
4. Open Registrar Account > New. Select Registrar. Enter API Key and API Secret. Check Active. Save.
5. Create one TLD Pricing row per TLD you sell with all three prices.
6. Test `check_availability` for available, taken, and premium names before you sell.

## 4. Product Group

DocType: Product Group.
Screen: Desk > Lube Station > Product Group > New.
Desk route: `/app/product-group`.

Every field:

- Group Name (`group_name`, Data, required, unique). What to enter: storefront section name. Purpose: groups plans on the portal and in Desk lists. Example: `Shared Hosting`, `VPS Plans`, `Cloud Servers`, `Email`, `SSL and Add-ons`, `Downloadable Software`.
- Slug (`slug`, Data). What to enter: lowercase with hyphens, for example `shared-cpanel-hosting`. Purpose: clean portal URL part for this group. Keep stable once linked. Changing it breaks saved links.
- Description (`description`, Text Editor). Purpose: rich text shown on the portal group page. List what is inside and who it suits. Keep short.
- Icon (`icon`, Attach Image). Purpose: thumbnail on the portal. Use a small square image.
- Sort Order (`sort_order`, Int, default 0). Purpose: display order. Lower numbers show first. Use 10, 20, 30 gaps so you can insert later without renumbering.
- Show On Portal (`show_on_portal`, Check, default on). Purpose: hides the whole group without deleting plans. Turn off for draft or retired sections.

Steps:

1. Open Product Group > New.
2. Enter Group Name.
3. Enter Slug.
4. Enter Description.
5. Upload Icon.
6. Enter Sort Order.
7. Check Show On Portal.
8. Save.

Create one group per storefront section. Examples: Shared Hosting, VPS Plans, Cloud Servers, Email, SSL and Add-ons, Downloadable Software.

## 5. Hosting Plan (the product)

DocType: Hosting Plan.
Screen: Desk > Lube Station > Hosting Plan > New.
Desk route: `/app/hosting-plan`.

This is the one sellable item. Product Type picks which of the 11 services it is. The rest of the form wires display, provisioning, checkout, tax, and stock.

Every field:

- Plan Name (`plan_name`, Data, required, unique). What to enter: customer-facing name. Purpose: shown on portal, cart, order, invoice, and Service. Example: `Starter Shared 10GB`, `VPS 4GB FSN1`. Keep unique and stable. Renaming after sale confuses history.
- Product Group (`product_group`, Link to Product Group, required). Purpose: storefront section this plan appears under. Controls portal grouping and sort.
- Product Type (`product_type`, Select, required): Shared Hosting, Reseller, VPS, Dedicated Server, Cloud, Email Hosting, Website Builder, SSL, Backup Addon, Migration Service, Downloadable Product. Purpose: drives which schema flags, which configuration DocType, and which provisioning path apply. You cannot change meaning later without rebuilding schema and config. Pick once.
- Provisioning Module (`provisioning_module`, Link to Provisioning Module). Purpose: which panel code provisions this plan (cPanel Shared, Plesk, DirectAdmin). Set for owned-server plans and Email or Builder plans on local panels. Leave empty for manual work (Migration Service) or pure upstream API plans that provision through Infrastructure Provider instead.
- Server Group (`server_group`, Link to Server Group). Purpose: which owned-server pool placements come from. Set for Shared, Reseller, and local Email or Builder. Leave empty for VPS, Cloud, Dedicated, SSL, Download, and Migration unless you pin them to a local node.
- Welcome Email Template (`welcome_email_template`, Link to Email Template). Purpose: mail sent after Active provisioning with login and next steps. Always set one. Missing template means a silent active service.
- Product Type Schema (`product_type_schema`, Link to Product Type Schema). Purpose: checkout fields the customer must fill. When empty, the system falls back to lookup by product type. Always link explicitly so checkout is predictable.
- Config Fields (`config_fields`, Table to Plan Config Field). Each row has Field Key (Data, required) and Field Value (Data). Purpose: fixed package mapping passed to the panel or adapter, for example `package = shared_basic`, `disk_quota_mb = 10240`. These are not customer choices. Customer choices live on the schema. Keep keys exact. A typo here provisions the wrong package.
- Is Active (`is_active`, Check, default on). Purpose: master switch. Inactive plans cannot be added to a new cart but old Services keep billing.
- Apply Tax (`taxable`, Check, default on). Purpose: lets Tax Rules apply to this plan. Turn off only for tax-exempt items.
- Stock Control (`stock_control`, Check, default off) and Qty Available (`qty_available`, Int, default 0). Purpose: limited-quantity switch. Turn on for Dedicated and finite licenses. Qty Available is units left. Orders decrement it where enforced. Leave off for unlimited shared or cloud seats.
- Tax Code (SAC/HSN) (`tax_code`, Link to Tax Code). Purpose: SAC or HSN printed for this plan. Falls back to Default Tax Code in settings when empty. Always set for GST invoices.

Steps for every plan:

1. Open Hosting Plan > New.
2. Enter Plan Name.
3. Select Product Group.
4. Select Product Type.
5. Select Provisioning Module when auto-provisioning applies.
6. Select Server Group when placement from owned servers applies.
7. Select Welcome Email Template.
8. Select Product Type Schema.
9. Add Config Fields rows for fixed package mapping.
10. Set Tax Code and Apply Tax.
11. Set Stock Control and Qty Available only for limited stock.
12. Check Is Active.
13. Save.
14. Add Plan Pricing rows per section 7.
15. Add the type-specific configuration per sections 8 to 15.

WHMCS difference: WHMCS selects product type once and shows type-specific tabs. Lube Station keeps one form and drives checkout requirements from Product Type Schema plus type-specific configuration DocTypes in sections 8 to 15.

## 6. Product Type Schema (checkout requirements)

DocTypes: Product Type Schema, Product Requirement Field (child table).
Screen: Desk > Lube Station > Product Type Schema > New.
Desk route: `/app/product-type-schema`.

Schema fields:

- Schema Name (`schema_name`, Data, required, unique). Example: `Shared Hosting Default`, `VPS Default`. Purpose: admin label picked on the plan. Name it `<Type> Default` or `<Type> <Variant>`.
- Product Type (`product_type`, Select, required, same 11 options). Purpose: fallback lookup key when a plan has no explicit schema link. Keep it equal to the plans that use it.
- Requires Domain (`requires_domain`, Check). Purpose: checkout must collect a domain name. Turn on for Shared, Reseller, Email, Builder with domain bind, and SSL common-name-by-domain flows.
- Requires Hostname (`requires_hostname`, Check). Purpose: checkout must collect a server hostname. Turn on for VPS, Dedicated, Cloud.
- Requires Root Password (`requires_root_password`, Check). Purpose: checkout collects a root or admin password (Password type on the portal). Turn on for VPS and Dedicated. Leave off for Shared.
- Requires OS (`requires_os`, Check). Purpose: checkout must collect an OS image. Turn on for VPS, Dedicated, Cloud.
- Requires Location (`requires_location`, Check). Purpose: checkout must collect a region. Turn on for VPS, Dedicated, Cloud.
- Requires Nameservers (`requires_nameservers`, Check). Purpose: checkout collects custom nameservers. Turn on only when you let customers bring nameservers at order time.
- Fields (`fields`, Table). Purpose: extra per-field rules. See below.

Each Product Requirement Field row:

- Field Key (`field_key`, Data, required). Purpose: machine key stored in Order Item `configuration_snapshot` and Cart Item `configuration_json`. Use lowercase with underscores, for example `common_name`, `ram_upgrade`. Keep stable. Renaming breaks history lookup.
- Label (`label`, Data, required). Purpose: portal label the customer sees.
- Field Type (`field_type`, Select, required, default Text): Text, Password, Integer, Decimal, Select, Multi Select, Checkbox, JSON. Purpose: portal control and server validation. Use Password for secrets, Select for choices, Integer or Decimal for numbers, JSON for structured input.
- Options Source (`options_source`, Select, default Static): Static, OS Image Catalog, Location Catalog, Server Inventory, Provider API. Purpose: where Select choices come from. Static reads Options JSON below. Catalog and API sources pull live lists (OS images, regions, stock, vendor plans). Use Static for fixed add-on choices. Use catalog or API for VPS OS and location.
- Options JSON (`options_json`, Code). Purpose: static choice list with optional price deltas for same-plan options. Enter valid JSON. Broken JSON blocks checkout.
- Required (`required`, Check). Purpose: server rejects the order with `Missing required field: {key}` when empty. Check for every must-fill field.
- Validation Rule (`validation_rule`, Data). Purpose: extra server check, for example a regex or range note enforced in code. Leave empty when Required plus Field Type is enough.
- Maps To (`maps_to`, Data). Purpose: adapter or panel parameter this field feeds, for example `os_image`, `datacenter`. Tells provisioning where to send the value. Keep exact per adapter docs.

Steps:

1. Open Product Type Schema > New.
2. Enter Schema Name. Example: `Shared Hosting Default`.
3. Select Product Type.
4. Check the flags the checkout must collect.
5. Add one row per extra field.
6. Save.
7. Open the Hosting Plan.
8. Select this schema in Product Type Schema.
9. Save the plan.

Resolution order used by `get_product_requirements`: explicit schema first, then plan link, then lookup by product type. The API rejects missing required input with `Missing required field: {key}`.

## 7. Plan Pricing

DocType: Plan Pricing.
Screen: Desk > Lube Station > Plan Pricing > New, or add from Hosting Plan.
Desk route: `/app/plan-pricing`.

Every field:

- Hosting Plan (`hosting_plan`, Link, required). Purpose: plan this price belongs to. One plan has many pricing rows, one per cycle.
- Billing Cycle (`billing_cycle`, Select, required): Monthly, Quarterly, Semi-Annually, Annually, Biennially, Triennially, One Time. Purpose: invoicing rhythm and Service Next Due Date math. Use Recurring cycles for hosting. Use One Time for fixed Migration and lifetime licenses. Use Annually for most SSL.
- Setup Fee (`setup_fee`, Currency, default 0). Purpose: one-time charge on the first invoice only. Use for provisioning or installation work. Leave 0 when there is no setup charge.
- Recurring Amount (`recurring_amount`, Currency, required). Purpose: amount billed every cycle. This is the number the customer compares. Enter the cycle total, not monthly equivalent.
- Currency (`currency`, Link to Currency). Purpose: ISO currency for this row. Must be a currency your gateway settles. Create one row per currency you accept when you sell multi-currency.

Steps:

1. Open Plan Pricing > New.
2. Select Hosting Plan.
3. Select Billing Cycle.
4. Enter Recurring Amount.
5. Enter Setup Fee when any.
6. Select Currency.
7. Save.
8. Repeat for each cycle you sell. Example: Monthly and Annually.

WHMCS difference: WHMCS pricing lives on tabs inside the product. Lube Station stores one Plan Pricing record per cycle.

## 8. Shared Hosting

When to use: single cPanel, Plesk, or DirectAdmin account on your server for one website or a small set of sites. This is the default first product.

WHMCS path: New Product, type Shared Hosting, module cPanel, Require Domain checked.
Lube Station path: Hosting Plan with Product Type Shared Hosting.

Records you need: Product Group, Server, Server Group, Provisioning Module, Product Type Schema, Hosting Plan, Plan Pricing.

Screen sequence:

- Screen 1: Desk > Product Group. Confirm group `Shared Hosting`.
- Screen 2: Desk > Server List. Confirm at least one Active cPanel, Plesk, or DirectAdmin server.
- Screen 3: Desk > Server Group. Confirm group and fill strategy.
- Screen 4: Desk > Product Type Schema. Confirm Requires Domain checked.
- Screen 5: Desk > Hosting Plan > New. Create the plan.
- Screen 6: Desk > Plan Pricing. Add cycles.

Steps:

1. Create Product Group `Shared Hosting` per section 4.
2. Create Server records per section 9. Set Control Panel to `cPanel / WHM`, `Plesk`, or `DirectAdmin`. Set Status Active.
3. Create Server Group per section 9. Add servers. Select Round Robin or Least Full.
4. Create schema `Shared Hosting Default`. Check Requires Domain. Clear Requires Root Password, Requires Hostname, Requires OS, Requires Location.
5. Create Hosting Plan. Set Product Type to Shared Hosting. Link Product Group, Provisioning Module, Server Group, Schema, and Welcome Email Template.
6. Add Config Fields rows for package mapping. Example: `package = shared_basic`, `disk_quota_mb = 10240`. Keep keys exact per panel docs.
7. Set Tax Code and Apply Tax.
8. Create Plan Pricing rows. Use Recurring cycles. Example: Monthly 5.00, Annually 50.00. Add Setup Fee only when you charge onboarding.
9. Check Is Active.
10. Place a test order and confirm Service creation and welcome email.

Pricing guidance: sell Monthly for trials and Annually with a discount for retention. Keep setup fee 0 unless onboarding costs staff time.

Test: order with a domain, pay the invoice, confirm Service moves Pending to Active, confirm account exists on the placed server, confirm welcome mail arrived.

Common mistakes: Requires Root Password left on (shared never needs it); Config Field package name typo so provisioning maps to the wrong quota; no Welcome Email Template so Active arrives silent.

## 9. Server and Server Group (owned infrastructure)

DocTypes: Server, Server Group, Server Group Entry (child).
Screens: Desk > Lube Station > Server > New; Desk > Server Group > New.
Desk routes: `/app/server`, `/app/server-group`.

Server fields, what to enter and why:

- Hostname (`hostname`, Data, required, unique). Purpose: admin and provisioning identity for this node. Enter the FQDN, for example `whm1.example.com`. Must be unique.
- IP Address (`ip_address`, Data). Purpose: connection target for the panel API. Enter the public IP or panel host IP.
- Control Panel (`control_panel`, Select): empty, `cPanel / WHM`, `Plesk`, `DirectAdmin`, `Custom`. Purpose: tells provisioning which API shape to speak. Must match the Provisioning Module panel for plans that use this server.
- API Username (`api_username`, Data). Purpose: panel API user. Use a scoped API user, not root where the panel allows it.
- API Secret (`api_secret`, Password). Purpose: panel token or secret. Masked. Never store in a Data field.
- Max Accounts (`max_accounts`, Int, default 0). Purpose: capacity cap for Least Full placement. 0 means no cap. Set a real cap so one node never fills.
- Active Accounts (`active_accounts`, Int, default 0). Purpose: counter used by Least Full. Updated by provisioning. Do not hand-edit except to correct drift after an audit.
- Status (`status`, Select, default Active): Active, Maintenance, Disabled. Purpose: placement switch. Active takes new accounts. Maintenance keeps old accounts but takes no new ones. Disabled is fully out.
- Server Group (`server_group`, Link to Server Group). Purpose: reverse pointer to the pool this node belongs to. Keep consistent with the Server Group `servers` table.
- Connection Status (`connection_status`, Select, read-only in practice): Not Checked, Online, Failed. Purpose: last health probe result.
- Last Checked On (`last_checked_on`, Datetime), Response Time (ms) (`response_time_ms`, Int), Last Check Message (`last_check_message`, Small Text). Purpose: health audit trail. Do not type these by hand. They fill on probe.

Server Group fields:

- Group Name (`group_name`, Data, required, unique). Example: `cPanel Shared Pool`, `Reseller Nodes`. Purpose: pool picked on the plan.
- Servers (`servers`, Table of Server Group Entry). Each row holds Server (Link, required). Purpose: members of this pool. Add each node once. Remove a node before maintenance.
- Fill Strategy (`fill_strategy`, Select, default Round Robin): Round Robin, Least Full, Manual. Purpose: placement rule. Round Robin spreads evenly. Least Full fills the emptiest node by Active Accounts against Max Accounts. Manual lets staff pick the server per Service.

Steps:

1. Open Server > New.
2. Enter Hostname.
3. Enter IP Address.
4. Enter Control Panel.
5. Enter API Username.
6. Enter API Secret.
7. Enter Max Accounts.
8. Set Status to Active.
9. Save.
10. Open Server Group > New.
11. Enter Group Name.
12. Add each Server row.
13. Select Fill Strategy.
14. Save.
15. Link this group on each Hosting Plan that uses owned servers.

## 10. Reseller Hosting

When to use: customer resells hosting under their own brand from a reseller package on your panel. They get a WHM or panel reseller account with sub-account limits.

WHMCS path: same as Shared, type Reseller Hosting, reseller package mapping.
Lube Station path: Hosting Plan with Product Type Reseller.

Records you need: same as section 8. Package mapping points to a reseller package.

Steps:

1. Create Product Group `Reseller Hosting`.
2. Create Server records for reseller-capable WHM, Plesk, or DirectAdmin hosts.
3. Create Server Group for reseller nodes. Prefer Least Full so large resellers spread.
4. Create schema `Reseller Default`. Check Requires Domain. Clear root, OS, and location flags.
5. Create Hosting Plan with Product Type Reseller.
6. Link Product Group, Provisioning Module for the panel, Server Group, Schema, and Welcome Email Template.
7. Add Config Fields for reseller limits. Example: `package = reseller_50`, `max_subaccounts = 50`. Do not reuse shared package names.
8. Set Tax Code and Apply Tax.
9. Create Plan Pricing rows with Recurring cycles and setup fee when needed.
10. Activate and test order, suspension, and termination.

Difference from Shared Hosting: Config Fields map to a reseller package, not an end-user package. Suspension here suspends the reseller and their sub-accounts per panel behavior. Test both suspend and unsuspend before live.

## 11. VPS

When to use: customer gets a virtual machine with dedicated CPU, RAM, disk, and root access. You sell fixed sizes or let the customer pick OS and region.

WHMCS path: type Server/VPS, module SolusVM or Virtualizor, hostname and password prompts.
Lube Station path: Hosting Plan with Product Type VPS plus VPS Configuration.

Records you need: Product Group, Infrastructure Provider, Provider Product, Reseller Agreement when you resell upstream, Product Type Schema, Hosting Plan, VPS Configuration, Plan Pricing.

VPS Configuration fields (one per Hosting Plan, Hosting Plan link is unique):

- Hosting Plan (`hosting_plan`, Link, required, unique). Purpose: which plan these specs belong to. One row per plan. Duplicate rows for the same plan are blocked.
- CPU Cores (`cpu_cores`, Int, default 1). Purpose: vCPU count provisioned. Must match the vendor size or the adapter rejects the build.
- RAM MB (`ram_mb`, Int, default 1024). Purpose: memory in megabytes. Example: 4096 for 4 GB.
- Storage GB (`storage_gb`, Int, default 20). Purpose: disk size in gigabytes.
- Bandwidth GB (`bandwidth_gb`, Int, default 100). Purpose: included transfer per cycle. Overage above this bills per Usage Snapshot rates below.
- OS Images JSON (`os_images_json`, Code). Purpose: allowed OS list shown at checkout, for example `["ubuntu-22.04", "debian-12"]`. Leave empty only for a fixed-OS plan where the schema does not ask. Broken JSON hides choices.
- Locations JSON (`locations_json`, Code). Purpose: allowed regions, for example `["fsn1", "nbg1"]`. Must match Provider Product `regions_json` or provisioning fails.
- IPv4 Count (`ipv4_count`, Int, default 1). Purpose: addresses attached. Extra IPs may need manual justification per provider.
- Backup Enabled (`backup_enabled`, Check, default off). Purpose: enables scheduled snapshots where the adapter supports it. Turn on only when you charge or include backups.
- Disk Overage Rate / GB (`disk_overage_rate`, Currency, default 0), Bandwidth Overage Rate / GB (`bandwidth_overage_rate`, Currency, default 0). Purpose: per-GB overage price applied from Usage Snapshot rows. 0 means no overage billing. Set real rates before you promise metered billing.

Screens:

- Screen 1: Desk > Infrastructure Provider. Confirm Active VPS API provider.
- Screen 2: Desk > Provider Product. Confirm regions and plans JSON.
- Screen 3: Desk > Product Type Schema. Confirm Requires Hostname, Requires Root Password, Requires OS, Requires Location.
- Screen 4: Desk > Hosting Plan. Create VPS plan.
- Screen 5: Desk > VPS Configuration. Create fixed specs.
- Screen 6: Desk > Plan Pricing. Add cycles.

Steps:

1. Create Product Group `VPS Plans`.
2. Create Infrastructure Provider with Provider Type VPS API. Set Status to Active. Fill API Base URL and Credential Reference.
3. Create Provider Product. Select Product Type VPS. Fill Regions JSON and Plans JSON. Set External Product ID to the vendor size code, for example `cx22`.
4. Create Reseller Agreement when you resell upstream capacity. Pick Billing Model and markup.
5. Create schema `VPS Default`. Check Requires Hostname, Requires Root Password, Requires OS, and Requires Location. Leave Requires Domain cleared unless you bundle a domain. Set Options Source to OS Image Catalog or Location Catalog where you want live lists.
6. Create Hosting Plan with Product Type VPS.
7. Create VPS Configuration for that plan. Enter CPU, RAM, storage, bandwidth, IPv4 count, OS images, and locations. Set overage rates when you bill overage.
8. Lock fixed plans by keeping specs only in VPS Configuration. Expose choices through schema fields only for customizable plans.
9. Create Plan Pricing rows with Recurring cycles.
10. Test boot, reboot, shutdown, snapshot, and usage display when the adapter supports them.

## 12. Dedicated Server

When to use: customer rents a whole physical machine or a pinned bare-metal slot. Stock is finite. Each unit moves through Available, Reserved, Assigned, Wipe Pending, Terminated.

WHMCS path: type Server/VPS with dedicated module.
Lube Station path: Hosting Plan with Product Type Dedicated Server plus Dedicated Server Configuration and Dedicated Server Inventory.

Records you need: Product Group, Infrastructure Provider, Dedicated Server Inventory rows, Product Type Schema, Hosting Plan, Dedicated Server Configuration, Plan Pricing.

Dedicated Server Configuration fields (one per Hosting Plan):

- Hosting Plan (`hosting_plan`, Link, required, unique). Purpose: plan these defaults belong to.
- Server Class (`server_class`, Data). Example: `Ryzen 9 7950X / 128GB / 2x1TB NVMe`. Purpose: customer-facing spec line. Keep exact so inventory matches.
- Location (`location`, Data). Purpose: default data center, for example `fsn1`. Override per order through schema location field when you offer choices.
- OS Image (`os_image`, Data). Purpose: default OS. Override per order when you offer choices.
- Control Panel (`control_panel`, Data). Purpose: panel installed by default, for example `cPanel / WHM` or `none`. Leave `none` for bare OS.
- Managed Service (`managed_service`, Check). Purpose: staff manage patching and monitoring. Check only when the price includes management.
- IP Count (`ip_count`, Int, default 1). Purpose: addresses included.
- Bandwidth Commitment (`bandwidth_commitment`, Int, default 0). Purpose: committed Mbps or GB per contract. 0 means best-effort or unmetered.

Dedicated Server Inventory fields (one row per physical unit):

- Provider (`provider`, Link to Infrastructure Provider). Purpose: whose facility or API this unit sits in.
- Asset ID (`asset_id`, Data). Purpose: your tag for this machine, for example `DC1-R42-U17`. Keep unique in practice.
- CPU (`cpu`, Data), RAM GB (`ram_gb`, Int), Storage JSON (`storage_json`, Code), Location (`location`, Data). Purpose: true hardware truth. Storage JSON lists disks, for example `[{"type": "nvme", "size_gb": 1000, "count": 2}]`.
- IP Pool (`ip_pool`, Small Text), Bandwidth Mbps (`bandwidth_mbps`, Int). Purpose: network truth for this unit.
- Status (`status`, Select, required, default Available): Available, Reserved, Assigned, Wipe Pending, Terminated. Purpose: lifecycle lock. Available can sell. Reserved holds for an order. Assigned serves a customer. Wipe Pending waits for wipe approval before reuse. Terminated is retired. A server returns to Available only after wipe confirmation.
- Assigned Service (`assigned_service`, Data). Purpose: Service holding this unit now. Filled on assign.
- Lease Key (`lease_key`, Data), Lease Expiry (`lease_expiry`, Datetime). Purpose: concurrency guard from the lease table. Prevents two orders taking the same unit. Do not hand-edit.

Steps:

1. Create Product Group `Dedicated Servers`.
2. Create Infrastructure Provider with Provider Type Dedicated Server Provider, Bare Metal API, or Local Infrastructure.
3. Create Dedicated Server Inventory rows. Keep Status as Available until sold. Fill true CPU, RAM, storage, location, IP pool, and bandwidth.
4. Create schema `Dedicated Default`. Check Requires Hostname and Requires OS. Add data-center or network fields as needed. Check Requires Location when the customer picks region.
5. Create Hosting Plan with Product Type Dedicated Server.
6. Create Dedicated Server Configuration for that plan with class, location, OS, panel, IP count, and bandwidth.
7. Enable Stock Control on the plan when quantity is limited. Set Qty Available to real free units.
8. Create Plan Pricing rows with Recurring cycles and setup fee for provisioning.
9. Test reserve, assign, release, and wipe approval. Confirm a unit returns to Available only after wipe confirmation.

## 13. Cloud

When to use: elastic VM or cloud instance billed per cycle or per usage from AWS, Hetzner Cloud, or Proxmox. Customer picks hostname, OS, and region. Resize and snapshot apply where the adapter supports them.

WHMCS mapping: no distinct Cloud type. WHMCS uses Server/VPS type with a cloud module.
Lube Station mapping: Hosting Plan with Product Type Cloud. Same pattern as VPS.

Records you need: Product Group, Infrastructure Provider of type Cloud API, Provider Product of type Cloud, Reseller Agreement, Product Type Schema, Hosting Plan, Plan Pricing. Reuse VPS Configuration fields where the adapter expects them, or map through Plan Config Field rows.

Infrastructure Provider fields for cloud:

- Provider Name (`provider_name`, Data, required). Example: `Hetzner Cloud`, `AWS ap-south-1`. Purpose: admin label picked on Provider Product and inventory.
- Provider Type (`provider_type`, Select, required): Cloud API, VPS API, Dedicated Server Provider, Bare Metal API, Control Panel, Reseller Program, Local Infrastructure. Purpose: picks Cloud API here. Controls which setup section applies.
- API Base URL (`api_base_url`, Data). Example: `https://api.hetzner.cloud/v1`. Purpose: vendor endpoint. Leave blank for local or manual provisioning.
- Credential Reference (`credential_reference`, Password). Purpose: API token. Masked. Used by live adapters.
- Capabilities (`capabilities`, Code). Purpose: JSON note auto-filled on save from linked Provider Products when empty, for example `{"regions": ["fsn1"], "snapshots": true}`. Leave empty to auto-fill. Edit only to correct drift.
- Status (`status`, Select, required, default Active): Active, Maintenance, Disabled. Purpose: Active allows new builds. Maintenance blocks new builds but keeps running nodes. Disabled blocks all calls.

Provider Product fields for cloud:

- Provider (`provider`, Link, required). Purpose: parent account.
- External Product ID (`external_product_id`, Data). Example: `cx22`. Purpose: vendor size code. Blank for local inventory.
- Product Type (`product_type`, Select, required, same 11). Select Cloud here.
- Regions JSON (`regions_json`, Code). Example: `["fsn1", "nbg1"]`. Purpose: regions offered. Feeds Capabilities summary and checkout region list.
- Plans JSON (`plans_json`, Code). Example: `[{"name": "cx22", "cpu": 2, "ram_gb": 4}]`. Purpose: sizes offered with specs.
- Available Quantity (`available_quantity`, Int, default 0). Purpose: quota hint. 0 means unlimited or unknown. Set a real cap for limited quota.
- Sync Status (`sync_status`, Select, default Manual): Manual, Synced, Stale, Sync Failed. Purpose: catalog freshness. Manual until a vendor catalog sync overwrites the row.

Reseller Agreement fields:

- Provider (`provider`, Link, required). Purpose: which provider these terms cover.
- Agreement Name (`agreement_name`, Data, required). Example: `Hetzner Resale 2026`. Purpose: admin label.
- Billing Model (`billing_model`, Select, required): Wholesale Recurring, Prepaid Credit, Per Usage, Commission. Purpose: how upstream bills you. Wholesale Recurring means flat per cycle. Per Usage means metered and needs Usage Snapshot. Match this to your Plan Pricing promise.
- Markup Type (`markup_type`, Select): Percentage, Fixed. Plus Markup Value (`markup_value`, Float, default 0). Purpose: your margin math. Percentage adds a share. Fixed adds currency. Example: Percentage 20 on a 100 cost sells at 120.
- Terms JSON (`terms_json`, Code). Purpose: contract notes in JSON, for example credit limits or SLA text.
- Active (`active`, Check, default on). Purpose: inactive agreements block new sales on that provider.

Steps:

1. Create Product Group `Cloud Servers`.
2. Create Infrastructure Provider with Provider Type Cloud API. Examples: AWS, Hetzner, Proxmox.
3. Create Provider Product with Product Type Cloud. Fill Regions JSON and Plans JSON.
4. Create Reseller Agreement with the matching Billing Model. Use Per Usage only when Usage Snapshot and overage rates are set.
5. Create schema `Cloud Default`. Check Requires Hostname, Requires OS, and Requires Location.
6. Create Hosting Plan with Product Type Cloud.
7. Reuse VPS Configuration fields where the adapter expects them, or map through Plan Config Field rows.
8. Create Plan Pricing rows. Use Per Usage billing model on the agreement when the plan bills by usage.
9. Test provision, resize, snapshot, and usage pull through Usage Snapshot.

## 14. Email Hosting, Website Builder, SSL, Backup Addon, Migration Service

Lube Station gives each add-on style product its own Product Type. Use this section when the item has its own price and cycle. Use section 16 to decide between a same-plan option and a separate plan.

### 14.1 Email Hosting

When to use: mailboxes under the customer domain on your panel or mail platform.

1. Create Product Group `Email Hosting`.
2. Create schema `Email Default`. Check Requires Domain. Clear root, OS, and location flags unless the platform needs them.
3. Create Hosting Plan with Product Type Email Hosting.
4. Link Provisioning Module for the mail platform and Server Group when hosted locally. Link Provider plus Provider Product when hosted upstream.
5. Add Config Fields for mailbox quota and mailbox count. Example: `quota_gb = 25`, `mailboxes = 10`.
6. Set Tax Code and Apply Tax.
7. Create Plan Pricing rows with Recurring cycles.

### 14.2 Website Builder

When to use: hosted site builder seats with templates. The site may or may not bind to a domain.

1. Create Product Group `Website Builder`.
2. Create schema `Builder Default`. Check Requires Domain only when sites bind to a domain at order time.
3. Create Hosting Plan with Product Type Website Builder.
4. Link the builder Provisioning Module or upstream Provider Product.
5. Add Config Fields for site tier and template set. Example: `tier = pro`, `templates = business_pack`.
6. Create Plan Pricing rows with Recurring cycles.

### 14.3 SSL Certificate

When to use: certificate issuance and install for one hostname or wildcard. Most sell yearly while hosting sells monthly, so this is almost always a separate plan.

1. Create Product Group `SSL and Add-ons`.
2. Create Infrastructure Provider with Provider Type Reseller Program when you resell certificates. Set Status Active.
3. Create Provider Product with Product Type SSL and External Product ID from the vendor, for example the vendor SKU for DV Single Domain.
4. Create schema `SSL Default`. Keep Requires Domain checked when you collect the domain through the standard flag. Clear it only when you collect the common name as a custom field instead.
5. When you cleared Requires Domain, add a requirement field `common_name` with Label `Common Name`, Field Type Text, Required checked, Maps To `common_name`.
6. Create Hosting Plan with Product Type SSL. Leave Server Group empty. Link the provider path, not an owned server pool.
7. Create Plan Pricing rows. Use Annually for most certificates. Add Setup Fee for installation only when you charge it.

### 14.4 Backup Addon

When to use: extra backup quota or retention sold on top of hosting. The cycle can differ from the parent plan.

1. Create Product Group `SSL and Add-ons`.
2. Create schema `Backup Default`. No domain flags in most cases. Add fields for target service or retention choice when the customer picks.
3. Create Hosting Plan with Product Type Backup Addon.
4. Add Config Fields for retention and quota. Example: `retention_days = 30`, `quota_gb = 100`.
5. Create Plan Pricing rows. The cycle can differ from the parent hosting plan.
6. Link to the parent through Cart Item or Order Item `parent_service` at order time so staff know which Service this backup covers.

### 14.5 Migration Service

When to use: one-time staff work to move a site or mailbox in. No panel provisioning in most cases.

1. Create Product Group `Services`.
2. Create schema `Migration Default`. Add fields for source panel, source host, and site size. Example keys: `source_panel`, `source_host`, `site_size_gb`. Mark them Required so staff get what they need without a follow-up mail.
3. Create Hosting Plan with Product Type Migration Service.
4. Leave Provisioning Module empty when staff perform the work manually. Link a module only when migration is automated.
5. Create Plan Pricing rows. Use One Time for fixed migrations.
6. Fulfil by ticket or linked support reference, then mark the Service Active on completion.

## 15. Downloadable and software license product

When to use: files, themes, plugins, or license keys the customer downloads after purchase. Access is gated by purchase or active service.

WHMCS path: type Other, Auto Release module, no domain.
Lube Station path: Hosting Plan with Product Type Downloadable Product plus Download Category and Downloadable Asset.

Download Category fields:

- Category Name (`category_name`, Data, required, unique). Example: `WordPress Themes`. Purpose: grouping shown on the portal.
- Parent Category (`parent_category`, Link to Download Category). Purpose: nesting. Leave empty for top level.
- Is Public (`is_public`, Check). Purpose: shows this category without login. Turn off for buyer-only catalogs.

Downloadable Asset fields:

- Title (`title`, Data, required). Purpose: customer-facing file name.
- Category (`category`, Link to Download Category). Purpose: grouping. Set it so the file appears in the right section.
- Storage Type (`storage_type`, Select, required, default Frappe File): Frappe File, Private Object Storage, Remote URL. Purpose: where bytes live. Frappe File uses an uploaded Attach. Private Object Storage uses your object store. Remote URL points outside. Pick one and fill only its source field.
- File (`file`, Attach). Purpose: uploaded file for Frappe File type. Required for that type. Leave empty for Remote URL.
- Remote URL (`remote_url`, Data). Purpose: outside link for Remote URL type. Must be exact including `https://`.
- Access Policy (`access_policy`, Select, required, default Logged-in Customers): Public, Logged-in Customers, Purchased Product, Active Service. Purpose: gate. Public needs no login. Logged-in Customers needs login. Purchased Product needs an Order for a linked plan. Active Service needs a non-expired Service for a linked plan. Use Purchased Product for lifetime licenses. Use Active Service for subscription files.
- Allowed Products (`allowed_products`, Table to Download Allowed Product). Each row holds Hosting Plan (Link, required). Purpose: which plans unlock this file when policy is Purchased Product or Active Service. Add one row per plan. Empty table with a gated policy blocks everyone, which is the most common download failure.
- Version (`version`, Data, default `1.0`). Purpose: release label. Bump on each upload so customers and staff know what they hold.
- Download Count (`download_count`, Int, default 0). Purpose: system counter. Do not hand-edit.
- Active (`active`, Check, default on). Purpose: inactive files are hidden even when the policy passes.

Steps:

1. Open Download Category > New.
2. Enter Category Name.
3. Select Parent Category when nested.
4. Save.
5. Open Downloadable Asset > New.
6. Enter Title.
7. Select Category.
8. Select Storage Type.
9. Attach File or enter Remote URL. Fill only the field your Storage Type uses.
10. Select Access Policy.
11. When policy is Purchased Product or Active Service, add Allowed Products rows with Hosting Plan links. Skip this and nobody can download.
12. Check Active.
13. Save.
14. Create Hosting Plan with Product Type Downloadable Product.
15. Link Product Group for software.
16. Leave Product Type Schema domain flags cleared unless the license binds to a domain.
17. Create Plan Pricing rows. Use One Time for lifetime licenses or Recurring for subscriptions.
18. Test purchase, download link release, and license key delivery. Test both a buyer and a non-buyer. Non-buyer must be blocked.

## 15A. Domains as a sellable service

When to use: customer registers, renews, or transfers a domain through you. This is separate from hosting plans and has its own pricing table.

Records you need: Registrar Adapter, Registrar Account, TLD Pricing rows, Registered Domain rows created by orders, DNS Record rows where you host DNS.

Registered Domain fields (created by order or availability flow, staff verify):

- Domain Name (`domain_name`, Data, required). Example: `example.com`. Purpose: exact name with TLD. Lowercase it.
- Customer (`customer`, Link to Hosting Customer). Purpose: owner billed for renewals.
- Registrar (`registrar`, Link to Registrar Adapter). Purpose: which vendor holds this name.
- Registration Date (`registration_date`, Date), Expiry Date (`expiry_date`, Date). Purpose: term truth. Expiry drives renewal invoices per Renewal Advance Days.
- Auto Renew (`auto_renew`, Check). Purpose: renewal invoice and registrar renew call run at once when on. Leave off when the customer renews by hand.
- Status (`status`, Select, default Unknown): Available, Taken, Premium, Unknown, Registered, Expired, Transferred. Purpose: availability or holding state. Available can sell. Premium needs `premium_price` confirmation. Registered is live. Expired and Transferred need staff action.
- Nameservers (`nameservers`, Small Text). Purpose: delegation list, one per line. Wrong entries take the site offline.
- WHOIS Privacy (`whois_privacy`, Check). Purpose: hides contact in WHOIS where the registry allows it.
- Last Checked (`last_checked`, Datetime), Premium Price (`premium_price`, Currency). Purpose: freshness and premium cost. Re-check before you quote a premium name.

DNS Record fields (only when you host DNS):

- Domain (`domain`, Link to Registered Domain, required). Purpose: zone this record lives in.
- Record Type (`record_type`, Select, required, default A): A, AAAA, CNAME, MX, TXT, NS, SRV. Purpose: record shape. MX needs Priority. SRV needs host and port in value per vendor format.
- Hostname (`hostname`, Data, required). Example: `@`, `www`, `mail`. Purpose: left side of the record. `@` means apex.
- Value (`record_value`, Data, required). Purpose: right side. IP for A, name for CNAME, text for TXT.
- TTL (`ttl`, Int, default 3600). Purpose: cache seconds. Lower before a move, raise after stable.
- Priority (`priority`, Int, default 0). Purpose: MX order. Lower delivers first.

Steps to sell domains:

1. Activate the Registrar Adapter and Account per section 3.6.
2. Create TLD Pricing rows for each TLD with register, renew, and transfer prices.
3. Confirm `check_availability` returns available, taken, and premium correctly for a test name.
4. Sell through cart Domain items. Renewal invoices use Renew Price and Renewal Advance Days.
5. Add DNS Records only after the domain is Registered. Wrong order leaves records orphaned.

## 16. Add-on services: configurable options versus separate addons

Use this decision table for every add-on.

| Situation | Lube Station method | Billing |
|---|---|---|
| Choice changes the same service price (extra RAM, disk, OS) | Plan Config Field rows plus requirement fields on schema | Same invoice and cycle as main plan |
| Standalone item with its own cycle (SSL yearly on monthly hosting) | Separate Hosting Plan with Product Type SSL, Backup Addon, or Migration Service | Own Plan Pricing and cycle |
| File or license tied to purchase | Downloadable Asset with Allowed Products | Follows linked plan |
| Third-party service without custom code | Infrastructure Provider plus Provider Product plus Reseller Agreement | Per agreement billing model |

Steps for a same-plan option (example: extra RAM):

1. Open the Hosting Plan.
2. Add a Product Requirement Field row for `ram_upgrade` on the linked schema.
3. Set Field Type to Select.
4. Set Options Source to Static.
5. Enter Options JSON with choices and price deltas. Keep JSON valid.
6. Save.
7. Confirm cart totals change with the choice. Totals recalc server-side, so portal math cannot bypass it.

Steps for a separate addon (example: yearly SSL on monthly hosting):

1. Create Hosting Plan with Product Type SSL per section 14.3.
2. Create Plan Pricing with Billing Cycle Annually.
3. Sell it as a separate order item linked to the same customer. Use Cart Item or Order Item `parent_service` to tie it to the hosting Service.
4. Confirm separate Next Due Date on each Service. They bill apart on purpose.

Cart Item fields sellers should know (portal fills most, staff verify on disputes):

- Type (`item_type`, Select, required, default Hosting Plan): Hosting Plan, Domain. Purpose: which catalog this line points to.
- Hosting Plan (`hosting_plan`, Link), Billing Cycle (`billing_cycle`, Select), Domain (`domain`, Data), Quantity (`quantity`, Int default 1). Purpose: what and how many. Quantity above 1 multiplies unit price.
- Parent Service (`parent_service`, Link to Service). Purpose: ties an addon line to its hosting Service.
- Configuration JSON (`configuration_json`, Code). Purpose: frozen checkout answers for this line. Copied to Order Item snapshot on order.
- Unit Price (`unit_price`, Currency). Purpose: server-recalculated price. Never trust portal math alone.

## 17. Provisioning Module and adapter setup (replaces WHMCS module install)

DocTypes: Provisioning Module, Provisioning Adapter.
Screens: Desk > Provisioning Module > New; Desk > Provisioning Adapter List.
Desk routes: `/app/provisioning-module`, `/app/provisioning-adapter`.

Provisioning Module fields:

- Module Name (`module_name`, Data, required, unique). Example: `cPanel Shared`. Purpose: label picked on the Hosting Plan. Name it `<Panel> <Use>`.
- Provisioning Adapter (`provisioning_adapter`, Link to Provisioning Adapter). Purpose: code row that fills Control Panel and Class Path. Pick this first so the next two fields auto-fill. This link is the field sellers miss most.
- Control Panel (`control_panel`, Select): empty, `cPanel / WHM`, `Plesk`, `DirectAdmin`. Purpose: panel family. Must match exactly. Unknown text falls back to `cPanel / WHM`. Must match the Server Control Panel for owned-server plans.
- Python Class Path (`class_path`, Data). Purpose: dotted path copied from the linked adapter. Auto-filled from the adapter. Optional without an adapter for manual modules. Leave as auto-filled unless Custom.

Provisioning Adapter fields:

- Adapter Name (`adapter_name`, Data, required, unique). Example: `cPanel Live`. Purpose: admin label.
- Vendor Name (`vendor_name`, Select, required): cPanel, Plesk, DirectAdmin, Virtualizor, Proxmox, Hetzner, AWS, Cloudflare, Custom. Purpose: picks built-in code on save.
- Class Path (`class_path`, Data). Leave empty for known vendors. It fills on save. Enter a path only for Custom. Shown only when Vendor is Custom or the path is empty.
- API Mode (`api_mode`, Select): empty, REST, XML API, JSON API, HTTP API, WHM API, EPP, Custom. Purpose: protocol note for the panel API. Helps staff use the right credential shape and debug format errors.
- Lifecycle Methods (`lifecycle_methods`, Small Text, auto-filled on save). Purpose: audit list of create, suspend, unsuspend, terminate, password, and package actions the code supports.
- Supports Usage (`supports_usage`), Supports Resize (`supports_resize`), Supports SSO (`supports_sso`), Supports Change Plan (`supports_change_plan`) (Checks). Purpose: capability flags. Turn on only what you tested. Usage feeds Usage Snapshot. Resize allows plan changes. SSO allows panel login from portal. Change Plan allows package moves.
- Active (`active`, Check). Purpose: inactive adapters never run.

Steps:

1. Open Provisioning Adapter List.
2. Confirm the adapter for cPanel, Plesk, DirectAdmin, Virtualizor, Proxmox, Hetzner, AWS, or Cloudflare exists.
3. Select Vendor Name and leave Class Path empty for known vendors. It fills on save.
4. Set API Mode to match vendor docs.
5. Set capability flags to what you tested.
6. Check Active for adapters you sell.
7. Open Provisioning Module > New.
8. Enter Module Name.
9. Pick Provisioning Adapter first.
10. Confirm Control Panel and Python Class Path filled from the adapter.
11. Save.
12. Select this module on each Hosting Plan it provisions.
13. Confirm Provider API Log records Success for create, suspend, unsuspend, and terminate tests.

WHMCS difference: WHMCS bundles code, package mapping, and automation buttons in one module screen. Lube Station keeps code in the adapter, seller selection in the module, capacity in servers or providers, and automation in background jobs plus Service status.

### 17.1 Custom vendor adapter (developer task)

Use this when Vendor is Custom for a payment, provisioning, or registrar adapter. A seller cannot do this from Desk. A developer writes one class.

1. Create a file under `adapters/payments/`, `adapters/provisioning/`, or `adapters/registrar/`.
2. Subclass the matching base: `PaymentGatewayAdapter`, `ProvisioningAdapter`, or `RegistrarAdapter`.
3. Implement each method the vendor supports. Throw for the rest. Copy `bank_transfer.py` as the template.
4. Take no constructor arguments. The loader instantiates the class with zero arguments.
5. Reload the bench so the module is importable.
6. Open the adapter record in Desk.
7. Select Vendor Custom.
8. Enter the dotted path, for example `lube_station.lube_station.adapters.payments.mygateway.MyGatewayAdapter`.
9. Set the capability flags to match the implemented methods.
10. Check Active and save. A bad path is rejected on save.
11. Point webhooks at the generic endpoint with `gateway=<Adapter Name>`. Put the signing secret in `webhook_secrets` in site config when the vendor signs callbacks.

No controller changes are needed. Payment, provisioning, domain, and dunning flows resolve the adapter through the registry, which falls back to the record Class Path for unknown names.

## 18. Service lifecycle and automation

DocType: Service.
Screen: Desk > Lube Station > Service List.
Desk route: `/app/service`.

Services are created by orders, not by hand. Staff read them to trace billing and provisioning. Create test Services only through test orders.

Every field sellers and support read:

- Customer (`customer`, Link to Hosting Customer, required). Purpose: owner billed and notified.
- Hosting Plan (`hosting_plan`, Link, required). Purpose: plan this Service runs. Change means upgrade or downgrade path, not a silent edit.
- Order (`order_ref`, Link to Order). Purpose: source order. Keeps the frozen configuration traceable.
- Billing Cycle (`billing_cycle`, Select, default Monthly): 7 cycles. Purpose: renewal rhythm. Must have a matching Plan Pricing row or renewal fails.
- Server (`server`, Link to Server). Purpose: placed node for owned-server plans. Empty for pure upstream or manual services.
- Primary Domain (`primary_domain`, Data). Purpose: main domain or hostname served. Collected from schema Requires Domain or Hostname.
- Username (`svc_username`, Data). Purpose: panel or system login created by provisioning.
- Vendor Reference (`vendor_ref`, Data). Purpose: upstream ID returned by the provider, for example VPS ID or certificate order ID. Needed for support tickets with the vendor.
- Node (`node`, Data). Purpose: hypervisor or cluster note for VPS, Cloud, and Dedicated.
- Parent Service (`parent_service`, Link to Service). Purpose: ties an addon Service (SSL, Backup) to its hosting Service. Used to suspend or cancel together.
- Status (`status`, Select, required, default Pending): Pending, Active, Suspended, Terminated, Cancelled. Purpose: lifecycle truth. Pending waits for payment and provisioning. Active serves. Suspended blocks on overdue per Dunning Rule. Terminated ended after approval. Cancelled voided before Active.
- Next Due Date (`next_due_date`, Date). Purpose: drives renewal invoices per Renewal Advance Days. Wrong dates bill early or late.
- Recurring Amount (`recurring_amount`, Currency, default 0). Purpose: cycle amount copied from Plan Pricing at creation. Source for renewal items.
- Cancellation Requested (`cancellation_requested`, Check), Cancellation Mode (`cancellation_mode`, Select: empty, Immediate, End of Billing Cycle), Cancellation Reason (`cancellation_reason`, Small Text). Purpose: cancel intent plus when and why. Immediate stops now. End of Billing Cycle serves to term end.
- Provisioning Log (`provisioning_log`, Small Text). Purpose: create, suspend, unsuspend, and terminate trace. Read this plus Provider API Log on failures.

Lifecycle:

1. Confirm Order acceptance creates Service in Pending.
2. Confirm successful invoice payment moves Service to Active and triggers provisioning.
3. Confirm overdue invoice plus Dunning Rule moves Service to Suspended.
4. Confirm termination approval moves Service to Terminated.
5. Use Provisioning Log and Provider API Log to trace failures. Provider API Log holds Provider, Action, Status (Success or Failed), Error text, and Idempotency Key per call.

Order fields staff verify on disputes:

- Customer (`customer`, Link), Source Cart (`source_cart`, Link), Status (`status`, required, default Pending Review): Pending Review, Accepted, Fraud, Cancelled. Purpose: review gate. Accepted creates Services and invoices. Fraud holds for staff. Cancelled voids.
- Fraud Score (`fraud_score`, Float, default 0). Purpose: sum from fraud rules in settings. High scores need manual review before Accept.
- Coupon Code (`coupon_code`, Data). Purpose: code applied. Totals already reflect it.
- Customer Notes (`customer_notes`, Small Text). Purpose: buyer note for staff.
- Items (`items`, Table to Order Item). Each Order Item holds Type, Reference, Billing Cycle, Unit Price, Quantity, Parent Service, and Configuration Snapshot (`configuration_snapshot`, Code, immutable). Purpose: frozen truth of what was sold. Snapshot never changes even when the plan changes later.
- Total (`total`, Currency). Purpose: order total. Must match invoice subtotal before tax.

## 19. Seller go-live checklist

Do this per service before you link it on the portal.

1. Confirm Lube Station Settings has company, support email, gateways in display order, tax mode, due days, renewal advance days, fraud scores, KYC provider, and live keys only for gateways you sell.
2. Confirm at least one Tax Rule is active where tax applies. Confirm Tax Code on each plan and Default Tax Code in settings.
3. Confirm at least one Dunning Rule is active. Confirm per-plan rules where you need stricter handling.
4. Confirm Product Groups show on the portal in the correct sort order. Hidden groups stay off with Show On Portal off.
5. Confirm every Hosting Plan has explicit schema, pricing for each sold cycle, Welcome Email Template, Tax Code, Apply Tax set correctly, and Is Active checked.
6. Confirm Shared and Reseller plans have Provisioning Module plus Server Group with Active servers. Confirm Requires Domain checked and root cleared.
7. Confirm VPS and Cloud plans have Active provider, Provider Product with regions and plans JSON, schema with hostname, root password, OS, and location, plus VPS Configuration or mapped config and overage rates where metered.
8. Confirm Dedicated plans have Dedicated Server Configuration and Available inventory rows with true specs. Confirm Stock Control and Qty Available match free units.
9. Confirm Email and Builder plans have the right module or provider path and quota or tier config fields.
10. Confirm SSL plans have Reseller Program provider, vendor SKU in External Product ID, and Annually pricing. Confirm common-name collection works.
11. Confirm Backup plans have retention and quota config and Parent Service linking tested.
12. Confirm Migration plans use One Time pricing and staff handoff is defined.
13. Confirm Download assets are Active, Storage Type matches the filled source field, Access Policy plus Allowed Products gate correctly for buyer and non-buyer.
14. Confirm domain path where sold: active Registrar Account, TLD Pricing for each TLD, availability check for available, taken, and premium, renewal pricing and Auto Renew behavior.
15. Confirm Coupon and Client Group logic where promos run. Confirm totals recalc server-side.
16. Place test orders for Shared, VPS or Cloud, and one addon. Confirm cart, order snapshot, invoice, payment, Service status, and welcome email.
17. Confirm suspension and unsuspension on an overdue test invoice. Confirm termination queues for approval instead of running at once.
18. Confirm Provider API Log shows Success for create, suspend, unsuspend, and terminate tests.

## Appendix A. Desk route reference

- Product Group: `/app/product-group`
- Hosting Plan: `/app/hosting-plan`
- Plan Pricing: `/app/plan-pricing`
- Product Type Schema: `/app/product-type-schema`
- Server: `/app/server`
- Server Group: `/app/server-group`
- Provisioning Module: `/app/provisioning-module`
- Provisioning Adapter: `/app/provisioning-adapter`
- Infrastructure Provider: `/app/infrastructure-provider`
- Provider Product: `/app/provider-product`
- Reseller Agreement: `/app/reseller-agreement`
- VPS Configuration: `/app/vps-configuration`
- Dedicated Server Configuration: `/app/dedicated-server-configuration`
- Dedicated Server Inventory: `/app/dedicated-server-inventory`
- Service: `/app/service`
- Payment Gateway Adapter: `/app/payment-gateway-adapter`
- Download Category: `/app/download-category`
- Downloadable Asset: `/app/downloadable-asset`
- Tax Rule: `/app/tax-rule`
- Tax Code: `/app/tax-code`
- GST Settings: `/app/gst-settings`
- Dunning Rule: `/app/dunning-rule`
- Registrar Adapter: `/app/registrar-adapter`
- Registrar Account: `/app/registrar-account`
- TLD Pricing: `/app/tld-pricing`
- Registered Domain: `/app/registered-domain`
- DNS Record: `/app/dns-record`
- Client Group: `/app/client-group`
- Coupon: `/app/coupon`
- Order: `/app/order`
- Hosting Invoice: `/app/hosting-invoice`
- Lube Station Settings: `/app/lube-station-settings`
