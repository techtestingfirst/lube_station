import frappe
from urllib.parse import urlparse

from lube_station.lube_station.settings import BRIDGED_GATEWAYS, gateway_order

# Legacy display order, used only before first Settings save.
MVP_ORDER = list(BRIDGED_GATEWAYS) + ["PayPal Checkout"]

GATEWAY_TIMEOUT = 30


def _bounded(fn, *args, **kwargs):
    """Run a gateway call with a hard timeout. Provider throws surface as ValidationError."""
    from concurrent.futures import ThreadPoolExecutor, TimeoutError

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(fn, *args, **kwargs)
        try:
            return future.result(timeout=GATEWAY_TIMEOUT)
        except TimeoutError:
            frappe.throw("gateway call timed out", frappe.ValidationError)
        except frappe.ValidationError:
            raise
        except Exception as e:
            frappe.throw(str(e), frappe.ValidationError)


def _site_path(url: str) -> str:
    """Site-relative path so checkout redirect stays on the portal origin.

    Works whether the portal is served from :8000 (production bundle) or the
    :8080 vite dev server (which proxies these website pages to the bench).
    """
    parts = urlparse(url)
    path = parts.path or "/"
    if parts.query:
        path += f"?{parts.query}"
    if not path.startswith("/"):
        path = "/" + path.lstrip("./")
    return path


def _razorpay_url(inv) -> dict:
    """Real Razorpay checkout via Frappe Payments app.

    Creates a Razorpay order + Integration Request through Razorpay Settings
    and returns the hosted checkout page. Requires Razorpay Settings keys.
    """
    if not frappe.db.exists("DocType", "Razorpay Settings") or not frappe.db.exists("Razorpay Settings", "Razorpay Settings"):
        frappe.throw("Razorpay not configured: create Razorpay Settings with API keys first")
    settings = frappe.get_doc("Razorpay Settings", "Razorpay Settings")
    if not settings.api_key:
        frappe.throw("Razorpay not configured: set API Key/Secret in Razorpay Settings first")
    from lube_station.lube_station.settings import get_setting

    capture_setting = get_setting("razorpay_auto_capture")
    customer = frappe.get_doc("Hosting Customer", inv.customer)
    user_email = frappe.db.get_value("User", customer.user, "email") or customer.user
    payer_name = frappe.db.get_value("User", customer.user, "full_name") or user_email
    url = settings.get_payment_url(
        amount=inv.total_due,
        title=f"Hosting Invoice {inv.name}",
        description=f"Payment for {inv.name}",
        reference_doctype="Hosting Invoice",
        reference_docname=inv.name,
        payer_email=user_email,
        payer_name=payer_name,
        order_id=inv.name,
        currency="INR",
        payment_gateway="Razorpay",
        # Auto-capture: without this Razorpay leaves test payments "authorized",
        # authorize sees no capture, and the invoice stays Unpaid.
        payment_capture=1 if capture_setting else 0,
    )
    return {"gateway": "Razorpay", "url": _site_path(url), "amount": inv.total_due}


def _stripe_url(inv) -> dict:
    """Stripe checkout via Frappe Payments app (card token page).

    Requires Stripe Settings with keys (saving it auto-creates Payment Gateway).
    """
    settings = None
    for row in frappe.get_all("Stripe Settings", ["name"]):
        doc = frappe.get_doc("Stripe Settings", row.name)
        if doc.get("publishable_key"):
            settings = doc
            break
    if settings is None:
        frappe.throw("Stripe not configured: create Stripe Settings with Publishable/Secret keys first")
    settings.validate_transaction_currency("INR")
    settings.validate_minimum_transaction_amount("INR", inv.total_due)
    gateway_name = frappe.db.get_value("Payment Gateway", {"gateway_controller": settings.name}, "name")
    if not gateway_name:
        frappe.throw(f"Stripe not configured: no Payment Gateway points at {settings.name}")
    customer = frappe.get_doc("Hosting Customer", inv.customer)
    user_email = frappe.db.get_value("User", customer.user, "email") or customer.user
    payer_name = frappe.db.get_value("User", customer.user, "full_name") or user_email
    url = settings.get_payment_url(
        amount=inv.total_due,
        title=f"Hosting Invoice {inv.name}",
        description=f"Payment for {inv.name}",
        reference_doctype="Hosting Invoice",
        reference_docname=inv.name,
        payer_name=payer_name,
        payer_email=user_email,
        currency="INR",
        payment_gateway=gateway_name,
    )
    return {"gateway": "Stripe", "url": _site_path(url), "amount": inv.total_due}


def _paypal_url(inv) -> dict:
    """PayPal Express Checkout via Frappe Payments app.

    Classic NVP API: live SetExpressCheckout call, customer pays on paypal.com,
    return path confirms capture and calls on_payment_authorized.
    NOTE: PayPal classic does not support INR, and Hosting Invoices are
    INR-only today, so this throws an informative error until invoice
    currency support lands. Kept code-complete for that day.
    """
    settings = frappe.get_doc("PayPal Settings")
    settings.validate_transaction_currency("INR")
    customer = frappe.get_doc("Hosting Customer", inv.customer)
    user_email = frappe.db.get_value("User", customer.user, "email") or customer.user
    payer_name = frappe.db.get_value("User", customer.user, "full_name") or user_email
    url = settings.get_payment_url(
        amount=inv.total_due,
        title=f"Hosting Invoice {inv.name}",
        description=f"Payment for {inv.name}",
        reference_doctype="Hosting Invoice",
        reference_docname=inv.name,
        payer_email=user_email,
        payer_name=payer_name,
        order_id=inv.name,
        currency="INR",
        payment_gateway="PayPal",
    )
    return {"gateway": "PayPal Checkout", "url": url, "amount": inv.total_due}


def pick_gateway(name: str | None = None) -> str:
    if name:
        if name not in BRIDGED_GATEWAYS:
            frappe.throw(f"{name} has no payment bridge yet")
        record = frappe.get_doc("Payment Gateway Adapter", name)
        if not record.active:
            frappe.throw(f"{name} inactive")
        if not record.supports_one_time:
            frappe.throw(f"{name} lacks one-time support")
        return name
    for candidate in gateway_order() or MVP_ORDER:
        if frappe.db.get_value("Payment Gateway Adapter", candidate, "active"):
            return candidate
    frappe.throw("No active one-time gateway")


@frappe.whitelist(methods=["GET", "POST"])
def payment_link(invoice: str, gateway: str | None = None) -> dict:
    from lube_station.lube_station.portal.guards import assert_owns

    inv = frappe.get_doc("Hosting Invoice", invoice)
    if "System Manager" not in frappe.get_roles() and frappe.session.user != "Administrator":
        assert_owns(inv.customer)
    if inv.status == "Paid":
        frappe.throw("Invoice already paid")
    chosen = pick_gateway(gateway or inv.gateway)
    inv.gateway = chosen
    inv.save(ignore_permissions=True)
    if chosen == "Bank Transfer":
        return {"gateway": chosen, "manual": True, "instructions": "Transfer to account, attach reference"}
    if chosen == "Razorpay":
        return _razorpay_url(inv)
    if chosen == "Stripe":
        return _stripe_url(inv)
    if chosen == "PayPal Checkout":
        return _paypal_url(inv)
    return {"gateway": chosen, "url": f"/payments/{chosen.lower().replace(' ', '-')}/pay/{inv.name}", "amount": inv.total_due}
