import frappe

from .guards import assert_owns, my_customer


def _is_staff() -> bool:
    return "System Manager" in frappe.get_roles()


def _assert_cart_access(cart_doc):
    if _is_staff():
        return
    mine = my_customer()
    if cart_doc.customer and cart_doc.customer != mine:
        frappe.throw("Cross-customer access denied", frappe.PermissionError)


def _open_cart(customer: str):
    """Latest cart for customer with no Order yet, else new one."""
    carts = frappe.get_all("Cart", {"customer": customer}, ["name"], order_by="modified desc", limit=10)
    for c in carts:
        if not frappe.db.exists("Order", {"source_cart": c.name}):
            return frappe.get_doc("Cart", c.name)
    return frappe.get_doc({"doctype": "Cart", "customer": customer}).insert(ignore_permissions=True)


def _cart_view(cart_doc) -> dict:
    return {
        "cart": cart_doc.name,
        "customer": cart_doc.customer,
        "coupon_code": cart_doc.coupon_code,
        "subtotal": cart_doc.subtotal or 0,
        "discount_total": cart_doc.discount_total or 0,
        "grand_total": cart_doc.grand_total or 0,
        "items": [
            {
                "row": i.name,
                "item_type": i.item_type,
                "hosting_plan": i.hosting_plan,
                "billing_cycle": i.billing_cycle,
                "domain": i.domain,
                "quantity": i.quantity,
                "unit_price": i.unit_price or 0,
                "configuration_json": i.configuration_json,
            }
            for i in (cart_doc.items or [])
        ],
    }


@frappe.whitelist(methods=["GET"], allow_guest=True)
def storefront():
    plans = frappe.get_all("Hosting Plan", {"is_active": 1}, ["name", "plan_name", "product_type", "product_group"])
    out = []
    for p in plans:
        prices = frappe.get_all("Plan Pricing", {"hosting_plan": p.name}, ["billing_cycle", "recurring_amount", "setup_fee"])
        out.append({**p, "prices": prices})
    return out


@frappe.whitelist(methods=["GET"])
def dashboard():
    customer = my_customer()
    return {
        "services": frappe.db.count("Service", {"customer": customer}),
        "unpaid": frappe.db.count("Hosting Invoice", {"customer": customer, "status": "Unpaid"}),
        "domains": frappe.db.count("Domain", {"customer": customer}),
        "tickets": frappe.db.count("Ticket Hosting Reference", {"customer": customer}),
    }


@frappe.whitelist(methods=["GET", "POST"])
def checkout_info(plan: str):
    schema = frappe.db.get_value("Hosting Plan", plan, "product_type_schema")
    prices = frappe.get_all("Plan Pricing", {"hosting_plan": plan}, ["billing_cycle", "recurring_amount", "setup_fee"])
    requirements = None
    if schema:
        from lube_station.lube_station.doctype.product_type_schema.product_type_schema import get_product_requirements

        requirements = get_product_requirements(plan=plan)
    return {"prices": prices, "requirements": requirements}


@frappe.whitelist(methods=["GET"])
def my_invoices():
    customer = my_customer()
    return frappe.get_all("Hosting Invoice", {"customer": customer}, ["name", "total_due", "status", "due_date", "gateway"])


@frappe.whitelist(methods=["GET"])
def my_services():
    customer = my_customer()
    return frappe.get_all("Service", {"customer": customer}, ["name", "hosting_plan", "status", "next_due_date"])


@frappe.whitelist(methods=["GET"])
def my_domains():
    customer = my_customer()
    return frappe.get_all("Domain", {"customer": customer}, ["domain_name", "status", "expiry_date"])


@frappe.whitelist(methods=["GET"])
def dns_list(domain: str):
    dom = frappe.get_doc("Domain", domain)
    assert_owns(dom.customer)
    return frappe.get_all("DNS Record", {"domain": domain}, ["name", "record_type", "hostname", "record_value", "ttl"])


@frappe.whitelist(methods=["POST"])
def vps_control(instance: str, action: str, arg: str | None = None):
    from lube_station.lube_station.doctype.vps_instance.vps_instance import vps_action

    inst = frappe.get_doc("VPS Instance", instance)
    if inst.order_ref:
        order = frappe.get_doc("Order", inst.order_ref)
        if order.customer:
            assert_owns(order.customer)
    return vps_action(instance, action, arg)


@frappe.whitelist(methods=["GET"])
def my_methods():
    customer = my_customer()
    return frappe.get_all("Saved Payment Method", {"customer": customer}, ["name", "gateway", "last_four", "expiry", "default_method"])


@frappe.whitelist(methods=["POST"])
def save_method(gateway: str, token: str, last_four: str | None = None, expiry: str | None = None, make_default: bool = False):
    customer = my_customer()
    doc = frappe.get_doc({"doctype": "Saved Payment Method", "customer": customer, "gateway": gateway, "token": token, "last_four": last_four, "expiry": expiry, "default_method": 1 if make_default else 0}).insert()
    return {"method": doc.name}


@frappe.whitelist(methods=["GET"])
def my_dedicated():
    customer = my_customer()
    services = frappe.get_all("Service", {"customer": customer}, pluck="name")
    if not services:
        return []
    return frappe.get_all("Dedicated Server Inventory", {"assigned_service": ["in", services]}, ["name", "asset_id", "location", "status", "assigned_service"])


@frappe.whitelist(methods=["POST"])
def dns_add(domain: str, record_type: str, hostname: str, value: str, ttl: int = 3600):
    dom = frappe.get_doc("Domain", domain)
    assert_owns(dom.customer)
    rec = frappe.get_doc({"doctype": "DNS Record", "domain": domain, "record_type": record_type, "hostname": hostname, "record_value": value, "ttl": ttl}).insert()
    return {"record": rec.name}


@frappe.whitelist(methods=["GET"])
def downloads():
    from lube_station.lube_station.doctype.downloadable_asset.downloadable_asset import check_entitlement

    assets = frappe.get_all("Downloadable Asset", {"active": 1}, ["name", "title", "access_policy"])
    return [a for a in assets if check_entitlement(a.name)["allowed"]]


@frappe.whitelist(methods=["GET"])
def my_account():
    customer = my_customer()
    return frappe.get_doc("Hosting Customer", customer).as_dict()


@frappe.whitelist(methods=["GET", "POST"])
def cart_current():
    """Get open cart for logged-in customer, creating one if needed.

    Customer cycle: storefront (guest) -> signup/login -> cart_current ->
    cart_add -> checkout -> pay -> my_services.
    """
    customer = my_customer()
    cart_doc = _open_cart(customer)
    return _cart_view(cart_doc)


@frappe.whitelist(methods=["GET", "POST"])
def cart_view(cart: str | None = None):
    customer = my_customer()
    cart_doc = frappe.get_doc("Cart", cart) if cart else _open_cart(customer)
    _assert_cart_access(cart_doc)
    return _cart_view(cart_doc)


@frappe.whitelist(methods=["POST"])
def cart_add(hosting_plan: str, billing_cycle: str = "Monthly", quantity: int = 1, domain: str | None = None, configuration: dict | str | None = None, cart: str | None = None):
    import json

    customer = my_customer()
    cart_doc = frappe.get_doc("Cart", cart) if cart else _open_cart(customer)
    _assert_cart_access(cart_doc)
    if not cart_doc.customer:
        cart_doc.customer = customer
    if not frappe.db.exists("Hosting Plan", hosting_plan):
        frappe.throw(f"Unknown plan {hosting_plan}")
    if not frappe.db.get_value("Hosting Plan", hosting_plan, "is_active"):
        frappe.throw(f"Plan {hosting_plan} is not active")
    if isinstance(configuration, dict):
        configuration = json.dumps(configuration)
    cart_doc.append(
        "items",
        {
            "item_type": "Hosting Plan",
            "hosting_plan": hosting_plan,
            "billing_cycle": billing_cycle,
            "domain": domain,
            "quantity": quantity or 1,
            "configuration_json": configuration,
        },
    )
    cart_doc.save(ignore_permissions=True)
    return _cart_view(cart_doc)


@frappe.whitelist(methods=["GET", "POST"], allow_guest=True)
def domain_check(domain: str) -> dict:
    """Guest-safe availability lookup (rate-limited server-side)."""
    from lube_station.lube_station.doctype.domain.domain import check_availability

    return check_availability(domain)


@frappe.whitelist(methods=["POST"])
def cart_add_domain(cart: str, domain: str, domain_action: str = "register", years: int = 1, auth_code: str | None = None):
    """Domain-only line (register/transfer). WHMCS domain step without hosting."""
    import json

    cart_doc = frappe.get_doc("Cart", cart)
    _assert_cart_access(cart_doc)
    _validate_domain_choice(domain, domain_action, auth_code)
    cart_doc.append(
        "items",
        {
            "item_type": "Domain",
            "domain": domain.strip().lower(),
            "billing_cycle": "One Time",
            "quantity": years or 1,
            "configuration_json": json.dumps({"domain_action": domain_action, "domain_years": years or 1, "epp": auth_code or ""}),
        },
    )
    cart_doc.save(ignore_permissions=True)
    return _cart_view(cart_doc)


@frappe.whitelist(methods=["POST"])
def cart_set_domain(cart: str, row: str, domain: str | None = None, domain_action: str = "none", years: int = 1, auth_code: str | None = None):
    """Attach WHMCS domain choice to a hosting-plan cart row.

    domain_action: register | transfer | own | none.
    """
    import json

    cart_doc = frappe.get_doc("Cart", cart)
    _assert_cart_access(cart_doc)
    if domain_action != "none":
        _validate_domain_choice(domain, domain_action, auth_code)
    for item in cart_doc.items:
        if item.name == row:
            item.domain = (domain or "").strip().lower() or None
            config = {}
            try:
                config = json.loads(item.configuration_json or "{}")
            except Exception:
                config = {}
            config.update({"domain_action": domain_action, "domain_years": years or 1, "epp": auth_code or ""})
            item.configuration_json = json.dumps(config)
    cart_doc.save(ignore_permissions=True)
    return _cart_view(cart_doc)


def _validate_domain_choice(domain: str | None, domain_action: str, auth_code: str | None):
    if domain_action not in ("register", "transfer", "own", "none"):
        frappe.throw("Unknown domain option")
    if domain_action == "none":
        return
    domain = (domain or "").strip().lower()
    if not domain or "." not in domain:
        frappe.throw("Enter a valid domain name")
    if domain_action == "transfer" and not (auth_code or "").strip():
        frappe.throw("Transfer needs the EPP authorization code")


@frappe.whitelist(methods=["POST"])
def cart_set_qty(cart: str, row: str, quantity: int):
    cart_doc = frappe.get_doc("Cart", cart)
    _assert_cart_access(cart_doc)
    for item in cart_doc.items:
        if item.name == row:
            item.quantity = quantity
    cart_doc.save(ignore_permissions=True)
    return _cart_view(cart_doc)


@frappe.whitelist(methods=["POST"])
def cart_remove(cart: str, row: str):
    cart_doc = frappe.get_doc("Cart", cart)
    _assert_cart_access(cart_doc)
    cart_doc.items = [i for i in cart_doc.items if i.name != row]
    cart_doc.save(ignore_permissions=True)
    return _cart_view(cart_doc)


@frappe.whitelist(methods=["POST"])
def cart_apply_coupon(cart: str, coupon_code: str):
    from lube_station.lube_station.doctype.cart.cart import discount_for  # noqa: F401

    cart_doc = frappe.get_doc("Cart", cart)
    _assert_cart_access(cart_doc)
    coupon = frappe.get_doc("Coupon", {"code": coupon_code})
    coupon.check_cart(cart_doc)
    cart_doc.coupon_code = coupon.code
    cart_doc.save(ignore_permissions=True)
    return _cart_view(cart_doc)


@frappe.whitelist(methods=["GET", "POST"])
def payment_gateways() -> list:
    """Enabled gateways with a real bridge behind them, in Settings order.

    PayPal Checkout stays hidden: classic NVP API has no INR support and
    Hosting Invoices are INR-only. Re-add when invoice currency lands.
    """
    from lube_station.lube_station.payments.links import gateway_order

    rows = frappe.get_all("Payment Gateway Adapter", {"active": 1, "supports_one_time": 1}, ["name"])
    names = {r.name for r in rows}
    return [{"name": g} for g in gateway_order() if g in names]


@frappe.whitelist(methods=["POST"])
def checkout(cart: str | None = None, gateway: str | None = None, notes: str | None = None, tos_accepted: bool = False) -> dict:
    """One-call purchase: cart -> Order -> Hosting Invoice -> payment link.

    WHMCS Complete Order: ownership + TOS enforced, fraud scored in
    place_order, order/invoice notifications fired, idempotent on retry.
    """
    from lube_station.lube_station.doctype.hosting_invoice.hosting_invoice import generate_invoice
    from lube_station.lube_station.doctype.order.order import place_order
    from lube_station.lube_station.notifications.events import fire
    from lube_station.lube_station.payments.links import payment_link, pick_gateway

    customer = my_customer()
    from lube_station.lube_station.settings import get_setting

    if get_setting("tos_required") and not _is_staff() and not frappe.db.get_value("Hosting Customer", customer, "tos_accepted"):
        if not tos_accepted:
            frappe.throw("Accept the Terms of Service to check out")
        frappe.db.set_value("Hosting Customer", customer, "tos_accepted", 1)
    cart_doc = frappe.get_doc("Cart", cart) if cart else _open_cart(customer)
    _assert_cart_access(cart_doc)
    if not cart_doc.items:
        frappe.throw("Cart empty")
    # Fail fast on bad gateway before creating order/invoice side effects.
    pick_gateway(gateway or cart_doc.get("gateway") or None)
    if not cart_doc.customer:
        cart_doc.customer = customer
        cart_doc.save(ignore_permissions=True)
    if frappe.db.exists("Order", {"source_cart": cart_doc.name}):
        order_name = frappe.db.get_value("Order", {"source_cart": cart_doc.name}, "name")
    else:
        order_name = place_order(cart_doc.name, customer, notes)["order"]
        _notify(customer, fire, "order", order_name)
    inv = generate_invoice(order_name, gateway)
    if not inv.get("reused"):
        _notify(customer, fire, "invoice", inv["invoice"])
    link = payment_link(inv["invoice"], gateway)
    return {"order": order_name, "customer": customer, **inv, "payment": link}


def _notify(customer: str, fire, event_type: str, reference: str):
    try:
        user = frappe.db.get_value("Hosting Customer", customer, "user")
        email = frappe.db.get_value("User", user, "email") if user else None
        fire(event_type, reference, email)
    except Exception:
        pass


@frappe.whitelist(methods=["GET"])
def my_orders():
    customer = my_customer()
    return frappe.get_all("Order", {"customer": customer}, ["name", "status", "total", "creation"], order_by="creation desc")


@frappe.whitelist(methods=["GET"])
def my_order_detail(order: str):
    order_doc = frappe.get_doc("Order", order)
    assert_owns(order_doc.customer)
    invoices = frappe.get_all("Hosting Invoice", {"order_ref": order}, ["name", "status", "total_due", "gateway"])
    return {
        "order": order_doc.as_dict(),
        "invoices": invoices,
    }


@frappe.whitelist(methods=["GET", "POST"])
def invoice_payment_link(invoice: str, gateway: str | None = None):
    from lube_station.lube_station.payments.links import payment_link

    inv = frappe.get_doc("Hosting Invoice", invoice)
    assert_owns(inv.customer)
    return payment_link(invoice, gateway)


@frappe.whitelist(methods=["POST"])
def invoice_pay_saved(invoice: str, payment_method: str):
    from lube_station.lube_station.payments.methods import charge_saved_method

    inv = frappe.get_doc("Hosting Invoice", invoice)
    assert_owns(inv.customer)
    method = frappe.get_doc("Saved Payment Method", payment_method)
    assert_owns(method.customer)
    return charge_saved_method(payment_method, invoice)


@frappe.whitelist(methods=["POST"], allow_guest=True)
def signup_customer(
    full_name: str,
    email: str,
    password: str,
    company: str | None = None,
    phone: str | None = None,
    address_line1: str | None = None,
    city: str | None = None,
    state: str | None = None,
    postcode: str | None = None,
    country: str | None = None,
    tos_accepted: bool = False,
) -> dict:
    import re

    email = (email or "").strip().lower()
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        frappe.throw("Invalid email")
    if len(password or "") < 8:
        frappe.throw("Password needs 8+ characters")
    if not (full_name or "").strip():
        frappe.throw("Full name required")
    if not tos_accepted:
        frappe.throw("Accept the Terms of Service to register")
    if frappe.db.exists("User", email):
        frappe.throw("Account already exists, sign in instead")
    user = frappe.get_doc({"doctype": "User", "email": email, "first_name": full_name, "enabled": 1, "new_password": password, "roles": [{"role": "Customer"}]}).insert(ignore_permissions=True)
    customer = frappe.get_doc(
        {
            "doctype": "Hosting Customer",
            "user": user.name,
            "company": company,
            "phone": phone,
            "address_line1": address_line1,
            "city": city,
            "state": state,
            "postcode": postcode,
            "country": country,
            "tos_accepted": 1,
            "status": "Active",
        }
    ).insert(ignore_permissions=True)
    try:
        from lube_station.lube_station.notifications.events import fire

        fire("signup", customer.name, email)
    except Exception:
        pass
    return {"customer": customer.name}


@frappe.whitelist(methods=["GET", "POST"], allow_guest=True)
def country_list() -> list:
    """All countries for the signup dropdown (uses the Country master)."""
    if not frappe.db.exists("DocType", "Country"):
        return [{"name": "India", "code": "IN"}]
    return [
        {"name": c.name, "code": (c.code or "").upper()}
        for c in frappe.get_all("Country", ["name", "code"], order_by="name")
    ]


@frappe.whitelist(methods=["GET", "POST"], allow_guest=True)
def pincode_lookup(postcode: str, country: str | None = None) -> dict:
    """City/state autofill from postal code (free public APIs, no keys).

    India (6-digit PIN): api.postalpincode.in. Everywhere else:
    zippopotam.us via the Country master's ISO code. Never blocks signup:
    failures throw a message telling the customer to type manually.
    """
    import re

    from frappe.integrations.utils import make_get_request

    code = (postcode or "").strip().replace(" ", "")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 \-]{2,9}", code or ""):
        frappe.throw("Enter a valid postcode")
    country_name = (country or "").strip()

    def indian() -> bool:
        if country_name.lower() in ("india", "bharat"):
            return True
        return not country_name and bool(re.fullmatch(r"\d{6}", code))

    # NOTE: these free APIs reset connections presenting the default
    # python-requests UA — a browser UA is required from bench Python.
    _UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
    try:
        if indian():
            if not re.fullmatch(r"\d{6}", code):
                frappe.throw("Indian PIN is 6 digits")
            resp = make_get_request(f"https://api.postalpincode.in/pincode/{code}", headers=_UA)
            offices = (resp[0].get("PostOffice") if isinstance(resp, list) and resp else None) or []
            if (resp[0].get("Status") if resp else "") != "Success" or not offices:
                frappe.throw("No record for this PIN, enter city manually")
            office = offices[0]
            return {"city": office.get("District") or office.get("Name"), "state": office.get("State"), "country": "India"}
        iso = frappe.db.get_value("Country", country_name, "code") if country_name else None
        if not iso:
            frappe.throw("Pick a country first, or enter city manually")
        resp = make_get_request(f"https://api.zippopotam.us/{iso.lower()}/{code}", headers=_UA)
        places = resp.get("places") or []
        if not places:
            frappe.throw("No record for this postcode, enter city manually")
        return {"city": places[0].get("place name"), "state": places[0].get("state"), "country": country_name}
    except frappe.ValidationError:
        raise
    except Exception:
        frappe.throw("Lookup unavailable right now, enter city manually")


@frappe.whitelist(methods=["POST"], allow_guest=True)
def forgot_password(email: str) -> dict:
    from frappe.core.doctype.user.user import reset_password

    reset_password(email.strip().lower())
    return {"sent": True}
