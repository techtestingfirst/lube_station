import frappe

from .guards import assert_owns, my_customer


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


@frappe.whitelist(methods=["GET"])
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
    return frappe.get_all("Hosting Invoice", {"customer": customer}, ["name", "total_due", "status", "due_date"])


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


@frappe.whitelist(methods=["POST"], allow_guest=True)
def signup_customer(full_name: str, email: str, password: str, company: str | None = None) -> dict:
    import re

    email = (email or "").strip().lower()
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        frappe.throw("Invalid email")
    if len(password or "") < 8:
        frappe.throw("Password needs 8+ characters")
    if frappe.db.exists("User", email):
        frappe.throw("Account already exists, sign in instead")
    user = frappe.get_doc({"doctype": "User", "email": email, "first_name": full_name, "enabled": 1, "new_password": password, "roles": [{"role": "Customer"}]}).insert(ignore_permissions=True)
    customer = frappe.get_doc({"doctype": "Hosting Customer", "user": user.name, "company": company, "status": "Active"}).insert(ignore_permissions=True)
    try:
        from lube_station.lube_station.notifications.events import fire

        fire("signup", customer.name, email)
    except Exception:
        pass
    return {"customer": customer.name}


@frappe.whitelist(methods=["POST"], allow_guest=True)
def forgot_password(email: str) -> dict:
    from frappe.core.doctype.user.user import reset_password

    reset_password(email.strip().lower())
    return {"sent": True}
