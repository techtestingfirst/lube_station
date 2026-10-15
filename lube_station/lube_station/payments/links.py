import frappe
from urllib.parse import urlparse

from lube_station.lube_station.settings import BRIDGED_GATEWAYS, gateway_order

# Legacy display order, used only before first Settings save.
MVP_ORDER = list(BRIDGED_GATEWAYS)

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
    if not frappe.db.exists("DocType", "Stripe Settings"):
        frappe.throw("Stripe not configured: create Stripe Settings with Publishable/Secret keys first")
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


def _adapter_url(inv, gateway_name: str, transport=None) -> dict:
    """One-time checkout through the adapter registry.

    Each adapter builds its own hosted step from its own keys and returns its
    own shape; this normalizes to what the portal `pay()` handler consumes:
    `url` (redirect: Mollie/PayPal approve_url), `post_url` + form fields
    (auto-POST: PayU/CCAvenue), `payment_session_id` (Cashfree SDK),
    `hint` (mandate flow: GoCardless). Adapters without hosted checkout
    (2Checkout panel buy-links) throw an informative error by design.
    `transport` is a test seam only; production calls pass none.
    """
    from lube_station.lube_station.adapters.registry import get_payment_adapter

    adapter = get_payment_adapter(gateway_name)
    # Called in-request, not in _bounded: adapters read Singles and reload
    # the invoice through frappe ORM, which has no site bound in pool threads.
    # Network legs stay bounded inside each adapter (TIMEOUT + RETRIES).
    kwargs: dict = {}
    if transport is not None:
        import inspect

        try:
            if "transport" in inspect.signature(adapter.create_payment).parameters:
                kwargs["transport"] = transport
        except (TypeError, ValueError):
            pass
    out = adapter.create_payment(inv.name, **kwargs)
    if not isinstance(out, dict):
        frappe.throw(f"{gateway_name} returned an unusable checkout payload")
    if out.get("approve_url"):
        return {"gateway": gateway_name, "url": out["approve_url"], "amount": inv.total_due}
    if out.get("post_url"):
        normalized = {"gateway": gateway_name, "post_url": out["post_url"], "amount": inv.total_due}
        for key in ("params", "enc_request", "access_code"):
            if out.get(key) is not None:
                normalized[key] = out[key]
        return normalized
    if out.get("payment_session_id"):
        from lube_station.lube_station.settings import get_setting

        try:
            sandbox = bool(int(get_setting("cashfree_sandbox") or 0))
        except Exception:
            sandbox = True
        return {
            "gateway": gateway_name,
            "payment_session_id": out["payment_session_id"],
            "order_id": out.get("order_id", inv.name),
            "sandbox": sandbox,
            "amount": inv.total_due,
        }
    if out.get("hint"):
        normalized = {"gateway": gateway_name, "hint": out["hint"], "amount": inv.total_due}
        if out.get("customer_id"):
            normalized["customer_id"] = out["customer_id"]
        return normalized
    if out.get("url"):
        return {"gateway": gateway_name, "url": out["url"], "amount": inv.total_due}
    return dict(out)


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
    # PayPal Checkout now uses the REST adapter (approve_url redirect) instead
    # of the classic NVP page, which never supported INR.
    return _adapter_url(inv, chosen)
